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
- [~] **ESPN live draft feed** — confirmed architecturally broken (not just untested), no known REST/WS fix exists. Manual "mark gone" mitigation shipped. Real fix (browser extension reading ESPN's DOM) not built. See [[project_espn_live_draft_broken]].
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

**Duplicate/orphaned implementations needing a canonical-path decision** (from `docs/audits/DECOMMISSION_TASK_LIST.md`, not re-verified — these are "which version wins" calls, not pass/fail bugs):
- Advanced analysis: 2 stat engines (`advanced_analysis_service.py`, wired vs. `advanced_historical_service.py`, better stats but unwired).
- Game situations: 3 implementations (`AdvancedAnalysisService`, wired; `enhanced_game_situation_service.py`, most rigorous, unwired; a third inline in `historical.py`, unwired).
- Matchup analysis: `matchup_analysis_service.py` used internally but its own endpoint file has zero frontend callers.
- Blog: `blog.py`+`content_service.py` fully dead vs. shipped `content.py`+`content_generation_service.py`.
- Player AI analysis: 2 parallel paths (`POST /players/{id}/analysis`, frontend-used, vs. `POST /players/enhanced/{id}/analysis`, unused).

## Reference docs (all re-verified as of the last docs pass, per CLAUDE.md)

Now organized under `docs/` (moved out of repo root this session): `docs/guides/AUTHENTICATION_GUIDE.md`, `docs/guides/DRAFT_ASSISTANT_GUIDE.md`, `docs/guides/ENHANCED_PLAYER_DATA.md`, `docs/testing/YAHOO_INTEGRATION_TEST.md`, `docs/testing/LIVE_DRAFT_TEST.md`, `docs/guides/API_GUIDE.md`, `docs/guides/STYLE_GUIDE.md`, `docs/audits/DECOMMISSION_TASK_LIST.md` (point-in-time audit — check git log before trusting an item as still-current). `README.md` and `CLAUDE.md` stay at repo root (tool/GitHub convention); `current-state.md`/`handoff.md`/`memory.md` stay at root by choice, for quick access during the `/clear`-resume workflow.
