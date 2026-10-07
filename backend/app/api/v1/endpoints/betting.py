"""This week's betting board: player props and game lines priced by
betting_service (Monte Carlo + de-vigged market, quarter-Kelly units)."""
import asyncio
import json
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.api.deps import get_current_active_user
from app.models.user import User
from app.services import betting_service, prizepicks_board
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


_MAX_BOARD_BYTES = 25 * 1024 * 1024


@router.post("/prizepicks-board")
async def upload_prizepicks_board(
    file: UploadFile = File(..., description="Saved api.prizepicks.com/projections?league_id=9 page"),
    current_user: User = Depends(get_current_active_user),
):
    """Store today's PrizePicks NFL board (see prizepicks_board.py for why
    it's uploaded rather than fetched). The board's PrizePicks tab prices
    it until a newer upload or it's 36h old."""
    raw = await file.read(_MAX_BOARD_BYTES + 1)
    if len(raw) > _MAX_BOARD_BYTES:
        raise HTTPException(status_code=413, detail="File too large for a PrizePicks board.")
    try:
        parsed = prizepicks_board.parse_board(json.loads(raw))
    except (ValueError, UnicodeDecodeError) as e:
        detail = str(e) if isinstance(e, prizepicks_board.BoardError) else (
            "That file isn't JSON. Save the api.prizepicks.com page itself (Cmd+S), not a screenshot or the app page.")
        raise HTTPException(status_code=400, detail=detail)
    stored = await prizepicks_board.save(parsed)
    betting_service._board_cache.clear()  # reprice on the next board request
    return {"lines": len(parsed["lines"]), "total_projections": parsed["total"], "uploaded_at": stored["uploaded_at"]}


@router.post("/prizepicks-entries")
async def get_prizepicks_entries(
    power: Optional[Dict[str, float]] = Body(None, description='Power Play payouts by size, e.g. {"3": 6}'),
    flex: Optional[Dict[str, Dict[str, float]]] = Body(None, description='Flex payouts, e.g. {"5": {"5": 10, "4": 2, "3": 0.4}}'),
    current_user: User = Depends(get_current_active_user),
):
    """Best 3-6 pick PrizePicks Power and Flex entries from this week's
    board legs, priced with the given payouts (defaults: PrizePicks'
    standard published multipliers -- they vary by state)."""
    board = await build_board()
    legs = (board.get("prizepicks") or {}).get("legs") or []
    try:
        power_table = {int(k): float(v) for k, v in power.items() if float(v) > 0} if power else None
        flex_table = ({int(k): {int(h): float(m) for h, m in tiers.items() if float(m) > 0} for k, tiers in flex.items()}
                      if flex else None)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Payouts must be numbers keyed by pick count.")
    entries = await asyncio.to_thread(betting_service.prizepicks_entries, legs, power_table, flex_table)
    return {"entries": entries, "legs_considered": min(len(legs), 12),
            "default_power": betting_service.bm.POWER_PAYOUTS, "default_flex": betting_service.bm.FLEX_PAYOUTS}
