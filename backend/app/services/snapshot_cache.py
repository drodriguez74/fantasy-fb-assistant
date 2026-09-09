"""Stale-while-revalidate JSON snapshot cache for slow per-league reads.

`serve_swr(db, user_league, kind, background_tasks=..., force=...)`:

  * fresh snapshot (age <= kind TTL) -> return it, no upstream call
  * stale snapshot -> return it immediately AND schedule a background
    refresh so the next load is fresh
  * no snapshot (or force=True) -> build synchronously, store, return.
    If a forced/cold build fails but a stale snapshot exists, the stale
    snapshot is returned rather than erroring.

The returned dict is the endpoint's normal body plus a `_cache` block:
`{as_of, age_seconds, stale, source}` where source is
"fresh" | "cache" | "cache-refreshing". The frontend uses this to show an
"updated Nm ago" marker and a subtle "syncing" hint when stale.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.league_snapshot import LeagueSnapshot
from app.models.user_league import UserLeague
from app.services.league_snapshots import (
    SnapshotBuildError,
    build_roster_analysis_snapshot,
    build_standings_snapshot,
    build_this_week_snapshot,
)

logger = logging.getLogger(__name__)

# kind -> (async builder(user_league) -> dict, ttl_seconds)
_REGISTRY: Dict[str, Tuple[Callable, int]] = {
    "this_week": (build_this_week_snapshot, 180),       # moves during games
    "roster_analysis": (build_roster_analysis_snapshot, 900),
    "standings": (build_standings_snapshot, 900),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _age_seconds(computed_at: datetime) -> float:
    return (_now() - _aware(computed_at)).total_seconds()


def _read(db: Session, user_league_id: int, kind: str) -> Optional[LeagueSnapshot]:
    return (
        db.query(LeagueSnapshot)
        .filter(
            LeagueSnapshot.user_league_id == user_league_id,
            LeagueSnapshot.kind == kind,
        )
        .one_or_none()
    )


def _write(db: Session, user_league_id: int, kind: str, payload: dict) -> None:
    text = json.dumps(payload, default=str)
    row = _read(db, user_league_id, kind)
    if row is None:
        db.add(
            LeagueSnapshot(
                user_league_id=user_league_id,
                kind=kind,
                payload=text,
                computed_at=_now(),
            )
        )
    else:
        row.payload = text
        row.computed_at = _now()
    db.commit()


def _wrap(payload: dict, computed_at: datetime, *, stale: bool, source: str) -> dict:
    return {
        **payload,
        "_cache": {
            "as_of": _aware(computed_at).isoformat(),
            "age_seconds": int(_age_seconds(computed_at)),
            "stale": stale,
            "source": source,
        },
    }


def _refresh_now(user_league_id: int, kind: str) -> None:
    """FastAPI BackgroundTask body -- its own DB session and event loop."""
    builder, _ttl = _REGISTRY[kind]
    db = SessionLocal()
    try:
        ul = db.get(UserLeague, user_league_id)
        if ul is None:
            return
        payload = asyncio.run(builder(ul))
        _write(db, user_league_id, kind, payload)
    except SnapshotBuildError as exc:
        logger.info("snapshot refresh %s/%s skipped: %s", user_league_id, kind, exc)
    except Exception:  # noqa: BLE001 - never let a background refresh crash
        logger.exception("snapshot refresh %s/%s failed", user_league_id, kind)
    finally:
        db.close()


async def serve_swr(
    db: Session,
    user_league: UserLeague,
    kind: str,
    *,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    if kind not in _REGISTRY:
        raise ValueError(f"unknown snapshot kind: {kind}")
    builder, ttl = _REGISTRY[kind]

    row = _read(db, user_league.id, kind)

    if row is not None and not force:
        payload = json.loads(row.payload)
        if _age_seconds(row.computed_at) <= ttl:
            return _wrap(payload, row.computed_at, stale=False, source="cache")
        background_tasks.add_task(_refresh_now, user_league.id, kind)
        return _wrap(payload, row.computed_at, stale=True, source="cache-refreshing")

    # cold load, or an explicit force-refresh
    try:
        payload = await builder(user_league)
    except SnapshotBuildError:
        if row is not None:
            stale_payload = json.loads(row.payload)
            return _wrap(stale_payload, row.computed_at, stale=True, source="cache-refreshing")
        raise

    _write(db, user_league.id, kind, payload)
    return _wrap(payload, _now(), stale=False, source="fresh")
