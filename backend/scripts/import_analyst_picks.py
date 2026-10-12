"""Load a show's picks (radio/podcast) into analyst_picks.

    python scripts/import_analyst_picks.py transcripts/2026-10-08-ffm.json

Run from backend/. The JSON shape is in app/services/analyst_picks.py. Each
pick is snapshotted against the saved NFL board (odds_cache "board:nfl")
when it's for the same week; picks already imported are skipped. A file
that names its "transcript" (a file in transcripts/) is recorded in the
import tracker (transcript_status.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services import analyst_picks  # noqa: E402
import transcript_status  # noqa: E402  (same folder)


def main() -> None:
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text())
        result = analyst_picks.import_show(data)
        print(f"{data['source']} ({data['aired_on']}): {result['added']} added, {result['skipped']} already there")
        if data.get("transcript"):
            transcript_status.record(data["transcript"], "imported", picks_file=Path(path).name,
                                     added=result["added"], already_there=result["skipped"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main()
