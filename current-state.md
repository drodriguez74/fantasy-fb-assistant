# Current State

_High-level project status. Read this (with `memory.md`) via `/orient` after `/clear`. Not a task queue — see `handoff.md` for the active task._

## What this project is

FastAPI + React/TS fantasy football assistant. PPR-scoped (keeper/dynasty explicitly out of scope, founder's call). Running locally against real Supabase Postgres, not deployed — see [[project_local_dev_supabase]] in memory. `docker-compose.yml` is stale, don't use it.

## Milestones (evidence-based, from repo docs + git log)

- [x] **P0 audit pass** (`AUDIT_TASK_LIST.md`) — auth was fake (login/`/me` stubs), 16 models invisible to `Base.metadata` (real data-loss risk on next migration), frontend build was broken, shared `httpx.AsyncClient` broke across event loops. All fixed.
- [x] **UX audit pass** (`UX_TASK_CHECKLIST.md`, `UX_PRODUCT_REVIEW.md`) — security holes (unauthenticated league endpoints), fabricated demo content on live analysis endpoints, blog duplicate-content bug, AI-copy honesty pass, visual identity system. 17/19 tracked items done.
- [x] **Visual identity rollout** — type system + signature "yard-divider" motif rolled out app-wide (most recent commits through `e0337b1`).
- [x] **Draft assistant hardening** — AI provider circuit breaker (`a7a5179`) + algorithmic fallback baseline (`c53df9e`) so draft recs degrade gracefully instead of 500ing when AI is down.
- [x] **ESPN roster/live-draft fixes** — season defaulting, roster grading, bench-slot bug (`8360cba`, `cd3b6bd`, `33a337a`).
- [x] **Mock draft (`DraftPage.tsx`) bug fix, 2026-08-29** — user-reported: recommendations kept pushing RB/WR causing an "overstocked" final grade, and K/DEF were never selectable. Root causes: (1) `getPositionNeeds`'s fallback `needs.length > 0 ? needs : ['RB', 'WR']` meant once RB/WR/QB/TE needs were satisfied, the code claimed RB/WR were *still* needed forever, driving the Team Needs panel, bot picks, and `generateRecommendations` requests to keep pushing RB/WR indefinitely; (2) the player pool fetch only requested RB/WR/QB/TE positional rankings — K/DEF were never in `availablePlayers` at all, despite the position filter dropdown offering them and the grading logic expecting 1 K + 1 DEF. Fixed both: `IDEAL_POSITION_COUNTS` now includes K:1/DEF:1 (matching `STANDARD_LINEUP` in `draft_recommendation_fallback.py`), the fallback now correctly returns an empty array ("no need, best player available") instead of re-injecting RB/WR, and the pool fetch now requests K/DEF rankings too. Verified live in-browser: K filter now returns real kickers; `pytest` unaffected (frontend-only change); `npm run build` green.
- [~] **ESPN live draft feed** — confirmed architecturally broken (not just untested), no known REST/WS fix exists. Manual "mark gone" mitigation shipped. Real fix (browser extension reading ESPN's DOM) not built. See [[project_espn_live_draft_broken]].
- [x] **Waiver wire personalization + dead-engine fix (2026-09-05)** — the live waiver endpoint (`GET /waiver-wire/recommendations`, `WaiverWireService.get_live_trending_recommendations`) previously ranked purely by raw Sleeper add-count with zero personalization; a second "league-aware"/"personalized" engine (`_evaluate_player_for_waiver`) was dead code (hardcoded empty performance history, so every sub-score silently defaulted to a fabricated 0.5). Fixed both: real roster-need weighting (FLEX-aware, via the same `draft_assistant._effective_position_requirements` helper other grading code uses) + real bye-week flagging + honest scoring-format context on the live endpoint; real historical-performance query restored on the dead engine, with `None`/"insufficient data" (not a fabricated default) surfaced as `data_confidence` when history is thin. `/league-aware-recommendations/{league_id}` now actually calls the live personalized method with a real fetched roster instead of the old dead local-DB path. Roster improvement recs (`post_draft_analysis_service.py::_generate_improvement_recommendations`) now surface real candidate players from the live feed instead of static templates. Frontend (`WaiverWirePage.tsx`) has a "Personalize for" league picker and per-card badges for the new signals. See `handoff.md` for exact file list — **not committed yet**.
- [ ] **Decommission audit findings** (`DECOMMISSION_TASK_LIST.md`) — large backlog of real, evidence-based bugs/dead-code, not yet started as a dedicated pass. See open items below.
- [ ] **Push alerts (in-app MVP)** — scoped, not built (`DEFERRED_FEATURES_CHECKLIST.md`).
- [ ] **Multi-platform league analysis** — Yahoo real; ESPN/Sleeper deliberately return "not implemented" rather than fake data. Deferred per founder ([[project_espn_comprehensive_analysis_ask]], [[project_yahoo_sleeper_roster_grading_ask]]).

## Founder-only / blocked items (not agent-workable)

- Rotate the ESPN session cookie that was briefly exposed in git history (needs the founder to log out/in to ESPN).
- Decide whether to rewrite local git history to purge that old commit.

## Decommission-list backlog: fully re-verified, fully stale (2026-08-29)

`docs/audits/DECOMMISSION_TASK_LIST.md`'s entire specific-bug backlog (11 items) was re-checked against current code this session. **Every single one is already fixed** — each fix site carries a docstring/comment explaining the original bug and, where identifiable, the fixing commit:

- Platform-enum string comparisons (`leagues.py`, `league_scoring.py`, `post_draft.py`, `league_management_service.py`) — all correctly use `.value.upper()`.
- `leagues.py::GET /{id}/roster-analysis` — real `team_id`/`season`, real `grade_roster` engine (`cd3b6bd`).
- `leagues.py::GET /{id}/standings` — real auth, scoped to caller's `UserLeague`, real per-platform data.
- `post_draft_analysis_service.py` roster lookup — already uses SQLAlchemy `or_()`, not Python `or`.
- `league_scoring.py::POST /compare-players` IDOR — real ownership check (`LeagueScoring` joined to `UserLeague.user_id`).
- `content.py::GET /content-stats` — `func` correctly imported from `sqlalchemy`, used as `func.count(...)`.
- `game_situation.py` models — use `func.now()`, not string `"now()"` (its own migration, `80e42eca85d0`, exists).
- `optimization_service.py::optimize_lineup` FLEX constraint — reworked to a combined-pool constraint (comment documents the exact old infeasibility bug).
- Season hardcoding in `matchup_analysis_service.py`, `players.py`, `draft_assistant_service.py::_calculate_round` — all derive real season/league-size instead of hardcoding.
- `ai_service.py::generate_multi_perspective_content`/`generate_consensus_recommendation` — both route through `_generate_with_fallback`.
- **Alembic fresh-DB migration chain** — verified empirically: spun up a throwaway local Postgres cluster (not the dev DB), ran `alembic upgrade head` against a blank database, all 20 migrations (including 2 merge heads) applied cleanly with zero errors.

**Lesson: this audit doc decays fast and should not be trusted as a live task list without re-checking each item against current code first.**

## Remaining open backlog (not bugs — product/architecture decisions, not attempted)

**Duplicate/orphaned implementations needing a canonical-path decision** (from `docs/audits/DECOMMISSION_TASK_LIST.md`, "which version wins" calls, not pass/fail bugs):
- [x] **Game situations — resolved 2026-08-29.** `enhanced_game_situation_service.py` (via `POST /game-situations/enhanced-analysis`) is now the sole implementation. Removed the dead duplicate `AdvancedAnalysisService.analyze_game_situations`/`POST /advanced-analysis/game-situations` (confirmed zero callers first) plus its 8 dedicated helper methods and now-dead imports. A third `historical.py` copy had already been removed in an earlier session. Verified: `pytest` 73/73, backend imports clean, `npm run build` green, no remaining references anywhere in the repo.
- [ ] Advanced analysis: 2 stat engines (`advanced_analysis_service.py`, wired vs. `advanced_historical_service.py`, better stats but unwired). *Not yet re-verified.*
- [ ] Matchup analysis: `matchup_analysis_service.py` used internally but its own endpoint file has zero frontend callers. *Not yet re-verified.*
- [ ] Blog: `blog.py`+`content_service.py` fully dead vs. shipped `content.py`+`content_generation_service.py`. *Not yet re-verified.*
- [ ] Player AI analysis: 2 parallel paths (`POST /players/{id}/analysis`, frontend-used, vs. `POST /players/enhanced/{id}/analysis`, unused). *Not yet re-verified.*

## Reference docs (all re-verified as of the last docs pass, per CLAUDE.md)

Now organized under `docs/` (moved out of repo root this session): `docs/guides/AUTHENTICATION_GUIDE.md`, `docs/guides/DRAFT_ASSISTANT_GUIDE.md`, `docs/guides/ENHANCED_PLAYER_DATA.md`, `docs/testing/YAHOO_INTEGRATION_TEST.md`, `docs/testing/LIVE_DRAFT_TEST.md`, `docs/guides/API_GUIDE.md`, `docs/guides/STYLE_GUIDE.md`, `docs/audits/DECOMMISSION_TASK_LIST.md` (point-in-time audit — check git log before trusting an item as still-current). `README.md` and `CLAUDE.md` stay at repo root (tool/GitHub convention); `current-state.md`/`handoff.md`/`memory.md` stay at root by choice, for quick access during the `/clear`-resume workflow.
