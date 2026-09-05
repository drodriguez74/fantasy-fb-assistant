"""Regression test for a real, production-observed bug: espn_api's
`Settings.position_slot_counts` mis-labels lineup slots whenever a league's
active ESPN slot IDs aren't contiguous from zero (true for essentially every
real league), silently binding position labels like "TE" to the wrong count
(e.g. the bench count). See `ESPNFantasyServiceEnhanced._real_position_slot_counts`
docstring for the full root-cause writeup.
"""

from app.services.espn_service_enhanced import ESPNFantasyServiceEnhanced


class _FakeEspnRequest:
    def __init__(self, raw):
        self._raw = raw

    def get_league(self):
        return self._raw


class _FakeSettings:
    # Simulates espn_api's broken positional zip: with these 9 slots present,
    # espn_api's own (buggy) code would bind "TE" to whatever count sits at
    # label-index 6 -- in this fixture, that's the real bench count (6), not
    # the real TE count (1). Used only as the last-resort fallback.
    position_slot_counts = {"QB": 1, "TQB": 2, "RB": 2, "RB/WR": 1, "WR": 1, "WR/TE": 1, "TE": 6, "OP": 1, "DT": 1}


class _FakeLeague:
    def __init__(self, raw):
        self.espn_request = _FakeEspnRequest(raw)
        self.settings = _FakeSettings()


def _raw_league_settings(lineup_slot_counts):
    return {"settings": {"rosterSettings": {"lineupSlotCounts": lineup_slot_counts}}}


def test_real_position_slot_counts_maps_by_real_slot_id_not_position():
    # A real 12-team PPR league: QB1 RB2 WR2 TE1 FLEX1 D/ST1 K1 BE6 IR1,
    # with ESPN's real slot IDs as string keys (0=QB, 2=RB, 4=WR, 6=TE,
    # 16=D/ST, 17=K, 20=BE, 21=IR, 23=FLEX). No slot IDs 1, 3, 5, 7-15, 18-19,
    # 22, 24-25 are present -- exactly the non-contiguous case that corrupts
    # espn_api's own positional-zip logic.
    raw = _raw_league_settings(
        {"0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "16": 1, "17": 1, "20": 6, "21": 1}
    )
    league = _FakeLeague(raw)

    svc = ESPNFantasyServiceEnhanced()
    result = svc._real_position_slot_counts(league)

    assert result["TE"] == 1
    assert result["RB"] == 2
    assert result["WR"] == 2
    assert result["QB"] == 1
    assert result["BE"] == 6
    assert result["D/ST"] == 1
    assert result["K"] == 1
    assert result["IR"] == 1
    assert result["RB/WR/TE"] == 1  # FLEX


def test_real_position_slot_counts_falls_back_when_raw_fetch_fails():
    class _BrokenRequest:
        def get_league(self):
            raise RuntimeError("network error")

    class _League:
        espn_request = _BrokenRequest()
        settings = _FakeSettings()

    svc = ESPNFantasyServiceEnhanced()
    result = svc._real_position_slot_counts(_League())

    # Falls back to the (possibly wrong) espn_api attribute rather than
    # raising -- callers already treat missing/odd starters data as
    # "use the standard-lineup fallback", so degrading here is safe.
    assert result == _FakeSettings.position_slot_counts
