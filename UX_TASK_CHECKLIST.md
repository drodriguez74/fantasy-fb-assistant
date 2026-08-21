# UX Audit — Task Checklist

Derived from `UX_PRODUCT_REVIEW.md` (four-persona review) and verified against current repo state before being written down — items are checked off only where a commit actually fixed them, not where a plan claimed to.

## Immediate (already fixed, prior sessions — listed for completeness/traceability)

- [x] Security: `GET /api/v1/leagues/`, `POST /espn/connect`, `/leagues/{id}/roster-analysis` had no auth check and served one global file to any caller — `8b97ec2`
- [x] Draft Assistant recommended retired NFL players (Frank Gore, Adrian Peterson, etc.) as Round 1 picks — `a65a988`
- [x] Frontend silently fabricated a fake 75% confidence score when the real recommendations call failed — `a65a988`
- [x] Raw Postgres stack traces rendered directly in the UI (Historical page) — `11dffb6`
- [x] `content_generation_service.py` called a nonexistent AI method (`AttributeError` on every call); saved posts falsely stamped `ai_model_used="claude-3"` regardless of whether AI was used — `30ee8dd`
- [x] Waiver Wire "Recommendations" returned empty by default — `0bc08e4`
- [x] `player_historical_performance` and 11 other tables existed in code but not in the DB — `b792a04`
- [x] Nav (12 items) overlapped the account menu, didn't collapse on mobile — `d498cd9`
- [x] No ADP/tier sort or bye-week visibility on Players — `3e877a6`
- [x] No onboarding path for new registrants — `52adf5b`
- [x] No real visual identity (stock Tailwind, no elevation, no semantic status colors) — `9f40aeb`
- [x] No way to play a full mock draft (only one pick, no bot opponents) — `b4eeff4`
- [x] No trade evaluation feature — `33561e1`
- [x] `User.is_premium` existed in schema/API but gated nothing anywhere — `62d01ef`

## Near-Term (real, current, actionable — this pass)

- [x] `GET /leagues/{id}/comprehensive-analysis` and `GET /leagues/{id}/insights` still return hardcoded demo content (e.g. "Lamar Jackson" as a start/sit recommendation, "Justice Hill"/"Rashod Bateman" as pickup targets) regardless of which league or user is asking — same root cause class as the leagues security fix, just not part of that fix's original scope — `be338db`: both now require auth, scope to the caller's real `UserLeague`, 404 for someone else's league; `/comprehensive-analysis` now calls the real `LeagueManagementService`, `/insights` returns honest league metadata instead of fabricated per-player advice
- [x] Blog has genuine duplicate content: 7 saved posts all titled "Week 1 ALL Fantasy Rankings" with no de-duplication guard on save — confirmed live against the current DB — `5f966d4`: traced to two separate save paths that appended suffixes to dodge slug collisions instead of preventing them; added a title+category dedup guard (24h window, updates in place instead of duplicating); dev DB cleaned 18→9 rows, 0 duplicate groups remain
- [ ] Players list renders a "Get AI Insights" button on every one of 4,263 individual player cards with no batching, lazy-loading, or on-demand scoping — a real workflow-friction / performance and cost concern (each is a live API-call trigger), flagged by the fantasy-enthusiast review
- [ ] Audit remaining "AI-powered" UI copy against what's actually true: content_generation_service.py's `ai_generated` flag was fixed to be honest at the data layer, but front-end copy/labels on pages surfacing this content haven't been checked for consistency with that honesty fix

## Long-Term / Explicitly Deferred (needs product decisions, infra, or the user directly — not attempted by agents)

- [ ] Rotate the ESPN session cookie that was briefly exposed — **requires the user**, not something an agent can do
- [ ] Decide whether to rewrite local git history to purge the old commit containing that cookie — **requires the user's explicit go-ahead** (destructive)
- [ ] Keeper/dynasty league support — needs real product decisions (contract-year rules, cost curves) before any implementation makes sense
- [ ] Push/mobile alerts — needs real notification infrastructure (service workers, a scheduling backend), a separate infra project
- [ ] Real external live-draft-room polling (connecting to an actual in-progress ESPN/Yahoo/Sleeper draft) — needs a live real draft to test against; confirmed stub, out of scope for a bug-fix pass
- [ ] Turning the 8 of 10 templated "AI content" generators into real LLM-backed content — a genuine feature build (real prompts, real provider calls, real cost/latency handling), not a bug fix; today's fix made the system honest about what's templated vs. real, it didn't make templated content real
