"""Weekly audit: every recommendation the app made in a week, what it said,
and what actually happened -- one table (and a CSV) across sections:

- Bets (units > 0), Best available fills and Most likely to win picks, from
  bet_picks (betting_tracking.py);
- the app's suggested PrizePicks tickets, from tracked_entries
  (tracked_entries.py);
- the user's own logged entries (user_entries.py), kept as a separate
  section because they're the user's picks, not the app's.

Each row carries the engine version that made it, so a week can be read
per engine. No-bet lines aren't recommendations; they live in Results →
Calibration.
"""
import csv
import io
from typing import Any, Dict, List, Optional

from app.db.base import SessionLocal
from app.models.bet_pick import BetPick
from app.services.betting_tracking import beat_close
from app.models.tracked_entry import TrackedEntry
from app.models.user_entry import UserEntry
from app.services import betting_model as bm

SECTIONS = ("Bets", "Best available", "Watch list", "Most likely to win", "Suggested tickets", "My entries")
COLUMNS = ("section", "pick", "market", "side", "line", "book", "price", "p_win", "books_prob", "engine_prob",
           "units", "engine_version", "status", "actual", "profit", "profit_unit", "kickoff", "graded_at",
           "close_line", "close_books_prob", "beat_close")
DECIDED = ("won", "lost", "partial")

MARKET_LABELS = {
    "player_pass_yds": "Pass yds", "player_rush_yds": "Rush yds", "player_reception_yds": "Rec yds",
    "player_receptions": "Receptions", "player_anytime_td": "Anytime TD", "spread": "Spread", "total": "Total",
}


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _section(p: BetPick) -> str:
    if p.kind == "pp_leg":
        return "Most likely to win"
    if p.confidence == "watch":
        return "Watch list"
    return "Best available" if p.confidence == "fill" else "Bets"


def pick_row(p: BetPick) -> Dict[str, Any]:
    side = p.side
    if p.kind == "pp_leg":
        side = "More" if p.side == "Over" else "Less"
    return {
        "section": _section(p),
        "pick": p.subject if p.kind in ("player_prop", "pp_leg") else p.game,
        "market": MARKET_LABELS.get(p.market, p.market), "side": side, "line": p.line,
        "book": p.book, "price": p.price or None,
        "p_win": p.p_win, "books_prob": p.market_prob, "engine_prob": p.model_prob,
        "units": p.units or None, "engine_version": p.engine_version or "pre-versioning",
        "status": p.status, "actual": p.actual,
        "profit": p.profit_units if p.kind != "pp_leg" else None, "profit_unit": "u" if p.kind != "pp_leg" else None,
        "kickoff": _iso(p.kickoff), "graded_at": _iso(p.graded_at),
        # Closing line: the last market seen for this side before kickoff.
        "close_line": getattr(p, "close_line", None), "close_books_prob": getattr(p, "close_market_prob", None),
        "beat_close": beat_close(p) if p.kind != "pp_leg" and getattr(p, "close_seen_at", None) else None,
    }


def _legs_text(legs: List[Dict[str, Any]]) -> str:
    return " + ".join(f"{l['player']} {l['side']} {float(l['line']):g} {MARKET_LABELS.get(l['market'], l['market'])}"
                      + (f" ({l['odds_type']})" if l.get("odds_type") not in (None, "standard") else "")
                      for l in legs)


def _hits_text(legs: List[Dict[str, Any]]) -> Optional[str]:
    decided = [l for l in legs if l.get("status") in ("won", "lost")]
    return f"{sum(l['status'] == 'won' for l in decided)}/{len(legs)} hit" if decided else None


def ticket_row(t: TrackedEntry) -> Dict[str, Any]:
    kind = {"pair": "2-pick pair", "safest_pair": "Safest pair", "entry": f"{t.size}-pick"}.get(t.source, t.source)
    return {
        "section": "Suggested tickets",
        "pick": f"{kind} {t.entry_type.title()}: {_legs_text(t.legs)}",
        "market": "Ticket", "side": None, "line": None,
        "book": "PrizePicks" + (" (goblin/demon: payout unknown)" if t.has_specials else ""), "price": None,
        "p_win": t.p_all, "books_prob": None, "engine_prob": None, "units": None,
        "engine_version": t.engine_version or "pre-versioning",
        "status": t.status, "actual": _hits_text(t.legs),
        "profit": None if t.payout_mult is None else round(t.payout_mult - 1, 4),
        "profit_unit": None if t.payout_mult is None else "x stake",
        "kickoff": None, "graded_at": _iso(t.graded_at),
    }


