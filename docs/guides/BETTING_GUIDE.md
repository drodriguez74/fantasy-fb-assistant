# Bets: how it works, what we decided, and why

The single record for the betting feature (`/bets`). It covers what was built, the method, every decision with its reason and evidence, data-access constraints, and what's still open. Last updated 2026-10-07 (incl. the TimesFM test, the calibration backtest and the model review in section 9).

Code: `backend/app/services/betting_model.py` (pure math), `betting_service.py` (boards), `betting_tracking.py` (record and grade), `odds_service.py`, `espn_projections.py`, `espn_game_predictor.py`, `prizepicks_board.py`; frontend `frontend/src/pages/BettingPage.tsx` and `frontend/src/components/betting/`. Endpoints: [API_GUIDE.md → Betting](API_GUIDE.md#betting-betting).

> For entertainment and research. Every number here is a model estimate. The founder places all wagers; the app only fetches and prices data.

---

## 1. What's built

| Area | What it does |
|---|---|
| NFL player props | Pass/rush/rec yards, receptions and anytime TD from DraftKings, FanDuel and Hard Rock, priced by simulation against the market, sized in units. |
| NFL game lines | Spreads and totals priced off the market with key-number margins; bets come from books off the consensus (line shopping). The Sleeper game model is shown for reference only (no weight since the 2026-10-07 review). |
| Cover + over/under combos | The four same-game parlays per game, with chance and fair odds to compare against a book's SGP price. |
| PrizePicks | The full board, uploaded daily: 2-pick pairs, 2–6 pick Power/Flex entries, and goblin/demon hit chances. |
| College football | Game lines only, behind an NFL / College switch. ESPN's predictor models spreads; college props are built but shelved. |
| Tracking & grading | Every priced line saved, then graded automatically. The Results tab shows record, units, ROI, calibration and NFL vs College. |
| My entries | The founder's real PrizePicks entries, logged on the page, snapshotted with the engine's view and graded from real stats, including a "whose read was right" check (books vs model). |
| Bets page | "This week's card" (the actual bets with dollars and kickoff times, always at least 3 picks), tiered cards, and tabs for the evidence. |

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
| `f9dcc91` | Analytics libraries lazy-loaded after a Render out-of-memory restart; this guide |
| (backtest) | TimesFM 3 tested and rejected; spread model validated on 4,755 real player-weeks (`scripts/backtest_projections.py`) |
| (review) | Model review on real 2025/2026 closing lines and outcomes: game-line model weight 0, key-number spreads, measured correlations (teammates fixed), ESPN check off for passing, "Best available" card fill (section 9) |

---

## 2. The method (current)

**Market.** Each book's two-way prices are de-vigged (multiplicative) and the median taken across DraftKings, FanDuel and Hard Rock Bet. This is the anchor: 70% of every estimate.

**Player model (30%).** A two-level Monte Carlo of Sleeper's weekly projected stat line, 20,000 draws:
1. The true mean is drawn around the projection (SD 30% of it).
2. The outcome is drawn around that mean. Yardage is gamma, with a coefficient of variation scaled by volume (mean^-0.25); receptions and TDs are Poisson.

**Slate centering.** Each market's projections are rescaled each week so the median prop's simulated P(over) matches the market (`fit_projection_scale`). Week 5: rec yds ×1.13, rush ×1.15, pass ×1.07, receptions ×1.05, TD ×0.93.

**Anytime TD de-vig.** Books quote "Yes" only, so each game's implied scoring rates are scaled to the TDs its Vegas total supports (`td_rate_scale`; 0.105 TDs per point, 95% to listed players). Typical scale is 0.66–0.76: a 30% price is really about 21%.

**ESPN cross-check.** ESPN's public weekly projections are centered the same way. A side gets units only if ESPN **confirms the edge on its own**: blended with the books exactly as Sleeper is, it must also clear 3% EV, and the stake is the smaller of the two sizes (since 2026-10-08, model version 2026-10-08.1). A side ESPN only leans toward stays on the watch list. Passing yards are exempt (`ESPN_CHECK_EXEMPT`; section 9).

**Game lines.** The market is the price (`GAME_MODEL_WEIGHT = 0`): a game-line bet exists only where one book's line or price is off the consensus. Spreads use a key-number margin distribution (`market_margin_pmf`: a normal, SD 13.26, reweighted so games land on 3, 7, 6, 10 and 14 as often as they really do, centered so the consensus spread is 50/50), so a half point through 3 or 7 is priced at its real value. Totals stay N(consensus, 13.0). The Sleeper team-points model (6 × rush + rec TDs + kicker points) and its ESPN checks are still computed and shown, but neither moves the price nor gates a side: on real closing lines they carried no information (section 9). College keeps its 0.15-weight ESPN predictor and plain normal margins.

**Sizing.** EV at the best available price. A bet needs EV ≥ 3% plus the model *and* the check agreeing (props; NFL game lines need only the price). Stake is quarter-Kelly in units (1u = 1% bankroll), rounded down to 0.5u, capped at 3u (college 1u). Sizes: Small 0.5–1u, Medium 1.5–2u, Max 2.5–3u. **Watch** = positive EV every source agrees on, but under 3%, so no units. Each bet also shows the worst price that still clears 3% (`min_price`).

**Best available (card fill).** The weekly card always has at least 3 picks (`MIN_CARD_PICKS`): when fewer bets qualify, the best remaining lines fill it at a flat 0.5u (`FILL_UNITS`), watch list first, then highest EV, never a stale-projection outlier. They're labeled "Best available" (confidence `fill`), shown with their EV, kept stable through the week once chosen (`fill_keys`), and tracked as their own tier in Results so they're judged apart from real bets.

**Watch alerts (2026-10-08).** Each watch-list line shows the price at which it would become a bet (`bet_at`, from `worst_price`). "Alert me" saves a `watch_alerts` row; every board build checks active alerts (`watch_alerts.check`) and, when the same pick (player or game, market, side; the line may have moved) is priced as a real bet, creates an in-app notification (navbar bell, type `bet_alert`) and marks the alert triggered. "Best available" fills don't count as bets. Alerts expire at kickoff. There's no scheduler, so alerts fire when a board is built (any page visit); props refresh only Wednesdays and Sundays on the free tier, game lines every 6 hours. The watch list itself is tracked as its own tier (confidence `watch`) and has its own section in the weekly audit.

**Two sections on the card (founder's call, 2026-10-07): "Best value" and "Most likely to win".** Best value is the EV bets plus fills above. Most likely to win (`most_likely`) lists up to 5 PrizePicks picks with a calibrated win chance of at least 70% (`MOST_LIKELY_MIN`), which clears the per-pick break-even of a 3x 2-pick (57.7%) and a one-goblin 2.6x 2-pick (62%). A pick is listed only if the engine backs it (engine chance ≥ the books') and ESPN doesn't contradict it; each shows the books' chance and the engine's edge over it, plus the safest 2-pick from two teams (P(both), correlation included). Standard -110 lines can't reach 70%, so these are mostly goblins. Each is tracked (kind `pp_leg`, no units or price) and graded, and Results shows predicted vs actual hit rate for them.

**Tuning loop.** `scripts/tune_from_results.py` (read-only) reads the graded lines and reports calibration per tier (bets, fills, most-likely, no-bet lines) with Wilson intervals, Brier for the books alone vs the engine alone vs the shipped blend, and the engine weight that would have scored best on earlier weeks, checked on the latest held-out weeks. It recommends a `MODEL_WEIGHT` change only with 300+ graded lines and a held-out gain whose CI excludes zero (on synthetic data with a real engine edge, 400 held-out lines weren't enough, so expect several weeks). The engine weight stays 0.30 until then.

**Stale-projection guard.** A prop whose projection is >35% off the market line (>1.6× for TDs) gets no units, is sorted last and is dimmed.

**PrizePicks.** Each line is priced at PrizePicks' own number: the books' fair probability at the nearest line, shifted along the simulation. A 2-pick Power is +200 on P(both). Entries use the hit-count distribution: exact (Poisson-binomial) for independent legs, a Gaussian copula for same-game legs, teammates and opponents alike (`LEG_CORRELATION`, measured; section 9). A 2-pick can't hold teammates (PrizePicks needs 2 teams), but a 3–6 pick entry can, and before the review those teammate pairs were wrongly treated as independent.

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
| ~~Game lines get a model~~ (superseded 2026-10-07) | Without one, they only flagged off-market books. Sleeper team points track the market closely but differ by up to 4 points. | MIN @ NO 46.4 vs 42.5 → 1u Over. |
| NFL game-line model weight 0 (2026-10-07) | On real closing lines the model added nothing: recalibration slope 0.11 (spreads) / −0.05 (totals), any weight above 0 scored worse out of sample, and its bets went 53-62-1 (−18u). Game-line edges now come only from books off the market. | 2025 + 2026 wk 1–4 backtest (section 9). |
| Key-number spread pricing (2026-10-07) | A rounded normal said a favorite wins by exactly 3 3% of the time; it's 9.7% at spreads of 2.5–3.5 and an exact-3 spread pushes 11%. That mispriced every half point through 3 and 7, the only place line shopping makes money. | 2,742 games fit, 336 scored out of sample; log-loss −0.137 [−0.193, −0.080]. |
| Measured correlations (2026-10-07) | The guessed opponent values were 2–3x too high and made same-game More/More pairs look +EV; opposing backs (−0.19) were missing; `COVER_TOTAL_RHO` was 0.15 vs a measured 0.03; teammates in 3+ pick entries were treated as independent (QB↔own WR is +0.38). | Section 9. |
| ESPN check not required for passing yards (2026-10-07) | Where ESPN and Sleeper differ by 15%+, the result lands on ESPN's side 53–60% for rush/rec/receptions but 37–45% for passing: the check only filtered noise there. | Two held-out seasons, section 9. |
| ESPN must confirm the edge, not just lean (2026-10-08) | Week 5's card had 12 bets, 10 of them Unders and mostly low-count receptions at plus money, whose edge came from Sleeper alone: the old check only needed ESPN to lean the same way, which is nearly free on low counts (Dotson Under 1.5 "agreed" with an ESPN projection of 2.1). Requiring ESPN's own blend to clear 3% EV, sized at the smaller of the two, left 4 bets (Brian Robinson Jr.'s 2.5u Under went: ESPN had exactly the books' 50%). Not yet validated on outcomes (no prop lines before week 5); judge it by the Audit's model-version split and `tune_from_results.py` after a few weeks. | Week-5 board, 2026-10-08. |
| "Most likely to win" section, engine must back it (2026-10-07) | Founder's goal: a high-confidence chance of the bet actually winning, with the engine giving an edge. Win chance is the confidence score; it's honest only if calibrated, and the 2025 backtest showed the engine's high-probability estimates are (rec yds 69.2% vs 67.8% real, rush 74.9/76.3, pass 90.7/92.1). | Week 5 build: 5 goblins at 80–91%, all engine- and ESPN-backed; safest 2-pick 75%. |
| Every recommendation auditable, per engine version (2026-10-07) | Founder: "Will all recommendations be auditable... I want to know if they all hit or didn't." Tickets the app suggested weren't tracked, the Most likely picks were only a total, and nothing recorded which engine made a pick -- so the fixed engine would have been judged on the old one's picks. | `ENGINE_VERSION` on every row; `tracked_entries`; `/betting/audit` + CSV. |
| Always 3 picks on the card (2026-10-07) | Founder's call: people bet every week. Fills are the best remaining lines at a flat 0.5u, labeled and tracked separately, so the card never inflates an edge to get there. | Week 5 after the review: 1 bet + 2 fills (both positive EV, from the watch list). |
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
| Results scoped per sport, with an "All sports" toggle | Each view shows its own sport's record and calibration by default. College uses a different, less-proven model (ESPN predictor at 0.15 weight), and mixing it with NFL would hide whether either works. "All sports" gives the combined bankroll view and the By-sport table. | Founder asked whether both Results tabs should be the same. |
| My entries log (`user_entries` table, `user_entries.py`) | The founder places real PrizePicks entries; the app should show their real record and test the engine on them. Each pick saves a snapshot (books-only and blended hit chance, Sleeper/ESPN projections, a `projections_disagree` flag) so graded results answer "does trusting the projections over the books pay?" (e.g. Irving: projections 75–78 vs a 57.5 line). Graded from Sleeper stats as each game goes final (ESPN scoreboard), with PrizePicks' rules: push/DNP drops out, the entry pays as the smaller entry, 1 pick left = refund. | Founder's real 2-pick (McCaffrey Less 36.5 + Irving More 51.5). |
| Entries are logged by hand, not pulled from PrizePicks | They're behind the founder's login and DataDome bot protection; logging in or getting around that is off the table. A screenshot import (Claude vision reads the entry and prefills the form) was offered as the convenient path. | — |
| "This week's card" first | Strategist review: bettors want what to bet, how much, by when. | Design review. |
| Hide near-duplicate PrizePicks entries | The top entries were the same six picks with one swap; playing several is one bet. | Live review. |
| TimesFM 3 not adopted as a projection source | Backtest on 4,556 2025 player-weeks: worse than Sleeper (avg miss 18.9 vs 18.1; passing 63.8 vs 56.8), barely better than a last-8-games average (19.1). Errors 0.89 correlated with Sleeper's; best out-of-sample blend helps ~1%. Its per-player spread scored worse than ours (pinball 7.42 vs 6.96). It needs ~3 GB RAM (Render has 512 MB). | Section 9. |
| Spread settings validated, not changed | Fitting projection error, CV and a dud-game rate per market on weeks 4–10 moved held-out (11–17) scores by −0.8% to +0.5%, mixed sign: noise. Duds made the goblin-relevant tail worse. The knobs exist (`PROJECTION_ERROR_BY_MARKET`, `DUD_PROB`) but are deliberately empty. | Section 9; rerun each season. |
| Lazy-load analytics libraries | A Render out-of-memory restart. scikit-learn, statsmodels, pandas and pulp loaded at startup put the app at 281 MB of 512 MB before any request. | Now 137 MB idle, ~209 MB peak on Bets, no leak over 6 rebuilds. |

---

## 4. Data sources and limits

| Source | Used for | Cost / limits |
|---|---|---|
| The Odds API (`ODDS_API_KEY`) | NFL + college lines, NFL props, PrizePicks standard lines | Free tier: 500 credits/month. Lines 2 credits/call (cached 6h); a full NFL prop slate measured **148 credits** for 15 games on 2026-10-07 (the earlier ~70 estimate was low). **Props refetch only on Wednesdays and Sundays (Eastern)** (`PROP_REFRESH_WEEKDAYS`, founder's call 2026-10-07 until the $30 tier): on those days a fetch older than 24h is refreshed; other days serve the last fetch whatever its age; college props ~4/game (shelved). Every response is persisted in `odds_cache`. Prop fetches stop at a 60-credit reserve. The $30/20K tier is needed for daily full boards or more prop markets. 277 credits left on 2026-10-07. |
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

**Everything is auditable (2026-10-07).**
- **Engine version:** every tracked pick, suggested ticket and logged entry (and each entry pick's snapshot) carries `betting_model.ENGINE_VERSION` (bump it whenever pricing changes; `2026-10-07.3` = market-only game lines + key numbers, measured correlations, zero-catch and zero-rush). Rows from before versioning are NULL ("pre-versioning"). Results splits by engine version and has a "Current engine only" toggle (`GET /betting/results?version=current`), so a fixed engine isn't judged on the old one's picks (e.g. the fake Goff 3u).
- **Suggested tickets** (`tracked_entries` table, `tracked_entries.py`): the board's top 5 2-pick pairs, the Most likely safest pair, and the best 3–6 pick Power / 2–6 pick Flex entry of each size shown by the entries endpoint are saved once per week and signature (picks + sides + lines + type; never overwritten) and graded with My entries' PrizePicks rules (`user_entries.grade_legs` / `entry_payout`; push or DNP drops out). Tickets holding a goblin or demon have no known payout, so they grade hit/miss only (`payouts`/`ev` null).
- **Weekly audit** (`GET /betting/audit?season=&week=&format=json|csv`, `betting_audit.py`): every recommendation that week, by section (Bets, Best available, Most likely to win, Suggested tickets, and the user's own entries separately), with what we said (win chance, books, engine, units), the engine version, the result, the actual stat and profit. Results → Audit shows it with a week picker, per-section hit rate vs predicted, and a CSV download. No-bet lines aren't recommendations, so they stay in Calibration.

**Judge on hundreds of bets and on calibration, not one week.** If the model's Brier score is worse than the market's, lower `MODEL_WEIGHT`. If a size tier loses over a large sample, raise `MIN_EV` for it. Fit `LEG_CORRELATION`, `COVER_TOTAL_RHO` and the CV constants from graded results.

**Week 5 caveat:** its 302 NFL rows (10 recs) were recorded under the original, Under-biased model before the fixes. They'll be graded as-is with no ESPN projection. Consider excluding week 5 from calibration.

---

## 6. The Bets page

Redesigned 2026-10-08 after a creative-director + UX review ("data overload"): one place per piece of information, one big number per row, details on tap. Phases 1 (noise) and 2 (tabs around the weekly loop) are shipped; Phase 3 (an entry-builder tray with the goblin payout check) is planned.

- **Header:** NFL / College switch, an ⓘ button (week, props/games priced, odds credits, refresh days, the method and sources) and Refresh; one-line disclaimer (21+, 1-800-GAMBLER). Loads come from the saved board (`serve_board`).
- **This week's best bets:** the top 5 bets by size (fills last) with units/dollars, win %, price, book and kickoff, then "See all N bets" (opens Play). Below: one-line links to the best profitable PrizePicks entry and to the Safest picks.
- **Pick rows** (`BetCard`): collapsed, two lines (the pick; price · book · game · kickoff) and the win chance as the one big number. A tap opens edge ("Edge +x%", expected profit per $1), "Good down to" (bets) or "Bet if it reaches" (watch), units/dollars, books vs Sleeper vs ESPN, and "Alert me if it becomes a bet". Stale-projection and ESPN-disagrees warnings stay visible collapsed. Toggle: Recommended / All lines.
- **Visual rules:** volt only means "act on this" (solid chip on a real bet, outlined on a Best-available fill, the main button, the active tab). Green/red only mean outcome or edge sign; More/Less, links and pending states are neutral. Nothing under 12px.
- **Tabs:** NFL: Play · PrizePicks · My entries · Track record. College: Play · Track record.
- **Play:** sportsbook bets with a Player props / Game lines switch and a Bets / All lines switch; the watch list is one collapsible row (open a pick to set an alert); game combos sit under Game lines.
- **Track record** (was Results): one sentence until something is graded (then record/units/ROI tiles), the **Audit** (week picker, every recommendation hit/miss by section, CSV), and **Model performance** collapsed (by bet size, market, week, model version, Safest-picks hit rate, calibration). Toggles: sport / All sports, All picks / Current model. The old Recommendations list was removed (the Audit covers it).
- **PrizePicks tab:** board freshness + Upload ("How to upload" collapsed when there's a board from today) → **Safest picks** (70%+ to win; the safest 2-pick shows the payout it needs, 1 / P(both)) → best entries with an entry-size filter → 2-pick pairs → goblins / demons (folded).
- **My entries:** "Log an entry" (with screenshot import) collapsed once you have entries; tiles only once something settles; a dot per pick (won / lost / pending).

---

## 7. Operations

- **Render free instance: 512 MB.** After the lazy-load fix the app idles at ~137 MB and peaks ~210 MB on Bets; opening every analytics page adds ~145 MB once. Keep heavy libraries (scikit-learn, statsmodels, pandas, pulp) out of startup imports: import them inside the function or endpoint that needs them.
- Cold starts take ~30 seconds. The page explains it, and boards are cached 15 minutes in memory.
- Migrations: `bet_picks` (`03c72f4e93d0`), `odds_cache` (`cea70c9ce01c`) and `espn_projection` (`f79e92683ff7`) are all applied to Supabase, which Render shares.

---

## 9. Validation and research

### Calibration backtest (`backend/scripts/backtest_projections.py`)

It uses a past season's Sleeper weekly projections and actual stats: free, cached in `backend/.cache/backtest/`. The cases are every player-week, weeks 4–17, where the player played and was projected for a prop-sized amount (QB passing ≥150, rush/rec yds ≥20, receptions ≥2). Settings are fitted on weeks 4–10 and scored on 11–17 with pinball loss over the 10th–90th percentiles (lower is better). Level isn't shipped, because slate centering sets it live from the market. Run it after each season: `cd backend && python scripts/backtest_projections.py --season 2026`.

**2025 result (4,755 cases).** The current settings are already near the best this model family allows.

| Market | Current (val.) | Fitted (val.) | Below q10 / median / above q90 (current) |
|---|---|---|---|
| Receiving yds | 8.678 | 8.656 | 15% / 52% / 8% |
| Receptions | 0.606 | 0.609 | 4% / 40% / 6% (discrete; ties land on the median) |
| Rushing yds | 8.784 | 8.810 | 14% / 46% / 9% |
| Passing yds | 23.93 | 23.77 | 9% / 49% / 3% |

The one consistent miss is that yards land below our 10th percentile 14–15% of the time (should be 10%). These are near-zero games such as early exits. In the region goblin lines occupy, though, the model is already close. P(at least half the projection), model vs real: rec yds 69.2% vs 67.8%, rush 74.9% vs 76.3%, pass 90.7% vs 92.1%. A dud-game rate fixes the extreme tail but worsens that region, so it stays off.

Caveat: this measures the *outcome spread* around Sleeper's projection. It can't measure the market blend; graded bets (Results tab) are still the test for that.

### TimesFM 3 (Google's time-series foundation model), tested 2026-10-07, rejected

The question was whether a zero-shot forecaster reading each player's game history (2023 onward) adds to Sleeper's projections, or gives better per-player spread (it outputs 10th–90th percentiles).

| Forecast | Avg miss, all | Passing | Rushing | Receiving | Receptions |
|---|---|---|---|---|---|
| Sleeper | **18.1** | **56.8** | 23.4 | 23.5 | **1.60** |
| TimesFM 3 | 18.9 | 63.8 | 24.0 | 23.7 | 1.69 |
| Last-8-games average | 19.1 | 63.5 | 24.2 | 24.1 | 1.70 |
| Blend, weight fit on wk 4–10, scored 11–17 | 17.9 | 60.1 (w=0) | 22.4 | 23.0 | 1.59 |

- Box-score history can't see injuries, roles or matchups, so it behaves like a smart moving average.
- Its errors are 0.89 correlated with Sleeper's, so it adds little information.
- Its percentiles were well calibrated (10/52/11%), but its per-player spread was less informative than ours: pinball 7.42 vs 6.96, and width-to-actual-miss correlation 0.56 vs 0.61.
- It needs ~3 GB RAM and a separate job.

Not worth adding. Reproducing it on an Intel Mac takes three workarounds:
- PyTorch 2.2 is the last Intel-Mac build, so pin numpy<2.
- Supply `nn.RMSNorm` (added in torch 2.4) as a small stand-in module.
- Batch only equal-length series: mixed lengths were padded and came back NaN (~20%).

The harness lived in the session scratchpad; the calibration script above keeps the reusable part.

### Model review on real outcomes (2026-10-07)

Every test was fit on one period and scored on data it never saw (2025 weeks 11–17, 2026 weeks 1–4, and 2024 or 2006–2014 where a second check was possible), with bootstrap CIs. About 25 ideas were tested; only results that held on more than one held-out set were adopted, since one or two "wins" in 25 are expected by chance. Scripts are in `backend/scripts/` and `backend/scripts/experiments/`, run from `backend/`; free data caches in `backend/.cache/backtest/`.

**Game lines on real closing lines** (`scripts/backtest_game_lines.py`, nflverse closing lines + scores, the shipped pricing code; `--model-weight 0.30` reproduces the pre-review model):

| | Bets | Record | Hit (95% CI) | Break-even | Sized result |
|---|---|---|---|---|---|
| 2025, weeks 1–18 | 109 | 50-58-1 | 46.3% [37, 56] | 51.7% | −17.4u (−10.5%) |
| 2026, weeks 1–4 | 7 | 3-4 | 42.9% | 52.1% | −0.8u |

Brier vs the line alone: spreads 0.2508 vs 0.2500, totals 0.2513 vs 0.2499 (2025). Sleeper alone was overconfident (its 70%+ calls hit 38.5%) and picked the underdog on 196 of 272 spreads (projected margins too narrow, slope 0.64). The ESPN check's vetoed bets went 21-13 (noise).

**Adopted**

| Change | Evidence | Script |
|---|---|---|
| NFL game-line model weight 0.30 → 0 | Recalibration slope 0.11 (spreads), −0.05 (totals): no information. Out of sample, w=0 scored best (totals 0.2501 vs 0.2544 at 0.30); isotonic/Platt recalibration only made it worse. | `experiments/exp3_weight_recal.py` |
| Key-number margins (`KEY_MARGIN_LOG_WEIGHTS`), `SPREAD_SD` 13.5 → 13.26 | Favorite wins by exactly 3 at spreads 2.5–3.5: 9.7% real vs 3.0% modeled; spreads of exactly 3 push 11.0% (n=391). Exact-margin log-loss −0.137 [−0.193, −0.080] out of sample. Example: market at −3, +3.5 at −110 is +3.5% EV (was priced −1.7%); −3.5 at +115 was a fake 4.3% bet (really −1.5%). Totals: no key-number gain, SD 13.0 confirmed. | `experiments/exp1_distribution.py`, `exp1b_centered.py`, `exp1c_export.py` (exports the weights) |
| `COVER_TOTAL_RHO` 0.15 → 0.03 | 2015–2025, 3,024 games: margin error vs total error +0.030 [−0.006, +0.065]; "favorite covers" vs "over" −0.009. Favorite-cover + Over at a +260 SGP: −1.4% EV shipped vs −8.3% measured. | `experiments/corr_cover_total.py` |
| Teammates correlated in 3+ pick entries (bug fix) | QB pass yds ↔ own WR/TE rec yds +0.38 [0.34, 0.42] (n=4,508). A QB More + own WR Less 3-pick was shown at −0.2% EV, really ~−20%. | `experiments/corr_props.py`, `corr_impact.py` |
| `LEG_CORRELATION` measured | Opponents 2–3x lower than guessed: QB↔opp QB 0.08 (was 0.25), QB↔opp WR 0.06 (0.15), WR↔opp WR 0.04 (0.10). Opposing RBs' rushing −0.19 [−0.26, −0.12] (was 0). RB↔own RB 0.00 (was −0.20). A QB More / opp QB More 2-pick was shown at +2.6% EV, really ~−5.5%. | `experiments/corr_props.py` |
| ESPN check off for passing yards | ESPN-direction hit rate where it differs from Sleeper by 15%+: rush 59.6% / 56.2%, rec yds 54.1% / 59.4%, receptions 53.2% / 59.3% (two held-out sets) vs passing 37.5% / 45.3%. | `experiments/props_mean_analyze.py extras` |

The prop correlations were measured against projection-centered lines, not real PrizePicks lines; graded entries remain the final test.

**Promising, not adopted yet**

| Idea | Evidence | What would settle it |
|---|---|---|
| Passing yards as a symmetric normal (CV ≈ 0.31) instead of gamma | The gamma overstates demon-line P(over) by +7.6 pp [5.1, 10.2] in all three held-out sets; pinball −2.0% [−1.0, −3.0]. It narrows the spread, which touches the "don't shrink CVs" rule. | A separate change, then graded passing props. `experiments/props_dist_eval.py --markets player_pass_yds --methods normal,current_refit --centered` |
| Raise `MIN_EV` to ~5–8% | One season can't tell how much of the estimated edge is real (fraction 0.10, CI [−1.2, 1.5]). At 3% the threshold assumes ~60% is real; 8% with quarter-Kelly halves the drawdown risk if none is. Half-Kelly is dominated. | Graded bets. `experiments/corr_kelly.py` |
| Anytime TD: Vegas team total + ESPN blend | Brier −1.3% [−2.2, −0.3] and −1.5% [−2.4, −0.7] on two held-out sets; books already price team totals. | Low priority. `experiments/props_mean_analyze.py td` |
| Wind unders (≥ 12 mph) | +15.5% [+6.4, +24.2] in 2015–24 (n=426), +4.4% in 2006–14, −4.4% in 2025–26 (n=40); game-time wind isn't knowable pregame. | Log forecast wind before kickoff. `experiments/exp4_quick_checks.py` |

**Rejected:** Elo/QB-adjusted ratings (worse than the market, significantly on spreads); situational regressions (rest, travel, divisional, weather; no coefficient |t| > 1.5); single-factor angles (backup QB, home dogs, byes); Sleeper/ESPN or Vegas-adjusted mean projections, recent usage, opponent defense and a gradient-boosted residual model (all within ±2%, sign flips between test sets); dud mixtures, per-player dispersion, negative binomial receptions, quantile regression, bootstrap residuals and PIT recalibration; more Monte Carlo draws (simulation error ~0.2% EV, far below the 3% bar).

**2026 weeks 1–4, engine calibration** (`experiments/engine_2026.py`; no prop lines exist for those weeks, so lines were set where PrizePicks puts them relative to a projection: goblin 50–70%, standard 95–100%, demon 125–140%). 19,096 priced picks from 1,736 player-weeks, current engine: said 50–60% → hit 56%, 60–70% → 64%, 70–80% → 76%, 80–90% → 84%, 90%+ → 94%; steady by week (said 54–55%, hit 54–55%). "Most likely"-style picks (goblin lines at 70%+): said 78%, hit 81% (n=1,800). This shows the engine's chances are honest; it can't show an edge over the books. It also matches the founder's PrizePicks screenshots: goblins the engine puts near 80% really hit ~80%, while PrizePicks' two-goblin 1.2x and goblin+standard 1.9x payouts price them like ~91%, so those tickets were overpriced. Excludes the lowest-volume players (under 15 projected yards / 1.5 catches), where the zero-catch and zero-rush fixes were validated separately.

**Not testable yet:** player props against real lines. No free archive of 2025 prop lines exists; The Odds API's historical endpoint (paid, ~13.7K credits for one pre-kickoff snapshot of 5 markets for every 2025 game, about one month of the $30 tier) is the cheapest legitimate source.

## 8. Open items

1. Verify PrizePicks 3–6 pick payouts in Florida (build an unsubmitted all-standard lineup and read "$1 to pay $X").
2. After 3–4 graded weeks: tune the prop `MODEL_WEIGHT` and the stale-guard bounds; judge the "Best available" fills (Results → By confidence); settle Sleeper vs ESPN accuracy from `espn_projection`. Game-line weight, `LEG_CORRELATION` and `COVER_TOTAL_RHO` were set from data in the 2026-10-07 review (section 9); rerun `scripts/backtest_game_lines.py --season 2026` and the correlation scripts after the season.
2a. Decide the "promising" items in section 9: passing yards as a normal, a higher `MIN_EV`, the TD blend, and logging forecast wind.
3. ~~Track PrizePicks entries~~: done as My entries. Screenshot import shipped (`1aa84c0`) but untested end to end: both AI accounts (OpenAI, Anthropic) were out of credits on 2026-10-07. Optional: grade the engine's own suggested entries too.
3b. Bump `ENGINE_VERSION` with every pricing change, so Results → By engine version stays honest.
3a. Backtest props on real lines: one month of The Odds API's paid tier for 2025 (and 2026 wk 1–4) historical props (section 9).
4. Un-shelve college props when credits allow (league_id=15 verified; set `CFB_PROPS_ENABLED`).
5. More prop markets and daily refreshes need the paid Odds API tier.
6. Optional: a scheduled weekly board snapshot so recording doesn't depend on someone opening the page.
