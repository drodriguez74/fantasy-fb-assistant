"""The user's own PrizePicks entries and sportsbook bets ("My entries" on
the Bets page).

The founder places entries on PrizePicks themselves; this logs them, keeps a
snapshot of what our engine said about each pick when it was logged, and
grades them from Sleeper's real stats (free) once each pick's game is final.
PrizePicks can't be read directly (login + DataDome bot protection), so
entries are entered on the page.

Grading rules (PrizePicks):
- A pick wins if the stat clears the line in the chosen direction; exactly
  on the line is a push, and a player who doesn't play is void. Pushed and
  void picks drop out and the entry pays as the smaller entry (standard
  payouts); a lineup reduced to one pick is refunded.
- Power: any loss loses the entry. Flex: pays by number of hits.
Payouts after a drop-out use the standard tables (betting_model), so they
are approximate if the user's state pays differently.

Sportsbook bets (platform "sportsbook", e.g. Hard Rock Bet) share the table,
the legs and the grading: a "straight" bet is one leg, a "parlay" 2-12, each
leg with its American price. A straight push or void is refunded; a parlay
loses on any lost leg, and pushed or void legs drop out (it pays the product
of the winning legs' prices, the full stated payout when every leg wins).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.base import SessionLocal
from app.models.user_entry import UserEntry
from app.services import betting_model as bm
from app.services.odds_service import normalize_team
from app.services.weekly_projections import normalize_name

logger = logging.getLogger(__name__)

# Market key -> (PrizePicks label, Sleeper stat keys summed).
MARKETS: Dict[str, tuple] = {
    "player_pass_yds": ("Pass Yards", ("pass_yd",)),
    "player_rush_yds": ("Rush Yards", ("rush_yd",)),
    "player_reception_yds": ("Receiving Yards", ("rec_yd",)),
    "player_receptions": ("Receptions", ("rec",)),
    "player_anytime_td": ("Anytime TDs", ("rush_td", "rec_td")),
    "player_pass_tds": ("Pass TDs", ("pass_td",)),
    "player_rush_rec_yds": ("Rush+Rec Yds", ("rush_yd", "rec_yd")),
    "player_pass_rush_yds": ("Pass+Rush Yds", ("pass_yd", "rush_yd")),
    "player_rush_attempts": ("Rush Attempts", ("rush_att",)),
    "player_pass_completions": ("Pass Completions", ("pass_cmp",)),
    "player_pass_attempts": ("Pass Attempts", ("pass_att",)),
    "player_pass_interceptions": ("INT", ("pass_int",)),
    "player_rec_targets": ("Rec Targets", ("rec_tgt",)),
    # Game picks PrizePicks also offers (graded from final scores, not stats):
    # "player" is the team (e.g. "JAX") for a winner pick -- side More, line
    # 0.5, actual 1 / 0 / 0.5 for a win / loss / tie (a tie lands on the line:
    # push) -- and the game ("PHI @ JAX") for a total, with team = home team.
    "team_win": ("Team wins", ()),
    # Spread: "player" is the team, line the margin it must beat (DAL -7.5 is
    # More 7.5 on Dallas's margin; a +3.5 underdog is More -3.5).
    "team_spread": ("Spread (team margin)", ()),
    "game_total": ("Total points", ()),
}
GAME_MARKETS = ("team_win", "team_spread", "game_total")


PLATFORMS = ("prizepicks", "sportsbook")
DEFAULT_BOOK = "Hard Rock Bet"  # the only book the founder can bet at (Florida)
MAX_PARLAY_LEGS = 12


class EntryError(ValueError):
    pass


def decimal_odds(price: int) -> float:
    return 1 + (price / 100 if price > 0 else 100 / -price)


def _price(value: Any) -> int:
    try:
        price = int(value)
    except (TypeError, ValueError):
        raise EntryError("Each bet needs its American odds (e.g. -110 or +150).")
    if -100 < price < 100:
        raise EntryError("American odds are -100 or lower, or +100 or higher.")
    return price


def validate(body: Dict[str, Any]) -> Dict[str, Any]:
    platform = body.get("platform") or "prizepicks"
    if platform not in PLATFORMS:
        raise EntryError("platform must be prizepicks or sportsbook")
    book = platform == "sportsbook"
    entry_type = body.get("entry_type")
    if entry_type not in (("straight", "parlay") if book else ("power", "flex")):
        raise EntryError("A sportsbook bet is straight or parlay." if book else "entry_type must be power or flex")
    stake = float(body.get("stake") or 0)
    legs = body.get("legs") or []
    # PrizePicks added 1-pick Power Plays (seen 2026-10-15: Broncos +2.5, $9.36 to win $18); Flex still needs 2.
    lo, hi = ((1, 1) if entry_type == "straight" else (2, MAX_PARLAY_LEGS)) if book else (1 if entry_type == "power" else 2, 6)
    if not lo <= len(legs) <= hi:
        raise EntryError({(1, 1): "A straight bet has one pick.", (2, MAX_PARLAY_LEGS): f"A parlay has 2 to {MAX_PARLAY_LEGS} picks.",
                          (1, 6): "A Power Play has 1 to 6 picks.", (2, 6): "A Flex Play has 2 to 6 picks."}[(lo, hi)])
    clean = []
    for leg in legs:
        player = (leg.get("player") or "").strip()
        if not player or leg.get("market") not in MARKETS or leg.get("side") not in ("More", "Less"):
            raise EntryError("Each pick needs a player, a stat and More or Less.")
        row = {"player": player, "team": normalize_team(leg.get("team")) if leg.get("team") else None,
               "market": leg["market"], "side": leg["side"], "line": float(leg["line"])}
        if book:
            row["price"] = _price(leg.get("price"))
        clean.append(row)
    if book:
        # The book's own payout when given (it rounds); else the legs' prices.
        full = stake
        for leg in clean:
            full *= decimal_odds(leg["price"])
        to_win = float(body.get("to_win") or 0) or round(full, 2)
    else:
        to_win = float(body.get("to_win") or 0)
        if len({normalize_name(l["player"]) for l in clean}) < len(clean):
            raise EntryError("PrizePicks allows one pick per player.")
    if stake <= 0 or to_win <= stake:
        raise EntryError("Stake must be positive and the full payout larger than the stake.")
    return {"platform": platform, "book": (body.get("book") or DEFAULT_BOOK).strip() if book else None,
            "entry_type": entry_type, "stake": stake, "to_win": to_win, "legs": clean,
            "notes": (body.get("notes") or "").strip() or None, "week": body.get("week")}


def leg_outcome(side: str, line: float, actual: Optional[float]) -> str:
    if actual is None:
        return "void"
    if actual == line:
        return "push"
    return "won" if (actual > line) == (side == "More") else "lost"


def entry_payout(entry_type: str, stake: float, to_win: float, statuses: List[str],
                 prices: Optional[List[int]] = None) -> tuple:
    """(status, payout) once every leg is decided."""
    if entry_type in ("straight", "parlay"):
        return _book_payout(stake, to_win, statuses, prices or [])
    n = len(statuses)
    active = [s for s in statuses if s in ("won", "lost")]
    k, hits = len(active), sum(s == "won" for s in active)
    if k == 0 or (k == 1 and n > 1):  # a multi-pick entry down to one pick is refunded
        return "refunded", stake
    if entry_type == "power":
        if hits < k:
            return "lost", 0.0
        mult = to_win / stake if k == n else bm.POWER_PAYOUTS.get(k, 0.0)
        return "won", round(stake * mult, 2)
    table = dict(bm.FLEX_PAYOUTS.get(k, {}))
    if k == n:
        table[n] = to_win / stake
    payout = round(stake * table.get(hits, 0.0), 2)
    status = "won" if payout > stake else "partial" if payout > 0 else "lost"
    return status, payout


def _book_payout(stake: float, to_win: float, statuses: List[str], prices: List[int]) -> tuple:
    """A sportsbook straight bet or parlay: any lost leg loses it; pushed and
    void legs drop out (all of them dropping out refunds the stake)."""
    if "lost" in statuses:
        return "lost", 0.0
    won = [p for s, p in zip(statuses, prices) if s == "won"]
    if not won:
        return "refunded", stake
    if len(won) == len(statuses):
        return "won", round(to_win, 2)
    payout = stake
    for p in won:
        payout *= decimal_odds(p)
    return "won", round(payout, 2)


def _book_ev(e: UserEntry) -> Optional[float]:
    """Expected return per $1 when logged, at the books' consensus chance
    (sportsbook bets only; None unless every leg was priced)."""
    if e.platform != "sportsbook" or e.est_hit_prob is None:
        return None
    return round(e.est_hit_prob * e.to_win / e.stake - 1, 4)


def _out(e: UserEntry) -> Dict[str, Any]:
    return {
        "id": e.id, "platform": e.platform or "prizepicks", "book": (e.legs[0].get("book") if e.legs else None),
        "est_ev": _book_ev(e), "entry_type": e.entry_type, "stake": e.stake, "to_win": e.to_win, "season": e.season,
        "week": e.week, "legs": e.legs, "est_hit_prob": e.est_hit_prob, "status": e.status, "payout": e.payout,
        "profit": None if e.payout is None else round(e.payout - e.stake, 2), "notes": e.notes,
        "engine_version": e.engine_version,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def create(user_id: int, data: Dict[str, Any], season: int, week: int, snapshots: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    book = {"book": data["book"]} if data.get("book") else {}
    legs = [{**leg, **book, "snapshot": snap, "status": "pending", "actual": None} for leg, snap in zip(data["legs"], snapshots)]
    probs = [(s or {}).get("books_prob") for s in snapshots]
    est = None
    if all(p is not None for p in probs):
        est = 1.0
        for p in probs:
            est *= p
    with SessionLocal() as db:
        e = UserEntry(user_id=user_id, platform=data.get("platform") or "prizepicks", entry_type=data["entry_type"], stake=data["stake"], to_win=data["to_win"],
                      season=season, week=int(data.get("week") or week), legs=legs,
                      est_hit_prob=round(est, 4) if est is not None else None, notes=data.get("notes"),
                      engine_version=bm.ENGINE_VERSION)
        db.add(e)
        db.commit()
        db.refresh(e)
        return _out(e)


def delete(user_id: int, entry_id: int) -> bool:
    with SessionLocal() as db:
        e = db.query(UserEntry).filter(UserEntry.id == entry_id, UserEntry.user_id == user_id).first()
        if not e:
            return False
        db.delete(e)
        db.commit()
        return True


def grade_legs(legs: List[Dict[str, Any]], stats: Dict[tuple, Dict[str, Any]], finals: Dict[tuple, Any],
               week_over: bool) -> List[Dict[str, Any]]:
    """Grade each pending pick whose game is final (or every pick once the
    week is over) from Sleeper's stats; returns new leg dicts. Shared with
    the app's own tracked tickets (tracked_entries.py)."""
    done_teams = {t for pair in finals for t in pair}
    by_name: Dict[str, List[tuple]] = {}
    for (name, team), row in stats.items():
        by_name.setdefault(name, []).append((team, row))
    out = [dict(leg) for leg in legs]
    for leg in out:
        if leg.get("status", "pending") != "pending":
            continue
        if leg["market"] in GAME_MARKETS:
            _grade_game_leg(leg, finals, week_over)
            continue
        candidates = by_name.get(normalize_name(leg["player"]), [])
        if leg.get("team"):
            candidates = [c for c in candidates if c[0] == leg["team"]] or candidates
        team = leg.get("team") or (candidates[0][0] if candidates else None)
        if not week_over and team not in done_teams:
            continue  # game not final yet
        row = candidates[0][1] if candidates else None
        actual = (float(sum(float(row.get(k) or 0.0) for k in MARKETS[leg["market"]][1]))
                  if row and row.get("gp") else None)
        leg["actual"], leg["status"] = actual, leg_outcome(leg["side"], leg["line"], actual)
    return out


