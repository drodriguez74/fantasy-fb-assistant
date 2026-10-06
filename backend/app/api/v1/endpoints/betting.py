"""This week's betting board: player props and game lines priced by
betting_service (Monte Carlo + de-vigged market, quarter-Kelly units)."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.betting_service import build_board
from app.services.betting_tracking import grade_pending, summarize

router = APIRouter()


@router.get("/board")
async def get_betting_board(
    refresh: bool = Query(False, description="Recompute now instead of the 15-minute cached board"),
    current_user: User = Depends(get_current_active_user),
):
    """Player props and game lines with model probability, market fair
    probability, expected value and recommended units (1u = 1% bankroll).
    `available: false` with a `detail` when odds aren't configured or no
    lines exist; odds fetches themselves are cached (6h lines, 24h props)
    regardless of `refresh`, so it never burns API credits."""
    return await build_board(force=refresh)


@router.get("/results")
async def get_betting_results(
    season: Optional[int] = Query(None, description="Limit to one season (default: all)"),
    current_user: User = Depends(get_current_active_user),
):
    """Track record of the board's recommendations. Settles any pending
    picks whose games are final first (Sleeper stats / ESPN scores, no
    Odds API credits), then returns record, units, ROI, splits by
    confidence / market / week, calibration and the pick list."""
    graded = await grade_pending()
    summary = await asyncio.to_thread(summarize, season)
    return {**summary, "newly_graded": graded}