def entry_row(e: UserEntry) -> Dict[str, Any]:
    return {
        "section": "My entries",
        "pick": f"{len(e.legs)}-pick {e.entry_type.title()} ${e.stake:g} to pay ${e.to_win:g}: {_legs_text(e.legs)}",
        "market": "Entry", "side": None, "line": None, "book": "PrizePicks", "price": None,
        "p_win": e.est_hit_prob, "books_prob": e.est_hit_prob, "engine_prob": None, "units": None,
        "engine_version": e.engine_version or "pre-versioning",
        "status": e.status, "actual": _hits_text(e.legs),
        "profit": None if e.payout is None else round(e.payout - e.stake, 2), "profit_unit": "$",
        "kickoff": None, "graded_at": _iso(e.graded_at),
    }


def section_summary(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per section: picks, decided, hits, hit rate and the average chance we
    gave the decided ones (predicted vs actual)."""
    out = {}
    for name in SECTIONS:
        rs = [r for r in rows if r["section"] == name]
        if not rs:
            continue
        decided = [r for r in rs if r["status"] in DECIDED]
        preds = [r["p_win"] for r in decided if r["p_win"] is not None]
        hits = sum(r["status"] == "won" for r in decided)
        out[name] = {"picks": len(rs), "decided": len(decided), "pending": sum(r["status"] == "pending" for r in rs),
                     "hits": hits, "hit_rate": round(hits / len(decided), 4) if decided else None,
                     "predicted": round(sum(preds) / len(preds), 4) if preds else None}
    return out


def weeks(user_id: Optional[int]) -> List[Dict[str, int]]:
    with SessionLocal() as db:
        found = {(s, w) for s, w in db.query(BetPick.season, BetPick.week).filter(
            (BetPick.recommended.is_(True)) | (BetPick.kind == "pp_leg") | (BetPick.confidence == "watch")).distinct()}
        found |= {(s, w) for s, w in db.query(TrackedEntry.season, TrackedEntry.week).distinct()}
        if user_id is not None:
            found |= {(s, w) for s, w in db.query(UserEntry.season, UserEntry.week)
                      .filter(UserEntry.user_id == user_id).distinct()}
    return [{"season": s, "week": w} for s, w in sorted(found, reverse=True)]


def audit(season: Optional[int], week: Optional[int], user_id: Optional[int]) -> Dict[str, Any]:
    available = weeks(user_id)
    if (season is None or week is None) and available:
        season, week = available[0]["season"], available[0]["week"]
    rows: List[Dict[str, Any]] = []
    if season is not None and week is not None:
        with SessionLocal() as db:
            picks = db.query(BetPick).filter(BetPick.season == season, BetPick.week == week).filter(
                (BetPick.recommended.is_(True)) | (BetPick.kind == "pp_leg") | (BetPick.confidence == "watch")).all()
            tickets = db.query(TrackedEntry).filter(TrackedEntry.season == season, TrackedEntry.week == week).all()
            entries = (db.query(UserEntry).filter(UserEntry.user_id == user_id, UserEntry.season == season,
                                                  UserEntry.week == week).all() if user_id is not None else [])
            order = {s: i for i, s in enumerate(SECTIONS)}
            rows = sorted([pick_row(p) for p in picks], key=lambda r: (order[r["section"]], -(r["units"] or 0),
                                                                        -(r["p_win"] or 0)))
            rows += sorted([ticket_row(t) for t in tickets], key=lambda r: -(r["p_win"] or 0))
            rows += [entry_row(e) for e in entries]
    return {"season": season, "week": week, "weeks": available, "engine_version": bm.ENGINE_VERSION,
            "summary": section_summary(rows), "rows": rows}


def to_csv(rows: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r[k]) for k in COLUMNS})
    return buf.getvalue()
