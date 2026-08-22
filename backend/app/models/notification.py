"""
Notification Model

In-app notification center: real, backend-tracked alerts a user can see when
they're in the app (bell icon + dropdown), generated only from real events
already available elsewhere in this codebase -- e.g. a genuine spike on
Sleeper's live trending-add feed (see app.services.notification_service and
WaiverWireService.get_live_trending_recommendations).

This is explicitly NOT true device/browser push: no service workers, no
VAPID keys, no browser permission prompts, no push-sending backend. That's
real, separate infrastructure (and a new secret to manage) that remains
deferred, future scope. This model exists to deliver the actual underlying
value -- "tell me when something real changed" -- without fabricating a
push capability that isn't there.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Notification(Base):
    """A single in-app notification for a user.

    Every row must trace back to a real event -- a real Sleeper trending-add
    data point, a real injury status change, etc. -- never a templated or
    fabricated message.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # e.g. "trending_add", "injury_update"
    type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)

    # Identifies the real-world event this notification came from (e.g.
    # "trending_add:4046" for Sleeper player id 4046), so the lazy-generation
    # trigger can avoid creating a duplicate notification for the same event
    # every time it re-fires for the same user.
    dedupe_key = Column(String(150), nullable=True, index=True)

    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")
