# Bets: how it works, what we decided, and why

The single record for the betting feature (`/bets`). It covers what was built, the method, every decision with its reason and evidence, data-access constraints, and what's still open. Last updated 2026-10-07.

Code: `backend/app/services/betting_model.py` (pure math), `betting_service.py` (boards), `betting_tracking.py` (record and grade), `odds_service.py`, `espn_projections.py`, `espn_game_predictor.py`, `prizepicks_board.py`; frontend `frontend/src/pages/BettingPage.tsx` and `frontend/src/components/betting/`. Endpoints: [API_GUIDE.md → Betting](API_GUIDE.md#betting-betting).

> For entertainment and research. Every number here is a model estimate. The founder places all wagers; the app only fetches and prices data.

---

## 1. What's built

| Area | What it does |
|---|---|
| NFL player props | Pass/rush/rec yards, receptions and anytime TD from DraftKings, FanDuel and Hard Rock, priced by simulation against the market, sized in units. |
| NFL game lines | Spreads and totals with a real model: Sleeper-projected team scores, cross-checked by ESPN. |
| Cover + over/under combos | The four same-game parlays per game, with chance and fair odds to compare against a book's SGP price. |
| PrizePicks | The full board, uploaded daily: 2-pick pairs, 2–6 pick Power/Flex entries, and goblin/demon hit chances. |
| College football | Game lines only, behind an NFL / College switch. ESPN's predictor models spreads; college props are built but shelved. |
| Tracking & grading | Every priced line saved, then graded automatically. The Results tab shows record, units, ROI, calibration and NFL vs College. |
| Bets page | "This week's card" (the actual bets with dollars and kickoff times), tiered cards, and tabs for the evidence. |

### Timeline (all 2026-10-06/07)

| Commit | Change |
|---|---|
| `dc77453` | Vegas implied totals on DEF/K streaming (first use of The Odds API) |
| `ada5cbb` | Bets page: props + game lines, Monte Carlo + de-vigged market, quarter-Kelly units; `odds_cache` table |
| `2445cee` | Every priced line tracked in `bet_picks` and graded; Results tab |
| `2c6844f` | PrizePicks 2-pick finder; slate centering, TD de-vig and volume-exponent fixes; ESPN cross-check |
| `9026f3e` | Full PrizePicks board upload; no teammate pairs |
| `0499f71` | Game-line model, cover/total combos, watch tier, 2–6 pick entries |
| `5fdce4b` | College game lines + NFL / College switch; college props shelved |
| `d056b58` | College lines tracked and graded |
| `a84835e`, `14fe535` | Redesign around "This week's card" after a strategist + design review |
| (memory fix) | Analytics libraries lazy-loaded after a Render out-of-memory restart |

---

## 2. The method (current)

**Market.** Each book's two-way prices are de-vigged (multiplicative) and the median taken across DraftKings, FanDuel and Hard Rock Bet. This is the anchor: 70% of every estimate.

**Player model (30%).** A two-level Monte Carlo of Sleeper's weekly projected stat line, 20,000 draws:
1. The true mean is drawn around the projection (SD 30% of it).
2. The outcome is drawn around that mean. Yardage is gamma, with a coefficient of variation scaled by volume (mean^-0.25); receptions and TDs are Poisson.

**Slate centering.** Each market's projections are rescaled each week so the median prop's simulated P(over) matches the market (`fit_projection_scale`). Week 5: rec yds ×1.13, rush ×1.15, pass ×1.07, receptions ×1.05, TD ×0.93.

**Anytime TD de-vig.** Books quote "Yes" only, so each game's implied scoring rates are scaled to the TDs its Vegas total supports (`td_rate_scale`; 0.105 TDs per point, 95% to listed players). Typical scale is 0.66–0.76: a 30% price is really about 21%.

**ESPN cross-check.** ESPN's public weekly projections are centered the same way. A side gets units only if ESPN also favors it over the market.

**Game model.** Projected team points are 6 × (rush + rec TDs) + kicker points, from Sleeper, centered on totals. Spreads are checked against ESPN's matchup predictor (win prob → margin, SD 13.5); totals against ESPN projections. Week 5: Sleeper totals vs market correlation 0.93, margins 0.97.

**Sizing.** EV at the best available price. A bet needs EV ≥ 3% plus the model *and* the check agreeing. Stake is quarter-Kelly in units (1u = 1% bankroll), rounded down to 0.5u, capped at 3u (college 1u). Sizes: Small 0.5–1u, Medium 1.5–2u, Max 2.5–3u. **Watch** = positive EV every source agrees on, but under 3%, so no units. Each bet also shows the worst price that still clears 3% (`min_price`).

**Stale-projection guard.** A prop whose projection is >35% off the market line (>1.6× for TDs) gets no units, is sorted last and is dimmed.

**PrizePicks.** Each line is priced at PrizePicks' own number: the books' fair probability at the nearest line, shifted along the simulation. A 2-pick Power is +200 on P(both). Entries use the hit-count distribution: exact (Poisson-binomial) for independent legs, a Gaussian copula for opposing same-game legs (`LEG_CORRELATION`).

---

## 3. Decisions log

| Decision | Why | Evidence |
|---|---|---|
| Market 70% / model 30% | Projections lose to closing lines over large samples; the model may lean on the market, not override it. | Standard practice; to be checked by Brier scores. |
| Quarter-Kelly, 3u cap, no 4u | Survives a model whose probabilities are a little off. 3u needs ~58% blended at −110 (~77% model vs a 50% market), which is almost always a stale projection. | 4u only if a few hundred graded bets show calibration and model Brier ≤ market. |
| Stale-projection guard (35% / 1.6×) | The first board's "3u" picks were stale projections (Braelon Allen 38 vs 70.5). | Live week-5 board. |
| Slate centering instead of tighter CVs | The model picked Less on 56 of 73 PrizePicks legs while projecting 62 of 87 players above the line. Matching by CV alone needed rec-yard CV ~0.33 (unrealistic), and passing couldn't be matched at all. | Fit run on the week-5 slate. |
| TD de-vig from game totals, not a flat 7% hold | Full games' Yes prices implied 5.5–7.5 TDs where ~4–5 happen. A 7% hold made 10 of 12 recs TD longshots. | After the fix: 0 TD recs; TD centering went 1.20 → 0.93. |
| Volume exponent 0.25, not 0.5 | 1/√volume made low-volume props lean Under (P(over) 0.39 for lines under 25 vs 0.52 for 50+) while the market's line/projection ratio was flat. | Week-5 bins; Darnold-type props are caught by the stale guard. |
| Sleeper primary, ESPN as a required check | Against the books' lines they're about equally close (Sleeper 15.3% vs ESPN 16.5% median error). Where they disagree, the edge is usually noise (Geno Smith: Sleeper 189, ESPN 232, line 208.5). | 262-prop comparison. |
| Yahoo not a source | Yahoo's API has no per-player projections. | Known since 2026-09-23. |
| Game lines get a model | Without one, they only flagged off-market books. Sleeper team points track the market closely but differ by up to 4 points. | MIN @ NO 46.4 vs 42.5 → 1u Over. |
| Cover/total combos show fair odds only | The Odds API carries no SGP prices. | — |
| Watch tier | A quiet week looked broken ("nothing recommended"); positive-EV, all-agree plays are shown without units. | Founder feedback. |
| PrizePicks: never pair teammates | PrizePicks requires 2+ teams. That removes the main correlation edge (QB + his WR). | Founder confirmed; killed the Daniels/Hurst stack. |
| PrizePicks board by upload, not scraping | The Chrome extension blocks prizepicks.com, and the API is behind a DataDome CAPTCHA. Getting around either is off the table. | Both verified. Upload: open the URL, Cmd+S, upload on /bets. |
| `per_page` irrelevant | The API returned all 3,557 lines on one page at per_page=1000. | Real file. |
| `allowed_wager_types` is a string | `"over"` / `"under_or_over"`; treating it as a list dropped almost every line. | Real file (13 → 673 priced). |
| Payouts editable, standard defaults | They vary by state and goblins/demons change them. Florida confirmed 2-pick Power 3x, 2-pick Flex 2x/0.5x, one goblin → 2.6x. 3–6 pick payouts are still unverified. | Founder screenshots. |
| PrizePicks max 6 picks | Not 8. | — |
| College: ESPN predictor spreads at 0.15 weight, 1u cap | One unvalidated source. At NFL settings it produced 15 bets up to 2.5u; at half weight, 3 small bets. | Week-6 college slate. |
| College totals market-only | Nothing projects college totals (Sleeper has no college data, ESPN fantasy is NFL-only). | Sleeper 400; ESPN checked. |
| College props shelved | ~4 credits per game with the month's budget nearly gone; game lines are the stronger part. Code kept behind `CFB_PROPS_ENABLED`. | Founder's call. |
| PrizePicks league label "NCAAFB" stored as-is | That's PrizePicks' real college label; never translate it. | Real file; founder's call. |
| NFL / College switch (not a separate tab) | More intuitive. College view: "CFB Game Lines" + Results. | Founder's call. |
| College graded without a migration | Saved as `kind = "cfb_game"`, filed under the NFL betting week, graded from ESPN's college scoreboard by full team name. | 54 real finals parsed in testing. |
| "This week's card" first | Strategist review: bettors want what to bet, how much, by when. | Design review. |
| Hide near-duplicate PrizePicks entries | The top entries were the same six picks with one swap; playing several is one bet. | Live review. |
| Lazy-load analytics libraries | A Render out-of-memory restart. scikit-learn, statsmodels, pandas and pulp loaded at startup put the app at 281 MB of 512 MB before any request. | Now 137 MB idle, ~209 MB peak on Bets, no leak over 6 rebuilds. |

---

## 4. Data sources and limits

| Source | Used for | Cost / limits |
|---|---|---|
| The Odds API (`ODDS_API_KEY`) | NFL + college lines, NFL props, PrizePicks standard lines | Free tier: 500 credits/month. Lines 2 credits/call (cached 6h); a full NFL prop slate ~70 (cached 24h); college props ~4/game (shelved). Every response is persisted in `odds_cache`. Prop fetches stop at a 60-credit reserve. The $30/20K tier is needed for daily full boards or more prop markets. 277 credits left on 2026-10-07. |
| Sleeper | Weekly projected stat lines; grading stats | Free. No college data. |
| ESPN fantasy (`lm-api-reads…/leaguedefaults/3`) | Weekly per-stat projections (cross-check) | Free, no login. NFL only. |
| ESPN site API | Matchup predictor (NFL + FBS); scoreboards for grading | Free. |
| PrizePicks | Full board (all stats, goblins, demons) | Uploaded by the founder daily (see Decisions). Odds API lines are the fallback. |

More stat types (pass TDs, rush+rec, pass+rush, completions, attempts, INT, rush attempts, kicking) are available from The Odds API at ~15 credits per market per slate. They were deferred until a paid tier.

---

## 5. Tracking, grading and how to judge the model

Every priced line is saved once to `bet_picks`, including no-bet lines (they're what calibration checks), frozen at the first price seen. A no-bet row can be upgraded to a bet; a bet is never overwritten. Grading happens when someone opens Results, 5h after kickoff:
- **NFL props:** Sleeper stats. No stat line or 0 games played = void.
- **NFL games:** ESPN's NFL scoreboard.
- **College games:** ESPN's college scoreboard.

None of it costs credits.

**Judge on hundreds of bets and on calibration, not one week.** If the model's Brier score is worse than the market's, lower `MODEL_WEIGHT`. If a size tier loses over a large sample, raise `MIN_EV` for it. Fit `LEG_CORRELATION`, `COVER_TOTAL_RHO` and the CV constants from graded results.

**Week 5 caveat:** its 302 NFL rows (10 recs) were recorded under the original, Under-biased model before the fixes. They'll be graded as-is with no ESPN projection. Consider excluding week 5 from calibration.

---

## 6. The Bets page

- **NFL / College** switch and Refresh. A one-line disclaimer (21+, 1-800-GAMBLER) with full text on "More".
- **This week's card:** the bets in kickoff order with size, price, book, "still a bet at X or better", dollars (bankroll setting, stored in the browser), and the best profitable PrizePicks entry.
- **Tabs:**
  - NFL: Player props · Game lines (+ folded combos) · PrizePicks · Results.
  - College: CFB Game Lines (+ combos) · Results.
- **Card tiers:**
  - Bet: lime border, units, size, dollars.
  - Watch: outlined.
  - No bet: dimmed.
  - Stale projection: dimmer still, sorted last.
- Win chance is the main number; books, Sleeper and ESPN sit in a quiet details line.
- **PrizePicks tab:** upload → best entries (by EV, profitable and distinct by default, overlap warnings, editable payouts) → 2-pick pairs (folded unless profitable) → goblins / demons (folded).
- A slow cold load says "Waking up the odds server…" after 8 seconds; Refresh keeps the current board on screen.

---

## 7. Operations

- **Render free instance: 512 MB.** After the lazy-load fix the app idles at ~137 MB and peaks ~210 MB on Bets; opening every analytics page adds ~145 MB once. Keep heavy libraries (scikit-learn, statsmodels, pandas, pulp) out of startup imports: import them inside the function or endpoint that needs them.
- Cold starts take ~30 seconds. The page explains it, and boards are cached 15 minutes in memory.
- Migrations: `bet_picks` (`03c72f4e93d0`), `odds_cache` (`cea70c9ce01c`) and `espn_projection` (`f79e92683ff7`) are all applied to Supabase, which Render shares.

---

## 8. Open items

1. Verify PrizePicks 3–6 pick payouts in Florida (build an unsubmitted all-standard lineup and read "$1 to pay $X").
2. After 3–4 graded weeks: tune `MODEL_WEIGHT`, CVs, the stale-guard bounds, `LEG_CORRELATION` and `COVER_TOTAL_RHO`; settle Sleeper vs ESPN accuracy from `espn_projection`.
3. Track PrizePicks entries in `bet_picks` so they're graded too.
4. Un-shelve college props when credits allow (league_id=15 verified; set `CFB_PROPS_ENABLED`).
5. More prop markets and daily refreshes need the paid Odds API tier.
6. Optional: a scheduled weekly board snapshot so recording doesn't depend on someone opening the page.
