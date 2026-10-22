"""Build this week's NFL board now, straight into the shared database.

    python scripts/build_board.py

Run from backend/ with the venv active. There's no scheduler on Render, so a
board is otherwise built only when someone opens the Bets page. On the
founder's Mac a launchd job (label com.fantasyfootball.board-close, plist in
scripts/launchd/) runs this at 12:00, 15:30 and 19:30 so each game's props get
their closing fetch in the 2h before kickoff (odds_service.PROP_CLOSE_LEAD)
and every pick gets a real closing line (betting_tracking.update_closing).
Outside those windows a build spends no prop credits: props are served from
odds_cache, game lines refetch at most every 12h.
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.services import betting_service, odds_service  # noqa: E402


def main() -> None:
    board = asyncio.run(betting_service.build_board(force=True))
    print(f"{datetime.now():%Y-%m-%d %H:%M} board built: available={board.get('available')} "
          f"props={len(board.get('player_props') or [])} recommended={board.get('recommended_count')} "
          f"credits left={odds_service.credits_remaining()}")


if __name__ == "__main__":
    main()
