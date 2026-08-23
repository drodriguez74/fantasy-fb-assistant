# Live Draft Assistant Testing Guide

## Overview
The Live Draft Assistant gives real-time, AI-assisted draft recommendations during a fantasy draft, backed by **real per-platform data** (Sleeper, ESPN, or Yahoo) for a league you've connected — not simulated/sample data. A WebSocket pushes fresh recommendations to the page roughly every 10 seconds.

This guide reflects the app as of the "wire Live Draft Assistant to real Sleeper/ESPN/Yahoo data end to end" work. It was live-tested against the real backend and the real Sleeper and ESPN APIs while writing this doc (see "What was actually verified" at the bottom); the Yahoo path was verified up to a real, external, currently-blocking OAuth configuration issue — see `YAHOO_INTEGRATION_TEST.md`.

## Prerequisites
- Backend running (`uvicorn app.main:app --reload --port 8000`, from `backend/` with the venv active) — default dev URL `http://localhost:8000`.
- Frontend running (`npm run dev`, from `frontend/`) — `http://127.0.0.1:3001` (see `frontend/vite.config.ts`; **not** Vite's default 5173).
- A registered/logged-in user account (`POST /api/v1/auth/register` needs `email`, `username`, `password`, optional `full_name`; then `POST /api/v1/auth/login`).
- **A connected league.** The Live Draft Assistant no longer accepts an arbitrary/typed-in league ID — it only drafts against a league you've connected from the Leagues page (`/leagues`), because that's where Sleeper/ESPN/Yahoo credentials and your team selection get persisted per-user. Connect first, then start a session.

## 1. Connect a League (prerequisite step, on `/leagues`)

Each platform has its own connect flow, reached via the "Yahoo" / "ESPN Connect" / "Sleeper" buttons at the top of the Leagues page. All three follow the same shape: enter league info → (ESPN/Sleeper) pick which team is yours → the league is persisted against your account (`UserLeague` row), not any shared/global file.

### Sleeper — no auth needed, and this path is fully live-testable today
Sleeper's API is public, so connecting only needs a real league ID:
1. Click **Sleeper**, enter the League ID (optionally a Sleeper username, to auto-suggest your team).
2. The app calls `GET /api/v1/leagues/sleeper/teams?league_id=...` to validate the league exists and list its rosters.
3. Pick your team (or skip and set it later), then **Connect League** → `POST /api/v1/leagues/sleeper/connect`.

**Verified live** with a real, public, historical Sleeper league (Sleeper's own documented example league, `league_id=289646328504385536`, a completed 12-team 2018 PPR league — real Sleeper leagues work the same way regardless of season):
```
GET /api/v1/leagues/sleeper/teams?league_id=289646328504385536
→ 200 {"league_name":"Sleeper Friends League","season":"2018","teams":[...12 real rosters with real owner usernames...]}

POST /api/v1/leagues/sleeper/connect  {"league_id":"289646328504385536"}
→ 200 {"success":true,"connected":true,"league":{"id":12,"league_name":"Sleeper Friends League","league_key":"289646328504385536","platform":"SLEEPER","league_size":12,"scoring_format":"PPR","team_id":null}}
```
Any real Sleeper league ID (find it in the league's Sleeper URL, or the app's League Settings) works the same way — no Sleeper login required.

### ESPN — needs league ID + season + SWID/espn_s2 cookies for private leagues
1. Click **ESPN Connect**, enter League ID and Season. For a private league, also paste the `SWID` and `espn_s2` cookie values from your browser while logged into ESPN Fantasy (public leagues can leave these blank).
2. **Continue** first tests the connection (`GET /api/v1/leagues/espn/test-connection`) then loads the league's teams (`GET /api/v1/leagues/espn/teams`) so you can pick which one is yours.
3. **Connect League** → `POST /api/v1/leagues/espn/connect`, persisting `espn_swid`/`espn_s2`/`team_id` on your own `UserLeague` row.

**Verified live** against the real private league already configured in `backend/.env` (`ESPN_LEAGUE_ID`/`ESPN_SEASON`/`ESPN_SWID`/`ESPN_S2` — reuse those values in the form to test locally):
```
GET /api/v1/leagues/espn/teams?league_id=1428917746&season=2026&swid=...&espn_s2=...
→ 200 {"teams":[{"team_id":"1","team_name":"LaMarvelous Saquads",...}, ...12 real teams...]}

POST /api/v1/leagues/espn/connect  {"league_id":"1428917746","season":2026,"swid":"...","espn_s2":"...","team_id":"1"}
→ 200 {"success":true,"connected":true,"access_level":"full","league":{"league_name":"Optis Titans","platform":"ESPN","league_size":12,"scoring_format":"H2H_POINTS",...}}
```
`access_level: "full"` confirms the SWID/espn_s2 cookies gave real private-league access, not just public data.

### Yahoo — OAuth popup, currently blocked (external config issue, not app code)
Clicking **Yahoo** opens a popup to Yahoo's real OAuth login. **As of this writing, Yahoo's own OAuth server rejects this app's auth request** with `invalid_request` / `invalid redirect uri` — confirmed directly (see below), independent of anything in this codebase. The connect *code* itself (auth-URL construction, the popup, the `postMessage` handshake back to the opener, the token exchange, per-user persistence) is real and correct, and was traced up to exactly this external failure point. **Do not expect a full Yahoo OAuth round-trip to succeed in this environment right now.** Full detail and a Yahoo Developer Console checklist for whoever owns the Yahoo app credentials is in `YAHOO_INTEGRATION_TEST.md`.

## 2. Start a Live Draft Session (`/live-draft`)

1. Navigate to `/live-draft` (must be logged in). The page calls `GET /api/v1/draft/my-leagues` and populates a dropdown from **your own connected leagues** (first one auto-selected).
2. If you have no connected leagues yet, the page shows "No Leagues Connected" with a button back to `/leagues` — connect one first (step 1 above).
3. Pick a league, review its Platform/Size/Scoring/Season, click **Start Live Draft**.
4. This calls `POST /api/v1/draft/live-draft/start-session` with `{platform, league_id, scoring_format, league_size}` derived from the selected league. The backend re-derives the real credentials for that league from your own connected `UserLeague` row server-side (it does **not** trust anything else the client might have sent) — for ESPN that's the stored SWID/espn_s2, for Yahoo the stored OAuth token, for Sleeper nothing extra is needed.
5. On success the page opens a WebSocket (`ws://.../api/v1/draft/live-draft/ws/{session_id}`) and loads recommendations, the draft board, and team analysis.

**Verified live** starting a session against the connected Sleeper league above:
```
POST /api/v1/draft/live-draft/start-session  {"platform":"sleeper","league_id":"289646328504385536","scoring_format":"PPR","league_size":12}
→ 200 session_id: "sleeper_289646328504385536_<timestamp>"
   draft_state.status: "complete"  (this league's real 2018 draft already finished)
   draft_state.current_pick / total_picks: 181 / 180
   draft_state.available_players: 50 real Sleeper player records
   draft_state.league_settings: {"starters":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":2,"DEF":1},"bench":6,"roster_size":15,
                                  "points_per_reception":1.0, "scoring_rules": {...real PPR scoring...}, "source":"sleeper"}
```
And against the connected ESPN league:
```
POST /api/v1/draft/live-draft/start-session  {"platform":"espn","league_id":"1428917746"}
→ 200 draft_state.status: "drafting", current_pick/total_picks: 1/192
   available_players[0]: {"full_name":"Jahmyr Gibbs","projected_points":364.86,"ownership":99.88,"platform":"espn",...}
   league_settings: real PPR (points_per_reception 1.0), real starters incl. 2 FLEX, roster_size 19
```
Both are real, live-fetched numbers for real leagues — not placeholders.

## 3. What a Tester Should Actually See

#### "Live" indicator & WebSocket
- A green pulsing dot + "Live" label appears once the WebSocket connects.
- **Verified live**: the socket sends a `{"type":"recommendations_update","data":{...},"timestamp":"now"}` message roughly 10 seconds after connecting, then every ~10s after that (see `asyncio.sleep(10)` in `live_draft.py`'s websocket loop). Note the `timestamp` field is currently the literal string `"now"`, not a real datetime — cosmetic, not a bug worth chasing, but don't be surprised by it.

#### AI Recommendations panel
- `top_recommendations` (top 5), each with player name/position/team, an AI-written `reason`, a `confidence` score, and a `tier`.
- **Real caveat, observed live**: if `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in `backend/.env` aren't currently valid (expired, wrong key, no credit), `ai_service` silently falls back through both providers and `top_recommendations` comes back as an **empty list** — everything else (position needs, draft strategy, draft board, roster tracking, WebSocket updates) still works normally. Check the backend log for lines like `AI provider 'openai' failed (...); falling back` if recommendations look empty — that's an AI-credentials issue, not a Live Draft Assistant bug.

#### Value Picks / Sleeper Picks
- `value_picks` and `sleeper_picks` (up to 3 each) surface high-projection, low-ownership players.
- **Real caveat**: for a **Sleeper** session, these are typically empty — Sleeper's public player-metadata endpoint carries no point projections at all (only bio/roster metadata), so every player's `projected_points` is 0 and nothing clears the value threshold. This is documented, expected behavior, not a bug.
- For an **ESPN** session, real `projected_points` are present, but `value_picks`/`sleeper_picks` only surface *low-ownership* upside plays — a top-50 "available" list dominated by ~99%+ owned stars (as it will be mid-draft) will also legitimately show empty lists here.

#### Available Players Board (`GET /draft-board/{session_id}`)
- Players grouped by position (QB/RB/WR/TE/K/DEF) into up to 4 tiers each, with `available_count` per position.
- **Verified live**: real position groupings and counts from both the Sleeper and ESPN sessions above.

#### Your Roster / Team Analysis
- `GET /team-analysis/{session_id}` returns your actual picks so far, real position-need gaps (using the connected league's real starter/FLEX requirements, not a generic hardcoded shape), and a roster-strength grade.
- **Verified live**: `POST /update-pick` immediately reflected in the next `team-analysis` roster/position-counts.

## 4. Making a Pick
1. Click any recommended player or any player in the Available Players board.
2. Frontend calls `POST /api/v1/draft/live-draft/update-pick` with `{session_id, player_picked}`.
3. **Note**: unlike `start-session`, this endpoint (and `recommendations`, `draft-board`, `team-analysis`, `session/{id}/status`, `DELETE session/{id}`) do **not** require a bearer token or check session ownership — anyone who knows the `session_id` can poll or update it. This matches the real current code; keep it in mind if testing with multiple accounts/sessions concurrently.
4. The backend also pushes a `pick_update` WebSocket message to whoever's connected to that session.

## 5. API Testing (curl)

All examples assume the backend is on `http://localhost:8000` and `TOKEN` is a real bearer token from `POST /api/v1/auth/login`. **Note the real router prefix is `/api/v1/draft/live-draft/...`**, not `/api/v1/live-draft/...`.

#### Start Session (requires auth — the endpoint looks up your own connected league's credentials)
```bash
curl -X POST http://localhost:8000/api/v1/draft/live-draft/start-session \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "sleeper",
    "league_id": "289646328504385536",
    "scoring_format": "PPR",
    "league_size": 12
  }'
```
For `platform: "espn"` or `"yahoo"`, you must have already connected that exact `league_id` via `/leagues/espn/connect` or `/leagues/yahoo/connect` for the calling user — otherwise you get a `400` with an explicit "connect your league first" message rather than a generic failure.

#### Get Recommendations
```bash
curl http://localhost:8000/api/v1/draft/live-draft/recommendations/SESSION_ID
```

#### Get Draft Board
```bash
curl http://localhost:8000/api/v1/draft/live-draft/draft-board/SESSION_ID
```

#### Get Team Analysis
```bash
curl http://localhost:8000/api/v1/draft/live-draft/team-analysis/SESSION_ID
```

#### Make a Pick
```bash
curl -X POST http://localhost:8000/api/v1/draft/live-draft/update-pick \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SESSION_ID",
    "player_picked": {
      "player_id": "6462",
      "full_name": "Ellis Richardson",
      "position": "TE",
      "team": null
    }
  }'
```
`player_picked` accepts arbitrary JSON — real player records commonly have `null`/numeric fields (no team for a free agent, no `projected_points`, etc.), which a strict `Dict[str,str]` schema would reject.

#### Session Status / End Session
```bash
curl http://localhost:8000/api/v1/draft/live-draft/session/SESSION_ID/status
curl -X DELETE http://localhost:8000/api/v1/draft/live-draft/session/SESSION_ID
```

#### WebSocket
```
ws://localhost:8000/api/v1/draft/live-draft/ws/SESSION_ID
```
**Verified live** with a raw Python `websockets` client: connects immediately, then delivers a `recommendations_update` message ~10 seconds later, matching the code exactly.

## 6. Expected Behavior Summary

| What | Real behavior observed |
|---|---|
| Session ID | `{platform}_{league_id}_{unix_timestamp}` |
| Sleeper session | No auth; draft state pulled from Sleeper's real public API; no player projections, so value/sleeper picks are usually empty |
| ESPN session | Requires a connected league (SWID/espn_s2); real per-league scoring & roster settings; real `projected_points`/`ownership` per player |
| Yahoo session | Requires a connected league with a live OAuth token; **currently unreachable end-to-end** — see the blocker above |
| AI recommendations | Real AI-generated when `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` are valid; silently empty (not an error) when both providers fail |
| WebSocket cadence | ~10s between `recommendations_update` pushes; immediate `pick_update` on a pick |
| Position needs / strategy | Derived from the real connected league's starter/FLEX/bench shape (falls back to a generic QB1/RB2/WR2/TE1/K1/DEF1/15-man shape only when no real settings could be fetched) |

## 7. Troubleshooting

1. **"No ESPN/Yahoo league connected for this league ID"** (400 from `start-session`) — you tried to start a session for a platform/league you haven't connected from `/leagues` yet with this account. Connect it first.
2. **Empty `top_recommendations`** — check the backend log for `AI provider '...' failed (...)`. This is an AI-provider credentials/quota issue, independent of the draft data pipeline (see section 3).
3. **Yahoo won't connect past the popup** — expected right now; see `YAHOO_INTEGRATION_TEST.md`.
4. **WebSocket never updates** — confirm the backend is actually reachable at the same origin `frontend/src/services/api.ts` is configured for (`http://localhost:8000/api/v1`, hardcoded — there's no env-var override). If your backend runs on a different port, the frontend will not reach it.
5. **"Your Yahoo connection has expired"** — Yahoo access tokens last ~1 hour and this app does not silently refresh them mid-poll (see `draft_assistant_service.py`'s `_get_yahoo_draft_state` docstring for why); reconnect from `/leagues`.

## Architecture (real, current)

- **Frontend**: `frontend/src/pages/LiveDraftPage.tsx` (draft session UI + WebSocket), `frontend/src/pages/LeaguesPage.tsx` (connect flows + team pickers).
- **Backend endpoints**: `backend/app/api/v1/endpoints/live_draft.py` (session/recommendations/board/analysis/pick/WebSocket), `backend/app/api/v1/endpoints/leagues.py` (per-platform connect flows), `backend/app/api/v1/endpoints/draft.py` (`GET /my-leagues`).
- **Core logic**: `backend/app/services/draft_assistant_service.py` — platform-dispatched draft-state fetching, AI recommendation generation, consensus ranking, position-needs/value-pick calculation.
- **Per-platform data**: `backend/app/services/sleeper_service.py` (public API), `backend/app/services/espn_service_enhanced.py` (SWID/espn_s2-authenticated), `backend/app/services/yahoo_service.py` (OAuth2-authenticated).
- **Consensus ranking**: `backend/app/services/consensus_ranking_service.py`, `backend/app/services/fantasypros_service.py`.
- **Session storage**: in-memory (`DraftAssistantService.active_drafts`), not persisted to the DB — a backend restart loses all active sessions.

## What Was Actually Verified vs. Code-Read Only
- **Verified live end-to-end**: registering/logging in a test user; Sleeper connect (`/leagues/sleeper/teams`, `/leagues/sleeper/connect`) against a real public league; ESPN connect against the real private league configured in `backend/.env`; starting a draft session for both Sleeper and ESPN; `recommendations`, `draft-board`, `team-analysis`, `update-pick`, session status/end; the WebSocket's `recommendations_update` push.
- **Code-read only, not independently live-tested**: the Yahoo draft-session data path (`_get_yahoo_draft_state`) beyond what the OAuth blocker allows, and the frontend UI rendering itself (the dev servers used for this pass were driven via API calls, not a live browser session) — the described UI behavior is taken directly from `LiveDraftPage.tsx`'s and `LeaguesPage.tsx`'s real source, not observed pixel-by-pixel in a browser.
