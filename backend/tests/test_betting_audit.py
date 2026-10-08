"""Audit trail: engine version on tracked rows, suggested-ticket tracking and
grading, and the weekly audit rows / CSV (pure functions; no network, no DB)."""
import csv
import io
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from app.services import betting_audit as audit
from app.services import betting_model as bm
from app.services import tracked_entries as te
from app.services.betting_tracking import _row_values
from app.services.user_entries import grade_legs


def _leg(player, team, market="player_rush_yds", side="More", line=30.5, p=0.6, odds_type="standard"):
    return {"player": player, "team": team, "game": "BUF @ KC", "market": market, "side": side, "line": line,
            "p_win": p, "odds_type": odds_type}


def test_engine_version_stamped_on_new_rows():
    prop = {"type": "player_prop", "player": "A", "team": "KC", "game": "BUF @ KC", "market": "player_rush_yds",
            "side": "Over", "line": 30.5, "book": "DraftKings", "price": -110, "units": 1.0, "confidence": "lean",
            "ev": 0.04, "p_win": 0.55}
    assert _row_values(2026, 5, prop)["engine_version"] == bm.ENGINE_VERSION
    pp = {"type": "pp_leg", "player": "A", "market": "player_rush_yds", "side": "More", "line": 4.5, "p_win": 0.8}
    assert _row_values(2026, 5, pp)["engine_version"] == bm.ENGINE_VERSION


def test_ticket_signature_dedupes_same_picks_in_any_order():
    a, b = _leg("A", "KC"), _leg("B", "BUF")
    assert te.ticket("pair", "power", [a, b], 0.36, 0.08, {2: 3.0})["signature"] == \
        te.ticket("pair", "power", [b, a], 0.36, 0.08, {2: 3.0})["signature"]
    assert te.ticket("pair", "power", [a, b], 0.36, 0.08, {2: 3.0})["signature"] != \
        te.ticket("pair", "power", [a, {**b, "line": 31.5}], 0.36, 0.08, {2: 3.0})["signature"]
    gob = te.ticket("safest_pair", "power", [a, _leg("C", "SF", odds_type="goblin")], 0.6, 0.2, {2: 3.0})
    assert gob["has_specials"] and gob["payouts"] is None and gob["ev"] is None  # goblin payouts unknown


def test_tickets_from_board_and_entries():
    pp = {"pairs": [{"legs": [_leg(f"P{i}", "KC"), _leg(f"Q{i}", "BUF")], "joint_prob": 0.35, "ev": 0.05 - i / 100}
                    for i in range(8)]}
    ml = {"picks": [_leg("X", "KC", p=0.8, odds_type="goblin"), _leg("Y", "SF", p=0.79, odds_type="goblin")],
          "safest_pair": {"legs": ["X", "Y"], "p_both": 0.63}}
    tickets = te.tickets_from_board(pp, ml)
    assert [t["source"] for t in tickets].count("pair") == te.TOP_PAIRS
    assert tickets[-1]["source"] == "safest_pair" and tickets[-1]["has_specials"]
    entries = [{"type": "power", "size": 3, "ev": 0.1, "p_all": 0.2, "payouts": {3: 6.0}, "legs": [_leg("A", "KC")] * 3},
               {"type": "power", "size": 3, "ev": 0.05, "p_all": 0.2, "payouts": {3: 6.0}, "legs": [_leg("B", "KC")] * 3},
               {"type": "flex", "size": 3, "ev": 0.02, "p_all": 0.2, "payouts": {3: 3.0, 2: 1.0}, "legs": [_leg("C", "KC")] * 3}]
    kept = te.tickets_from_entries(entries)
    assert len(kept) == 2 and kept[0]["ev"] == 0.1  # best per (type, size)


def test_ticket_grading_rules():
    assert te.outcome("power", 2, {"2": 3.0}, ["won", "won"]) == ("won", 3.0)
    assert te.outcome("power", 2, {"2": 3.0}, ["won", "lost"]) == ("lost", 0.0)
    assert te.outcome("power", 3, {"3": 6.0}, ["won", "won", "void"]) == ("won", 3.0)  # DNP: pays as a 2-pick
    assert te.outcome("power", 2, None, ["won", "won"]) == ("won", None)                # goblins: hit/miss only
    assert te.outcome("power", 2, None, ["won", "push"]) == ("refunded", None)
    stats = {("a", "KC"): {"gp": 1, "rush_yd": 40}, ("b", "BUF"): {"gp": 1, "rush_yd": 10}}
    finals = {("KC", "BUF"): (24, 20)}
    legs = grade_legs([_leg("A", "KC"), _leg("B", "BUF")], stats, finals, week_over=False)
    assert [l["status"] for l in legs] == ["won", "lost"] and legs[0]["actual"] == 40.0


def test_audit_rows_summary_and_csv():
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    bet = NS(kind="player_prop", subject="A", game="BUF @ KC", market="player_rush_yds", side="Over", line=30.5,
             book="DraftKings", price=-110, p_win=0.56, market_prob=0.52, model_prob=0.6, units=1.0, confidence="lean",
             engine_version=bm.ENGINE_VERSION, status="won", actual=40.0, profit_units=0.909, kickoff=now, graded_at=now)
    fill = NS(**{**vars(bet), "subject": "B", "confidence": "fill", "units": 0.5, "status": "lost", "profit_units": -0.5})
    likely = NS(**{**vars(bet), "kind": "pp_leg", "subject": "C", "side": "Over", "price": 0, "units": 0.0,
                   "confidence": "likely", "p_win": 0.8, "engine_version": None})
    ticket = NS(source="pair", size=2, entry_type="power", legs=[{**_leg("A", "KC"), "status": "won"},
                                                                  {**_leg("B", "BUF"), "status": "lost"}],
                has_specials=False, p_all=0.35, engine_version=bm.ENGINE_VERSION, status="lost", payout_mult=0.0,
                graded_at=now)
    rows = [audit.pick_row(bet), audit.pick_row(fill), audit.pick_row(likely), audit.ticket_row(ticket)]
    assert [r["section"] for r in rows] == ["Bets", "Best available", "Most likely to win", "Suggested tickets"]
    assert rows[2]["side"] == "More" and rows[2]["engine_version"] == "pre-versioning" and rows[2]["profit"] is None
    assert rows[3]["actual"] == "1/2 hit" and rows[3]["profit"] == -1.0
    s = audit.section_summary(rows)
    assert s["Bets"]["hit_rate"] == 1.0 and s["Best available"]["hit_rate"] == 0.0 and s["Bets"]["predicted"] == 0.56
    parsed = list(csv.DictReader(io.StringIO(audit.to_csv(rows))))
    assert list(parsed[0].keys()) == list(audit.COLUMNS) and len(parsed) == 4 and parsed[0]["status"] == "won"


def test_watch_list_is_tracked_as_its_own_section():
    from types import SimpleNamespace
    from app.services.betting_audit import _section
    from app.services.betting_tracking import _row_values
    row = {"type": "player_prop", "player": "A", "game": "B @ C", "market": "player_rush_yds", "side": "Over",
           "line": 40.5, "book": "DraftKings", "price": -110, "units": 0.0, "confidence": "none", "ev": 0.02,
           "p_win": 0.535, "watch": True}
    v = _row_values(2026, 5, row)
    assert v["confidence"] == "watch" and not v["recommended"] and v["units"] == 0.0
    assert _row_values(2026, 5, {**row, "watch": False})["confidence"] == "none"
    assert _section(SimpleNamespace(kind="player_prop", confidence="watch")) == "Watch list"
