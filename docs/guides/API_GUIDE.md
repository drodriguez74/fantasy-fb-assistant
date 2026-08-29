# Fantasy Football Assistant API Guide

## Overview

The Fantasy Football Assistant API provides AI-powered fantasy football analysis, multi-perspective content generation, and multi-platform league integration (Sleeper, ESPN, Yahoo).

**Base URL:** `http://localhost:8000/api/v1` (the dev server started via `uvicorn app.main:app --reload --port 8000`, per `CLAUDE.md`; this guide's `curl` examples use that port).

This guide is grounded in the actual code in `backend/app/api/v1/router.py` and each endpoint module, verified live against a running instance, and cross-checked against `frontend/src/services/api.ts` and the pages/components that call it. Endpoints are grouped below by whether the real frontend actually calls them today, not just by whether they exist in the backend — a meaningful number of routes below are real and functional but currently unreached by the UI (see "Backend-only / not currently wired to the UI").

## Authentication

**This is real, not a placeholder.** Auth is JWT-based (`python-jose`), implemented in `backend/app/api/v1/endpoints/auth.py` and `users.py`, with `app/api/deps.py::get_current_user`/`get_current_active_user` decoding the bearer token on every protected route. Older versions of this doc described the API as "open, auth not yet implemented" — that has not been true for a while.

- `POST /auth/register` — body `{email, username, password, full_name}` → creates the user (`is_verified: true` is set unconditionally today — email verification exists as an endpoint but isn't enforced at registration) and returns the user object (no token).
- `POST /auth/login` — body `{email, password}` → `{access_token, refresh_token, token_type: "bearer", expires_in, user}`. Note the frontend's `auth.login()` helper accepts a `username` field and maps it onto `email` in the request body — the wire format is always `{email, password}`.
- `POST /auth/refresh` — body `{refresh_token}` → a fresh token pair.
- `POST /auth/logout` — requires a valid token; purely client-side (no server-side revocation/blacklist).
- `GET /auth/me` — current user, from the token.
- `POST /auth/change-password`, `POST /auth/request-password-reset`, `POST /auth/reset-password`, `POST /auth/verify-email`, `POST /auth/resend-verification` — all real and wired to `email_service.py` (real SMTP now that `SMTP_SERVER`/`SMTP_USERNAME`/etc. are declared in `Settings`; falls back to logging the email content instead of sending when SMTP env vars aren't set, rather than failing). **Known quirk:** `request-password-reset` and `resend-verification` both return the raw token in the JSON response body in addition to emailing it — a "remove in production" comment on this was never acted on, so don't rely on this doc to describe a security posture stronger than what's really there.

Send the token as `Authorization: Bearer <access_token>` on every subsequent request. Verified live: register → login → `GET /auth/me` → protected calls all work end-to-end against a running instance.

**Demo-mode quirk (intentional, not a bug):** if a bearer token decodes to user id `"1"` and no such user row exists, `get_current_user` auto-creates a demo user (`demo@test.com`) instead of 401ing. Don't "fix" this without checking with the product owner first (see `CLAUDE.md`).

### User profile & account (`/users`, real, JWT-protected)

- `GET /users/me`, `PUT /users/me` — profile read/update (frontend: `auth.getProfile()`, `auth.updateProfile()` — note the update call hits `/users/me`, not `/auth/me`, since there is no `PUT` under the `/auth` prefix).
- `GET /users/me/stats` — user stats summary.
- `DELETE /users/me` — deactivates (soft-deletes) the account.
- `POST /users/me/leagues`, `GET /users/me/leagues`, `DELETE /users/me/leagues/{league_id}` — an older, parallel league-storage path (`UserService.add_user_league`/`get_user_leagues`) separate from the one the Leagues page actually uses (see below) — real but not the one the frontend calls today.
- `GET /users/me/drafts` — user's recent draft sessions.
- `GET /users/{username}/public` — public profile lookup.
- `GET /users/{user_id}` — self or superuser only.

## Players

### `GET /players/` — the real, live path `PlayersPage.tsx` uses

```http
GET /players/?position={QB|RB|WR|TE|K|DEF}&sort={rank|bye_week|consensus}&page={1}&page_size={50}
```

No auth required. **This is a live, on-the-fly snapshot from Sleeper's public player catalog on every request — not a query against the local `Player` table.** There is no `team` or `limit` query param (an earlier version of this doc described both; the real params are `position`, `sort`, `page`, `page_size`, capped at `page_size<=200`).

Response:
```json
{
  "players": [
    {"id": 9509, "name": "Bijan Robinson", "team": "ATL", "position": "RB",
     "sleeper_id": "9509", "espn_id": null, "yahoo_id": null,
     "projected_points": null, "adp": null, "bye_week": null,
     "injury_status": "Healthy", "depth_chart_order": 1,
     "ai_analysis": null, "risk_level": null,
     "created_at": "...", "updated_at": "..."}
  ],
  "pagination": {"total_count": 4263, "total_pages": 86, "current_page": 1,
                 "page_size": 50, "has_next": true, "has_previous": false,
                 "next_page": 2, "previous_page": null}
}
```
Verified live (200, real Sleeper data, ~4,263 fantasy-relevant players). `projected_points`/`adp` are always `null` on this endpoint (not computed here — see `?sort=consensus` for a real relative ranking instead).

- `GET /players/{player_id}` — `player_id` is the Sleeper player id (string). Returns `{id, player_data, stats, ai_analysis, recent_news, sleeper_id}` with a real AI-generated analysis (via `ai_service`). Verified live. `recent_news` is always `null` by design — the underlying per-player news scraper (`scraper_service.py::_search_player_news`) is an explicit mock that fabricates text, so it's deliberately not wired in rather than presenting fake news as real.
- `GET /players/search/{player_name}` — searches the local `Player` table first, then falls back to/extends with a Sleeper name search. Returns `{matches: [...], search_term}`. Verified live.
- `POST /players/add-from-sleeper` — auth required. Body `{sleeper_id}`. Adds a player from Sleeper into the local `Player` table and kicks off historical sync for it.
- `POST /players/{player_id}/analysis` — auth required. Regenerates AI analysis for a player (Sleeper-backed). This is the AI-analysis path the frontend actually calls (`components/players/AIAnalysis.tsx`).
- `GET /players/{player_id}/quick-analysis?include_ai={bool}` — lighter-weight version of the above, optional AI.
- `GET /players/trending?trend_type={add|drop}&hours={24}&limit={25}` — real Sleeper trending feed. Verified live.
- `GET /players/projections/week/{week}?season={2024}` — real Sleeper projections passthrough. **Not called from the frontend.**

### Local-DB-backed "enhanced" player system (`/players/enhanced/*`, `/players/database`, `/players/sync`)

This is a separate, real subsystem (`PlayerDataService`, backed by the local `Player` table's extended columns — target share, ceiling/floor, tiers, risk level, etc.) documented in detail in `ENHANCED_PLAYER_DATA.md`. **Short version: it is real, working backend code, but the live frontend does not call any of it today** (`PlayersPage.tsx` uses `GET /players/` above, not this family). See that doc for the full picture, including two confirmed-live bugs (`GET /players/enhanced/` 500s on every call, and `GET /players/database` is unreachable due to a route-ordering bug).

## Draft Assistant

- `GET /draft/my-leagues` — auth required. The current user's connected leagues, for the Live Draft Assistant's league picker. Reads the real per-user `UserLeague` table.
- `POST /draft/recommendations` — body `{available_players, team_needs, draft_position, scoring_format, league_size}` → AI-generated draft recommendation. No auth required today (the frontend always calls it while logged in, but the route itself doesn't enforce it).
- `GET /draft/trending-candidates?hours={48}&limit={50}` — Sleeper trending-add players as draft targets. Verified live.
- `GET /draft/positional-rankings/{position}?limit={30}&sort={search_rank|consensus}` — real, filters to active-roster players only (excludes long-retired players Sleeper still tags `"Active"`, e.g. Frank Gore, by requiring a real current `team` too). `sort=consensus` blends Sleeper + FantasyPros (if `FANTASYPROS_API_KEY` is set). Verified live.
- `GET /draft/league-analysis/{league_id}`, `GET /draft/waiver-candidates/{league_id}`, `GET /draft/projections/week/{week}` — real Sleeper-backed endpoints, **not called from the frontend** (superseded by the live-draft-assistant flow and `/waiver-wire/*` below).

## Live Draft Assistant (`/draft/live-draft/*`)

Mounted at `/draft/live-draft` (not `/live-draft`), used by `LiveDraftPage.tsx` via raw `api.get/post` calls (not a grouped `api.ts` export). All session endpoints below are the real, wired path:

- `POST /draft/live-draft/start-session` — auth required. Body `{league_id, platform, scoring_format, league_size, user_team_id}`. For ESPN/Yahoo, this looks up the user's own connected `UserLeague` row for real credentials (ESPN `swid`/`espn_s2`, Yahoo OAuth token) rather than trusting anything in the request body, and rejects with a clear message if the platform isn't connected or the Yahoo token has expired. Returns a `session_id`.
- `GET /draft/live-draft/recommendations/{session_id}`, `GET /draft/live-draft/draft-board/{session_id}`, `GET /draft/live-draft/team-analysis/{session_id}` — session data.
- `POST /draft/live-draft/update-pick` — body `{session_id, player_picked}`.
- `DELETE /draft/live-draft/session/{session_id}` — end session.
- `WS /draft/live-draft/ws/{session_id}` — WebSocket, pushes recommendation updates every ~10s and on pick updates.

**Backend-only / not currently wired (real code, dead in the UI, and two of them have live signature bugs):** `GET /draft/live-draft/espn/leagues/{id}/info`, `/teams`, `/draft`, `POST /draft/live-draft/yahoo/authenticate`, `GET /draft/live-draft/yahoo/leagues`, `GET /draft/live-draft/yahoo/leagues/{key}/draft`, `GET /draft/live-draft/session/{id}/status`. The two Yahoo routes in this block call `yahoo_service` with wrong argument signatures (confirmed by reading, not live-tested) — real traps if called directly, not just unused code.

## Leagues (`/leagues`)

Real per-user league connect/management, backed by `UserLeague` rows scoped to `current_user` (not the old shared `connected_league.json` file this subsystem partly still leans on in a couple of spots — see below).

**Connect flows (all real, all wired to `LeaguesPage.tsx`):**
- `GET /leagues/sleeper/teams?league_id=&username=` → lists rosters in a Sleeper league (no auth needed to look up — Sleeper's API is public) and suggests which team is yours if you pass a username.
- `POST /leagues/sleeper/connect` — auth required. Body `{league_id, team_id?, username?}`. Persists the connection; resolves `team_id` from `username` server-side if omitted.
- `GET /leagues/espn/teams?league_id=&season=&swid=&espn_s2=` → lists teams in an ESPN league so the user can pick theirs.
- `POST /leagues/espn/connect` — auth required. Body `{league_id, season, swid?, espn_s2?, team_id?}`.
- `GET /leagues/espn/test-connection` — tests without persisting.
- `POST /leagues/yahoo/connect` — auth required. Body `{authorization_code, redirect_uri}`. Full real OAuth code exchange → fetches the user's real Yahoo leagues → persists one `UserLeague` row per league with real tokens.
- `GET /leagues/yahoo/auth-url` — builds the Yahoo OAuth URL.
- `GET /leagues/` — auth required. All of the current user's connected leagues. Verified live (returns `[]` for a fresh user).
- `PUT /leagues/{league_id}/settings` — auth required. Body is a dict; only `enable_notifications`, `auto_draft_assistant`, `team_id` are actually applied. **This is real and wired** — `LeaguesPage.tsx` uses it to let a user manually set/correct their `team_id` after connecting.
- `DELETE /leagues/{league_id}` — disconnect a league.

**Analysis endpoints on a connected league (real, auth-scoped, wired):**
- `GET /leagues/{league_id}/comprehensive-analysis`, `GET /leagues/{league_id}/waiver-recommendations`, `GET /leagues/{league_id}/trade-suggestions` — all three delegate to `LeagueManagementService.get_comprehensive_league_analysis`, which branches on `league.platform.value.upper()` (the correct enum-comparison pattern — an earlier, now-fixed bug compared the raw enum object directly against a string, which was always `False` and silently returned `{}` for every user on every platform).
- `GET /leagues/{league_id}/insights` — real league metadata plus an honest "not yet computed" placeholder for start/sit and pickup-target advice (this used to return hardcoded specific-player picks like "start Lamar Jackson" for every league regardless of who actually owned it; that's been replaced with an honest empty state rather than fabricated advice).
- `GET /leagues/{league_id}/roster-analysis` — **known-fabricated-data warning:** even for a real connected ESPN league, this endpoint hardcodes `composition_score: 85`, a fixed "B+" grade, canned strengths/weaknesses text, and a leftover dev team-name fallback (`"CMC-Allen Wrenches"`). It also hardcodes `team_id=1` and `season=2025` rather than using the connected league's real values. Treat this endpoint's output as a UI placeholder, not real analysis.
- `GET /leagues/{league_id}/standings` — **known auth gap:** unlike every other route in this file, this one has no `current_user` dependency at all. For `league_id=1` it reads a hardcoded file path (`backend/connected_league.json`) off disk; for any other id it returns a static `{"league_name": "Demo League", "teams": []}` regardless of who's asking. Live, called by `LeagueDetailPage.tsx` — don't assume its response reflects the calling user's real league.
- `GET /leagues/{league_id}/analysis`, `GET /leagues/{league_id}/matchups` — real (correct platform-enum comparison, Yahoo/ESPN roster+AI-analysis or matchup data), but **not called from the frontend today**.

**Backend-only / debug, not wired:** `GET /leagues/yahoo/test-credentials`, `POST /leagues/yahoo/test-auth` (explicitly a debug endpoint per its own docstring), `GET /leagues/espn/diagnostics`.

## League Scoring (`/league-scoring`) — real, wired

A manual scoring-configuration override that the Draft Assistant honors ahead of auto-detected platform scoring (see `draft_assistant_service.py::_apply_manual_scoring_override`). `leagueId` here is the app's own `UserLeague.id`, same id space as the `/leagues` endpoints above.

- `GET /league-scoring/league/{league_id}` — auth required, ownership-checked. Returns `{has_custom_scoring, scoring_config?}`.
- `POST /league-scoring/configure` — auth required, ownership-checked. Body includes `user_league_id`, `scoring_type` (`PPR`/`Half_PPR`/`Standard`/`Custom`), and every per-stat point value (passing/rushing/receiving/kicking/defense/fumbles/target/carry points). Wired to `components/leagues/LeagueScoringSettings.tsx`.
- `GET /league-scoring/presets` — **confirmed broken live: always 500s** against this app's real Postgres database. `ScoringPreset` rows are seeded with `scoring_type` values like `"Standard"`, but the DB's `scoringtype` Postgres enum type (created by an older migration) doesn't accept that value, so the seeding insert itself raises (`psycopg2.errors.InvalidTextRepresentation`). Not currently called by the frontend, which is presumably why this has gone unnoticed.
- `POST /league-scoring/compare-players` — auth required, but **not ownership-checked**: it accepts `scoring_config_ids` for any scoring config, not just ones belonging to the caller (an IDOR gap that every other route in this file avoids). Not called from the frontend today.
- `GET /league-scoring/analysis/{league_id}` — auth required, ownership-checked; not called from the frontend today.

## Waiver Wire (`/waiver-wire`)

- `GET /waiver-wire/recommendations?week=&season=&position=&priority=&limit=` — auth required. **Real data, sourced from Sleeper's live trending-add feed** (`WaiverWireService.get_live_trending_recommendations`), not the local `WaiverWireRecommendation`/`WaiverWireTrend` tables (those have no ingestion pipeline and are always empty on a fresh deploy). As a side effect, also lazily creates in-app notifications for high-signal new trending adds. Verified live. Wired to `WaiverWirePage.tsx`.
- `GET /waiver-wire/trending?week=&season=&position=&trend_direction={up|down|both}&limit=` — auth required. Same real Sleeper-sourced signal, extended to cover drops too. `week`/`season` are accepted for URL consistency but don't actually scope the feed (Sleeper's trending endpoint is always "right now"). This was rebuilt this session — it used to query the never-populated `WaiverWireTrend` table and always return empty. Verified live.
- `POST /waiver-wire/analyze-roster` — auth required. Body `{roster_player_ids, week?, season}`.
- `POST /waiver-wire/generate-recommendations?week=&season=&force_refresh=` — auth required; runs synchronously if `force_refresh=true`, otherwise as a FastAPI background task.
- `GET /waiver-wire/league-aware-recommendations/{league_id}` — real, reads league context via `app.utils.league_data_loader` (the older shared-file loader, not the per-user `UserLeague` table) — **not called from the frontend.**

**Removed this session:** `GET /waiver-wire/alerts` and `POST /waiver-wire/alerts/subscribe` no longer exist. Both queried/wrote tables (`WaiverWireAlert`) that nothing in the codebase ever populated (`/alerts/subscribe` was an explicit non-persisting stub). The Alerts tab in `WaiverWirePage.tsx` now reads the real in-app notification center (`GET /notifications/*` below) instead.

**Backend-only / not currently wired:** `GET /waiver-wire/recommendations/priority/{level}` (queries the empty `WaiverWireRecommendation` table directly — will return nothing on a fresh deploy), `GET /waiver-wire/player/{id}/evaluation`, `GET /waiver-wire/insights/weekly-summary`.

## Matchup Analysis (`/matchup-analysis`) — partially surfaced this session

- `GET /matchup-analysis/defense-streaming/{week}?current_defense=` — auth required. Real defensive-streaming targets driven by `MatchupAnalysisService`/`WaiverWireService`, live NFL schedule + defensive rankings. Wired to `WaiverWirePage.tsx`.
- `GET /matchup-analysis/position-outlook/{position}?weeks_ahead=` — auth required. Multi-week matchup outlook for a position. Wired to `WaiverWirePage.tsx`.
- `GET /matchup-analysis/current-week` — auth required. Returns `{current_week, season}` computed from the real current date, not hardcoded. Verified live (returned `{"current_week": 1, "season": 2026}`).

**Backend-only / not currently wired:** `GET /matchup-analysis/player-matchups/{player_id}?weeks_ahead=`, `POST /matchup-analysis/roster-matchup-analysis`, `GET /matchup-analysis/player-vs-defense/{player_id}/{opponent_team}`.

## Game Situations (`/game-situations`)

- `POST /game-situations/enhanced-analysis` — **the canonical, wired path** (used by `AdvancedAnalysisPage.tsx`). Body `{player_ids, analysis_type}` where `analysis_type` is one of `all`, `home_away`, `weather`, `opponent`, `game_script`, `venue`, `prime_time`, `rivalry`. Backed by `EnhancedGameSituationService`, which this session's audit called "the most rigorous, best-documented code in the audit" — it was previously unwired; a thinner duplicate (`AdvancedAnalysisService.analyze_game_situations`, still present at `POST /advanced-analysis/game-situations`) and a third inline copy in `historical.py` existed alongside it. The `historical.py` copy has since been removed; this is now the one real implementation. No auth required on this specific route (unlike most of the rest of this file).
- `GET /game-situations/home-away-analysis/{player_id}`, `/weather-analysis/{player_id}`, `/opponent-analysis/{player_id}`, `/game-script-analysis/{player_id}`, `/venue-analysis/{player_id}`, `/prime-time-analysis/{player_id}`, `/rivalry-analysis/{player_id}`, `POST /compare-home-away`, `POST /compare-weather-impact`, `GET /defensive-rankings`, `GET /venues`, `GET /situational-trends/{player_id}`, `GET /situation-summary`, `GET /constants` — real, granular single-factor endpoints behind the same service; **not individually called from the frontend** (the UI only calls the combined `POST /enhanced-analysis` above).
- `POST /game-situations/game-situations/bulk-create` — note the doubled path segment (mounted under `/game-situations`, and the route itself is also `/game-situations/bulk-create`) — this is how it's really registered, not a typo in this doc.

## Advanced Analysis (`/advanced-analysis`) — real, wired

All require auth. Wired to `AdvancedAnalysisPage.tsx`:
- `POST /advanced-analysis/compare-players` — body `{player_ids (2-5), metrics?}`.
- `POST /advanced-analysis/strength-of-schedule` — body `{player_ids (1-10), weeks_ahead (1-8, default 4)}`.
- `POST /advanced-analysis/breakout-candidates` — body `{position?, min_ownership, max_ownership}`.
- `GET /advanced-analysis/player-suggestions?query=&position=&limit=` — searches the local `Player` table (small, seed-sized — see below). Verified live.

**Backend-only / not currently wired:** `POST /advanced-analysis/game-situations` (superseded by `POST /game-situations/enhanced-analysis` above), `GET /advanced-analysis/analysis-summary` (returns local-DB player counts — verified live, currently 14 seed players), `GET /advanced-analysis/metrics-available`.

## Content / Blog (`/content`) — real, wired; `/blog` is a dead legacy duplicate still present in the code

`content.py` + `content_generation_service.py` is what actually shipped and is what `BlogPage.tsx`/`ContentPage.tsx` call (via raw `api.get/post()` calls with string-literal paths, not grouped `api.ts` functions — a deviation from this project's own documented API-call convention).

- `POST /content/generate-and-save`, `GET /content/templates`, `GET /content/blog-posts/`, `GET /content/blog-posts/{id}`, `PUT /content/blog-posts/{id}/publish`, `DELETE /content/blog-posts/{id}`, `POST /content/weekly-rankings`, `POST /content/waiver-wire`, `POST /content/injury-report` — all real and wired. Verified `GET /content/templates` and `GET /content/blog-posts/` live.
- Of the 10 content types `generate`/`generate-and-save` accept, only `player_analysis` and `injury_report` actually call the AI service; the other 8 (`weekly_rankings`, `waiver_wire`, `start_sit`, `trade_analysis`, `breakout_candidates`, `draft_strategy`, `matchup_analysis`, `season_recap`) are static, templated f-strings honestly flagged `ai_generated: false` in their response — real content, just not AI-written despite what "AI-powered" framing elsewhere might suggest.
- `GET /content/content-stats` — **confirmed broken live: always 500s.** The handler calls `db.func.count(...)`, but a SQLAlchemy `Session` object has no `func` attribute (`func` was never imported from `sqlalchemy` in this file) — every call raises `AttributeError`, caught and turned into a 500. Not called from the frontend.
- `POST /content/generate` — real but not called (the frontend always uses `generate-and-save`).

**`/blog` (`blog.py`, all 7 routes: `GET /posts`, `/waiver-wire/{week}`, `/player-spotlight/{player_name}`, `/rankings/{position}/week/{week}`, `POST /save-post`, `GET /trending-topics`, `GET /content-sources`) is fully superseded by `/content` above and has zero frontend callers** (no page calls it; `components/blog/BlogCard.tsx`/`BlogSearch.tsx`/`ContentGenerator.tsx`, the components that once used it, are themselves unused). It is still present and still registered in `router.py` today — it has not actually been removed despite being a known decommission candidate — so it still works if called directly, it's just dead weight. Don't build new integrations against it.

## Historical Data (`/historical`)

- `POST /historical/sync` — auth required. Body `{seasons?, force_refresh}`.
- `GET /historical/stats/overview` — no auth. Verified live (`{data_coverage, recommendations}`).
- `GET /historical/players/{player_id}/summary?seasons=`, `GET /historical/trends/league-wide` — wired to `HistoricalPage.tsx`.
- `GET /historical/players/{player_id}/trends`, `GET /historical/players/{player_id}/weekly-performance/{season}`, `GET /historical/positions/{position}/analysis`, `POST /historical/players/compare`, `GET /historical/players/{player_id}/season-summaries`, `GET /historical/matchups/{team_a}/{team_b}`, `GET /historical/players/{player_id}/consistency-analysis` — real, **not called from the frontend** (defined in `api.ts` but unused by any page).

**Removed this session:** the `/historical/advanced/*` family (strength-of-schedule, game-situation-analysis, etc. — a third, inline reimplementation of logic that now lives in `enhanced_game_situation_service.py`) no longer exists; it was merged into the canonical `game-situations` path above rather than left as a duplicate.

## Analytics & Optimization (`/analytics`) — partially wired

Wired to `AnalyticsPage.tsx`: `POST /analytics/predict/player-performance`, `POST /analytics/optimize/lineup`, `GET /analytics/correlations/players`.

**Backend-only / not currently wired:** `GET /analytics/clustering/players`, `GET /analytics/trends/player/{player_id}`, `POST /analytics/optimize/multi-lineup`, `POST /analytics/optimize/season-roster`, `POST /analytics/risk/portfolio-analysis`, `GET /analytics/metrics/position-efficiency`, `GET /analytics/metrics/matchup-analysis`, `GET /analytics/visualization/correlation-matrix`, `GET /analytics/visualization/performance-clusters` — real routes exist, but `AnalyticsPage.tsx`'s "Clustering" and "Visualization" tabs explicitly render "Feature Coming Soon" instead of calling them.

## Post-Draft Analysis (`/post-draft`)

- `GET /post-draft/user-leagues`, `GET /post-draft/import-roster/{league_id}`, `POST /post-draft/analyze-roster`, `POST /post-draft/personalized-waivers` — wired to `PostDraftAnalysisPage.tsx`.
- **Known-fabricated-data warning:** `GET /post-draft/import-roster/{league_id}` docstring literally says "NO MOCK DATA," but the handler unconditionally returns a hardcoded 5-player demo roster (Lamar Jackson, Derrick Henry, Cooper Kupp, Travis Kelce, Christian McCaffrey) regardless of the real connected league — this is live, and it's what `PostDraftAnalysisPage.tsx` actually shows users today.
- `GET /post-draft/roster-grade`, `GET /post-draft/improvement-suggestions` — real, **not called from the frontend.**

## Matchup / Trade Analyzer (`/trade`) — real, wired

Deliberately a transparent heuristic, not an AI model — see the module docstring in `trade.py` for the full reasoning.
- `GET /trade/player-search?q=&limit=` — filters to active-roster players only. Verified live.
- `POST /trade/analysis` — body `{side_a_gives: [sleeper_id...], side_b_gives: [sleeper_id...]}` → per-side total value, per-player breakdown, plain-language verdict. Value model: `10000 / (search_rank + 19)`, documented in-code as a judgment call, not a statistical fit.

## Notifications (`/notifications`) — real, wired, added this session

In-app notification center (not device/browser push), wired to the navbar bell (`components/common/NotificationBell.tsx`) and the Waiver Wire Alerts tab.
- `GET /notifications/?page=&page_size=&unread_only=` — verified live.
- `GET /notifications/unread-count` — verified live.
- `POST /notifications/{id}/read`, `POST /notifications/read-all`.

Notification rows are created as a side effect of real events elsewhere (e.g. `GET /waiver-wire/recommendations` calling `notify_trending_adds`), not by any endpoint in this file.

## Multi-Perspective Content Generation

Several content paths (draft recommendations, waiver-wire posts, player analysis) generate content from 5 fixed perspectives that get synthesized into a consensus — see `DRAFT_ASSISTANT_GUIDE.md` for the full schema before changing this. Only some content types actually invoke the AI (see the Content section above for which).

## AI Services

`ai_service.py` supports both OpenAI and Anthropic, with fallback. One real gap: `generate_multi_perspective_content`/`generate_consensus_recommendation` don't have the OpenAI→Anthropic fallback every other method in the file has — if only `ANTHROPIC_API_KEY` is set, the literal string `"OpenAI client not configured"` can get saved as if it were real AI-generated analysis text.

## Error Handling

Structured error responses:
```json
{"detail": "Error description"}
```
Common status codes: `400` (bad request/validation), `401` (missing/invalid/expired token), `404` (not found), `500` (internal error — many handlers wrap all exceptions, including their own `HTTPException`s, into a 500 with a prefixed message; don't assume every 500 body indicates an unhandled crash rather than a deliberate 4xx-turned-500).

## Confirmed-live bugs worth knowing about

These were found by actually calling the running API, not just reading code:
- `GET /players/database` — **unreachable.** It's registered after `GET /players/{player_id}` in the same router, and FastAPI matches routes in registration order, so a request to `/players/database` is swallowed by the `{player_id}` route (`player_id="database"`) and returns a wrapped 404→500 ("Failed to get player details: 404: Player not found") instead of ever reaching its own handler.
- `GET /players/enhanced/` — **always 500s.** The handler calls `PlayerDataService.get_players_by_criteria(..., limit=limit)`, but that method's real signature takes `page`/`page_size`, not `limit`.
- `GET /league-scoring/presets` — **always 500s** against Postgres (enum value mismatch seeding `ScoringPreset` rows — see the League Scoring section above).
- `GET /content/content-stats` — **always 500s** (`Session.func` doesn't exist; `func` was never imported from `sqlalchemy`).

## Development Setup

```bash
docker-compose up -d          # Postgres, Redis, backend, frontend together
# or, from backend/ with venv activated:
uvicorn app.main:app --reload --port 8000
```
- API: `http://localhost:8000` — Docs: `http://localhost:8000/docs` — Frontend dev server: `http://127.0.0.1:3001` (see `frontend/vite.config.ts` — not the Vite default 5173, and not 3000).
- Set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (and, for real outbound email, `SMTP_SERVER`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`FROM_EMAIL`) in `backend/.env`.

## Background Tasks

**Not currently running.** `app/core/celery_app.py` + `app/tasks/*.py` define real task functions (weekly waiver content, player spotlights, data sync), but there is no beat schedule, no `.delay()`/`.apply_async()` call anywhere in the codebase, and no celery worker/beat service in `docker-compose.yml`. This was decommissioned this session as dead scaffolding rather than left half-wired — don't rely on any content or sync "happening automatically."

## Platform Integration

Sleeper (public API, no auth needed), ESPN (cookie-based `swid`/`espn_s2` for private leagues), and Yahoo (real OAuth2) are all live and integrated, dispatched by `UserLeague.platform` via `LeagueManagementService` and platform-specific services (`sleeper_service.py`, `espn_service_enhanced.py`, `yahoo_service.py`). `espn_service.py` (the older, pre-`espn_service_enhanced` client) is still present but its only remaining live caller is the dead ESPN block in `live_draft.py` noted above.
