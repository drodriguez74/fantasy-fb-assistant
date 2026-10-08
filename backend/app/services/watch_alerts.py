"""Watch-list alerts: "alert me if it becomes a bet" (Bets page).

A watch line is positive EV that every source agrees with but under the 3%
bar, so it carries no units. The user can ask to be told if it becomes a
bet. There's no background worker in this app (see CLAUDE.md, Background
tasks), so alerts are checked as a side effect of each board build: when the
same pick (player or game, market, side; the line may have moved) is priced
as a real bet, the user gets an in-app notification (navbar bell) and the
alert is marked triggered. Alerts expire at kickoff. On the free Odds API
tier props refresh only on Wednesdays and Sundays, so prop alerts can only
fire then; game lines refresh every 6 hours.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.db.base import SessionLocal
from app.models.notification import Notification
from app.models.watch_alert import WatchAlert
from app.services import betting_model as bm

logger = logging.getLogger(__name__)


class AlertError(ValueError):
    pass


def _subject(r: Dict[str, Any]) -> str:
    return r["player"] if r.get("type") == "player_prop" else r["game"]


def _parse(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _out(a: WatchAlert) -> Dict[str, Any]:
    return {
        "id": a.id, "season": a.season, "week": a.week, "kind": a.kind, "subject": a.subject, "market": a.market,
        "side": a.side, "line": a.line, "target_price": a.target_price, "p_win": a.p_win, "book": a.book,
        "price": a.price, "kickoff": a.kickoff.isoformat() if a.kickoff else None, "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        "triggered_line": a.triggered_line, "triggered_book": a.triggered_book,
        "triggered_price": a.triggered_price, "triggered_units": a.triggered_units,
    }


def find_row(rows: Iterable[Dict[str, Any]], kind: str, subject: str, market: str, side: str) -> Optional[Dict[str, Any]]:
    for r in rows:
        if r.get("type") == kind and _subject(r) == subject and r["market"] == market and r["side"] == side:
            return r
    return None


def create(user_id: int, season: int, week: int, row: Dict[str, Any], kind: Optional[str] = None) -> Dict[str, Any]:
    """Save an alert for a board row (the current priced line). Idempotent:
    an existing alert for the same pick this week is returned (and
    re-activated if it had expired)."""
    if row["units"] > 0 and not row.get("card_fill"):
        raise AlertError("That line is already a bet.")
    kind = kind or row["type"]
    subject = _subject(row)
    with SessionLocal() as db:
        a = db.query(WatchAlert).filter_by(user_id=user_id, season=season, week=week, kind=kind, subject=subject,
                                           market=row["market"], side=row["side"]).first()
        if a is None:
            a = WatchAlert(user_id=user_id, season=season, week=week, kind=kind, subject=subject, market=row["market"],
                           side=row["side"])
            db.add(a)
        a.line, a.book, a.price = row.get("line"), row.get("book"), int(row["price"])
        a.p_win = float(row["p_win"])
        a.target_price = row.get("bet_at")
        a.kickoff = _parse(row.get("kickoff"))
        a.engine_version = bm.ENGINE_VERSION
        if a.status != "triggered":
            a.status = "active"
        db.commit()
        db.refresh(a)
        return _out(a)


def list_for(user_id: int) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.query(WatchAlert).filter(WatchAlert.user_id == user_id).order_by(WatchAlert.created_at.desc()).limit(100).all()
        return [_out(a) for a in rows]


def delete(user_id: int, alert_id: int) -> bool:
    with SessionLocal() as db:
        a = db.query(WatchAlert).filter(WatchAlert.id == alert_id, WatchAlert.user_id == user_id).first()
        if not a:
            return False
        db.delete(a)
        db.commit()
        return True


def _message(a: WatchAlert, r: Dict[str, Any]) -> Dict[str, str]:
    line = r.get("line")
    pick = f"{a.subject} {r['side']}{f' {line:g}' if line is not None else ''} {r.get('market_label', a.market)}"
    body = (f"{pick} at {r['price']:+d} ({r['book']}) now clears the bar: {r['units']:g}u, "
            f"{r['p_win'] * 100:.0f}% to win, EV {r['ev'] * 100:+.1f}%.")
    if a.line is not None and line is not None and line != a.line:
        body += f" The line moved from {a.line:g}."
    return {"title": f"Now a bet: {a.subject}", "body": body}


def check(rows: List[Dict[str, Any]], season: int, week: int, kind_override: Optional[str] = None,
          now: Optional[datetime] = None) -> int:
    """Fire every active alert whose pick is now a bet on this board; expire
    alerts past kickoff. `kind_override`: the tracked kind for this board's
    rows (college game lines are "cfb_game"). Returns alerts triggered."""
    now = now or datetime.now(timezone.utc)
    kinds = {kind_override} if kind_override else {"player_prop", "game"}
    fired = 0
    with SessionLocal() as db:
        active = db.query(WatchAlert).filter(WatchAlert.status == "active", WatchAlert.season == season,
                                             WatchAlert.week == week, WatchAlert.kind.in_(kinds)).all()
        for a in active:
            kickoff = a.kickoff.replace(tzinfo=timezone.utc) if a.kickoff and a.kickoff.tzinfo is None else a.kickoff
            if kickoff and kickoff <= now:
                a.status = "expired"
                continue
            r = next((x for x in rows if (kind_override or x.get("type")) == a.kind and _subject(x) == a.subject
                      and x["market"] == a.market and x["side"] == a.side), None)
            if r is None or r["units"] <= 0 or r.get("card_fill") or r.get("projection_outlier"):
                continue  # a "Best available" fill isn't a bet
            a.status, a.triggered_at = "triggered", now
            a.triggered_line, a.triggered_book = r.get("line"), r.get("book")
            a.triggered_price, a.triggered_units = int(r["price"]), float(r["units"])
            msg = _message(a, r)
            db.add(Notification(user_id=a.user_id, type="bet_alert", title=msg["title"][:200], body=msg["body"],
                                dedupe_key=f"watch_alert:{a.id}", is_read=False))
            fired += 1
        db.commit()
    return fired
