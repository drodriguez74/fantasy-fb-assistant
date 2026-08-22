"""
Notification Service

Generates real, backend-tracked in-app notifications from actual events that
already exist elsewhere in this app. This is a lazy, request-driven trigger
rather than a scheduled background job: this app has a Celery worker
(app/tasks) for content generation, but that requires a running worker +
Redis, which isn't a given in every dev environment, and the notification
signal here (a live Sleeper trending-add spike) is already fetched fresh on
every hit to GET /waiver-wire/recommendations. Piggybacking on that existing
request is simpler and just as real -- the notification is derived from the
exact same live API response the user is looking at, not a separate stale
poll. A Celery beat task remains a reasonable future upgrade if this needs
to fire even when no one has the app open.

Real event source used: Sleeper's live trending-add feed, already wired up
in WaiverWireService.get_live_trending_recommendations. A player lands in
the top decile of that feed's add-count ranking ("urgent" priority) only
because real fantasy managers are actually adding them across real Sleeper
leagues in the last 24 hours -- not a synthetic signal.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.notification import Notification

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
