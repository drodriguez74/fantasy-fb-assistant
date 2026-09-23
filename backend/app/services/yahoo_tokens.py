"""Yahoo access-token renewal, shared by every Yahoo call site.

Yahoo access tokens last ~1 hour. Before this existed, every call site just
checked `yahoo_token_expires_at` and told the user to reconnect once it
passed -- `yahoo_service.refresh_access_token` existed but had no callers,
so every Yahoo feature died an hour after connecting. `get_valid_yahoo_token`
is now the one place a stored token is read: it returns the current token
while it's still good, and otherwise trades the stored refresh token for a
new one and persists it before returning.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import inspect
from sqlalchemy.orm import Session, object_session

from app.db.base import SessionLocal
from app.models.user_league import PlatformType, UserLeague
from app.services.yahoo_service import yahoo_service

logger = logging.getLogger(__name__)

# Refresh a little before the real expiry so a token can't lapse between
# this check and the Yahoo request that uses it.
REFRESH_MARGIN = timedelta(minutes=2)

# One refresh at a time per user: the connect flow stores the same token
# pair on every one of a user's Yahoo leagues, and the league page fires
# several Yahoo-backed requests at once. Keyed by event loop too -- snapshot
# background refreshes run under their own asyncio.run() loop, and an
# asyncio.Lock can't be shared across loops.
_locks: Dict[Tuple[int, int], asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    # Postgres returns this timezone-aware column aware; SQLite (tests)
    # returns it naive. Treat naive as UTC so the comparison never raises.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(user_league: UserLeague) -> bool:
    expires_at = _aware(user_league.yahoo_token_expires_at)
    return expires_at is None or expires_at - REFRESH_MARGIN > datetime.now(timezone.utc)


async def get_valid_yahoo_token(user_league: UserLeague) -> Optional[str]:
    """This league's usable Yahoo access token, renewed first if expired.

    Returns None when there's no token at all, or when renewal fails (no
    refresh token stored, or Yahoo rejected it) -- callers keep reporting
    their existing "please reconnect Yahoo" message in that case, which is
    then genuinely the only fix.
    """
    if not user_league.yahoo_access_token:
        return None
    if _is_fresh(user_league):
        return user_league.yahoo_access_token
    if not user_league.yahoo_refresh_token:
        return None

    async with _lock_for(user_league.user_id):
        db = object_session(user_league)
        owns_session = db is None
        if owns_session:
            db = SessionLocal()
        try:
            # Another request may have renewed it while we waited on the lock.
            if not owns_session:
                if inspect(user_league).persistent:
                    db.refresh(user_league, ["yahoo_access_token", "yahoo_refresh_token", "yahoo_token_expires_at"])
            else:
                stored = db.get(UserLeague, user_league.id) if user_league.id else None
                if stored is not None:
                    _copy_tokens(stored, user_league)
            if user_league.yahoo_access_token and _is_fresh(user_league):
                return user_league.yahoo_access_token

            old_refresh = user_league.yahoo_refresh_token
            result = await yahoo_service.refresh_access_token(old_refresh)
            if "error" in result:
                logger.warning(
                    "Yahoo token refresh failed for user %s: %s", user_league.user_id, result["error"]
                )
                return None

            new_access = result["access_token"]
            # Yahoo normally returns the same refresh token, but keep
            # whatever it hands back in case it ever rotates it.
            new_refresh = result.get("refresh_token") or old_refresh
            try:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(result.get("expires_in")))
            except (TypeError, ValueError):
                expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            _persist(db, user_league, old_refresh, new_access, new_refresh, expires_at)
            return new_access
        finally:
            if owns_session:
                db.close()


def _copy_tokens(src: UserLeague, dst: UserLeague) -> None:
    dst.yahoo_access_token = src.yahoo_access_token
    dst.yahoo_refresh_token = src.yahoo_refresh_token
    dst.yahoo_token_expires_at = src.yahoo_token_expires_at


def _persist(
    db: Session,
    user_league: UserLeague,
    old_refresh: str,
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
) -> None:
    """Write the renewed pair to every one of this user's Yahoo leagues that
    shared the old refresh token (the connect flow stores one pair across
    all of them), so a sibling league doesn't hold a refresh token Yahoo
    may have just retired."""
    rows = (
        db.query(UserLeague)
        .filter(
            UserLeague.user_id == user_league.user_id,
            UserLeague.platform == PlatformType.YAHOO,
            UserLeague.yahoo_refresh_token == old_refresh,
        )
        .all()
    )
    for row in rows:
        row.yahoo_access_token = access_token
        row.yahoo_refresh_token = refresh_token
        row.yahoo_token_expires_at = expires_at
    try:
        db.commit()
    except Exception:  # noqa: BLE001 - a failed save must not lose the new token for this request
        db.rollback()
        logger.exception("Could not save refreshed Yahoo token for user %s", user_league.user_id)

    # Always reflect it on the caller's object, persisted or not (a detached
    # or never-saved row isn't covered by the query above).
    user_league.yahoo_access_token = access_token
    user_league.yahoo_refresh_token = refresh_token
    user_league.yahoo_token_expires_at = expires_at
