"""Tests for league_value_model: lineup-impact valuation behind waiver and
trade advice."""
from app.services import league_value_model as m

STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1}


def P(name, pos, season, week=None, **kw):
    return {"id": name, "name": name, "position": pos, "season": season,
            "week": season / 17 if week is None else week, **kw}


def roster():
    return [
        P("QB1", "QB", 300), P("RB1", "RB", 250), P("RB2", "RB", 180), P("RB3", "RB", 120),
        P("WR1", "WR", 260), P("WR2", "WR", 200), P("WR3", "WR", 150), P("TE1", "TE", 110),
        P("K1", "K", 120), P("DEF1", "D/ST", 100), P("BenchWR", "WR", 90),
    ]


class TestBestLineup:
    def test_fills_dedicated_slots_then_flex(self):
        total, chosen = m.best_lineup(roster(), STARTERS)
        names = {p["name"] for p in chosen}
        # FLEX goes to the best leftover RB/WR/TE: WR3 (150) over RB3 (120).
        assert names == {"QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1", "K1", "DEF1"}
        assert total == 300 + 250 + 180 + 260 + 200 + 150 + 110 + 120 + 100

    def test_ir_slot_and_long_term_status_excluded(self):
        r = roster() + [P("Star", "WR", 400, slot="IR"), P("Susp", "RB", 400, injury_status="SUS")]
        _, chosen = m.best_lineup(r, STARTERS)
        assert not {"Star", "Susp"} & {p["name"] for p in chosen}

    def test_out_this_week_only_affects_week_horizon(self):
        r = roster() + [P("Hurt", "WR", 400, week=25, injury_status="O")]
        assert "Hurt" in {p["name"] for p in m.best_lineup(r, STARTERS, "season")[1]}
        assert "Hurt" not in {p["name"] for p in m.best_lineup(r, STARTERS, "week")[1]}


class TestWaivers:
    def test_ranks_by_lineup_gain_not_raw_points(self):
        fas = [
            P("Big QB", "QB", 290),         # most raw points, but a backup QB: no lineup gain
            P("Good TE", "TE", 170),         # +60 over TE1
            P("OK WR", "WR", 160),           # +10 over WR3 in FLEX
        ]
        recs = m.waiver_targets(roster(), fas, STARTERS, m.replacement_levels(fas))
        assert [r["player"]["name"] for r in recs] == ["Good TE", "OK WR"]
        assert recs[0]["kind"] == "upgrade"
        assert recs[0]["season_gain"] > recs[1]["season_gain"]

    def test_drops_the_least_valuable_player_not_a_starter(self):
        recs = m.waiver_targets(roster(), [P("Good TE", "TE", 170)], STARTERS, {})
        # Dropping TE1 (now benched) or the deep-bench WR are the candidates;
        # never a starter at another position.
        assert recs[0]["drop"]["name"] in {"TE1", "BenchWR"}
        assert recs[0]["replaces"][0]["name"] == "TE1"

    def test_streamer_when_only_this_week_helps(self):
        r = roster()
        r[-2] = P("DEF1", "DEF", 100, week=0.0)  # my defense is on bye
        fa = P("Stream DEF", "DEF", 95, week=8.0)
        recs = m.waiver_targets(r, [fa], STARTERS, {})
        assert recs[0]["kind"] == "streamer"
        assert recs[0]["week_gain"] >= m.MIN_WEEK_GAIN

    def test_injured_free_agents_skipped(self):
        recs = m.waiver_targets(roster(), [P("Hurt TE", "TE", 200, injury_status="IR")], STARTERS, {})
        assert recs == []

    def test_watch_list_when_nothing_clears_the_bar(self):
        fas = [P("Meh TE", "TE", 112), P("Meh WR", "WR", 95)]
        levels = m.replacement_levels(fas)
        assert m.waiver_targets(roster(), fas, STARTERS, levels) == []
        needs = m.team_needs(roster(), [{"team_id": "1", "players": roster()}], STARTERS)
        watch = m.watch_list(roster(), fas, STARTERS, [n for n in needs if n["position"] == "TE"], levels)
        assert watch[0]["kind"] == "watch" and watch[0]["player"]["name"] == "Meh TE"


class TestTrades:
    def teams(self, their_players):
        return [
            {"team_id": "1", "team_name": "Me", "players": roster()},
            {"team_id": "2", "team_name": "Them", "players": their_players},
        ]

    def test_surplus_for_need_improves_both_lineups(self):
        # They're thin at WR and deep at TE; I'm the reverse.
        theirs = [
            P("TQB", "QB", 280), P("TRB1", "RB", 150), P("TRB2", "RB", 140), P("TWR1", "WR", 220),
            P("TWR2", "WR", 80), P("TTE1", "TE", 190), P("TTE2", "TE", 170), P("TK", "K", 120), P("TDEF", "DEF", 100),
        ]
        levels = {"QB": 250, "RB": 110, "WR": 120, "TE": 100, "K": 115, "DEF": 95}
        picks = m.trade_targets("1", self.teams(theirs), STARTERS, levels)
        assert picks, "expected a mutually beneficial deal"
        top = picks[0]
        assert m.normalize_position(top["receive"]["position"]) == "TE"
        assert top["my_gain"] >= m.MIN_SEASON_GAIN
        assert top["their_gain"] >= max(m.MIN_THEIR_GAIN, m.ACCEPTANCE_RATIO * top["my_gain"])

    def test_never_trade_for_what_waivers_offer(self):
        # Their kicker is barely better than the best free-agent kicker.
        theirs = [P("TK", "K", 140), P("TWR", "WR", 50)]
        levels = {"K": 138}
        picks = m.trade_targets("1", self.teams(theirs), STARTERS, levels)
        assert all(m.normalize_position(p["receive"]["position"]) != "K" for p in picks)

    def test_one_sided_deals_are_not_suggested(self):
        # Their star would help me, but nothing I have helps them enough.
        theirs = [P("Star WR", "WR", 330), P("TWR2", "WR", 300), P("TWR3", "WR", 290), P("TRB1", "RB", 300),
                  P("TRB2", "RB", 290), P("TTE", "TE", 250), P("TQB", "QB", 350), P("TK", "K", 150), P("TDEF", "DEF", 150)]
        picks = m.trade_targets("1", self.teams(theirs), STARTERS, {})
        assert all(p["their_gain"] >= m.MIN_THEIR_GAIN for p in picks)

    def test_unavailable_players_never_requested(self):
        theirs = [P("IR Star", "TE", 300, slot="IR"), P("TWR", "WR", 50), P("TTE", "TE", 60)]
        picks = m.trade_targets("1", self.teams(theirs), STARTERS, {})
        assert all(p["receive"]["name"] != "IR Star" for p in picks)


def test_depth_counts_only_above_replacement():
    levels = {"WR": 90}
    base = m.best_lineup(roster(), STARTERS)[0]
    # BenchWR (90) is replacement-level -> no depth value; RB3 (120) is 120
    # over an unknown (0) RB replacement -> 20% of it.
    assert m.team_value(roster(), STARTERS, levels) == round(base + 0.2 * 120, 2)
