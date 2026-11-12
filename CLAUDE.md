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

pip install -r requirements-dev.txt         # runtime deps + pytest (Render installs requirements.txt only)
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
npm test            # vitest (pure helpers: src/**/__tests__)
npm run preview     # serve production build
```

### Full stack via Docker

`docker-compose.yml` is stale (see `memory.md`): don't use it, and don't fix or delete it without asking the founder. Local dev runs the backend and frontend directly against the Supabase database.

### CI

`.github/workflows/ci.yml` runs `pytest` and the frontend lint, tests and build on every push to any branch. Render deploys `main` only after this workflow passes: Auto-Deploy is set to "After CI Checks Pass" in the Render dashboard (2026-11-12). The live service (`fantasy-fb-assistant`) is not managed by `render.yaml`, so settings and env vars change in the dashboard; the file is a record, kept in step by hand. Vercel deploys on its own but runs the same `tsc -b && vite build`, so a type or build error stops it; lint and vitest failures do not, so keep the run green.

## Architecture

### Backend layering

`app/api/v1/endpoints/*.py` (route handlers, one file per domain) → `app/services/*.py` (business logic, one class per concern) → `app/models/*.py` (SQLAlchemy models). Endpoints are registered in `app/api/v1/router.py`; add new endpoint modules there. Pydantic settings live in `app/core/config.py` and are read from `backend/.env` (`.env.example` documents required keys).

Models are wired together in `app/models/__init__.py`, which imports every model class and then attaches cross-model `relationship()`s explicitly (rather than declaring them inline on each model). New models must be imported and related there or they won't be registered/joinable.

### Multi-platform league integration

`LeagueManagementService` (`app/services/league_management_service.py`) is the entry point for league *analysis* (roster grading, matchups, standings, waiver/trade recommendations bundled into one response) and branches on `league.platform.value.upper()` (compare the resolved `.value`, never the raw `Enum` against a string literal — `UserLeague.platform` is a plain `enum.Enum`, and comparing it directly to `"YAHOO"`/`"ESPN"` is always `False`; this exact bug once made the whole analysis path silently return `{}` for every user). `get_comprehensive_league_analysis` has real Yahoo and ESPN implementations (ESPN since 2026-09-05). Sleeper deliberately returns an honest "not supported for this platform yet" error rather than partial or fake data; building it out is real, tracked future work, not a quick fix.

Per-platform credentials: Sleeper needs none (its data is public); ESPN needs a per-user `SWID`/`espn_s2` cookie pair, saved by `POST /leagues/espn/connect` (ESPN has no OAuth for fantasy); Yahoo needs a per-user OAuth token, saved by `POST /leagues/yahoo/connect`. All are stored on the connecting user's own `UserLeague` row, never on a shared service instance, and every platform service method takes the token or cookies as a parameter.

The draft assistant (live and mock draft) was removed on 2026-09-08; Post-Draft Analysis and Draft History were kept on purpose as in-season reports. ESPN exposes no in-progress draft picks to a backend (every competitor reads the draft page with a browser extension), so don't rebuild a live draft feature without that plan.

### Waiver & trade engine

In-season waiver and trade advice for ESPN/Yahoo leagues uses one valuation model.
- `league_value_data.py` (platform adapters) loads real rosters, free agents, starter slots and projections.
- `league_value_model.py` (pure, unit-tested) computes the optimal lineup, replacement level, and team value (lineup + 20% of bench value above replacement).
- `league_advice_service.py` shapes the responses: waivers, DEF/K streaming boards, and trades.

Endpoints: `GET /leagues/{id}/waiver-recommendations`, `/streaming`, `/trade-suggestions`. Both League Detail's Waiver tab and the Waivers page render waivers through the shared `components/waivers/LineupWaivers.tsx`.

All values are **rest-of-season**. ESPN's `projected_total_points` already is. Yahoo has no per-player projections, so it sums Sleeper's weekly rows via `weekly_projections.fetch_rest_of_season_projections`. Never use Sleeper's season feed (`fetch_season_projections`) for mid-season value: it's a static preseason total that ignores injuries and games already played.

The `/waiver-wire/*` routes (`WaiverWireService`) are the older league-wide Sleeper trending feed, kept only as the no-league view.

**Vegas odds** (`odds_service.py`, optional `ODDS_API_KEY` from the-odds-api.com): one request fetches every NFL game's spreads and totals from DraftKings, FanDuel and Hard Rock Bet. Each team's implied total is (median total − its median spread) / 2. Results are cached 12h (college lines refetch only Thu–Sat, `CFB_LINE_WEEKDAYS`); each fetch costs 2 credits. They feed the DEF/K streaming boards (a defense's opponent implied total, a kicker's own team total). Without a key, or on any failure, odds are simply omitted. Never log the request URL: it carries the key. Player props are fetched per game (16 markets = 16 credits per game since 2026-10-15; the PrizePicks book adds nothing, measured 2026-10-13), once in the 36h before kickoff (`PROP_FETCH_LEAD`) and once more in the last 2h (`PROP_CLOSE_LEAD`, the closing line; since 2026-10-20). Render has no scheduler, so GitHub Actions (`.github/workflows/board-build.yml`, since 2026-11-09) calls `POST /betting/cron-build` (secret `DIGEST_CRON_SECRET`) hourly 7am–10pm ET Thu–Mon. The Mac's launchd job (`com.fantasyfootball.board-close`, `backend/scripts/build_board.py`) is only a backup: it misses runs while the Mac sleeps, which cost weeks 8–9 their closing lines. Every Odds API response is persisted in the `odds_cache` table, because Render's free tier restarts often and an in-memory cache would refetch on each cold start. Prop fetches stop at a 60-credit reserve.

### Bets (`/bets`) — full record in `docs/guides/BETTING_GUIDE.md`

Read the guide before touching betting code: it has the method, every decision with its reason and evidence, the data-access limits and open items. Code: `betting_model.py` (pure math), `betting_service.py` (NFL + college boards, PrizePicks), `betting_tracking.py` (record and grade), `odds_service.py`, `espn_projections.py`, `espn_game_predictor.py`, `prizepicks_board.py`. Rules that are easy to break:
- **The market anchors everything** (70/30 blend for props). A prop bet needs EV ≥ 3% from Sleeper *and* from ESPN on its own (each blended with the books; stake = the smaller size), not just ESPN leaning the same way; passing yards are exempt (`ESPN_CHECK_EXEMPT`) but capped at 1u when ESPN projects the other side (`SPLIT_PROJECTION_MAX_UNITS`). It also needs a **price edge** (`PROP_MIN_BOOK_EV`, 2026-11-09): the price must be fair on the books' own chance, or the pick is `model_only` and drops to watch; model-only bets predicted 55% and hit ~49% (2025 + live). PrizePicks pairs/entries use the same idea: each pick is priced at `pp_value`, the smaller of our blend and ESPN's. Bump `ENGINE_VERSION` whenever a change alters what gets recommended. Quarter-Kelly, 3u cap (college 1u), no 4u until calibration earns it.
- **NFL game lines are market-only** (`GAME_MODEL_WEIGHT = 0`, key-number spreads via `market_margin_pmf`): on real closing lines the Sleeper game model carried no information, so a game-line bet is only a book off the consensus. Don't give it weight again without an out-of-sample gain from `scripts/backtest_game_lines.py`.
- **The card always has 3+ picks** (founder's call): fills are "Best available" (confidence `fill`, flat 0.5u, `fill_card`), labeled and tracked as their own tier. Never meet the minimum by loosening the bet rules or inflating EV.
- **"Most likely to win"** (`most_likely`): PrizePicks picks at a calibrated 70%+ win chance that the engine backs (engine ≥ books) from players with 50%+ lagged snap share (`MOST_LIKELY_MIN_SNAP`), tracked as `pp_leg` and checked predicted-vs-actual in Results. Tune the engine only through `scripts/tune_from_results.py` (held-out gain required).
- **Correlations are measured, not guessed** (`LEG_CORRELATION`, `COVER_TOTAL_RHO`; guide section 9). Same-game legs are correlated for teammates too: a 3+ pick entry can hold a QB and his own receiver. A prop vs its game's total uses `PROP_TOTAL_CORRELATION` (QB passing yards +0.40). Two stats of one player (PrizePicks allows it) use the measured `SAME_PLAYER_CORRELATION`; unmeasured pairs aren't priced, and the generated suggestions stay one pick per player.
- **Don't undo the bias fixes:** slate centering (`fit_projection_scale`), game-total TD de-vig (`td_rate_scale`, recalibrated ×1.30 by `TD_RATE_CALIBRATION` on held-out data, 2026-11-09), and volume exponent 0.25. Each fixed a measured fake edge. Don't "fix" a lean by shrinking CVs; that makes the model overconfident.
- **Betr replaced PrizePicks (2026-11-09; Hard Rock first, Betr second).** Betr has no feed: the founder pastes screenshots (or text) of stat tabs from picks.betr.app (`betr_screenshot.py` / `POST /betting/betr-screenshots`, a vision read per image; `betr_board.py` / `POST /betting/betr-board` for text), stored in the PrizePicks upload slot with `platform: "betr"` and priced by the same code. Special lines (discounted, or >15% off the books) are never paired at the standard multiplier. Payouts from the founder's slip: Perfect 3x/6x for 2/3 picks, Flex 2-pick 2x/0.5x (`BETR_PERFECT_PAYOUTS`, `BETR_FLEX_PAYOUTS`). **Betr pays less on same-game picks**, so Betr pairs/entries use one pick per game (`distinct_games`) and correlated stacks are off for Betr. Only read Betr through Chrome when the founder asks.
- **PrizePicks:** every entry needs players from 2+ teams (5 from one team + 1 other is fine; founder-confirmed), so a 2-pick never pairs teammates while 3+ pick stacks can. Correlated stacks (`correlated_stacks`) are priced from the books' chances only; keep TD props out of them (books quote Yes only). The board comes only from the founder's browser upload: the Chrome extension blocks prizepicks.com and the API is behind a DataDome CAPTCHA, so never scrape or get around it. `allowed_wager_types` is a string. College league label is `"NCAAFB"`, used as-is. College props are shelved (`CFB_PROPS_ENABLED = False`).
- **Spread settings are backtested:** `backend/scripts/backtest_projections.py` (free Sleeper data) validated the CVs and projection error on 4,755 real 2025 player-weeks. Change them only if a rerun shows an out-of-sample gain. TimesFM 3 was tested as a projection source and rejected (guide, section 9).
- **Books:** seven books feed the consensus (`odds_service.BOOKMAKERS`; up to 10 cost the same credits). `BETTING_MY_BOOKS` limits units to books the user can bet at (Florida: Hard Rock Bet only). Every pick's closing line is stored until kickoff (`update_closing`, CLV in Track record).
- **Board speed:** `GET /betting/board` goes through `betting_service.serve_board`: the last built board per sport is saved in `odds_cache` (`board:nfl` / `board:cfb`) and served at once, with a background rebuild when it's over 15 minutes old (`refreshing: true`). Concurrent builds share one (`_build_lock`). The saved copy is never put in `_board_cache` (logging an entry needs a real build's `_pricing_context`). Uploaded PrizePicks lines are simulated once per (player, stat).
- **Credits** ($30 tier, 20,000/month since 2026-10-15; the founder may drop back to free). Each game's props are fetched in the 36h before its kickoff (`PROP_FETCH_LEAD`) and again in the last 2h (`PROP_CLOSE_LEAD`): ~480 credits a week for 16 markets; game lines every 12h, college only Thu–Sat. On the free tier (500/month) that no longer fits: set `ODDS_PLAN=free` in Render before the paid plan lapses (`odds_service.free_plan`, 2026-11-09): 5 core prop markets once per game, no closing fetch, game lines once a day, ~410 credits a month. Real use on the $30 plan: ~2,200 a month (~11%). **Markets** (`odds_service.PROP_MARKETS`): the 4 core stats + anytime TD, 7 more PrizePicks stats (pass TDs, attempts, completions, INT, rush attempts, rush+rec, pass+rush) and the books' alternate lines for the core 4, used only to price PrizePicks goblins/demons (`_pp_fair_over`). `scripts/backtest_props.py` is pinned to the original five (`HIST_MARKETS`): historical calls cost 10x. Every Odds API response is persisted in `odds_cache`; never log the request URL (it carries the key).
- **My entries** (`user_entries.py`, `user_entries` table): the founder's real PrizePicks entries, snapshotted via `betting_service.snapshot_leg` (needs the last NFL board build's `_pricing_context`) and graded with PrizePicks' push/DNP drop-out rules. They're entered by hand: never try to pull them from PrizePicks. The same form logs Hard Rock bets (platform `sportsbook`, straight or parlay, odds per leg); college Hard Rock bets (`sport: "cfb"`, game lines only, each leg's kickoff) grade from ESPN's college scoreboard like the Shows tab.
- **Shows** (`analyst_picks.py`, `analyst_picks` table, Shows tab): radio/podcast picks from transcripts the founder supplies (never download SiriusXM; transcripts stay in gitignored `backend/transcripts/`). YouTube NFL/college picks shows (VSiN's uploads, Fantasy Alarm's live streams, and for college only Action Network's Big Bets On Campus, added 2026-10-17 as the one extra source: more shows add noise, not edge; `CHANNELS` in the script, each with its own title filter) are pulled automatically by `scripts/fetch_show_transcripts.py` (deps in `requirements-scripts.txt`, never on Render; run 3x a day on the founder's Mac by launchd job `com.fantasyfootball.show-transcripts`, plist in `backend/scripts/launchd/`). A SessionStart hook (`.claude/settings.json` → `scripts/transcript_status.py --hook`) fetches new shows and lists every transcript not yet in the tracker (`backend/transcripts/import_log.json`); import those at the start of the session. Picks are extracted by hand into JSON (with a `"transcript"` field naming the .txt, which records it in the tracker) and loaded with `scripts/import_analyst_picks.py`; a transcript with nothing to import is marked with `transcript_status.py --skip FILE --note`; each keeps a snapshot of our board and is graded like My entries. Tracked only: never feed a show into pricing without a held-out gain on 300+ graded picks. The Shows verdict (`showTypes.verdictFor`) says Fade only when our card bets the other side, never merely because the model leans away.
- **Weeks:** everything on the Bets page is filed under the NFL betting week (Thu–Mon), college included (college week 6 = NFL week 5). Tabs show This week next to Season; hit/miss lists show one week at a time.
- **Tracking:** every priced line is saved once (no-bet lines too); bets are never overwritten. Every pick, suggested PrizePicks ticket (`tracked_entries`) and logged entry carries `ENGINE_VERSION` (bump it on any pricing change); `GET /betting/audit` (+ CSV) lists a week's recommendations and results. College lines are `kind = "cfb_game"`. Grading uses Sleeper stats and ESPN scoreboards, never credits. Watch for numpy scalars in responses: they 500 FastAPI's encoder.

### Memory on Render (512 MB free instance)

Keep heavy libraries out of startup imports. scikit-learn, statsmodels, pandas and pulp (~200 MB) once loaded at startup through the analytics endpoints and caused an out-of-memory restart (2026-10-07). Those endpoints and their libraries were removed on 2026-11-12 (Analytics, Advanced Analysis and Game Situations: no tests, no auth on some routes, little use), so `requirements.txt` now holds only what the app imports; numpy and scipy are the only numeric libraries. Idle is ~137 MB and the Bets peak ~210 MB. Any new heavy dependency should be imported where it's used, not at module top, and research-only libraries go in `requirements-scripts.txt`.

### AI content generation

`ai_service.py`'s `_generate_with_fallback()` is the one consolidated primitive every AI-generation call should go through — it tries the primary provider (OpenAI by default), specifically detects `openai.RateLimitError`/`anthropic.RateLimitError` for an immediate fallback to the secondary provider, and also falls back on other real failures (auth, network, malformed response). It routes through two model tiers (`FAST_OPENAI_MODEL`/`FAST_ANTHROPIC_MODEL` for short, low-stakes generations; `DEEP_*` for multi-perspective analysis and consensus synthesis) — don't hardcode a model name at a new call site, reference these tier constants. `_generate_openai`/`_generate_anthropic` still exist as legacy non-raising wrappers for a couple of call sites that predate this consolidation; don't add new callers of those, use `_generate_with_fallback`.

`content_generation_service.py` generates content from 5 fixed "perspectives" (Conservative, Aggressive, Data-Driven, Situational, Dynasty) synthesized into a consensus recommendation — see `docs/guides/DRAFT_ASSISTANT_GUIDE.md`. Only 2 of its 10 `ContentType`s (`player_analysis`, `injury_report`) actually call the AI; the other 8 are honest, explicitly-labeled (`ai_generated: False`) static templates — this is a known, tracked capability gap (`docs/audits/DECOMMISSION_TASK_LIST.md`), not an oversight, so don't assume a given content type is AI-backed without checking.

### Player rankings & scoring

Three real systems, easy to confuse:
- **Consensus ranking** (`consensus_ranking_service.py`) blends whichever of Sleeper `search_rank`, ESPN `percent_owned`, Yahoo `ownership_percentage`, and FantasyPros `rank_ecr` are actually available for a player, each converted to a percentile *within its own population* before averaging (never average raw values across sources — the scales aren't comparable). FantasyPros only contributes once `FANTASYPROS_API_KEY` is set in `.env` (free tier available); everything degrades cleanly with fewer sources.
- **Real per-league scoring rules** (`scoring_rules.py`) extracts a connected league's actual scoring settings (PPR value, and — new — the full stat picture: completions/incompletions/attempts, yardage, TDs, INTs, fumbles) from Sleeper/ESPN, replacing the old hardcoded-PPR assumption.
- **Manual scoring override** (`league_scoring.py` endpoints, `LeagueScoring` model) lets a user hand-configure scoring rules that take priority over auto-detected settings when both exist for the same league — useful when auto-detection isn't available for a platform yet, or a user wants to model a hypothetical.

### Data confidence UI pattern

`frontend/src/components/common/DataConfidenceBadge.tsx` — a small three-state badge (`computed` / `heuristic` / `insufficient`) used anywhere a number on screen is derived rather than typed in by a human, so a real computed value never looks visually identical to a fabricated one. Use it on any new page that surfaces a score, rank, or projection.

### Auth

JWT auth via `python-jose`; `app/api/deps.py::get_current_user` decodes the bearer token and loads the `User` (401 if the user row is gone: the old auto-created demo user was removed on 2026-11-12, and the founder's account is user 1). Passwords are hashed with `bcrypt` directly (`core/security.py`; passlib was dropped, and passwords are cut to bcrypt's 72 bytes the way passlib did, so old hashes still verify). Token types matter: access tokens carry no `type` claim, and `verify_token` refuses refresh, reset and verification tokens; `/auth/refresh` uses `verify_refresh_token`. Account lockout (`user_service.py::authenticate_user`) compares `locked_until` against `datetime.now(timezone.utc)`, not `datetime.utcnow()`: the columns are timezone-aware, and mixing naive and aware datetimes once caused a 500 on any account with an expired lockout.

**Registration is closed by default.** `POST /auth/register` only accepts emails in `REGISTRATION_ALLOWED_EMAILS` (comma-separated, or `*`); unset means nobody. Any account can call the AI and vision endpoints, so don't reopen sign-up without a per-user limit on those. The uploaded Betr / PrizePicks board is one shared slot that everyone's picks are priced from: only the owner (user id 1) or the emails in `BOARD_UPLOAD_EMAILS` may replace it (`betting.require_board_uploader`).

**Rate limits** (`core/rate_limit.py`, in memory, per IP): login, register, refresh, password reset, the AI content and player-analysis routes, the public `GET /players/{id}` (it calls the AI) and the Betr / entry screenshot reads. Use `dependencies=[Depends(rate_limit(name, limit, seconds))]` on any new route that costs money. Every route outside `auth` and the public player and blog reads requires a login; keep it that way.

### Email

`email_service.py` sends real SMTP mail for password-reset/email-verification when `SMTP_SERVER`/`SMTP_USERNAME`/etc. are set in `.env` (all optional); with none configured it stays in an honest dev-log mode (logs the would-be email, returns success, never crashes) rather than silently no-op'ing. This is deliberately a separate channel from the in-app notification center below — different transport, different trigger model, not meant to be unified.

### Background tasks

There is no background task system. Celery/Redis were removed (`docker-compose.yml`, `requirements.txt`) after an audit found the scheduled tasks either called into an already-abandoned content pipeline or never persisted their results anywhere — see git history ("Decommission dead Celery/Redis background-task scaffolding") for the reasoning if reviving scheduled tasks is ever worth it. The real in-app notification center (`notification_service.py`, `Notification` model, `GET /notifications/*`, the navbar bell) is populated synchronously as a side effect of real requests (e.g. waiver recommendations), not on a schedule.

### Frontend

`src/services/api.ts` is a single axios instance (with a request interceptor for the bearer token and a response interceptor that redirects to `/auth` on 401 — not `/login`, which doesn't exist as a route) plus grouped endpoint functions (`auth`, `leagues`, `players`, ...) — add new API calls there rather than calling axios directly from components. Routing/pages live in `src/pages/` (one file per route), reusable UI in `src/components/<domain>/`. Auth state: the `useAuth` hook and context are in `src/hooks/useAuth.ts`, the provider in `src/components/auth/AuthProvider.tsx` (a file that exports a component can't also export a hook: the fast-refresh lint rule). The two big pages are split by tab: `LeagueDetailPage` renders `components/leagues/detail/*Tab.tsx` and `WaiverWirePage` renders `components/waivers/page/*Tab.tsx`; each folder has a `types.ts` for response shapes and pure helpers. The page owns the state and data loading and passes props down, so add a tab as a new component there rather than growing the page.

## Reference docs

Detailed guides live under `docs/` and are worth reading before touching the relevant area: `docs/guides/BETTING_GUIDE.md` (bets: method, decisions log, data limits), `docs/guides/AUTHENTICATION_GUIDE.md` (auth flows), `docs/guides/DRAFT_ASSISTANT_GUIDE.md` (draft recommendation engine + perspective/consensus format), `docs/guides/ENHANCED_PLAYER_DATA.md` (player data model), `docs/testing/YAHOO_INTEGRATION_TEST.md` / `docs/testing/LIVE_DRAFT_TEST.md` (manual test procedures for those features), `docs/guides/API_GUIDE.md` (endpoint shapes). `docs/audits/DECOMMISSION_TASK_LIST.md` is a point-in-time audit of what's real/broken/dead across the whole codebase — useful context, but check git log for anything that's since been fixed before trusting an item in it as still-current. As of this session's docs pass, all of the above have been re-verified against real code and live-tested where practical — but this codebase moves fast; re-verify anything load-bearing rather than trusting a doc blindly.
