# Decommission & Remediation Task List

Full exhaustive audit of the entire codebase — every one of 19 backend endpoint files, 28 services, 12 models (cross-checked against real migration history), and the full frontend (18 pages, 24 components). Six independent review-only passes, each grounded in real code-reading, `pyflakes`/`tsc`/`eslint`, live API calls where credentials allowed, and — for the migration chain specifically — an actual `alembic upgrade head` run against a fresh local Postgres cluster, not just static analysis.

**Verdict**: the app is not in a "100% functional" state. Tests pass and the build is clean, but that's because dev setup bypasses the two systems this audit found most broken — Alembic migrations (dev uses `create_all()` instead) and several silently-empty recommendation paths (nothing asserts on them). Nothing here is a guess; every item below has a stated method of confirmation.

---

## Cross-Cutting Patterns (fix once, resolves multiple findings)

These aren't isolated bugs — they're the same mistake made repeatedly across the codebase. Fixing the pattern is higher leverage than fixing each instance separately.

### Pattern 1 — Enum compared against a raw string (always `False`)
`UserLeague.platform` is a plain `enum.Enum` (`PlatformType`, lowercase values `"yahoo"`/`"espn"`), not a string-mixed enum. Comparing it directly to `"YAHOO"`/`"ESPN"` is **always `False`** — confirmed with a standalone repro. The correct pattern (`user_league.platform.value.upper() == "ESPN"`) already exists elsewhere in the same codebase.
- [ ] `backend/app/services/league_management_service.py::get_comprehensive_league_analysis` — **highest-impact instance**: this is the shared engine behind the *live* `waiver-recommendations` and `trade-suggestions` endpoints. Because the check is always `False` and there's no `else` branch at all, several hundred lines of real AI roster/matchup/waiver/trade logic are unreachable — every user on every platform gets `{}` back today.
- [ ] `backend/app/api/v1/endpoints/leagues.py` — `GET /{league_id}/analysis` and `GET /{league_id}/matchups` have the same bug (lower impact only because both are already dead/unreachable from the frontend — fix or decommission together).

### Pattern 2 — Hardcoded `season = 2024` (now two years stale)
Found independently in five separate files. Every instance silently serves old data as if current, with no error or warning.
- [ ] `backend/app/services/matchup_analysis_service.py` — 8+ call sites, cascades into `advanced_analysis_service.py` and `enhanced_game_situation_service.py` since they depend on it. Single highest-leverage fix in this pattern.
- [ ] `backend/app/services/advanced_historical_service.py::analyze_strength_of_schedule`
- [ ] `backend/app/services/fantasypros_service.py` (`get_consensus_rankings`, `get_consensus_rankings_players`) — not yet live-triggered (no API key configured today), but will silently serve 2024 rankings the moment a key is added
- [ ] `backend/app/api/v1/endpoints/players.py::POST /{player_id}/analysis` — the one AI-analysis path the frontend actually calls fetches Sleeper stats for `"2024"` by default; real current season is available via `sleeper_service.get_nfl_state()` (already used elsewhere) but never called here
- [ ] `backend/app/services/draft_assistant_service.py::_calculate_round` — not a season bug but the same category: hardcodes a 12-team league assumption in all 3 call sites even though `session["draft_settings"]["league_size"]` already holds the real value

**Recommendation**: add one real "current season" helper (wrapping `sleeper_service.get_nfl_state()`) and thread it everywhere instead of fixing each literal independently.

