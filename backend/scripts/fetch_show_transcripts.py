"""Save new NFL and college picks-show transcripts from VSiN's YouTube channel.

    python scripts/fetch_show_transcripts.py             # newest 10 uploads
    python scripts/fetch_show_transcripts.py --limit 80  # look further back

Run from backend/ with requirements-scripts.txt installed. Only titles that
look like an NFL or college picks show are kept (Prop Points, Beating the
Book, Fezzik's best bets, the college picks compilation); tennis, UFC, MLB,
survivor and opening-line videos are skipped. Each transcript is written to
transcripts/ (gitignored) as <upload date>-vsin-<nfl|cfb>-<slug>-<video id>.txt;
a video already saved is skipped, and one whose captions aren't up yet is
retried on the next run. Picks are still extracted by hand into JSON and
loaded with import_analyst_picks.py.

Feeds the Shows tab on the Bets page (analyst_picks.py). On the founder's Mac
it runs three times a day from a launchd job, label
com.fantasyfootball.show-transcripts (scripts/launchd/ has the plist with
install/remove steps; log at ~/Library/Logs/show-transcripts.log).
"""
import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi

CHANNEL = "https://www.youtube.com/@VSiNLive/videos"
OUT_DIR = Path(__file__).resolve().parents[1] / "transcripts"
# A picks show names its sport (Prop Points titles only say "Prop Betting
# Expert") and says it has picks.
SPORT = re.compile(r"\b(NFL|College Football|CFB)\b|Prop Betting Expert", re.I)
COLLEGE = re.compile(r"\b(College Football|CFB)\b", re.I)
PICKS = re.compile(r"Best Bets|Expert Picks|Props That|Bets for Week|Fezzik", re.I)
PAUSE = 3  # seconds between videos; YouTube answers bursts with 429s


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M} {msg}", flush=True)


def is_picks_show(title: str) -> bool:
    return bool(SPORT.search(title) and PICKS.search(title))


def slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", "", title.lower().replace("vs", "")).split()
    return "-".join(words[:6])


def saved_ids() -> set:
    ids = set()
    for p in OUT_DIR.glob("*.txt"):
        ids.update(re.findall(r"watch\?v=([\w-]{11})", p.read_text(errors="ignore")[:500]))
    return ids


def recent_uploads(limit: int) -> list:
    opts = {"extract_flat": True, "playlistend": limit, "quiet": True, "no_warnings": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL, download=False)
    return [(e["id"], e.get("title") or "") for e in info.get("entries") or []]


def upload_date(video_id: str) -> str:
    with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    d = info.get("upload_date") or datetime.now().strftime("%Y%m%d")
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def save(video_id: str, title: str) -> Path:
    lines = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    day = upload_date(video_id)
    sport = "cfb" if COLLEGE.search(title) else "nfl"
    path = OUT_DIR / f"{day}-vsin-{sport}-{slug(title)}-{video_id}.txt"
    body = "\n".join(f"[{int(s.start) // 60}:{int(s.start) % 60:02d}] {s.text}" for s in lines)
    path.write_text(
        f"# {title}\n# VSiN | {day} | {sport}\n# https://www.youtube.com/watch?v={video_id}\n\n{body}\n"
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=10, help="how many of the newest uploads to check")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    have = saved_ids()
    new = [(vid, t) for vid, t in recent_uploads(args.limit) if is_picks_show(t) and vid not in have]
    log(f"{len(new)} new picks show(s) to fetch")
    failed = 0
    for vid, title in new:
        try:
            log(f"saved {save(vid, title).name}")
        except Exception as e:  # captions not up yet, rate limit, ...: retry next run
            failed += 1
            log(f"skipped {vid} ({title}): {type(e).__name__}: {str(e).splitlines()[0][:160]}")
        time.sleep(PAUSE)
    return 1 if failed and failed == len(new) else 0


if __name__ == "__main__":
    sys.exit(main())
