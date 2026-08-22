"""
Notifications API Endpoints

RESTful endpoints for the in-app notification center: list a user's
notifications, mark them read, and get an unread count for the navbar bell
badge. Notification rows themselves are created elsewhere (see
app.services.notification_service) as a side effect of real events -- this
module only reads/updates them, scoped to the authenticated user.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.notification import Notification

router = APIRouter()


def _serialize(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


@router.get("/")
async def list_notifications(
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    page_size: int = Query(20, ge=1, le=100, description="Notifications per page"),
    unread_only: bool = Query(False, description="Only return unread notifications"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List the current user's notifications, most recent first."""
    try:
        query = db.query(Notification).filter(Notification.user_id == current_user.id)
        if unread_only:
            query = query.filter(Notification.is_read.is_(False))

        total = query.count()
        notifications = (
            query.order_by(desc(Notification.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "notifications": [_serialize(n) for n in notifications],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list notifications: {str(e)}")


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get the count of unread notifications, for the navbar bell badge."""
    try:
        count = (
            db.query(Notification)
            .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
            .count()
        )
        return {"unread_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get unread count: {str(e)}")


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    try:
        notification = (
            db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
            .first()
        )
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification.is_read = True
        db.commit()
        db.refresh(notification)

        return _serialize(notification)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark notification as read: {str(e)}")


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Mark all of the current user's unread notifications as read."""
    try:
        updated = (
            db.query(Notification)
            .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
            .update({"is_read": True})
        )
        db.commit()

        return {"marked_read": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark all notifications as read: {str(e)}")
