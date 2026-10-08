"""The app's own suggested PrizePicks tickets, tracked and graded.

The board suggests whole tickets -- the best 2-pick pairs, the 3-6 pick
Power/Flex entries and the "Most likely to win" safest pair -- not just
single picks. Each one is saved the first time it's shown (one row per
season, week and ticket signature; never overwritten, so the record shows
what was actually suggested at the time) and graded with the same
PrizePicks rules as the founder's own entries (user_entries.grade_legs /
entry_payout: a push or DNP drops out and the ticket pays as a smaller one).

Payouts for goblins and demons aren't known in advance (the founder's real
screenshots: two goblins paid 1.2x, a goblin with a standard 1.9x, a
standard 2-pick 3x), so tickets holding one are graded hit/miss only.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import SessionLocal
from app.models.tracked_entry import TrackedEntry
from app.services import betting_model as bm
from app.services.user_entries import entry_payout, grade_legs

logger = logging.getLogger(__name__)

TOP_PAIRS = 5


def _leg(leg: Dict[str, Any]) -> Dict[str, Any]:
    return {"player": leg["player"], "team": leg.get("team"), "game": leg.get("game"), "market": leg["market"],
            "side": leg["side"], "line": float(leg["line"]), "odds_type": leg.get("odds_type") or "standard",
            "p_win": float(leg["p_win"]) if leg.get("p_win") is not None else None,
            "status": "pending", "actual": None}


def signature(entry_type: str, legs: Iterable[Dict[str, Any]]) -> str:
    """Same picks, sides, lines and entry type = the same ticket."""
    parts = sorted(f"{l['player']}|{l['market']}|{l['side']}|{float(l['line']):g}|{l.get('odds_type') or 'standard'}"
                   for l in legs)
    return f"{entry_type}:" + ";".join(parts)


def ticket(source: str, entry_type: str, legs: List[Dict[str, Any]], p_all: Optional[float],
           ev: Optional[float], payouts: Optional[Dict[int, float]]) -> Dict[str, Any]:
    legs = [_leg(l) for l in legs]
    specials = any(l["odds_type"] != "standard" for l in legs)
    return {"source": source, "entry_type": entry_type, "size": len(legs), "legs": legs,
            "signature": signature(entry_type, legs),
            "p_all": round(float(p_all), 4) if p_all is not None else None,
            # Goblin/demon payouts aren't known, so neither is EV.
            "ev": None if specials or ev is None else round(float(ev), 4),
            "payouts": None if specials or not payouts else {str(k): v for k, v in payouts.items()},
            "has_specials": specials}


def tickets_from_board(prizepicks: Dict[str, Any], most_likely: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The board's suggested tickets: the top 2-pick pairs by EV (3x) and the
    Most likely safest pair."""
    out = [ticket("pair", "power", p["legs"], p.get("joint_prob"), p.get("ev"), {2: bm.POWER_PLAY_2_PRICE / 100 + 1})
           for p in (prizepicks.get("pairs") or [])[:TOP_PAIRS]]
    pair = (most_likely or {}).get("safest_pair")
    if pair:
        by_name = {p["player"]: p for p in most_likely.get("picks") or []}
        legs = [by_name[n] for n in pair["legs"] if n in by_name]
        if len(legs) == 2:
            out.append(ticket("safest_pair", "power", legs, pair.get("p_both"), None, None))
    return out


def tickets_from_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The best 3-6 pick Power / 2-6 pick Flex entry of each size and type
    (betting_service.prizepicks_entries' first per group is its best)."""
    seen, out = set(), []
    for e in sorted(entries, key=lambda e: -e["ev"]):
        key = (e["type"], e["size"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ticket("entry", e["type"], e["legs"], e.get("p_all"), e.get("ev"), e.get("payouts")))
    return out


def record(season: int, week: int, tickets: List[Dict[str, Any]]) -> int:
    """Insert tickets not seen this week; existing ones are never touched."""
    if not tickets:
        return 0
    values = [{**t, "season": season, "week": week, "engine_version": bm.ENGINE_VERSION, "status": "pending"}
              for t in tickets]
    with SessionLocal() as db:
        stmt = pg_insert(TrackedEntry).values(values).on_conflict_do_nothing(constraint="uq_tracked_entry")
        result = db.execute(stmt)
        db.commit()
        return result.rowcount or 0


def outcome(entry_type: str, size: int, payouts: Optional[Dict[str, float]], statuses: List[str]) -> tuple:
    """(status, payout multiple per unit) once every pick is decided. With
    unknown payouts (goblins/demons): status only, multiple None."""
    if payouts:
        table = {int(k): float(v) for k, v in payouts.items()}
        to_win = table.get(size) or (bm.POWER_PAYOUTS.get(size) if entry_type == "power" else None) or 1.0
        status, paid = entry_payout(entry_type, 1.0, to_win, statuses)
        return status, round(paid, 4)
    active = [s for s in statuses if s in ("won", "lost")]
    if len(active) <= 1:
        return "refunded", None
    hits = sum(s == "won" for s in active)
    if hits == len(active):
        return "won", None
    return ("partial" if entry_type == "flex" and hits else "lost"), None


async def grade_pending(current_season: int, current_week: Optional[int]) -> int:
    """Grade pending tickets whose picks' games are final (Sleeper stats, ESPN
    scoreboard; no Odds API credits). Network failures leave them pending."""
    from app.services.betting_tracking import _espn_finals, _sleeper_stats

    with SessionLocal() as db:
        pending = db.query(TrackedEntry).filter(TrackedEntry.status == "pending").all()
        weeks: Dict[tuple, tuple] = {}
        graded = 0
        for t in pending:
            key = (t.season, t.week)
            if key not in weeks:
                try:
                    weeks[key] = (await _espn_finals(t.season, t.week), await _sleeper_stats(t.season, t.week))
                except Exception as err:  # noqa: BLE001 - try again next time
                    logger.warning("Tracked tickets %s/%s grading skipped: %s", t.season, t.week, type(err).__name__)
                    weeks[key] = None
            if not weeks[key]:
                continue
            finals, stats = weeks[key]
            week_over = t.season < current_season or (current_week is not None and t.week < current_week)
            legs = grade_legs(t.legs, stats, finals, week_over)
            t.legs = legs
            if all(l["status"] != "pending" for l in legs):
                t.status, t.payout_mult = outcome(t.entry_type, t.size, t.payouts, [l["status"] for l in legs])
                t.graded_at = datetime.now(timezone.utc)
                graded += 1
        db.commit()
    return graded


def out(t: TrackedEntry) -> Dict[str, Any]:
    return {"id": t.id, "season": t.season, "week": t.week, "source": t.source, "entry_type": t.entry_type,
            "size": t.size, "legs": t.legs, "p_all": t.p_all, "ev": t.ev, "payouts": t.payouts,
            "has_specials": t.has_specials, "engine_version": t.engine_version, "status": t.status,
            "payout_mult": t.payout_mult,
            "profit_units": None if t.payout_mult is None else round(t.payout_mult - 1, 4),
            "first_seen_at": t.first_seen_at.isoformat() if t.first_seen_at else None,
            "graded_at": t.graded_at.isoformat() if t.graded_at else None}
