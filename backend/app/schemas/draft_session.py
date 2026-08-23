from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime


# Summary shape used for the draft history list (GET /users/me/drafts).
# Deliberately omits the full `user_roster` payload to keep the list
# response light -- callers that need the full roster/analysis use
# GET /users/me/drafts/{session_id}.
class DraftSessionSummary(BaseModel):
    id: int
    session_id: str
    platform: str
    league_id: str
    user_team_id: Optional[str] = None
    draft_settings: Optional[Dict[str, Any]] = None
    is_active: bool
    is_completed: bool
    draft_grade: Optional[str] = None
    recommendations_used: Optional[int] = None
    ai_accuracy_score: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DraftSessionListResponse(BaseModel):
    draft_sessions: List[DraftSessionSummary]
    total: int


# Full detail shape for a single draft session (GET /users/me/drafts/{session_id}),
# including the full drafted roster and the human-readable analysis text.
class DraftSessionDetail(BaseModel):
    id: int
    session_id: str
    platform: str
    league_id: str
    user_team_id: Optional[str] = None
    draft_settings: Optional[Dict[str, Any]] = None
    is_active: bool
    is_completed: bool
    user_roster: Optional[List[Dict[str, Any]]] = None
    draft_grade: Optional[str] = None
    final_analysis: Optional[str] = None
    recommendations_used: Optional[int] = None
    ai_accuracy_score: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
