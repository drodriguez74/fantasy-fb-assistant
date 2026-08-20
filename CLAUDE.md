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

`docker-compose up -d` runs Postgres, Redis, backend, and frontend together.

## Architecture

### Backend layering

`app/api/v1/endpoints/*.py` (route handlers, one file per domain) → `app/services/*.py` (business logic, one class per concern) → `app/models/*.py` (SQLAlchemy models). Endpoints are registered in `app/api/v1/router.py`; add new endpoint modules there. Pydantic settings live in `app/core/config.py` and are read from `backend/.env` (`.env.example` documents required keys).

Models are wired together in `app/models/__init__.py`, which imports every model class and then attaches cross-model `relationship()`s explicitly (rather than declaring them inline on each model). New models must be imported and related there or they won't be registered/joinable.

### Multi-platform league integration

`LeagueManagementService` (`app/services/league_management_service.py`) is the entry point for league analysis and branches on `UserLeague.platform` (`"YAHOO"`, `"ESPN"`, `"SLEEPER"`, etc.), delegating to platform-specific services (`yahoo_service.py`, `espn_service.py` / `espn_service_enhanced.py`, `sleeper_service.py`). When adding a platform-aware feature, follow this same "one service per platform, dispatched by `league.platform`" pattern rather than branching inside endpoint handlers.

### AI content generation

`ai_service.py` and `content_generation_service.py` wrap both OpenAI and Anthropic clients with fallback between providers. Content is generated from 5 fixed "perspectives" (Conservative, Aggressive, Data-Driven, Situational, Dynasty) that get synthesized into a consensus recommendation — see `DRAFT_ASSISTANT_GUIDE.md` for the full perspective/consensus schema before changing this code.

### Auth

JWT auth via `python-jose`; `app/api/deps.py::get_current_user` decodes the bearer token and loads the `User`. Notably, if the token's user id is `"1"` and no matching user row exists, it auto-creates a demo user (`demo@test.com`) rather than 401ing — this is intentional demo-mode behavior, not a bug, so don't "fix" it without checking with the user first.

### Background tasks

Celery (`app/core/celery_app.py`, `app/tasks/*.py`) handles scheduled content generation (weekly waiver posts, player spotlights) and data sync, backed by Redis.

### Frontend

`src/services/api.ts` is a single axios instance (with a request interceptor for the bearer token and a response interceptor that redirects to `/login` on 401) plus grouped endpoint functions (`auth`, `leagues`, `players`, ...) — add new API calls there rather than calling axios directly from components. Routing/pages live in `src/pages/` (one file per route), reusable UI in `src/components/<domain>/`, and `src/hooks/useAuth.tsx` holds auth state.

## Reference docs

Detailed guides exist at the repo root and are worth reading before touching the relevant area: `AUTHENTICATION_GUIDE.md` (auth flows), `DRAFT_ASSISTANT_GUIDE.md` (draft recommendation engine + perspective/consensus format), `ENHANCED_PLAYER_DATA.md` (player data model), `YAHOO_INTEGRATION_TEST.md` / `LIVE_DRAFT_TEST.md` (manual test procedures for those features). `API_GUIDE.md` describes endpoint shapes but is stale on auth (it predates JWT auth being added) — trust the actual endpoint code over that doc for anything auth-related.
