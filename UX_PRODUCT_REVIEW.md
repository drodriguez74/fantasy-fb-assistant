# UX & Product Review — Fantasy Football Assistant

Four independent reviews (Creative Director, Fantasy Football Enthusiast, Data Scientist, Product/Business Manager) of the actual running app — not the code in the abstract. Grounded in real Playwright screenshots of the live app (desktop 1440px + mobile 390px, logged in and out) plus live API calls and source tracing. Full persona write-ups are in `scratchpad` during the session that produced this; this document is the synthesis.

## 🔴 Security finding (found during this review, fixed immediately)

`GET /api/v1/leagues/` has **no authentication check at all** — it doesn't take a user, it just reads a single file (`backend/connected_league.json`) off the server's disk and returns it to *any* caller, logged in or not. That file contains real ESPN session cookies (`espn_swid`, `espn_s2`) plus a real league ID. Every account — including one registered seconds earlier for this review — sees the same connected league, because the endpoint has no concept of "whose league is this."

Worse: that file got swept into the git history created earlier this session (commit `8ae3635`, an unqualified `git add -A`) and was never in `.gitignore`. **Already fixed**: untracked the file, added it to `.gitignore` (commit `675a841`). Not yet fixed: the secret is still sitting in that one local commit (never pushed anywhere — no remote is configured, so exposure is contained to this machine), and the endpoint itself is still unauthenticated.

**Status:**
1. ✅ **Fixed** (commit `8b97ec2`): `GET /api/v1/leagues/`, `POST /espn/connect`, and `GET /leagues/{id}/roster-analysis` now require `current_user` and read/write real per-user `UserLeague` rows instead of the shared file. Also fixed a latent crash: `UserService.get_user_league` (singular) didn't exist at all, so every endpoint that already looked correctly-scoped was actually throwing `AttributeError` on every call. Verified live with two fresh accounts: user B sees an empty league list and gets a 404 (not user A's data) requesting user A's league by ID.
2. **Still your call**: rotate the ESPN cookie (log out/in to ESPN) — cheapest way to fully neutralize the leak regardless of git history.
3. **Still your call**: whether to rewrite local git history to purge commit `8ae3635` of the file entirely (destructive — changes every commit hash after it). Repo was never pushed, so this is optional/cosmetic once the cookie is rotated.

Note: `GET /{league_id}/comprehensive-analysis` and `GET /{league_id}/insights` still read from the same global file/hardcoded demo data (e.g. `/insights` returns "Lamar Jackson" as a start/sit recommendation regardless of the actual league) — these were already returning canned data before this fix and weren't part of the original security finding, but are worth the same treatment; not yet done.

## The one bug all four reviewers hit independently

Every persona — without coordinating — flagged the same thing as the single worst problem: **the "AI Draft Recommendations" for Round 1, Pick 6 of a 12-team PPR draft are Frank Gore, Darren Sproles, Steven Jackson, Marshawn Lynch, Adrian Peterson, and Tyler Thigpen — six retired NFL players — each shown with an identical 75% confidence score and identical boilerplate text.**

The data scientist review traced this to its actual root cause, live over the wire:
- `POST /api/v1/draft/recommendations` currently fails server-side (`{"detail":"Failed to get draft recommendations: "}`).
- The frontend (`frontend/src/pages/DraftPage.tsx:114-151`) silently swallows that failure and falls back to a **hardcoded client-side stub**: every player gets `confidence: 75` and the string `"Top available {position} with strong projections"`, built from the first 3 unfiltered entries in the player list — no ranking, no model, no disclosure to the user that this isn't real.
- Even the *real* path is broken: `GET /api/v1/draft/positional-rankings/RB` returns raw, unsorted Sleeper rows with no `projected_points` field, mixed active/inactive/retired status, and no filter excluding players no longer on an NFL roster. There is no `is_active`/retired flag anywhere on the `Player` model at all.

This one root cause explains what looked to the creative director like "broken AI branding," to the enthusiast like "a disqualifying trust failure," to the data scientist like "fabricated confidence scores," and to the PM like "proof the AI claim is currently fiction."

✅ **Fixed** (commit `a65a988`): `GET /draft/positional-rankings/{position}` now filters to players with both a real NFL team and `status: "Active"` — verified by scanning all 947 rows returned across QB/RB/WR/TE and confirming none of the six named retired players remain (one legitimately-active *different* player also named "Frank Gore" does appear, correctly). Ranking now sorts by Sleeper's own `search_rank` instead of raw DB order. The frontend's silent fake-confidence fallback in `DraftPage.tsx` is gone — a failed recommendations call now shows an honest "Couldn't load recommendations. Try refreshing." instead of fabricating data.

## Cross-cutting findings (hit by 2+ reviewers)

| Finding | Evidence | Who flagged it |
|---|---|---|
| Top nav (12 items) visually overlaps the username/Sign Out once logged in, and doesn't collapse to a hamburger on mobile at all — just overflows | `06-draft.png`, `16-mobile-home.png` | Creative Director, PM |
| Historical Performance shows a raw Postgres stack trace (`psycopg2.errors.UndefinedTable`) directly in the UI | `11-historical.png` | Creative Director, Enthusiast, PM |
| Waiver Wire "Recommendations" is empty by default — the highest-frequency weekly touchpoint returns nothing | `09-waiver-wire.png` | Enthusiast, PM |
| Leagues aren't scoped per user — see security finding above | `08-leagues.png` | Enthusiast, PM (independently, before I confirmed it was an auth bug not just a display bug) |
| "AI-powered" claims (content generation, ML predictions) are substantially template/decorative, not reachable model output | `12-blog.png` (6 near-duplicate posts), Analytics page | Creative Director, Data Scientist |
| No onboarding — logged-in Home is identical to logged-out Home plus one "Welcome back" box | `01-home-unauth.png` vs `04-home-auth.png` | PM |

