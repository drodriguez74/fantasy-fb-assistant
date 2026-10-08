"""Watch-list alerts: saved from a board row, fired when the pick becomes a real bet (SQLite, no network)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification
from app.models.watch_alert import WatchAlert
from app.services import watch_alerts as wa


@pytest.fixture
def db(test_engine, monkeypatch):
    Session = sessionmaker(bind=test_engine)
    monkeypatch.setattr(wa, "SessionLocal", Session)
    yield Session
    with Session() as s:
        s.query(WatchAlert).delete()
        s.query(Notification).filter(Notification.type == "bet_alert").delete()
        s.commit()


KICKOFF = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def row(units=0.0, price=-110, line=40.5, **kw):
    return {"type": "player_prop", "player": "A Back", "game": "X @ Y", "market": "player_rush_yds",
            "market_label": "Rushing yards", "side": "Over", "line": line, "book": "FanDuel", "price": price,
            "units": units, "p_win": 0.545, "p_push": 0.0, "ev": 0.04 if units else 0.02, "kickoff": KICKOFF,
            "watch": not units, "bet_at": 104 if not units else None, **kw}


def test_alert_fires_once_when_the_pick_becomes_a_bet(db):
    a = wa.create(7, 2026, 5, row())
    assert a["status"] == "active" and a["target_price"] == 104
    assert wa.check([row()], 2026, 5) == 0                     # still only a watch
    assert wa.check([row(units=1.0, price=110, line=39.5)], 2026, 5) == 1
    with db() as s:
        alert = s.query(WatchAlert).one()
        note = s.query(Notification).filter(Notification.type == "bet_alert").one()
    assert alert.status == "triggered" and alert.triggered_price == 110 and alert.triggered_units == 1.0
    assert note.user_id == 7 and "A Back" in note.title and "line moved from 40.5" in note.body
    assert wa.check([row(units=1.0, price=110)], 2026, 5) == 0  # never twice


def test_fill_is_not_a_bet_and_kickoff_expires(db):
    wa.create(7, 2026, 5, row())
    assert wa.check([row(units=0.5, card_fill=True)], 2026, 5) == 0   # "Best available" doesn't count
    past = datetime.now(timezone.utc) + timedelta(days=3)
    assert wa.check([row(units=1.0)], 2026, 5, now=past) == 0
    with db() as s:
        assert s.query(WatchAlert).one().status == "expired"


def test_cannot_alert_on_an_existing_bet(db):
    with pytest.raises(wa.AlertError):
        wa.create(7, 2026, 5, row(units=1.0))