def _grade_game_leg(leg: Dict[str, Any], finals: Dict[tuple, Any], week_over: bool) -> None:
    """Team-winner and game-total picks, from the final score of the game the
    leg's team played in; void once the week is over without a final."""
    team = leg.get("team") or leg["player"]
    final = next(((home, away, score) for (home, away), score in finals.items() if team in (home, away)), None)
    if final is None:
        if week_over:
            leg["actual"], leg["status"] = None, "void"
        return
    home, away, (home_score, away_score) = final
    mine, theirs = (home_score, away_score) if team == home else (away_score, home_score)
    if leg["market"] == "team_win":
        actual = 1.0 if mine > theirs else 0.0 if mine < theirs else 0.5
    elif leg["market"] == "team_spread":
        actual = float(mine - theirs)
    else:
        actual = float(home_score + away_score)
    leg["actual"], leg["status"] = actual, leg_outcome(leg["side"], leg["line"], actual)


async def grade_pending(user_id: int, current_season: int, current_week: Optional[int]) -> int:
    """Grade pending legs whose game is final (ESPN scoreboard), or every leg
    once the NFL week is over. Network failures leave entries pending."""
    from app.services.betting_tracking import _espn_finals, _sleeper_stats

    with SessionLocal() as db:
        pending = db.query(UserEntry).filter(UserEntry.user_id == user_id, UserEntry.status == "pending").all()
        graded = 0
        for e in pending:
            week_over = e.season < current_season or (current_week is not None and e.week < current_week)
            try:
                finals = await _espn_finals(e.season, e.week)
                stats = await _sleeper_stats(e.season, e.week)
            except Exception as err:  # noqa: BLE001 - try again next time
                logger.warning("Entry %s grading skipped: %s", e.id, type(err).__name__)
                continue
            legs = grade_legs(e.legs, stats, finals, week_over)
            e.legs = legs
            if all(leg["status"] != "pending" for leg in legs):
                e.status, e.payout = entry_payout(e.entry_type, e.stake, e.to_win, [leg["status"] for leg in legs],
                                                  [leg.get("price") for leg in legs])
                e.graded_at = datetime.now(timezone.utc)
                graded += 1
        db.commit()
    return graded


