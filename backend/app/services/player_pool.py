"""Small, generic helpers for working with Sleeper's player dataset.

Extracted from the removed draft endpoint; `trade.py` and any future
player-pool code share these.
"""

# Sleeper uses 9999999 as a sentinel for "unranked" players; treat a missing
# search_rank the same way so unranked players sort to the bottom, not the top.
UNRANKED_SENTINEL = 9999999


def is_on_active_roster(player_data: dict) -> bool:
    """Whether a Sleeper player record represents someone currently rosterable
    (i.e. not retired / free agent / unaffiliated).

    Sleeper's `status` field alone is unreliable: long-retired players (e.g.
    Frank Gore, Adrian Peterson) are still tagged `status: "Active"`. The
    reliable signal is that they also have `team: null` once they're off an
    NFL roster, so require both a real team and an active status.
    """
    return bool(player_data.get("team")) and player_data.get("status") == "Active"
