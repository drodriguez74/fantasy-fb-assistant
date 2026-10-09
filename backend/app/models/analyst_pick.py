from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class AnalystPick(Base):
    """A pick made on a radio show or podcast ("Shows" on the Bets page),
    extracted from a transcript the founder supplies and graded like My
    entries (user_entries.grade_legs). Tracked, never priced: a show only
    earns weight in the model through a held-out test on its graded record
    (analyst_picks.py).

    College picks (sport "cfb") use the full team names the college board
    uses ("UCLA Bruins"); they're graded from ESPN's college scoreboard.

    Picks use the My entries leg shape: player (or the team for a spread,
    or the game "TB @ DAL" for a total, with team = home team), market,
    side More|Less, line. DAL -8.5 is team_spread More 8.5; LV +3.5 is
    team_spread More -3.5.
    """

    __tablename__ = "analyst_picks"
    __table_args__ = (
        UniqueConstraint("source", "aired_on", "analyst", "player", "market", "side", "line", name="uq_analyst_pick"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False, index=True)        # the show, e.g. "Fantasy Football Morning"
    network = Column(String, nullable=True)                    # e.g. "SiriusXM Fantasy Sports Radio"
    analyst = Column(String, nullable=False)
    segment = Column(String, nullable=True)                    # e.g. "Best bets", "Dog of the week"
    sport = Column(String, nullable=False, default="nfl", index=True)  # nfl | cfb
    aired_on = Column(Date, nullable=False)
    season = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False, index=True)
    player = Column(String, nullable=False)
    team = Column(String, nullable=True)
    game = Column(String, nullable=True)
    kickoff = Column(DateTime(timezone=True), nullable=True)  # from the board; college grading looks up finals by date
    market = Column(String, nullable=False)
    side = Column(String, nullable=False)                      # More | Less
    line = Column(Float, nullable=False)
    line_stated = Column(Boolean, nullable=False, default=True)  # False: the analyst gave no number; the board's line is used
    price = Column(Integer, nullable=True)                     # American odds if stated
    conviction = Column(String, nullable=False, default="bet")  # bet | lean
    quote = Column(Text, nullable=True)
    snapshot = Column(JSON, nullable=True)                     # what our board said when imported
    status = Column(String, nullable=False, default="pending", index=True)  # pending|won|lost|push|void
    actual = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    graded_at = Column(DateTime(timezone=True), nullable=True)
