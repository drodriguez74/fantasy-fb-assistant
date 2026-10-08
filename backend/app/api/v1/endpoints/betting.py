"""This week's betting board: player props and game lines priced by
betting_service (Monte Carlo + de-vigged market, quarter-Kelly units)."""
import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.api.deps import get_current_active_user
from app.models.user import User
from app.services import betting_service, entry_screenshot, prizepicks_board, tracked_entries, user_entries
from app.services.sleeper_service import sleeper_service
from app.services.betting_service import build_board
from app.services.betting_tracking import grade_pending, summarize

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/board")
async def get_betting_board(
    refresh: bool = Query(False, description="Recompute now instead of the 15-minute cached board"),
    sport: str = Query("nfl", pattern="^(nfl|cfb)$", description="nfl or cfb (college football)"),
    current_user: User = Depends(get_current_active_user),
):
    """Player props and game lines with model probability, market fair
    probability, expected value and recommended units (1u = 1% bankroll).
    `available: false` with a `detail` when odds aren't configured or no
    lines exist; odds fetches themselves are cached (6h lines, 24h props)
    regardless of `refresh`, so it never burns API credits. `sport=cfb`
    is the college board (betting_service.build_cfb_board)."""
    if sport == "cfb":
        return await betting_service.build_cfb_board(force=refresh)
    return await build_board(force=refresh)


@router.get("/results")
async def get_betting_results(
    season: Optional[int] = Query(None, description="Limit to one season (default: all)"),
    sport: str = Query("all", pattern="^(nfl|cfb|all)$", description="nfl, cfb (college) or all"),
    version: str = Query("all", pattern="^(all|current)$",
                         description="all picks, or only those made by the current engine version"),
    current_user: User = Depends(get_current_active_user),
):
    """Track record of the board's recommendations. Settles any pending
    picks whose games are final first (Sleeper stats / ESPN scores, no
    Odds API credits), then returns record, units, ROI, splits by
    sport / confidence / market / week, calibration and the pick list --
    for one sport, or all of them."""
    graded = await grade_pending()
    summary = await asyncio.to_thread(summarize, season, None if sport == "all" else sport,
                                      None if version == "all" else version)
    return {**summary, "sport": sport, "version": version, "newly_graded": graded}


@router.get("/audit")
async def get_betting_audit(
    season: Optional[int] = Query(None, description="Season (default: the latest week with tracked picks)"),
    week: Optional[int] = Query(None, description="NFL week (default: the latest week with tracked picks)"),
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: User = Depends(get_current_active_user),
):
    """Every recommendation made in one week -- bets, Best available fills,
    Most likely to win picks, the app's suggested PrizePicks tickets and the
    user's own entries (separate section) -- with what we said, the engine
    version and what happened. Grades anything newly final first (free
    sources). format=csv downloads the same rows."""
    from fastapi.responses import StreamingResponse
    from app.services import betting_audit

    await grade_pending()
    cur_season, cur_week = await _nfl_week()
    for grade in (lambda: tracked_entries.grade_pending(cur_season, cur_week),
                  lambda: user_entries.grade_pending(current_user.id, cur_season, cur_week)):
        try:
            await grade()
        except Exception as e:  # noqa: BLE001 - grading retries next time; the audit still shows
            logger.warning("Audit grading skipped: %s", type(e).__name__)
    data = await asyncio.to_thread(betting_audit.audit, season, week, current_user.id)
    if format == "csv":
        name = f"bets-audit-{data['season']}-week{data['week']}.csv" if data["week"] else "bets-audit.csv"
        return StreamingResponse(iter([betting_audit.to_csv(data["rows"])]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})
    return data


_MAX_BOARD_BYTES = 25 * 1024 * 1024


@router.post("/prizepicks-board")
async def upload_prizepicks_board(
    file: UploadFile = File(..., description="Saved api.prizepicks.com/projections?league_id=9 page"),
    current_user: User = Depends(get_current_active_user),
):
    """Store today's PrizePicks NFL or college board -- the league is read
    from the file (see prizepicks_board.py for why it's uploaded rather than
    fetched). Priced until a newer upload of that league or it's 36h old."""
    raw = await file.read(_MAX_BOARD_BYTES + 1)
    if len(raw) > _MAX_BOARD_BYTES:
        raise HTTPException(status_code=413, detail="File too large for a PrizePicks board.")
    try:
        parsed = prizepicks_board.parse_board(json.loads(raw))
    except (ValueError, UnicodeDecodeError) as e:
        detail = str(e) if isinstance(e, prizepicks_board.BoardError) else (
            "That file isn't JSON. Save the api.prizepicks.com page itself (Cmd+S), not a screenshot or the app page.")
        raise HTTPException(status_code=400, detail=detail)
    if parsed["league"] == "NCAAFB" and not betting_service.CFB_PROPS_ENABLED:
        raise HTTPException(status_code=400, detail="College player props are shelved for now. Upload the NFL board (league_id=9).")
    stored = await prizepicks_board.save(parsed)
    betting_service._board_cache.clear()  # reprice on the next board request
    return {"league": parsed["league"], "lines": len(parsed["lines"]), "total_projections": parsed["total"],
            "uploaded_at": stored["uploaded_at"]}