### Pattern 3 — Parallel/duplicate implementations, only one wired to the UI
The codebase has repeatedly grown a second implementation of the same feature instead of extending the first, then never connected or removed the loser.
- [ ] **"Advanced analysis" (compare-players / strength-of-schedule / breakout-candidates)**: real in both `advanced_analysis_service.py` (wired, frontend-used) and `advanced_historical_service.py` (not wired — but has *better* statistics, real ANOVA/Mann-Whitney/Cohen's d that the wired version lacks). Decide: merge the better stats into the wired path, then decommission `advanced_historical_service.py`'s duplicate methods.
- [ ] **"Game situations"**: exists in *three* places — `AdvancedAnalysisService.analyze_game_situations` (wired to `AdvancedAnalysisPage.tsx`), `enhanced_game_situation_service.py` (the most rigorous, best-documented code in the entire audit — **zero frontend callers**), and a third inline reimplementation directly in `historical.py`'s `/advanced/game-situation-analysis/{id}` (also unwired). Recommendation: make `enhanced_game_situation_service.py` (via `game_situations.py`) the canonical path — it's simply better-built — and decommission the other two.
- [ ] **Matchup analysis**: `matchup_analysis_service.py` is real and used internally by two other services, but its own endpoint file (`matchup_analysis.py`, 6 routes: defense-streaming, player-matchups, roster-matchup, position-outlook) has **zero frontend callers** despite being genuinely useful (defensive streaming targets, matchup outlook). Either surface it in the UI or decommission the endpoint file.
- [ ] **Blog/content**: `blog.py` (7 routes) + `content_service.py` is the abandoned original; `content.py` + `content_generation_service.py` is what actually shipped and is frontend-wired. `blog.py` is fully dead (one route is a literal `"coming soon"` stub). `content_service.py`'s `save_blog_post` still has the exact `ai_model_used="gpt-4"` mislabeling bug that was fixed in its sibling — moot only because nothing calls it.
- [ ] **Player AI analysis**: two parallel paths — `POST /players/{id}/analysis` (real, Sleeper-backed, frontend-used) vs. `POST /players/enhanced/{id}/analysis` (real, local-DB-backed, zero frontend callers). Not urgent, but worth a decision on which is canonical.
- [ ] **Frontend components built and abandoned**: entire `components/blog/` directory (3 files: `BlogCard`, `BlogSearch`, `ContentGenerator`) and 4 of 5 files in `components/draft/` (`DraftBoard`, `TeamRoster`, `RecommendationCard`, `DraftSettings`) — each superseded by an inline reimplementation in the page that would have used them. `PerformanceTrendChart.tsx` (1 of 6 chart components) is similarly orphaned.

### Pattern 4 — Fabricated/mock data indistinguishable from real data
Distinct from "dead code" — these run on live, reachable paths and produce fake output presented as genuine.
- [ ] `backend/app/api/v1/endpoints/post_draft.py::GET /import-roster/{league_id}` — docstring literally says **"NO MOCK DATA"**, function unconditionally returns a hardcoded 5-player demo roster. Live, called by `PostDraftAnalysisPage.tsx`.
- [ ] `backend/app/services/scraper_service.py` — `_search_player_news`, `_scrape_fantasypros_trending`, `_scrape_espn_trending` are explicit mocks (comment: "Mock implementation"). The trending ones were newly found this pass, missed by an earlier session check that only looked at the news-search method.
- [ ] `backend/app/api/v1/endpoints/leagues.py::GET /{league_id}/roster-analysis` — fetches a real roster, then layers fabricated analysis on top: hardcoded `"composition_score": 85`, canned strengths/weaknesses text, and a leftover dev team name (`"CMC-Allen Wrenches"`) as a fallback.
- [ ] `frontend/src/pages/BlogPage.tsx` — "Quick Hits" sidebar renders four completely static, hardcoded insight strings next to genuinely dynamic blog content, with no visual distinction.
- [ ] `backend/app/services/ai_service.py::generate_multi_perspective_content` / `generate_consensus_recommendation` — skip the OpenAI→Anthropic fallback every other method in the file has. If only `ANTHROPIC_API_KEY` is set, the literal string `"OpenAI client not configured"` gets embedded as real "analysis" text and saved as AI-generated content — undermining the one path (`player_analysis`) currently claimed as genuinely AI-driven.

### Pattern 5 — Auth/ownership scoping gaps (same bug class as the earlier P0 fix, missed spots)
- [ ] `backend/app/api/v1/endpoints/leagues.py::GET /{league_id}/standings` — **no `current_user` dependency at all**, reads the old shared hardcoded `connected_league.json` file, returns fake "Demo League" for any other id. Live — called by `LeagueDetailPage.tsx`. This is the exact bug class the P0 fix addressed on every sibling endpoint in the same file except this one.
- [ ] `backend/app/api/v1/endpoints/league_scoring.py::POST /compare-players` — IDOR: requires `current_user` but never checks that the `scoring_config_ids` being compared actually belong to that user. Every other route in the same file does this check.
- [ ] `backend/app/api/v1/endpoints/leagues.py::GET /{league_id}/roster-analysis` — hardcodes `team_id=1` and `season=2025` instead of the connected league's real `user_league.team_id`/`.season`. If the real team_id isn't 1, users see another team's roster labeled as their own.

---

## Critical — Fix Before Anything Else

- [ ] **Alembic migration chain cannot run on a fresh database at all** (`backend/alembic/versions/`) — empirically confirmed via a real `alembic upgrade head` run against a blank local Postgres cluster:
  1. Fails immediately at migration `7a4b2d1e5f89` — an inline `sa.Enum('home','away','neutral', name='gamelocation')` collides with a defensively-created `CREATE TYPE gamelocation` in the same migration (`psycopg2.errors.DuplicateObject`), rolling back everything.
  2. Even past that, `8f2a4c5d6e91` creates `blog_posts` a second time (already created in `0b92d89d8227`, never dropped) — guaranteed "relation already exists" failure.
  3. Even past that, **12 real tables are permanently missing** from a from-scratch deploy: `league_scoring`, `scoring_presets`, `player_scoring_calculations` (never had a migration, ever) plus 9 more (`waiver_wire_recommendations`, `waiver_wire_trends`, `player_evaluations`, `waiver_wire_alerts`, `player_historical_performance`, `player_season_summaries`, `matchup_histories`, `player_trends`, `fantasy_league_histories`) that were created, then dropped by a bad autogenerate run (`b35a100cf963`, generated while those models weren't yet imported into `app/models/__init__.py`), and never recreated. `player_scoring_calculations` is actively read/written by `scoring_calculation_service.py` at runtime.
  - **This is why nothing has caught it**: local dev uses `init_db.py`'s `Base.metadata.create_all()`, which bypasses Alembic entirely.
- [ ] `league.platform == "YAHOO"`/`"ESPN"` string comparisons — Pattern 1 above. Fix in `league_management_service.py` first (highest impact), then `leagues.py`.
- [ ] `backend/app/services/optimization_service.py::optimize_lineup` — FLEX-slot constraint bug (previously documented, confirmed still present and unfixed). Individual position `==` constraints already force the RB/WR/TE sum to exactly the base requirement, so the separate FLEX `>=` constraint reduces to `0 >= FLEX_required` — **infeasible under default settings**. Default lineup optimization always returns "No optimal solution found."
- [ ] `backend/app/api/v1/endpoints/content.py::GET /content-stats` — calls `db.func.count(...)`; `Session` has no `func` attribute (`func` was never imported from `sqlalchemy`). Raises `AttributeError` on every call, caught and turned into a 500.
- [ ] `backend/app/api/v1/endpoints/live_draft.py` — two dead-but-live-in-Swagger routes call `yahoo_service` methods with wrong argument signatures: `GET /yahoo/leagues/{league_key}/draft` (missing required `league_key` after `access_token`) and `GET /yahoo/leagues` (passes `season` positionally where `access_token` is expected — guaranteed to fail auth for every caller). Unreachable from the frontend today, but real traps for direct API use.
- [ ] `backend/app/services/post_draft_analysis_service.py::analyze_roster_comprehensive` — player lookup uses Python `or` instead of SQLAlchemy `or_()`: `Player.id == pid or Player.name == pname` always evaluates just the first clause (SQLAlchemy `BinaryExpression` truthiness), so **name-based roster matching never actually works**. Since the local `Player` table is documented elsewhere as nearly empty, and `RosterPlayer.player_id` defaults to `None`, this silently breaks roster analysis for the realistic case (name-only submission).
- [ ] `backend/app/models/game_situation.py` — 5 tables use `server_default="now()"` (a bare Python string) instead of `server_default=func.now()`. Works on Postgres (matches migration text) but empirically **crashes on SQLite** (`ValueError: Invalid isoformat string: 'now()'`) — this project's own test suite runs on SQLite per `tests/conftest.py`. Any insert into these tables without manually setting the timestamp will crash.
- [ ] Pattern 5 items above (leagues.py standings auth gap, league_scoring IDOR, roster-analysis hardcoded team_id).
- [ ] Pattern 4 items above (fabricated data on live paths).

---

## Functional Gap — Real Code, Wrong/Incomplete/Misleading Output

- [ ] `backend/app/services/waiver_wire_service.py` + `backend/app/api/v1/endpoints/waiver_wire.py::GET /trending`, `GET /alerts` — query `WaiverWireTrend`/`WaiverWireAlert` tables that **nothing in the codebase ever writes to**. Always return empty. (Also currently impossible to fix without first fixing the Critical migration gap above, since these tables don't exist in a fresh deploy anyway.)
- [ ] `backend/app/api/v1/endpoints/waiver_wire.py::POST /alerts/subscribe` — explicit non-persisting stub (comment: "this would integrate with a notification system"), echoes the request back with no DB write.
- [ ] `backend/app/services/email_service.py` — real, working SMTP code (`smtplib`, real MIME construction), called from real production paths (`auth.py`'s password-reset/verification) — but `Settings` never declares `SMTP_SERVER`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`FROM_EMAIL`, so `smtp_username` is always `None` and the app can never leave dev-log mode in any environment. Fully disconnected from the real in-app notification center (`notification_service.py`) — two parallel "notifications" systems that don't know about each other.
- [ ] `backend/app/services/content_generation_service.py` — the "8 of 10 content types are hardcoded templates with zero AI calls" finding from the original UX review is **still true today**, unresolved beyond honest labeling. Only `player_analysis` and `injury_report` call `ai_service`; the other 8 are static f-strings honestly flagged `ai_generated: False` — labeling is fixed, the underlying capability gap is not.
- [ ] `backend/app/api/v1/endpoints/analytics.py` / frontend "Clustering"/"Visualization" tabs — backend routes exist (`cluster/players`, both `/visualization/*`) but the frontend explicitly renders "Feature Coming Soon" instead of calling them.
- [ ] `frontend/src/services/api.ts` — the 401 response interceptor redirects to `/login`, a route that **does not exist** in `App.tsx` (the real route is `/auth`, and `ProtectedRoute.tsx` correctly uses it — only the interceptor has the wrong path). Every session-expiration mid-use sends the user to a blank page instead of the login form. One-line fix, real UX break for every user eventually.
- [ ] `backend/app/core/celery_app.py` + `backend/app/tasks/*.py` — 7 well-built task functions (weekly waiver content, player spotlights, data sync) with **no beat schedule anywhere, no `.delay()`/`.apply_async()` call anywhere, and no celery worker/beat service in `docker-compose.yml`**. Pure scaffolding; the "background tasks" CLAUDE.md describes do not run.

---

## Dead Code — Decommission Candidates (safe to delete after a product-scope decision, not before)

Grouped by confidence — "confirmed zero callers" items are safe to remove outright; others need a product call first (build the UI for it, or drop it).

**Backend — confirmed zero frontend callers, safe to remove:**
- `backend/app/api/v1/endpoints/blog.py` (all 7 routes; superseded by `content.py`)
- `backend/app/api/v1/endpoints/league_scoring.py`'s sibling dead routes: none — this file is now live (see Cluster B fix history), skip
- `leagues.py`: `GET /{league_id}/analysis`, `GET /{league_id}/matchups`, `GET /{league_id}/comprehensive-analysis`, `PUT /{league_id}/settings`, `POST /yahoo/test-auth`, `GET /yahoo/test-credentials`, `GET /espn/diagnostics`
- `live_draft.py`: the entire "platform-specific" block — `GET /espn/leagues/{id}/info`, `/teams`, `/draft`, `POST /yahoo/authenticate`, `GET /yahoo/leagues`, `GET /yahoo/leagues/{key}/draft`, `GET /session/{id}/status`
- `players.py`: `GET /trending`, `GET /projections/week/{week}`, `GET /{player_id}/stats/{season}`, `GET /{player_id}/quick-analysis`, `POST /sync`, entire `/enhanced/*` family (7 routes)
- `draft.py`: `GET /league-analysis/{id}`, `GET /waiver-candidates/{id}`, `GET /projections/week/{week}`
- `waiver_wire.py`: `/recommendations/priority/{level}`, `/player/{id}/evaluation`, `/insights/weekly-summary`, `/alerts/subscribe`, `/league-aware-recommendations/{id}`
- `post_draft.py`: `_import_sleeper_roster`, `_import_espn_roster`, `_import_yahoo_roster` (never called, each also fake), `GET /roster-grade`, `GET /improvement-suggestions`
- `content.py`: plain `POST /generate`, `GET /content-stats` (also has the Critical bug above)
- `league_management_service.py`: `get_league_insights`, `_generate_weekly_outlook`, `_generate_start_sit_recs`, `_get_top_pickup_targets`, `_optimize_lineup` — zero callers, and `get_league_insights` still contains the exact hardcoded "Lamar Jackson" fake picks that were supposedly fixed at the endpoint level
- `content_generation_service.py`: duplicate method definitions `_get_matchup_info` (x2), `_format_weekly_rankings` (x2, second silently shadows first), plus never-called `_calculate_waiver_priority`, `_format_waiver_wire`
- `espn_service.py` — the older, pre-`espn_service_enhanced` raw-httpx ESPN client; only remaining live caller is the dead `live_draft.py` block above

**Frontend — confirmed zero imports, safe to remove:**
- `components/blog/BlogCard.tsx`, `BlogSearch.tsx`, `ContentGenerator.tsx` (entire directory)
- `components/draft/DraftBoard.tsx`, `TeamRoster.tsx`, `RecommendationCard.tsx`, `DraftSettings.tsx`
- `components/charts/PerformanceTrendChart.tsx` (both exports)
- `components/charts/ChartTypes.ts`'s `POSITION_COLORS`, `DIFFICULTY_COLORS`, `HeatmapData`, `ChartColors` exports
- `services/api.ts`: `leagues.getAnalysis/getMatchups/getStandings`, `waiverWire.getRecommendationsByPriority/getPlayerEvaluation/getWeeklyInsights/subscribeToAlerts`, `draft.getLeagueAnalysis/getWaiverCandidates/getProjections`, `historical.getWeeklyPerformance/getPositionAnalysis/comparePlayers/getSeasonSummaries/getConsistencyAnalysis`, `players.getFromDatabase`
- npm dependencies: `d3`, `@types/d3`, `@tailwindcss/forms` (confirmed unused); `tailwind.config.js` itself is inert under Tailwind v4 (no `@config` directive loads it — real tokens live in `index.css`)

**Needs a product decision before touching (real, working code — just orphaned or duplicative):**
- `advanced_historical_service.py` — better statistics than the wired version; merge or drop
- `enhanced_game_situation_service.py` / `game_situations.py` — best code in the audit, zero users; make canonical or drop
- `matchup_analysis.py` / `matchup_analysis_service.py`'s endpoint surface — genuinely useful (defensive streaming), never surfaced
- `player_data_service.py`'s `/enhanced/*` surface on `players.py` — the service itself is used by other files, only its own endpoint routes are dead
- `content_service.py` — real code, unreachable except through dead `blog.py`

---

## Minor — Cleanup, No Functional Impact

- Unused imports flagged by `pyflakes` across nearly every file audited (full list in each cluster's original report — not reproduced here, run `pyflakes` repo-wide before a cleanup pass to regenerate)
- `console.log` debug leftovers: `LiveDraftPage.tsx` (WebSocket connect/disconnect), `HistoricalPage.tsx` (4 instances, all in a real search flow)
- `HistoricalPage.tsx`'s dev-only debug panel (hardcoded test buttons, dead-code-eliminated in production builds but present in source)
- `LeaguesPage.tsx` — ESPN form resets to `season: 2024` after connect, but its own initial default is `2025`
- Stale/inaccurate comments: `users.py`'s "admin only for now" (code already restricts it correctly), `enhanced_game_situation_service.py`'s stale "placeholder" comment on a method that's since been fixed to return an honest insufficient-data state
- `app/models/player.py` — 5 relationship declarations commented out ("temporarily... to fix immediate issue") and never revisited
- `app/models/waiver_wire.py`, `historical_performance.py` — stale "these would be added to Player model" planning comments left in source
- `auth.py` — password-reset/verification tokens returned in the raw JSON response body in addition to being emailed ("remove in production" comment never acted on)
- `security.py` — inconsistent `datetime` vs. pre-converted `.timestamp()` when building JWT claims (both valid, just inconsistent)
- `content.py`'s pages call raw `api.get/post()` string literals instead of grouped `api.ts` functions, contrary to this project's own documented convention

---

## Suggested Order of Attack

1. **Fix the Alembic migration chain** (enum collision, duplicate `blog_posts`, recreate the 12 missing tables) — nothing else matters if a fresh deploy can't stand up its own database.
2. **Fix the two enum-string comparison bugs** (Pattern 1) — restores real waiver/trade recommendations for every user, likely the single highest perceived-value fix available.
3. **Fix the FLEX optimizer bug** — restores the lineup optimizer to working at all under default settings.
4. Work through the rest of **Critical**, then **Functional-Gap**.
5. Make the three **product decisions** flagged above (game-situations canonical path, advanced-historical merge-or-drop, matchup-analysis surface-or-drop) before touching their code.
6. Decommission the confirmed-dead code once the above decisions are made — much of it is duplicative with what's being fixed anyway.
7. Minor cleanup last, opportunistically.