def summary(user_id: int) -> Dict[str, Any]:
    with SessionLocal() as db:
        entries = db.query(UserEntry).filter(UserEntry.user_id == user_id).order_by(UserEntry.created_at.desc()).all()
        rows = [_out(e) for e in entries]
    pp = [r for r in rows if r["platform"] == "prizepicks"]
    settled = [r for r in pp if r["status"] != "pending"]
    staked = sum(r["stake"] for r in settled)
    returned = sum(r["payout"] or 0.0 for r in settled)
    # Pick-level check (PrizePicks picks): what the books said vs what the
    # full model said vs what happened.
    legs = [l for r in pp for l in r["legs"] if l.get("status") in ("won", "lost") and l.get("snapshot")]

    def check(subset):
        if not subset:
            return None
        books = [l["snapshot"]["books_prob"] for l in subset if l["snapshot"].get("books_prob") is not None]
        model = [l["snapshot"]["model_prob"] for l in subset if l["snapshot"].get("model_prob") is not None]
        return {"picks": len(subset), "hit_rate": round(sum(l["status"] == "won" for l in subset) / len(subset), 4),
                "books_said": round(sum(books) / len(books), 4) if books else None,
                "model_said": round(sum(model) / len(model), 4) if model else None}

    disagree = [l for l in legs if l["snapshot"].get("projections_disagree")]
    return {
        "entries": rows,
        # PrizePicks only: the page tallies sportsbook bets apart, never mixed.
        "record": {"entries": len(pp), "settled": len(settled), "pending": len(pp) - len(settled),
                   "won": sum(r["status"] == "won" for r in settled), "lost": sum(r["status"] == "lost" for r in settled),
                   "staked": round(staked, 2), "returned": round(returned, 2), "profit": round(returned - staked, 2),
                   "roi": round((returned - staked) / staked, 4) if staked else None},
        "pick_check": {"all": check(legs), "projections_disagreed_with_books": check(disagree)},
        "markets": {k: v[0] for k, v in MARKETS.items()},
        "default_book": DEFAULT_BOOK,
    }
