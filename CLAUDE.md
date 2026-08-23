# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Fantasy Football Assistant: a FastAPI backend + React/TypeScript frontend that gives PPR fantasy football users AI-generated draft/waiver advice and aggregates data from multiple fantasy platforms (ESPN, Yahoo, Sleeper).

## Commands

### Backend (run from `backend/`, with venv activated)

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000   # dev server -> http://localhost:8000/docs

alembic revision --autogenerate -m "..."    # create migration after model changes
alembic upgrade head                        # apply migrations

python -c "from app.db.init_db import init_db; init_db()"   # (re)seed sample data

pytest                                      # run all tests
pytest tests/test_players.py                # run a single test file
pytest tests/test_players.py::test_name -v  # run a single test
```

Tests use an isolated SQLite DB (see `tests/conftest.py`), not the Postgres dev database.

### Frontend (run from `frontend/`)

```bash
npm run dev       # dev server -> http://127.0.0.1:3001 (see vite.config.ts; NOT the default 5173)
npm run build      # tsc -b && vite build
npm run lint        # eslint
npm run preview     # serve production build
```

### Full stack via Docker

`docker-compose up -d` runs Postgres, backend, and frontend together. There is no Redis/Celery service — see "Background tasks" below.

## Architecture

### Backend layering

`app/api/v1/endpoints/*.py` (route handlers, one file per domain) → `app/services/*.py` (business logic, one class per concern) → `app/models/*.py` (SQLAlchemy models). Endpoints are registered in `app/api/v1/router.py`; add new endpoint modules there. Pydantic settings live in `app/core/config.py` and are read from `backend/.env` (`.env.example` documents required keys).

Models are wired together in `app/models/__init__.py`, which imports every model class and then attaches cross-model `relationship()`s explicitly (rather than declaring them inline on each model). New models must be imported and related there or they won't be registered/joinable.

### Multi-platform league integration

`LeagueManagementService` (`app/services/league_management_service.py`) is the entry point for league *analysis* (roster grading, matchups, standings, waiver/trade recommendations bundled into one response) and branches on `league.platform.value.upper()` (compare the resolved `.value`, never the raw `Enum` against a string literal — `UserLeague.platform` is a plain `enum.Enum`, and comparing it directly to `"YAHOO"`/`"ESPN"` is always `False`; this exact bug once made the whole analysis path silently return `{}` for every user). Today `get_comprehensive_league_analysis` only has a real Yahoo implementation — ESPN/Sleeper deliberately return an honest "not implemented for this platform yet" error rather than partial/fake data; building that out is real, tracked future work, not a quick fix.

Live Draft (`app/api/v1/endpoints/live_draft.py` → `draft_assistant_service.py`) is a separate integration across all three platforms, each with a different auth model: Sleeper needs no credentials (its player/draft data is public); ESPN needs a per-user `SWID`/`espn_s2` cookie pair, persisted via `POST /leagues/espn/connect` (paste-your-own-cookies, since ESPN has no OAuth for fantasy); Yahoo needs a per-user OAuth token, persisted via `POST /leagues/yahoo/connect`. All three store credentials on the connecting user's own `UserLeague` row — never on a shared/global service instance — and every platform service method takes the token/cookies as an explicit parameter rather than storing them on `self`.

**ESPN's live draft data feed is confirmed broken, not just untested** (verified 2026-08-23 against a real, in-progress ESPN draft, mid-draft at round 15/16): neither the legacy `fantasy.espn.com` REST API `espn_api` calls, nor ESPN's own modern `lm-api-reads.fantasy.espn.com` host (same `mDraftDetail` view, fetched from inside the user's own authenticated browser session on ESPN's actual live draft page) ever returns real picks — both report 0 drafted players and `drafted: false` throughout, even as the real draft board visibly progressed through 190+ real picks. `espn_api`'s `_fetch_draft()` has an early-return specifically for this (`if not draftDetail.drafted: return`), discarding whatever in-progress data exists. Whatever actually powers ESPN's own live Pick History UI is almost certainly a WebSocket push feed with no discovered REST equivalent — reverse-engineering it is a real research project, not a quick fix. **Practical effect: ESPN's live draft session starts fine (auth, websocket infra, UI) but its "available players"/recommendations will silently include already-drafted players for the entire draft.** Researched whether a real API/WebSocket fix exists (2026-08-23): no documented path exists anywhere (no GitHub issue, library, or writeup); every real commercial competitor (FantasyPros, Draft Sharks, Subvertadown, Pick Pulse) solves this via a **browser extension reading the ESPN draft page's DOM directly**, not a backend API call — there may not be an externally-callable API for this at all. That's the real fix, not yet built.

**Mitigation shipped in the meantime**: a manual "Mark gone" button per available player on `LiveDraftPage.tsx` (`POST /live-draft/mark-drafted` → `DraftAssistantService.mark_player_drafted`), letting the user manually remove a player from the pool when ESPN's feed hasn't. Session-scoped `manually_drafted_player_ids`, re-applied as a filter on every recommendations refresh (necessary since `_refresh_draft_state` wholesale-replaces `available_players` from the live feed every ~10s via the websocket loop, which would otherwise silently undo a manual correction). Distinct from `/update-pick`, which means "I drafted this" — don't conflate the two.

Sleeper's live-pick feed is confirmed architecturally sound (hits a real, publicly-documented, non-cached live endpoint). Yahoo's code has no caching bug either, but whether Yahoo's platform actually exposes in-progress picks (vs. only post-completion, ESPN's exact failure mode) is unverified — don't assume it's fine by default; verify against a real in-progress Yahoo draft before trusting it.

### AI content generation

`ai_service.py`'s `_generate_with_fallback()` is the one consolidated primitive every AI-generation call should go through — it tries the primary provider (OpenAI by default), specifically detects `openai.RateLimitError`/`anthropic.RateLimitError` for an immediate fallback to the secondary provider, and also falls back on other real failures (auth, network, malformed response). It routes through two model tiers (`FAST_OPENAI_MODEL`/`FAST_ANTHROPIC_MODEL` for short, low-stakes generations; `DEEP_*` for multi-perspective analysis and consensus synthesis) — don't hardcode a model name at a new call site, reference these tier constants. `_generate_openai`/`_generate_anthropic` still exist as legacy non-raising wrappers for a couple of call sites that predate this consolidation; don't add new callers of those, use `_generate_with_fallback`.

`content_generation_service.py` generates content from 5 fixed "perspectives" (Conservative, Aggressive, Data-Driven, Situational, Dynasty) synthesized into a consensus recommendation — see `DRAFT_ASSISTANT_GUIDE.md`. Only 2 of its 10 `ContentType`s (`player_analysis`, `injury_report`) actually call the AI; the other 8 are honest, explicitly-labeled (`ai_generated: False`) static templates — this is a known, tracked capability gap (`DECOMMISSION_TASK_LIST.md`), not an oversight, so don't assume a given content type is AI-backed without checking.

### Player rankings & scoring

Three real systems, easy to confuse:
- **Consensus ranking** (`consensus_ranking_service.py`) blends whichever of Sleeper `search_rank`, ESPN `percent_owned`, Yahoo `ownership_percentage`, and FantasyPros `rank_ecr` are actually available for a player, each converted to a percentile *within its own population* before averaging (never average raw values across sources — the scales aren't comparable). FantasyPros only contributes once `FANTASYPROS_API_KEY` is set in `.env` (free tier available); everything degrades cleanly with fewer sources.
- **Real per-league scoring rules** (`scoring_rules.py`) extracts a connected league's actual scoring settings (PPR value, and — new — the full stat picture: completions/incompletions/attempts, yardage, TDs, INTs, fumbles) from Sleeper/ESPN, replacing the old hardcoded-PPR assumption.
- **Manual scoring override** (`league_scoring.py` endpoints, `LeagueScoring` model) lets a user hand-configure scoring rules that take priority over auto-detected settings when both exist for the same league — useful when auto-detection isn't available for a platform yet, or a user wants to model a hypothetical.

### Data confidence UI pattern

`frontend/src/components/common/DataConfidenceBadge.tsx` — a small three-state badge (`computed` / `heuristic` / `insufficient`) used anywhere a number on screen is derived rather than typed in by a human, so a real computed value never looks visually identical to a fabricated one. Use it on any new page that surfaces a score, rank, or projection.

### Auth

JWT auth via `python-jose`; `app/api/deps.py::get_current_user` decodes the bearer token and loads the `User`. Notably, if the token's user id is `"1"` and no matching user row exists, it auto-creates a demo user (`demo@test.com`) rather than 401ing — this is intentional demo-mode behavior, not a bug, so don't "fix" it without checking with the user first. Account lockout (`user_service.py::authenticate_user`) compares `locked_until` against `datetime.now(timezone.utc)`, not `datetime.utcnow()` — the columns are timezone-aware; mixing naive/aware datetimes here previously caused a 500 on any account with an expired lockout.

### Email

`email_service.py` sends real SMTP mail for password-reset/email-verification when `SMTP_SERVER`/`SMTP_USERNAME`/etc. are set in `.env` (all optional); with none configured it stays in an honest dev-log mode (logs the would-be email, returns success, never crashes) rather than silently no-op'ing. This is deliberately a separate channel from the in-app notification center below — different transport, different trigger model, not meant to be unified.

### Background tasks

There is no background task system. Celery/Redis were removed (`docker-compose.yml`, `requirements.txt`) after an audit found the scheduled tasks either called into an already-abandoned content pipeline or never persisted their results anywhere — see git history ("Decommission dead Celery/Redis background-task scaffolding") for the reasoning if reviving scheduled tasks is ever worth it. The real in-app notification center (`notification_service.py`, `Notification` model, `GET /notifications/*`, the navbar bell) is populated synchronously as a side effect of real requests (e.g. waiver recommendations), not on a schedule.

### Frontend

`src/services/api.ts` is a single axios instance (with a request interceptor for the bearer token and a response interceptor that redirects to `/auth` on 401 — not `/login`, which doesn't exist as a route) plus grouped endpoint functions (`auth`, `leagues`, `players`, ...) — add new API calls there rather than calling axios directly from components. Routing/pages live in `src/pages/` (one file per route), reusable UI in `src/components/<domain>/`, and `src/hooks/useAuth.tsx` holds auth state.

## Reference docs

Detailed guides exist at the repo root and are worth reading before touching the relevant area: `AUTHENTICATION_GUIDE.md` (auth flows), `DRAFT_ASSISTANT_GUIDE.md` (draft recommendation engine + perspective/consensus format), `ENHANCED_PLAYER_DATA.md` (player data model), `YAHOO_INTEGRATION_TEST.md` / `LIVE_DRAFT_TEST.md` (manual test procedures for those features), `API_GUIDE.md` (endpoint shapes). `DECOMMISSION_TASK_LIST.md` is a point-in-time audit of what's real/broken/dead across the whole codebase — useful context, but check git log for anything that's since been fixed before trusting an item in it as still-current. As of this session's docs pass, all of the above have been re-verified against real code and live-tested where practical — but this codebase moves fast; re-verify anything load-bearing rather than trusting a doc blindly.
