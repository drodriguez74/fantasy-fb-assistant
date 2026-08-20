# UX & Product Review — Fantasy Football Assistant

Four independent reviews (Creative Director, Fantasy Football Enthusiast, Data Scientist, Product/Business Manager) of the actual running app — not the code in the abstract. Grounded in real Playwright screenshots of the live app (desktop 1440px + mobile 390px, logged in and out) plus live API calls and source tracing. Full persona write-ups are in `scratchpad` during the session that produced this; this document is the synthesis.

## 🔴 Security finding (found during this review, fixed immediately)

`GET /api/v1/leagues/` has **no authentication check at all** — it doesn't take a user, it just reads a single file (`backend/connected_league.json`) off the server's disk and returns it to *any* caller, logged in or not. That file contains real ESPN session cookies (`espn_swid`, `espn_s2`) plus a real league ID. Every account — including one registered seconds earlier for this review — sees the same connected league, because the endpoint has no concept of "whose league is this."

Worse: that file got swept into the git history created earlier this session (commit `8ae3635`, an unqualified `git add -A`) and was never in `.gitignore`. **Already fixed**: untracked the file, added it to `.gitignore` (commit `675a841`). Not yet fixed: the secret is still sitting in that one local commit (never pushed anywhere — no remote is configured, so exposure is contained to this machine), and the endpoint itself is still unauthenticated.

**Recommended next steps, your call:**
1. Rotate the ESPN cookie (log out/in to ESPN) — cheapest way to fully neutralize the leak regardless of git history. Worth doing regardless of the option below.
2. Decide whether to rewrite local git history to purge commit `8ae3635` of the file entirely (destructive — changes every commit hash after it). Given the repo was never pushed, this is optional/cosmetic once the cookie is rotated, but say the word if you want it done.
3. Fix `GET /api/v1/leagues/` and `GET /api/v1/leagues/{id}/roster-analysis` to require `Depends(get_current_active_user)` and query `UserLeague` by `current_user.id`, same as the already-correct `/leagues/{id}/analysis` endpoint. This is the actual root cause and is a P0 alongside everything below.

## The one bug all four reviewers hit independently

Every persona — without coordinating — flagged the same thing as the single worst problem: **the "AI Draft Recommendations" for Round 1, Pick 6 of a 12-team PPR draft are Frank Gore, Darren Sproles, Steven Jackson, Marshawn Lynch, Adrian Peterson, and Tyler Thigpen — six retired NFL players — each shown with an identical 75% confidence score and identical boilerplate text.**

The data scientist review traced this to its actual root cause, live over the wire:
- `POST /api/v1/draft/recommendations` currently fails server-side (`{"detail":"Failed to get draft recommendations: "}`).
- The frontend (`frontend/src/pages/DraftPage.tsx:114-151`) silently swallows that failure and falls back to a **hardcoded client-side stub**: every player gets `confidence: 75` and the string `"Top available {position} with strong projections"`, built from the first 3 unfiltered entries in the player list — no ranking, no model, no disclosure to the user that this isn't real.
- Even the *real* path is broken: `GET /api/v1/draft/positional-rankings/RB` returns raw, unsorted Sleeper rows with no `projected_points` field, mixed active/inactive/retired status, and no filter excluding players no longer on an NFL roster. There is no `is_active`/retired flag anywhere on the `Player` model at all.

This one root cause explains what looked to the creative director like "broken AI branding," to the enthusiast like "a disqualifying trust failure," to the data scientist like "fabricated confidence scores," and to the PM like "proof the AI claim is currently fiction." Fix the data hygiene (filter by active roster status) and make failures visible instead of silently faked, and the single most damaging finding in this whole review disappears.

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
1. Scope `GET /api/v1/leagues/` and `/leagues/{id}/roster-analysis` to `current_user` (security bug, see top).
2. Rotate the ESPN session cookie; decide on git history rewrite.
3. Filter the draft/ranking candidate pool by active roster status; stop the silent fake-confidence fallback in `DraftPage.tsx` (either surface the real error or clearly label a fallback as an estimate).
4. Wrap pages in an error boundary — no more raw stack traces in the UI (Historical page today).
5. Fix the `generate_multi_perspective_analysis` → `generate_multi_perspective_content` bug; stop stamping `ai_model_used` on template-only content.

**P1 — before any external beta:**
- Seed real waiver-wire recommendations (rank by ownership-delta/trending-add) instead of an empty default view.
- Run the missing `player_historical_performance` migration so the real (already-written) ML code can actually execute.
- Cut the beta nav to ~4 items (Home, Draft Assistant, Leagues, Players); flag or hide the rest until each has real data behind it.
- Add ADP/tier sort and a bye-week column to Players — higher value than another AI button.
- Build a real onboarding path (register → connect a league → see one real recommendation).

**P2 — roadmap:**
- Real visual identity (palette, injury-status color scale, card elevation system).
- Mock draft simulator, trade analyzer, keeper/dynasty support, push alerts.
- Decide `is_premium`'s fate — either build the gate or remove the column.
- Live in-draft reactivity (recommendations that update as picks come off the board) — the actual differentiator worth building, but only after the list stops recommending Frank Gore.
