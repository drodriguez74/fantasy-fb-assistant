"""This week's betting board: player props and game lines priced by
betting_service (Monte Carlo + de-vigged market, quarter-Kelly units)."""
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.betting_service import build_board

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
