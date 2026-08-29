# Enhanced Player Data System

## Reachability, up front

**This is real, working backend code that the live frontend does not use today.** `PlayersPage.tsx` — the actual Players page users see — calls `GET /players/` (`players.getAll()` in `frontend/src/services/api.ts`), which is a live, on-the-fly snapshot built fresh from Sleeper's public player catalog on every request. It is a completely different code path from everything documented below. Nothing in the frontend calls `/players/enhanced/*` or `/players/database`; grepping `frontend/src` confirms zero call sites for `players.getFromDatabase` (the one `api.ts` export that targets `/players/database`) and there is no `api.ts` export at all for the `/enhanced/*` family — pages that would use it would have to call `api.get('/players/enhanced/...')` directly, and none do.

This doc describes the local-database-backed system anyway because it's real, substantial code (`backend/app/services/player_data_service.py`, the extended columns on `app/models/player.py`), not vaporware — just currently orphaned. Two of its endpoints are also confirmed broken by a live call, documented below; that's worth knowing before anyone decides to wire this system up.

**Where the data actually comes from and how much of it exists:** `POST /players/sync` (auth required) is the real mechanism that would populate this system — it pages through Sleeper's full player catalog and upserts into the local `Player` table. In this app's current dev database, that has not happened at any meaningful scale: `GET /advanced-analysis/analysis-summary` (a real endpoint that counts rows in the same `Player` table) reports **14 total players** (3 QB, 6 RB, 4 WR, 1 TE — clearly a small hand-seeded sample, not a real sync), and both `GET /players/enhanced/trending/{direction}` and `GET /players/enhanced/injury-report` return empty lists live. There's also no Celery schedule or any other automatic trigger for `/players/sync` — background tasks in this app are pure scaffolding today (no beat schedule, no `.delay()` call anywhere, no worker in `docker-compose.yml`). So even setting aside the UI-reachability gap, this system's data would need a manual sync to be useful at all.

## What's real

### Advanced Player Model (`app/models/player.py`)
Real columns exist for: basic bio (age, height, weight, college, experience), fantasy metrics (PPR/Half-PPR/Standard projections, ADP, ownership %), advanced usage analytics (target share, air yards share, snap count %, carries share), injury tracking (status, body part, notes, practice status), AI-analysis-derived fields (ceiling/floor scores, consistency rating), a calculated risk level (LOW/MEDIUM/HIGH), and rankings/tiers (position rank, draft tier, expert consensus rank).

### Endpoints (`backend/app/api/v1/endpoints/players.py`)

All of these are real and exist in the running app today (verified against `router.py` and live requests). None require auth except the two write/mutate ones noted.

- `POST /players/sync` — auth required. Syncs the full Sleeper player catalog into the local `Player` table via `PlayerDataService.sync_player_data()`. Real, not called from the frontend, not scheduled.
- `GET /players/enhanced/` — filter by `position`, `team`, `injury_status`, `min_projected_points`, `max_risk_level`, `limit`. **Confirmed broken live: always returns a 500.** The handler calls `PlayerDataService.get_players_by_criteria(..., limit=limit)`, but that method's real signature is `get_players_by_criteria(position, team, injury_status, min_projected_points, max_risk_level, page=1, page_size=50)` — there is no `limit` parameter, so every call raises `TypeError: get_players_by_criteria() got an unexpected keyword argument 'limit'`, caught and returned as a 500. This is not a hypothetical — it was reproduced live against the running instance.
- `GET /players/enhanced/trending/{direction}` (`UP`/`DOWN`) — works live, but returns an empty list today since no player in the 14-row local table has `trending_direction` set.
- `GET /players/enhanced/injury-report` — works live; returns `{injury_report: [], total_injured: 0}` today (no seeded injury data).
- `PUT /players/enhanced/{player_id}/metrics` — auth required. Works live: recalculates `ceiling_score`/`floor_score`/`risk_level`/`tier` for one player from its stored data. Verified against seeded player id 1 (Josh Allen) — returned real, non-trivial computed values.
- `POST /players/enhanced/{player_id}/analysis` — auth required. Generates AI analysis using local player data as context (parallel to, but a separate code path from, the frontend-used `POST /players/{id}/analysis`, which is Sleeper-backed rather than local-DB-backed).
- `GET /players/enhanced/comparison?player_ids=1,2,3` (max 5) — works live; verified against the seed data (Josh Allen vs. Christian McCaffrey), returned full comparison fields.
- `GET /players/database` — filter by `position`, `team`, `injury_status`, `min_projected_points`, `max_risk_level`, paginated. **Confirmed unreachable live**, and for a different reason than the 500 above: this route is registered *after* `GET /players/{player_id}` in the same file, and FastAPI/Starlette matches routes in registration order. A request to `/players/database` therefore matches `GET /{player_id}` first, with `player_id` bound to the literal string `"database"` — its own handler never runs. Confirmed by the actual response: `{"detail": "Failed to get player details: 404: Player not found"}`, which is exactly `get_player()`'s error-wrapping format for "player id not found in Sleeper," not `get_players_from_database()`'s. This route is real, sensible code that has simply never been reachable since the day it was added after `/{player_id}` in this file.

### Injury Status Enum
`HEALTHY`, `QUESTIONABLE`, `DOUBTFUL`, `OUT`, `IR`, `PUP`, `SUSPENDED` — real enum, defined in `app/models/player.py`.

### Risk Level Calculation
LOW / MEDIUM / HIGH, computed in `PlayerDataService.calculate_advanced_metrics` (age + injury-history based). Confirmed to run correctly via the live `PUT /players/enhanced/{id}/metrics` call above.

## Frontend integration: none today

Contrary to what an earlier version of this document implied, none of the following exist in the real frontend:
- No "advanced filtering," risk badges, injury badges, or trending indicators sourced from this system on the real Players page — `PlayersPage.tsx` renders data from `GET /players/`, whose player objects always have `risk_level: null` and `ai_analysis: null` by construction (that endpoint doesn't compute them).
- No Draft Assistant integration with local risk levels / ceiling-floor — the draft recommendation flow is Sleeper-backed.
- No "real-time" injury/trending UI wired to `/players/enhanced/*`.

If a future task decides to wire this up, the two live bugs above (`limit` vs. `page`/`page_size` on the list endpoint, and the `/database` route-ordering shadow) need fixing first, and `POST /players/sync` needs to actually run against real Sleeper data (or be scheduled) before the local `Player` table has enough rows for any of this to be meaningfully different from the current 14-row seed set.

## Parallel system note

There are now two separate "player AI analysis" paths in this codebase: `POST /players/{id}/analysis` (Sleeper-backed, real, the one the frontend actually calls) and `POST /players/enhanced/{id}/analysis` (local-DB-backed, real, zero frontend callers, documented above). Both work; only one is reachable from the UI. This mirrors the same "parallel implementation, only one wired" pattern that shows up elsewhere in this codebase (e.g. game-situations analysis, matchup analysis) — worth knowing if you're deciding which one to extend.
