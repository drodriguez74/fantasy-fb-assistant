"""
Notification Service

Generates real, backend-tracked in-app notifications from actual events that
already exist elsewhere in this app.

`notify_trending_adds` is a lazy, request-driven trigger: the notification
signal (a live Sleeper trending-add spike) is already fetched fresh on every
hit to GET /waiver-wire/recommendations, so piggybacking on that existing
request is simpler and just as real -- the notification is derived from the
exact same live API response the user is looking at, not a separate stale
poll.

`generate_weekly_digest_for_user` is the one genuinely schedule-driven
exception -- see its docstring. Celery/Redis were removed from this app
entirely (see git history, "Decommission dead Celery/Redis background-task
scaffolding"); there is no background worker to piggyback a beat task on
here, so the actual trigger lives outside the app (see notifications.py's
POST /generate-weekly-digest).

Real event sources used: Sleeper's live trending-add feed (a player lands
in the top decile of that feed's add-count ranking, "urgent" priority, only
because real fantasy managers are actually adding them across real Sleeper
leagues in the last 24 hours) and, for the weekly digest, each connected
league's real live waiver recommendations and (ESPN only) real bye-week
radar -- never a synthetic or templated signal.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

# Only the top-decile "urgent" tier (see WaiverWireService._priority_from_rank)
# is notification-worthy -- otherwise a user would get a notification for
# every trending player on every page load.
_NOTIFIABLE_PRIORITIES = {"urgent"}

# Cap how many notifications a single fetch can create so one big trending
# wave (e.g. an early-slate Sunday injury cascade) can't flood a user's
# notification list in one request.
_MAX_NOTIFICATIONS_PER_FETCH = 3


def notify_trending_adds(
    db: Session, user_id: int, recommendations: List[Dict[str, Any]]
) -> List[Notification]:
    """Create notification rows for genuinely high-signal trending adds the
    user hasn't already been notified about.

    `recommendations` must be the real output of
    WaiverWireService.get_live_trending_recommendations -- every field used
    here (player_name, position, team, add_count_24h) traces back to
    Sleeper's live trending-add feed for the last 24 hours. Safe to call on
    every request: already-notified players are skipped via `dedupe_key`, so
    repeated calls for the same trending player are a no-op after the first.
    """
    created: List[Notification] = []

    try:
        urgent = [r for r in recommendations if r.get("priority") in _NOTIFIABLE_PRIORITIES]

        for rec in urgent[:_MAX_NOTIFICATIONS_PER_FETCH]:
            player_id = rec.get("player_id")
            if player_id is None:
                continue

            dedupe_key = f"trending_add:{player_id}"

            already_notified = (
                db.query(Notification)
                .filter(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
                .first()
            )
            if already_notified:
                continue

            player_name = rec.get("player_name", "A player")
            position = rec.get("position", "")
            team = rec.get("team", "")
            add_count = rec.get("add_count_24h", 0)

            notification = Notification(
                user_id=user_id,
                type="trending_add",
                title=f"{player_name} is trending",
                body=(
                    f"{player_name} ({position} - {team}) has been added in "
                    f"{add_count:,} Sleeper fantasy leagues in the last 24 hours "
                    f"-- one of today's top waiver-wire targets."
                ),
                dedupe_key=dedupe_key,
                is_read=False,
            )
            db.add(notification)
            created.append(notification)

        if created:
            db.commit()
            for notification in created:
                db.refresh(notification)

    except Exception as e:
        # Notification generation is a side effect of fetching
        # recommendations, not the point of the request -- never let it take
        # down the actual waiver-wire response.
        logger.error(f"Error generating trending-add notifications for user {user_id}: {str(e)}")
        db.rollback()

    return created


# Only one digest per league per real calendar week -- re-running the
# trigger endpoint (e.g. a retried cron hit) is a no-op after the first
# real send that week, via the same dedupe_key pattern notify_trending_adds
# uses above.
def _iso_week_key(now: datetime) -> str:
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def generate_weekly_digest_for_user(db: Session, user: User) -> List[Notification]:
    """Real weekly digest: one notification per connected league (with a
    team_id configured) summarizing this week's actual top waiver target
    and any real upcoming bye-week risk on the user's own roster.

    Unlike notify_trending_adds, nothing about this user's session drives
    it -- a user who never opens the app between Monday morning and Sunday
    kickoff would otherwise never see a mid-week waiver alert. It's real,
    schedule-shaped content, so it needs a real trigger outside a request
    a logged-in user happens to make. This app has no background worker
    (Celery/Redis were removed -- see the module docstring), so the trigger
    is POST /notifications/generate-weekly-digest, meant to be hit by an
    external scheduler (a GitHub Actions cron, see .github/workflows/
    weekly-digest.yml) rather than fired from inside this process.

    Best-effort per league: a platform call failing for one league just
    means that league contributes no digest content, never a crash for the
    whole user. Skips a league entirely (creates nothing) if there's
    genuinely no real content to report, rather than sending an empty
    "nothing happened" notification.
    """
    from app.services.user_service import UserService
    from app.services.waiver_wire_service import WaiverWireService

    created: List[Notification] = []

    try:
        user_service = UserService(db)
        leagues = [
            league for league in user_service.get_user_leagues(user.id)
            if league.team_id
        ]
        if not leagues:
            return created

        week_key = _iso_week_key(datetime.now(timezone.utc))
        waiver_service = WaiverWireService(db)

        for league in leagues:
            dedupe_key = f"weekly_digest:{league.id}:{week_key}"
            already_sent = (
                db.query(Notification)
                .filter(Notification.user_id == user.id, Notification.dedupe_key == dedupe_key)
                .first()
            )
            if already_sent:
                continue

            body_parts: List[str] = []

            # Real top waiver target -- same live Sleeper trending-add feed
            # GET /waiver-wire/recommendations uses, unweighted (no roster
            # fetch here -- this runs for every connected user on a
            # schedule, not in response to one user's own request).
            try:
                recs = await waiver_service.get_live_trending_recommendations(limit=10)
                top = next((r for r in recs if r.get("priority") in ("urgent", "high")), None)
                if top:
                    body_parts.append(
                        f"Top waiver target: {top['player_name']} "
                        f"({top.get('position')}, {top.get('team')}) -- "
                        f"{top.get('add_count_24h', 0):,} adds across Sleeper leagues in the last 24 hours."
                    )
            except Exception as e:
                logger.warning(f"Weekly digest: waiver lookup failed for league {league.id}: {str(e)}")

            # Real upcoming bye-week risk on this team's own roster (ESPN
            # only -- get_bye_week_radar has no Yahoo/Sleeper equivalent
            # yet). Flags anything within the next 2 weeks so a digest sent
            # any day this week still gives real advance notice.
            if league.platform.value.upper() == "ESPN":
                try:
                    from app.services.espn_service_enhanced import espn_service_enhanced

                    radar = await espn_service_enhanced.get_bye_week_radar(
                        league_id=league.league_id,
                        team_id=int(league.team_id),
                        season=league.season,
                        swid=league.espn_swid,
                        espn_s2=league.espn_s2,
                    )
                    if isinstance(radar, dict) and "error" not in radar:
                        soon = [
                            p for p in radar.get("upcoming_byes", [])
                            if isinstance(p.get("weeks_until_bye"), int) and p["weeks_until_bye"] <= 1
                        ]
                        if soon:
                            names = ", ".join(p["player_name"] for p in soon)
                            this_week = [p["player_name"] for p in soon if p["weeks_until_bye"] == 0]
                            if this_week:
                                body_parts.append(f"On bye this week: {names}.")
                            else:
                                body_parts.append(f"On bye next week: {names}.")
                except Exception as e:
                    logger.warning(f"Weekly digest: bye-week radar failed for league {league.id}: {str(e)}")

            if not body_parts:
                continue

            league_label = league.league_name or f"League {league.league_id}"
            notification = Notification(
                user_id=user.id,
                type="weekly_digest",
                title=f"Your {league_label} weekly digest",
                body=" ".join(body_parts),
                dedupe_key=dedupe_key,
                is_read=False,
            )
            db.add(notification)
            created.append(notification)

        if created:
            db.commit()
            for notification in created:
                db.refresh(notification)

    except Exception as e:
        logger.error(f"Error generating weekly digest for user {user.id}: {str(e)}")
        db.rollback()

    return created
