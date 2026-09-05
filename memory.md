# Memory

_Cross-session context that isn't project convention (that's CLAUDE.md's job) — deferred product decisions, founder calls, and gotchas that would otherwise get re-litigated or re-discovered every session. Read via `/orient` alongside `current-state.md`. This is a project-local, git-tracked complement to the global auto-memory at `~/.claude/projects/-Users-darwinrodriguez-projects-fantasy-football-assistant/memory/` — check that too; it may have grown items since this file was last updated._

## Product scope decisions (founder-made, don't re-litigate)

- **Keeper/dynasty leagues: explicitly out of scope.** Founder's words: "i don't care about keeper or dynasty leagues on traditional fantasy ppr ot standard." Product is scoped to traditional redraft PPR/Standard. An agent that had started on keeper-league MVP was stopped mid-read, no code written.
- **Push alerts: in-app notification center only, not real device push.** True browser/device push (service workers, VAPID keys) was judged too large a first slice for an app with zero existing notification infra. Device push stays explicit future scope. In-app notification center (`notification_service.py`, `Notification` model, navbar bell) is the real MVP and is already built/shipped.
- **ESPN/Sleeper comprehensive league analysis: deferred, not forgotten.** Only Yahoo has a real `get_comprehensive_league_analysis` implementation; ESPN/Sleeper honestly return "not implemented" rather than fake data. The founder's own league is ESPN, so this gap is felt directly — deferred anyway, by choice, not oversight.
- **Yahoo/Sleeper roster grading: deferred until connections are testable.** Real grading engine (`grading.py`/`roster_grading.py`) is built and shipped for ESPN only. Wiring Yahoo/Sleeper waits until those platform connections can actually be tested end-to-end, not a code-complexity blocker.
- **Gemini as a 3rd AI provider fallback tier**: asked about, deferred. `ai_service.py::_generate_with_fallback` currently has OpenAI↔Anthropic only.

## Known-broken, confirmed via live testing (not "untested" — actually verified broken)

- **ESPN live draft data feed is confirmed broken**, verified 2026-08-23 against a real in-progress ESPN draft (round 15/16). Neither the legacy `espn_api`/`fantasy.espn.com` REST path nor ESPN's own modern `lm-api-reads.fantasy.espn.com` `mDraftDetail` view (fetched from inside an authenticated browser session on ESPN's live draft page) ever reflects real picks — both report 0 drafted players throughout a real draft that progressed 190+ picks. `espn_api`'s `_fetch_draft()` has an early-return (`if not draftDetail.drafted: return`) that discards in-progress data. Researched same day: no documented REST/WS fix exists anywhere; every real competitor (FantasyPros, Draft Sharks, Subvertadown, Pick Pulse) solves this via a **browser extension reading the ESPN draft page's DOM**, not a backend API call. That's the real fix — not yet built. Manual "Mark gone" mitigation is shipped and is the current state of the art for this feature.
- **Sleeper's live-pick feed is architecturally sound** (real, public, non-cached endpoint) — don't lump it in with the ESPN problem above.
- **Yahoo's live-pick feed has no caching bug, but whether Yahoo exposes in-progress (vs. only post-completion) picks is unverified.** Don't assume it's fine by default — verify against a real in-progress Yahoo draft before trusting it, same rigor as was applied to ESPN.

## Standing capabilities (must keep working, not one-off asks)

- **Updating ESPN draft rankings from a spreadsheet is a permanent, expected capability**, not a one-time favor. `backend/scripts/update_espn_draft_rankings.py` is the maintained tool for this — see `handoff.md`'s "How to update ESPN draft rankings" for the exact procedure. It works by resolving spreadsheet players to ESPN's real playerIds (via the app's existing ESPN connection) and POSTing directly to ESPN's private write endpoint, the same one ESPN's own "Save Rankings" button uses (there's no bulk-import in ESPN's own UI). Used successfully 5+ times across evolving rankings sheets as of 2026-09-04. If ESPN's frontend build changes and the hardcoded `--platform-version` hash goes stale, refreshing it (procedure in the script's docstring) is a priority fix, not a "someday."

## Environment / infra decisions

- **App is not deployed.** Running locally against a real Supabase Postgres for persistence (not a local throwaway DB) — treat data in it as real, not disposable.
- **`docker-compose.yml` is stale** — don't use it, don't "fix" it as a side effect of unrelated work without checking with the user first (it may just need deleting rather than maintaining, but that's the user's call).
- **No Celery/Redis** — deliberately removed after an audit found the scheduled tasks were either dead-pipeline calls or never persisted results. The in-app notification center is populated synchronously as a side effect of real requests, not on a schedule. Don't reintroduce a background-task system without checking this reasoning first (git history has the full removal rationale).

## Working-style notes for this repo

- Every UX/audit fix in this project's history has been verified against the running app or a real failing test — "code compiles" / "tsc passes" is not treated as done. Keep that bar for new work here.
- Docs (`AUTHENTICATION_GUIDE.md`, `API_GUIDE.md`, etc.) get periodically re-verified against real code; a doc being "re-verified as of the last pass" (per CLAUDE.md) is not a guarantee it's still current — re-check anything load-bearing.