## Persona-specific highlights

**Creative Director** — no visual identity (`tailwind.config.js` has zero theme customization; stock Tailwind gray-50/blue-600), flat shadowless cards with no elevation hierarchy, ~2/3 of the home page viewport is empty void, inconsistent one-off color usage (raw purple/red platform buttons vs. the app's own blue). Recommends a real dark-leaning palette with one saturated accent, a proper injury-status color scale, one shadow tier, and filling home-page dead space with something live.

**Fantasy Enthusiast** — would not trust this for a real draft or waivers today; core promise is actively broken, not just rough. Positives: Players list UI, IA/nav structure maps to a real season, draft settings panel covers the basics. Missing table-stakes vs. ESPN/Yahoo/Sleeper/Underdog: ADP/tier sort, bye-week column, mock draft simulator, trade analyzer, keeper/dynasty support, push alerts. 4,263 individual "Get AI Insights" buttons with no batching is a real workflow problem.

**Data Scientist** — the underlying ML code is *better than the product shows*: real scikit-learn (Ridge/RandomForest/GradientBoosting with train/test split) and real PuLP linear-programming optimization exist and are methodologically sound, but are completely unreachable because `player_historical_performance` was never migrated. Separately, 8 of 10 "AI content" generators are hardcoded template text with zero AI calls, and the two that do attempt a real LLM call hit a straight `AttributeError` (`generate_multi_perspective_analysis` doesn't exist; only `generate_multi_perspective_content` does) — yet every saved post is still stamped `ai_model_used="claude-3"` regardless.

**Product/Business Manager** — not ready for anyone outside the founder. `User.is_premium` exists in the schema, is serialized in every user API response, but gates nothing anywhere — unused scaffolding, not a business model. No sharp positioning statement exists yet ("AI-powered... smart... insights" is generic); the sharpest credible claim available is something like *"the only draft assistant that pools ESPN + Yahoo + Sleeper league settings into one live cheat sheet"* — but the build doesn't reliably support even the ESPN half of that yet.

## Prioritized punch list

**P0 — must fix before anyone but you touches this:**
1. ✅ Scope `GET /api/v1/leagues/` and `/leagues/{id}/roster-analysis` to `current_user` (security bug, see top). — `8b97ec2`
2. Rotate the ESPN session cookie; decide on git history rewrite. — **still open, needs you**
3. ✅ Filter the draft/ranking candidate pool by active roster status; stop the silent fake-confidence fallback in `DraftPage.tsx`. — `a65a988`
4. ✅ Wrap pages in an error boundary — no more raw stack traces in the UI. — `11dffb6` (also hardened the shared `getErrorMessage()` helper to catch raw backend errors across all ~15 pages that use it, not just Historical)
5. ✅ Fix the `generate_multi_perspective_analysis` → `generate_multi_perspective_content` bug; stop stamping `ai_model_used` on template-only content. — `30ee8dd`

**P1 — before any external beta:**
- ✅ Seed real waiver-wire recommendations (rank by ownership-delta/trending-add) instead of an empty default view. — `0bc08e4`, sourced from Sleeper's live trending-add feed, confidence tied to real add-counts
- ✅ Run the missing `player_historical_performance` migration so the real (already-written) ML code can actually execute. — `b792a04`, also healed 11 other tables that had drifted from what alembic believed was applied
- ✅ Cut the beta nav to ~4 items (Home, Draft Assistant, Leagues, Players); flag or hide the rest until each has real data behind it. — `d498cd9`, rest behind a "More" menu, real mobile hamburger added
- ✅ Add ADP/tier sort and a bye-week column to Players. — `3e877a6`
- ✅ Build a real onboarding path (register → connect a league → see one real recommendation). — `52adf5b`, new registrants land on Draft Assistant with real data instead of the marketing homepage

**P2 — roadmap:**
- ✅ Real visual identity (palette, injury-status color scale, card elevation system). — `9f40aeb`, a navy/rust "Friday Night Lights" palette with a real semantic status scale, applied to the highest-traffic surfaces (Players, Draft Assistant, Leagues, Navbar)
- ✅ Mock draft simulator + live in-draft reactivity, merged into one feature. — `b4eeff4`, the Draft Assistant now simulates the other 11 teams' picks (using the same real, active-roster-filtered ranking data as the recommendations engine) so a user can play a full draft with recommendations updating turn by turn
- ✅ Trade analyzer. — `33561e1`, an honest heuristic (inverse Sleeper rank) trade evaluator, explicitly labeled as a heuristic rather than "AI" in the UI copy
- ✅ Decide `is_premium`'s fate. — `62d01ef`, removed (confirmed dead — serialized everywhere, gated nothing anywhere); a real premium tier is a pricing/business decision for later, not something to fake in the meantime
- Keeper/dynasty support, push alerts — not attempted. Both need real infrastructure/product decisions (contract-year rules, a notification service with service workers + scheduling) beyond what fits a bug-fix-shaped pass; flagging rather than shipping a shallow version of either.
- Real external live-draft-room polling (the separate "Live Draft" page connecting to an actual in-progress ESPN/Yahoo/Sleeper draft) remains a confirmed stub. Deliberately out of scope for the mock draft simulator work above — it needs a live real draft to test against and real per-platform polling, a larger project than this pass.
