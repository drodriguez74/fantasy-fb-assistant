"""Tests for Sleeper-sourced weekly projections (app.services.weekly_projections),
which give Yahoo leagues the per-player projection Yahoo's API lacks."""
from app.services.scoring_rules import default_scoring_rules
from app.services.this_week_service import _attach_yahoo_projections
from app.services.weekly_projections import attach_projections, normalize_name, score_projection


def _row(first, last, team, position, **stats):
    return {
        "player": {"first_name": first, "last_name": last, "position": position, "team": team},
        "team": team,
        "opponent": "OPP",
        "stats": stats,
    }


def test_normalize_name_strips_suffixes_and_punctuation():
    assert normalize_name("Aaron Jones Sr.") == "aaron jones"
    assert normalize_name("D'Andre Swift") == "dandre swift"
    assert normalize_name("Marvin Harrison Jr.") == normalize_name("marvin harrison")


def test_no_rules_returns_sleeper_standard_total():
    assert score_projection({"pts_std": 12.34}, None) == 12.34
    assert score_projection({}, None) is None


def test_canonical_rules_correct_from_sleeper_standard():
    # Sleeper standard is 4pt pass TD / -1 INT / 0 per reception; this
    # league plays 6pt pass TD, -3 INT, full PPR, +0.5 per completion.
    rules = default_scoring_rules("yahoo")
    rules["passing"].update({"td": 6.0, "interception": -3.0, "completion": 0.5})
    rules["receiving"]["reception"] = 1.0
    stats = {"pts_std": 20.0, "pass_td": 2.0, "pass_int": 1.0, "pass_cmp": 20.0, "rec": 3.0}
    # 20 + 2*(6-4) + 1*(-3 - -1) + 20*0.5 + 3*1 = 20 + 4 - 2 + 10 + 3
    assert score_projection(stats, rules) == 35.0


def test_incompletions_derived_from_attempts_minus_completions():
    rules = default_scoring_rules("yahoo")
    rules["passing"]["incompletion"] = -0.5
    stats = {"pts_std": 10.0, "pass_att": 30.0, "pass_cmp": 20.0}
    assert score_projection(stats, rules) == 5.0


def test_yahoo_extra_stats_like_first_downs_and_big_plays():
    stats = {"pts_std": 10.0, "pass_fd": 12.0, "pass_cmp_40p": 1.0, "rush_2pt": 0.5}
    # stat 79 passing 1st downs +1, 59 40+yd completions +4, 16 2-pt at 3 (Sleeper std 2)
    assert score_projection(stats, None, {79: 1.0, 59: 4.0, 16: 3.0}) == 10.0 + 12.0 + 4.0 + 0.5


def test_attach_matches_by_name_and_team_defense_by_team():
    rows = [
        _row("Aaron", "Jones", "MIN", "RB", pts_std=11.0),
        _row("Josh", "Allen", "BUF", "QB", pts_std=20.0),
        _row("Josh", "Allen", "JAX", "LB", pts_std=0.0),
        _row("Kansas City", "Chiefs", "KC", "DEF", pts_std=7.5),
    ]
    lineup = [
        {"name": "Aaron Jones Sr.", "team": "Min", "position": "RB", "projected_points": None, "pro_opponent": None},
        {"name": "Josh Allen", "team": "Buf", "position": "QB", "projected_points": None},
        {"name": "Chiefs", "team": "KC", "position": "DEF", "projected_points": None},
        {"name": "Nobody Here", "team": "SEA", "position": "WR", "projected_points": None},
    ]
    unmatched = attach_projections(lineup, rows, None)
    assert [p["projected_points"] for p in lineup] == [11.0, 20.0, 7.5, None]
    assert lineup[0]["pro_opponent"] == "OPP"
    assert unmatched == ["Nobody Here"]


def test_name_only_fallback_requires_a_unique_name():
    rows = [_row("Mike", "Williams", "NYJ", "WR", pts_std=5.0), _row("Mike", "Williams", "PIT", "WR", pts_std=9.0)]
    lineup = [{"name": "Mike Williams", "team": "FA", "position": "WR", "projected_points": None}]
    assert attach_projections(lineup, rows, None) == ["Mike Williams"]
    assert lineup[0]["projected_points"] is None


def test_yahoo_attach_zeroes_byes_and_skips_ir_in_unmatched():
    rows = [_row("Real", "Player", "DAL", "WR", pts_std=9.0)]
    lineup = [
        {"name": "Real Player", "team": "Dal", "position": "WR", "slot_position": "WR"},
        {"name": "On Bye", "team": "SEA", "position": "RB", "slot_position": "RB", "on_bye": True},
        {"name": "Injured Guy", "team": "SEA", "position": "RB", "slot_position": "IR"},
        {"name": "Unknown Bench", "team": "SEA", "position": "WR", "slot_position": "BN"},
    ]
    unmatched = _attach_yahoo_projections(lineup, rows, None, None)
    assert lineup[0]["projected_points"] == 9.0
    assert lineup[1]["projected_points"] == 0.0
    assert unmatched == ["Unknown Bench"]


def _rows_by_week(monkeypatch, weekly, season_rows=None):
    import asyncio
    from app.services import weekly_projections as wp

    async def fetch_week(season, week):
        return weekly.get(week, [])

    async def fetch_season(season):
        return season_rows or []

    monkeypatch.setattr(wp, "fetch_weekly_projections", fetch_week)
    monkeypatch.setattr(wp, "fetch_season_projections", fetch_season)
    return lambda *a: asyncio.run(wp.fetch_rest_of_season_projections(*a))


def test_rest_of_season_sums_remaining_weeks_so_byes_and_injuries_count(monkeypatch):
    healthy = lambda pts: dict(_row("Amon-Ra", "St. Brown", "DET", "WR", pts_std=pts, rec=5.0), player_id="1")
    hurt = dict(_row("Travis", "Etienne", "JAX", "RB", pts_std=10.0, rec=2.0), player_id="2")
    # Week 6 is St. Brown's bye (no row); Etienne is out until week 7.
    ros = _rows_by_week(monkeypatch, {5: [healthy(12.0)], 6: [hurt], 7: [healthy(14.0), hurt]})

    rows = {r["player_id"]: r for r in ros(2026, 5, 7)}

    assert rows["1"]["stats"] == {"pts_std": 26.0, "rec": 10.0}
    assert rows["2"]["stats"] == {"pts_std": 20.0, "rec": 4.0}
    assert rows["1"]["opponent"] is None  # a summed line has no single opponent
    lineup = [{"name": "Amon-Ra St. Brown", "team": "DET", "position": "WR"}]
    attach_projections(lineup, list(rows.values()), {"receiving": {"reception": 1.0}})
    assert lineup[0]["projected_points"] == 36.0


def test_rest_of_season_falls_back_to_season_feed_when_incomplete(monkeypatch):
    season_rows = [dict(_row("A", "B", "DET", "WR", pts_std=200.0), player_id="1")]
    ros = _rows_by_week(monkeypatch, {5: [dict(_row("A", "B", "DET", "WR", pts_std=12.0), player_id="1")]}, season_rows)

    assert ros(2026, 5, 6) == season_rows       # week 6 fetch came back empty
    assert ros(2026, None, None) == season_rows  # current week unknown