@router.post("/prizepicks-entries")
async def get_prizepicks_entries(
    power: Optional[Dict[str, float]] = Body(None, description='Power Play payouts by size, e.g. {"3": 6}'),
    flex: Optional[Dict[str, Dict[str, float]]] = Body(None, description='Flex payouts, e.g. {"5": {"5": 10, "4": 2, "3": 0.4}}'),
    sport: str = Query("nfl", pattern="^(nfl|cfb)$"),
    current_user: User = Depends(get_current_active_user),
):
    """Best PrizePicks Power (3-6) and Flex (2-6) entries from this week's
    board legs, priced with the given payouts (defaults: PrizePicks'
    standard published multipliers -- they vary by state)."""
    board = await (betting_service.build_cfb_board() if sport == "cfb" else build_board())
    legs = (board.get("prizepicks") or {}).get("legs") or []
    try:
        power_table = {int(k): float(v) for k, v in power.items() if float(v) > 0} if power else None
        flex_table = ({int(k): {int(h): float(m) for h, m in tiers.items() if float(m) > 0} for k, tiers in flex.items()}
                      if flex else None)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Payouts must be numbers keyed by pick count.")
    entries = await asyncio.to_thread(betting_service.prizepicks_entries, legs, power_table, flex_table)
    if sport == "nfl" and board.get("week") and board.get("season"):
        try:  # the suggested entries are tracked and graded (tracked_entries.py)
            await asyncio.to_thread(tracked_entries.record, int(board["season"]), int(board["week"]),
                                    tracked_entries.tickets_from_entries(entries))
        except Exception as e:  # noqa: BLE001 - tracking must never break the endpoint
            logger.warning("Recording suggested entries failed: %s", e)
    return {"entries": entries, "legs_considered": min(len(legs), 12),
            "default_power": betting_service.bm.POWER_PAYOUTS, "default_flex": betting_service.bm.FLEX_PAYOUTS}


async def _nfl_week():
    state = await sleeper_service.get_nfl_state()
    season = int(state.get("season") or 0) if isinstance(state, dict) else 0
    week = state.get("week") if isinstance(state, dict) else None
    return season, (int(week) if week else None)


@router.get("/entries")
async def get_my_entries(current_user: User = Depends(get_current_active_user)):
    """The user's logged PrizePicks entries. Grades any whose games are final
    first (Sleeper stats, no credits), then returns the list, the record and
    a pick-level check of books vs model vs results."""
    season, week = await _nfl_week()
    graded = await user_entries.grade_pending(current_user.id, season, week)
    return {**await asyncio.to_thread(user_entries.summary, current_user.id), "newly_graded": graded}


@router.post("/entries")
async def log_entry(body: Dict = Body(...), current_user: User = Depends(get_current_active_user)):
    """Log an entry the user placed on PrizePicks: {entry_type: power|flex,
    stake, to_win, legs: [{player, team?, market, side: More|Less, line}],
    week?, notes?}. Each pick is snapshotted with the engine's current view."""
    try:
        data = user_entries.validate(body)
    except (user_entries.EntryError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    season, week = await _nfl_week()
    if not week:
        raise HTTPException(status_code=503, detail="Couldn't determine the current NFL week.")
    await build_board()  # makes sure the engine's view is loaded for the snapshot
    snaps = [betting_service.snapshot_leg(leg) for leg in data["legs"]]
    for leg, snap in zip(data["legs"], snaps):
        if snap and not leg.get("team"):
            leg["team"] = snap.get("team")
    return await asyncio.to_thread(user_entries.create, current_user.id, data, season, week, snaps)


@router.post("/entries/read-screenshot")
async def read_entry_screenshot(
    file: UploadFile = File(..., description="Screenshot of a placed PrizePicks entry"),
    current_user: User = Depends(get_current_active_user),
):
    """Read a PrizePicks entry screenshot into the My entries form fields
    (entry_type, stake, to_win, picks, warnings). Nothing is saved: the user
    checks the prefilled form and saves it via POST /entries."""
    image = await file.read(entry_screenshot.MAX_BYTES + 1)
    try:
        return await entry_screenshot.read_screenshot(image, file.content_type or "")
    except entry_screenshot.ScreenshotError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/watch-alerts")
async def get_watch_alerts(current_user: User = Depends(get_current_active_user)):
    """The user's "alert me if it becomes a bet" alerts (active, triggered, expired)."""
    from app.services import watch_alerts
    return {"alerts": await asyncio.to_thread(watch_alerts.list_for, current_user.id)}


@router.post("/watch-alerts")
async def add_watch_alert(body: Dict = Body(...), current_user: User = Depends(get_current_active_user)):
    """Alert me if this watch-list line becomes a bet: {sport: nfl|cfb, type:
    player_prop|game, subject (player or game label), market, side}. The pick
    is looked up on the current board; its target price is saved with it."""
    from app.services import watch_alerts
    sport = body.get("sport") or "nfl"
    board = await (betting_service.build_cfb_board() if sport == "cfb" else build_board())
    rows = (board.get("player_props") or []) + (board.get("game_props") or [])
    row = watch_alerts.find_row(rows, body.get("type") or "player_prop", body.get("subject") or "",
                                body.get("market") or "", body.get("side") or "")
    if row is None:
        raise HTTPException(status_code=404, detail="That line isn't on the current board.")
    season, week = await _nfl_week()
    if not week:
        raise HTTPException(status_code=503, detail="Couldn't determine the current NFL week.")
    try:
        return await asyncio.to_thread(watch_alerts.create, current_user.id, season, week, row,
                                       "cfb_game" if sport == "cfb" else None)
    except watch_alerts.AlertError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/watch-alerts/{alert_id}")
async def delete_watch_alert(alert_id: int, current_user: User = Depends(get_current_active_user)):
    from app.services import watch_alerts
    if not await asyncio.to_thread(watch_alerts.delete, current_user.id, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"deleted": alert_id}


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: int, current_user: User = Depends(get_current_active_user)):
    if not await asyncio.to_thread(user_entries.delete, current_user.id, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"deleted": entry_id}
