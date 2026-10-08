"""Closing-line value: the latest market for each pick's own side until kickoff (SQLite, no network)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as P

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.bet_pick import BetPick
from app.services import betting_tracking as bt


def test_beat_close_rules():
    assert bt.beat_close(P(side="Over", line=40.5, close_line=40.5, market_prob=0.50, close_market_prob=0.54))
    assert bt.beat_close(P(side="Over", line=40.5, close_line=40.5, market_prob=0.50, close_market_prob=0.46)) is False
    assert bt.beat_close(P(side="Over", line=40.5, close_line=40.5, market_prob=0.50, close_market_prob=0.501)) is None
    assert bt.beat_close(P(side="Under", line=40.5, close_line=38.5, market_prob=0.5, close_market_prob=0.5))
    assert bt.beat_close(P(side="Over", line=40.5, close_line=42.5, market_prob=0.5, close_market_prob=0.5))
    assert bt.beat_close(P(side="KC", line=3.5, close_line=2.5, market_prob=0.5, close_market_prob=0.5))  # we got +3.5


@pytest.fixture
def db(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(bt, "SessionLocal", Session)
    yield Session
    with Session() as s:
        s.query(BetPick).filter(BetPick.season == 2099).delete()
        s.commit()


def test_update_closing_tracks_our_side_even_when_the_board_flips(db):
    kickoff = datetime.now(timezone.utc) + timedelta(days=1)
    with db() as s:
        s.add(BetPick(season=2099, week=5, kind="player_prop", subject="A", team="KC", game="X @ Y", market="player_rush_yds",
                      side="Over", line=40.5, book="FanDuel", price=-110, units=1.0, confidence="lean", recommended=True,
                      ev=0.04, p_win=0.55, p_push=0.0, market_prob=0.50, kickoff=kickoff, status="pending"))
        s.commit()
    # The market moved against us: the board's best side is now the Under at 40.5 (books 56% Under).
    row = {"type": "player_prop", "player": "A", "game": "X @ Y", "market": "player_rush_yds", "side": "Under",
           "line": 40.5, "price": -120, "book": "DraftKings", "market_prob": 0.56, "p_push": 0.0}
    assert bt.update_closing(2099, 5, [row]) == 1
    with db() as s:
        p = s.query(BetPick).filter(BetPick.season == 2099).one()
        assert p.close_line == 40.5 and abs(p.close_market_prob - 0.44) < 1e-6 and p.close_price is None
        assert bt.beat_close(p) is False
    # After kickoff nothing changes.
    assert bt.update_closing(2099, 5, [row], now=kickoff + timedelta(minutes=1)) == 0
