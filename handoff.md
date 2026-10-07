# Handoff (2026-10-07, session 19 wrap) — Render memory fix + full betting documentation

**Status:** everything pushed except this entry's commit (see git log). 214 backend tests pass.

**Render out-of-memory restart, root-caused and fixed.** Measured, not guessed:
- The app used **281 MB before any request**. scikit-learn (113 MB), statsmodels, pandas (47 MB) and pulp were imported at startup by `analytics.py` / `advanced_analysis.py`, for pages the Bets work never touches. Render's free instance has 512 MB.
- Today's Bets work added ~60 MB on top (peak 348 MB). Normal use elsewhere could then tip it over.
- Fix: those services are imported lazily inside `_analytics_service` / `_optimization_service` / `_analysis_service`. Idle is now **137 MB**, the Bets peak **209 MB**, and opening every analytics page reaches ~282 MB.
- No leak: memory held at ~185 MB across 6 full rebuilds of the NFL board, entries and college board.

**Docs:** new `docs/guides/BETTING_GUIDE.md` is the single record: what's built, timeline, method, a decisions log with reasons and evidence, data sources and limits, grading, page layout, operations and open items. CLAUDE.md's Bets section is condensed to the must-not-break rules plus a pointer, and has a new "Memory on Render" rule. The API guide's Betting section is rewritten for every current endpoint and field. current-state.md and memory are updated.

**Next (from the guide's open items):** verify FL 3–6 pick payouts; tune constants after 3–4 graded weeks; grade PrizePicks entries; un-shelve college props when credits allow (paid Odds API tier for more markets).

---

# Handoff (2026-10-07, session 19 cont.) — Bets page UX redesign (strategist + design review)

**Status:** built, 214 backend tests pass, frontend build + lint clean. **Not committed, not seen in a
browser**: local sign-in failed (the demo password in LoginForm doesn't match the shared DB's demo
user), so the visual check has to happen on the deployed site after a push.

From a live review of every Bets screen (desktop + phone):
1. **This week's card** (`ThisWeekCard.tsx`) at the top: the actual bets across props/games, in
   kickoff order, with units → dollars (bankroll setting, localStorage), "still a bet at X or better"
   (backend `worst_price` / `min_price` on every sized bet), and the best +EV PrizePicks entry.
2. **Scannable cards** (`BetCard.tsx`): bet / watch / no-bet look distinct (volt border + badge for
   bets), fixed-width badge, plain sizes (Small / Medium / Max), "54.6% to win" as the hero number,
   kickoff times, plain-language details ("Books: BAL +3 · we project BAL +2.2").
3. **PrizePicks order**: upload → best entries (ranked by EV, profitable only by default, overlap
   warnings) → 2-pick pairs (folded when none profitable) → goblins/demons (folded).
   Entries data moved to `prizePicksEntriesData.ts` (hook shared with the card).
4. **Polish**: one-line disclaimer (21+ and helpline always visible, full text on "More"), stats and
   method moved below the content, combos folded with column headers, the board stays on screen while
   refreshing, and a "waking up the odds server" note after 8s on a cold load.

---

# Handoff (2026-10-07, session 19 cont.) — College picks tracked and graded

**Status:** 213 tests pass, build + lint clean. Not committed yet.
- The college board saves every priced line to `bet_picks` as kind `cfb_game` (no migration), filed
  under the NFL betting week. Verified live: 114 lines saved (57 games × spread/total), 3 recommended.
- Grading: ESPN college scoreboard by kickoff date (± a day for late UTC kickoffs), matched by full team
  name. Verified live against last weekend: 54 real finals parsed.
- Results: new "By sport" split (NFL vs College); college picks are marked "CFB"; the College view now
  has a Results tab too.

---

# Handoff (2026-10-07, session 19 cont.) — College football section on /bets

**Status:** 212 tests pass, frontend build + lint clean. **Not committed.** Founder will test.
/bets has an **NFL / College switch**; College shows one tab, **"CFB Game Lines"** (spreads, totals,
cover/total combos), loaded the first time College is picked. **College props are shelved** (`CFB_PROPS_ENABLED = False`; uploads of a college
board are refused), so college costs only the 2-credit lines call per 6h.
- Spreads: ESPN predictor model (54 of 57 games this week), 0.15 weight, 1u cap → 3 bets
  (Nevada −8.5 at FanDuel 1u, Coastal Carolina +2.5 0.5u, Memphis −14 0.5u) + 12 watch.
- Totals: market-only (no college projection source exists).
- PrizePicks college (shelved): priced against the books only; would fetch props for up to 10 board
  games (~4 credits each). league_id=15 verified with a real file; the league is stored as PrizePicks'
  own "NCAAFB".
- Credits: 277 left this month.

**Next:** college grading (ESPN college scoreboard) so college picks can be tracked; un-shelve
college props when the budget allows.

---

# Handoff (2026-10-07, session 19 cont.) — watch tier, game model, combos, 3-6 pick entries

**Status:** built and tested (208 pass, frontend build + lint clean), not committed. Not visually
checked in a browser (local login needs the founder).

- **Props watch tier:** positive-EV props that every source agrees with but that are under the 3% bar get no units.
  Week 5: 0 bets, 9 watch.
- **Game lines are now modeled** (Sleeper team points vs consensus; ESPN FPI and ESPN projections as
  checks). Week 5: **MIN @ NO Over 42 (1u)** (model 46.4, ESPN 44.1), **BUF @ LAR Under 54.5 (0.5u)**,
  plus 5 game watch plays.
- **Cover + over/under combos** per game: probability + fair odds (compare with the book's SGP price).
- **PrizePicks 3-6 pick Power/Flex entries** with editable payouts (localStorage). Week 5 at standard
  payouts: best 3-pick Power +4.4%, 5-pick Flex +4.8%, 6-pick Flex +8.5%. **Depends on payouts**: the
  founder (Florida) couldn't see multipliers; they show as "$1 to pay $X" on a built lineup.

**Payout data (Florida):** 2-pick Power = 3x all-standard; one goblin made it 2.6x. Founder nearly
played two stale-projection rows (Davis Less 10.5 + Gainwell goblin More 9.5, ~23% to hit vs 38.5%
needed). "Show everything" now sorts stale rows last and dims them.
**Next:** confirm Florida payouts; grade game-line picks once the week settles; fit COVER_TOTAL_RHO and
LEG_CORRELATION from results.

---

# Handoff (2026-10-06, session 19 cont.) — PrizePicks full-board upload

**Status:** built and tested (206 pass, frontend build + lint clean), not committed yet.
The founder's board (saved 2026-10-06 evening) is already stored in Supabase `odds_cache`.

**Why upload, not fetch:** the Chrome extension blocks prizepicks.com, and PrizePicks' API
answers server requests with a DataDome CAPTCHA page. The founder's own browser passes it, so the
daily flow is: open api.prizepicks.com/projections?league_id=9 → Cmd+S → Upload board on /bets.

**Rule fix:** PrizePicks entries need players from 2+ teams, so same-team pairs are excluded.
That killed the Daniels/Hurst TB stack, and week 5 now has **0 +EV PrizePicks pairs**.
**What it prices:** of 3,557 lines, 2,003 are in stats we model; 673 are priced (players the books
also price), and 513 are skipped for having no sportsbook market. Week 5: one pair with units,
Jalon Daniels More 179.5 pass yds + Ted Hurst III More 21.5 rec yds (+6.6%, 0.5u; the edge depends on
the unfitted +0.45 QB-WR correlation). Top goblins hit about 83-88%; their payouts aren't in the file.

**Next:** ask the founder for goblin/demon multipliers to compute their EV; track uploaded-board
picks in bet_picks for grading.

---

# Handoff (2026-10-06, session 19 cont.) — PrizePicks 2-pick Power Play finder

**Status:** built, NOT committed yet. Backend 198 tests pass; frontend build + lint clean.
Verified against this week's real cached odds (no new credits). Not checked in the
browser: PrizePicks itself is blocked by the Chrome extension, and minting a local
login token was denied, so the new tab was checked through the API only.

**Built:** a "PrizePicks 2-pick" tab on `/bets`, from the board's new `prizepicks` section.
- Lines come from The Odds API's `prizepicks` bookmaker (already fetched with props):
  ~185 standard lines this week across pass/rush/rec yards and receptions. No anytime
  TD, no goblin/demon lines.
- Each leg is priced at PrizePicks' number: the books' fair P(over) at the nearest book
  line, shifted by the simulation's move between the two lines, then blended 30/70.
- Pairs: a 3x payout is priced as +200 on P(both hit), using the usual EV/Kelly/unit
  rules. Same-game legs use a Gaussian copula with `LEG_CORRELATION` (QB↔own WR +0.45,
  opposing QBs +0.25, ...; standard SGP magnitudes, not fitted). Same player twice is excluded.

**Week 5 result:** 22 +EV pairs. The top ones are same-team QB Under + WR Under stacks.
**Caveat:** every leg is a Less and the market sits near 50% on all of them, so the edge
is entirely the model's Under lean (right-skewed gamma: mean projection > median). This
is the same Under lean flagged earlier; it is unvalidated until graded results come in.

**Update, same session — Under lean fixed by slate centering.** A review found the model picked
Less on 56 of 73 PrizePicks legs while Sleeper projected 62 of 87 players above their line.
Fitting the CVs to the market would need unrealistically tight spreads, so instead
`fit_projection_scale` rescales each market's projections per slate (week 5: rec yds ×1.13,
rush ×1.15, pass ×1.07, receptions ×1.05, TD ×1.20). Legs are now 32 Less / 28 More and 5 pairs
are +EV (top: the same Wilson/Geno Smith stack at +6.6%, 0.5u). Also fixed: the Less side's
market probability on whole-number lines ignored pushes.
**TD longshots fixed.** Books quote anytime TD Yes-only, and a full game's prices imply 5.5-7.5 TDs
where ~4-5 happen, so the hold is ~30-40%, not the 7% assumed. `td_rate_scale` now scales each
game's implied scoring rates to its Vegas total (scale ~0.66-0.76; a 30% price is really ~21%).
TD recs went from 10 to 0, and the TD centering factor went from 1.20 to 0.93.
**Low-volume Under lean fixed.** CV now scales with mean^-0.25, not ^-0.5 (`VOLUME_EXPONENT`).
Week 5 now: 1 board rec (Godwin Over 3.5 receptions, 0.5u); PrizePicks legs 34 Less / 26 More,
8 +EV pairs, top is still the Wilson/Geno Smith stack (+7.1%, 0.5u).

**ESPN cross-check (same session).** ESPN's public weekly projections (`espn_projections.py`) tracked
the books' lines about as well as Sleeper (median error 16.5% vs 15.3%; ESPN better on rush/TD,
Sleeper on rec yds), so Sleeper stays primary and ESPN must agree before a side gets units.
`bet_picks.espn_projection` added (migration `f79e92683ff7`, **already applied to Supabase**).
Week 5 result: 0 board recs, 0 PrizePicks pairs with units (best +2.5%, under the 3% bar). The Geno
Smith stack died: Sleeper 189 vs ESPN 232 vs line 208.5.
**Heads-up:** week 5's 302 rows (10 recs) were recorded under the old, Under-biased model and are
frozen, so they'll be graded as-is with no ESPN projection. Consider excluding week 5 from calibration.

**Next:**
- Grade Sleeper vs ESPN projections against actual stats once a few weeks are tracked.
- Track PrizePicks legs/pairs in `bet_picks` so they get graded (needs a new `kind`;
  the unique key is per subject+market, which the book-side row already uses).
- Check the Under lean against graded results before trusting these.
- Fit `LEG_CORRELATION` from graded same-game outcomes.

---

# Handoff (2026-10-06, session 19 cont.) — Bets track record: every pick saved and graded

**Status:** pushed to `main`. Backend 196 tests pass. Migration `03c72f4e93d0`
(`bet_picks`) is **already applied to Supabase**. `ODDS_API_KEY` is now set on Render
and the live Bets page shows data.

**Built:**
- Every priced line on the board is saved to `bet_picks`, including 0-unit lines,
  frozen at the price first seen. Only games that haven't kicked off are priced or saved.
- `GET /betting/results` grades pending picks once their game is final: Sleeper
  stats for props, ESPN scoreboard for games. Both are free.
- New Results tab: record, units, ROI, splits by confidence/market/week,
  calibration (predicted vs actual) with Brier scores for blend vs model vs market,
  and the pick list.

**Verified:** live grading against week 4 using two temporary picks (deleted
afterwards). CeeDee Lamb Over 80.5 receiving yards graded won (actual 189); CLE −2.5
graded won (27–24).

**Current record:** week 5 is recorded. 302 lines tracked, 10 recommendations, all
pending. The first grades land after TB @ DAL (Thursday); the full week settles
after Monday night. Grading runs when someone opens the Results tab.

**How to read it:** one week is noise. Judge on a few hundred bets and on
calibration. If the model's Brier score is worse than the market's, lower
MODEL_WEIGHT. If a confidence tier loses money over a big sample, raise MIN_EV for it.

**Next:**
- Use the graded data to tune `betting_model` constants (after ~3–4 weeks).
- A correlated same-game Monte Carlo (QB ↔ WR yards).
- Optionally, a scheduled board snapshot each week. Recording currently happens
  only when someone opens the Bets page.

---

# Handoff (2026-10-06, session 19 cont.) — Bets: player props + game lines with unit sizing

**Status:** pushed to `main`. Backend 191 tests pass; frontend build clean.
Migration `cea70c9ce01c` (`odds_cache` table) is **already applied to Supabase**,
which Render shares. Render still needs `ODDS_API_KEY` set (see the entry below).

**Built:** `/bets` page and `GET /betting/board`.
- Player props: pass/rush/rec yards, receptions and anytime TD from DraftKings,
  FanDuel and Hard Rock, with PrizePicks lines shown alongside.
- Game lines: spreads and totals.
- Pricing: de-vigged market consensus, plus a two-level Monte Carlo of Sleeper's
  projected stat line, blended 30/70.
- Sizing: quarter-Kelly units (1u = 1% bankroll), capped at 3u, and only when
  EV ≥ 3% and the model agrees with the side. Lean is 0.5–1u, Strong 1.5–2u,
  High 2.5–3u.
- Responsible-gambling disclaimer (21+, 1-800-GAMBLER) and method explainer on the page.

**Model problems found live and fixed:**
1. Stale projections showed up as fake 3u edges (Braelon Allen projected 38 vs a
   70.5 line). Fix: an outlier guard; props more than 35% off the market (more than
   1.6x for TDs) get no units.
2. A low-volume QB rushing prop (Darnold over 4.5) got 3u. Fix: yardage variability
   now scales with 1/√volume.
3. A numpy bool leaked into the JSON response and caused a 500. Cast fixed, plus a
   regression test.

Week 5 result: 10 recs, all 0.5–1.5u, mostly Unders. Game lines: 0 (the books agree).

**Credits (important):** a full prop slate is about 68 credits. The cache is in the DB
(memory → `odds_cache` → API), because the in-memory cache was refetching on every
process start, and Render free tier restarts constantly. Props cache 24h; prop
fetches stop at 60 credits left. 285 of 500 credits remain this month after testing.
**The free tier can't sustain daily prop refreshes. The $30/20K tier can.**

**Next:**
- Grade picks against real results. Persist each week's recs, then score them once
  stats are final. This is the only way to calibrate MODEL_WEIGHT, the CV values and
  the outlier bounds, and to check the Under lean.
- Then a correlated same-game simulation (e.g. QB yards ↔ WR yards), which is where
  Monte Carlo pays off over closed-form math.

---

# Handoff (2026-10-06, session 19 cont.) — Vegas implied totals on DEF/K streaming

**Status:** committed and pushed to `main`. Backend 183 tests pass; frontend build clean.
**Founder action needed:** add `ODDS_API_KEY` in Render → Environment. It's declared in
render.yaml as `sync: false`, so the deployed backend shows no odds until it's set. The
key was shared in chat; the founder plans to rotate it later. It lives only in
gitignored `backend/.env`.

**Built:** `app/services/odds_service.py`. The Odds API returns spreads and totals for all
NFL games from DraftKings, FanDuel and Hard Rock Bet in one call (2 credits). Each team's
implied total is (median total − its median spread) / 2. Only this NFL week's games count
(before next Tuesday 10:00 UTC), so bye teams are absent. Cached 6h, which is about
8 credits/day against the free tier's 500/month. With no key, odds are omitted.
`GET /leagues/{id}/streaming` now carries `vegas` per DEF/K: the opponent's implied total
for a defense, the team's own for a kicker. The Streaming tab shows it color-coded.

**Live check (week 5):** 30 teams with lines (KC is on bye, matching its 0 projection).
Bengals DEF @ MIA has MIA implied 17.5 and is also the top projection; Harrison Mevis
(K) has team implied 28.5.

**Next (odds):** player props (pass/rush/rec yards, receptions, anytime TD) → a
market-based fantasy projection scored with league rules, shown beside ESPN/Sleeper on
This Week start/sit. Props must be fetched one game per request (~15 games × markets),
so plan around the cache and probably the $30/20K tier. Implied totals could also feed
This Week as a game-environment tag.

---

# Handoff (2026-10-06, session 19) — waiver goal: ROS values + league-first Waivers page

**Status:** pushed to `main` (Render/Vercel auto-deploy). Backend 178 tests pass; frontend build clean (lint: only the pre-existing
useAuth.tsx error). Browser-checked locally on both leagues, desktop and
390px mobile.

**`777a236` Yahoo rest-of-season projections (a real bug).** Sleeper's
season feed is a static 18-game preseason total. Checked live in week 5:
an injured RB still showed 207 there vs 102 when his weekly rows are
summed. So Yahoo waiver, trade and roster-grade values counted weeks
already played and ignored byes and injuries. New
`weekly_projections.fetch_rest_of_season_projections(season, week,
end_week)` sums Sleeper weekly rows from the current week through the
league's `end_week` (default 17). It falls back to the season feed if any
week fails, takes about 1.2s, and every week is cached. ESPN needed no
change: its `projected_total_points` is already rest-of-season (St. Brown
246 = 18.9 × 13 remaining games). Labels now say "rest-of-season".

**`fdd089c` Waivers page leads with lineup-impact advice.** It now
auto-selects your league (remembered in localStorage `waivers.leagueId`).
The primary list is the same engine and card as League Detail, via the new
shared `components/waivers/LineupWaivers.tsx`: team-needs strip, drop,
bid, plus this page's competition badge. The global trending list is only
shown when no league is selected, and on the Trending tab. The Week picker
follows the league's real current week; it used to show a wrong date
guess of Week 6. Removed: the Roster Analyzer tab (typed internal player
IDs, season 2024 hardcoded, a made-up 0.5 drop score when data was
missing), the local-DB "generate recommendations" Refresh, and a no-op
"Add" button. Also removed their endpoints (`POST /waiver-wire/
analyze-roster`, `/generate-recommendations`) and the API_GUIDE lines.

**Checked, not a bug:** Pro Bowl's recs all say "Drop Joe Mixon (RB, 0
proj)". He's healthy on the bench, and Sleeper carries no projection for
him at all, so 0 is the honest value.

**`f239562` DEF/K Streaming tab rebuilt on real data.** The old tab read
local matchup tables that hold no 2026 data. Every defense came back
empty, yours got a placeholder 5.0, and kickers always showed nothing.
The new `GET /leagues/{id}/streaming` (`league_value_model.
streaming_options`) compares your DEF and K this week against the top 5
free agents by this week's projection, each with its edge over yours and
a stream/keep call. The tab uses it whenever a league is selected; the old
view stays only for no-league. Live results, week 5: Optis Titans
SEA 6.2 → Jets +2.6; Pro Bowl Chiefs on bye → Bengals +8.3; both kickers
"keep yours". The waiver response also gained `my_defense`, which
prefills the old view's DEF box. Docs: CLAUDE.md now has a "Waiver &
trade engine" section (and the stale "comprehensive analysis is
Yahoo-only" line is fixed); API_GUIDE's waiver section is rewritten.

**Still open (judgment calls / non-waiver):** the weights (+5 waiver
floor, 20% depth, 25% trade acceptance) are worth tuning against results.
2-for-1 trades don't credit the freed roster spot. The old `/matchup-analysis`
DEF/K tables are empty for 2026; with streaming now running on league data
they're a candidate for removal.

---

# Handoff (2026-09-23, session 18) — waiver + trade engines rebuilt on lineup impact

**Status:** committed to `main`, not pushed. Backend 172 tests pass;
frontend build clean (lint: only the pre-existing useAuth.tsx error).
`/goal` (waivers based on our needs + sensible trade opportunities) done.

**Why rebuilt (baseline measured on both real leagues first):** waivers
ranked Sleeper's GLOBAL trending list — 8 of Pro Bowl's top 10 projected
below the weakest bench player. Trades compared raw points across positions
(suggested a WR for a kicker) and repeatedly offered an IR player.

**New engine (ESPN + Yahoo League Detail waiver/trade tabs):**
- `league_value_model.py` (pure, tested): optimal lineup for the league's real
  starter slots; replacement level = best free agent per position; team value
  = lineup + 20% of top-4 bench VOR. Waivers = every real FA scored by
  team-value gain after the best drop (season "upgrade") or this-week lineup
  gain ("streamer"); if nothing clears +5, a labeled "watch" list at the
  weakest positions. Trades = 1-for-1 and 2-for-1 deals ranked by my gain,
  requiring the partner to gain ≥25% of mine (≥2) so they'd accept; never
  request Out/IR players or anyone <5 VOR (take the free agent instead);
  ≤1 per player, ≤2 per partner.
- `league_value_data.py`: platform adapters (ESPN own season+week
  projections; Yahoo via Sleeper projections; Yahoo K/DEF FA pages fetched
  separately — the default 300 had zero defenses). Sleeper 24h trending adds
  kept only as an urgency note.
- `league_advice_service.py`: API shapes + plain-language reasons ("starts
  over X", "takes Y's lineup spot"), team-needs table (my starters' rank vs
  league per position), real ESPN trade deadline (was hardcoded "Week 13").
- Deleted `trade_finder_service.py` + dead helpers. Frontend: needs strip,
  kind badges, season/week gains, 2-for-1 trade cards with both sides'
  gains; "Best for your lineup" section on the Waivers page when a league
  is selected. Browser-verified on both leagues.

**Live results:** Optis Titans — needs K 12/12, TE 11/12, RB 9/12; top trade
McConkey + Fannin → Isaiah Likely (TE); no FA clears the bar (watch: K Trey
Smack +4.8). Pro Bowl — RB 12/12 despite 6 RBs (quality, not count); trades
consolidate depth into Dobbins / Jadarian Price (+58–61); waiver: Lions DEF +5.

**Limits (honest):** season projections are full-season, not rest-of-season;
a 2-for-1 doesn't credit the freed roster spot; weights (20% depth, 25%
acceptance, +5 floor) are judgment calls worth tuning with results.

---

# Handoff (2026-09-23, session 17 end) — ESPN/Yahoo parity DONE

**Status:** `main`, last commit `7937e90`; 3 commits not pushed at time of
writing (`9d0e111`, `a216409`, `7937e90`). Backend 167 tests pass; frontend
build clean (lint: only the pre-existing useAuth.tsx error).
`/goal feature parity between ESPN and Yahoo` is complete — every
league-detail feature ESPN has now has a real Yahoo implementation.

**Key decision: Yahoo per-player projections come from Sleeper.** Yahoo's
API has none (confirmed live). New `app/services/weekly_projections.py`
pulls Sleeper's public RotoWire-sourced feed (weekly and full-season; the
un-versioned `api.sleeper.app/projections/nfl/...` path — `/v1/` returns
empty stubs), matches by name+team (defenses by team), and scores with
the league's real Yahoo rules: `pts_std` corrected per stat by
`count * (league rate - Sleeper standard rate)`. Sleeper's standard rates
were confirmed empirically (-1 per INT, not -2). Stats outside the
canonical rules (first downs, 40+ yd plays, pick-sixes, 2-pt) are scored via
`YAHOO_EXTRA_STATS` + a new `stat_values` map on `get_league_settings`.
K/DEF stay on Sleeper standard (disclosed). Sanity-checked: Dak projects
58-60 in this league vs real 38.1/71.0 actuals.

**Shipped (this session, after the token-renewal commit):**
- `939d201` Yahoo This Week optimizer + start/sit (weekly projections).
  Fixed: Yahoo `BN`/`W/R/T` slot labels unrecognized (bench = starters);
  IR players in the optimizer bench pool (ESPN too — suggested starting an
  IR player).
- `7a7cd06` Yahoo trades: real `trade_finder_service` over one
  `get_league_rosters` call + season projections (was AI-invented); real
  Yahoo trade deadline.
- `9d0e111` league-aware waivers read the caller's real UserLeague;
  deleted `app/utils/league_data_loader.py` (shared-file + fake demo data).
- `a216409` Yahoo waiver parity. **Real bug:** `get_available_players` only
  ever got 25 players (Yahoo caps pages at 25; filters must be matrix
  params) — the availability filter dropped nearly every real free agent.
  Now pages to 300 with real ownership %. Plus Yahoo waiver enrichment
  (`yahoo_waiver_context.py`), drop candidates, position pressure, digest
  byes. **Shared bug fixed:** `effective_position_requirements` sent every
  FLEX slot to the thinnest position even when surplus depth covered it
  (a 6-RB/1-TE roster was told it needed 3 TEs) — affects ESPN grading too.
- `7937e90` Yahoo roster grade uses season projections (was composition-only).

**Known limitations (honest, not bugs):** trade finder counts IR as bench,
so an injured IR star can dominate trade suggestions (both platforms);
Sleeper-projection coverage is ~all active players but a few (PUP etc.)
go unmatched and are excluded from the optimizer, and the response says so.

**Next (ranked backlog):** weekly recap + shareable card (needs a
"shareable" design decision); consolidate the 3 analysis pages (audit
real-vs-fabricated first). Sleeper This Week is still unsupported (no box
score API) — Sleeper's projections feed could power a partial version.

---

# Handoff (2026-09-22, session 17 cont.) — Yahoo parity: This Week, scoring, bye radar, matchup history

**Status:** committed to `main`, NOT pushed. Backend 136 tests pass. `/goal feature
parity between ESPN and Yahoo` still ACTIVE.

**Shipped since the entry below:** `65e80dc` real Yahoo This Week
(scoreboard w/ Yahoo's own projected team totals + win probability, real
lineup; no optimizer, stated honestly). `47f1c9b` real Yahoo scoring rules
(`get_league_settings` had been always-failing), waiver position, bid
tiers. Latest commit: Yahoo **Bye Week Radar** (real per-player
`bye_weeks.week` off `get_team_roster`) + **Matchups history** (one
scoreboard call per week via new `get_week_matchup_summary`); both
builders return the exact ESPN response shape, so no frontend changes.

**Yahoo token renewal fixed (follow-up commit):** new
`app/services/yahoo_tokens.get_valid_yahoo_token` is now the one place a
stored Yahoo token is read. It renews via `refresh_access_token` when the
token is within 2 min of expiry, saves the new pair to every one of the
user's Yahoo leagues sharing it, and allows one renewal per user at a
time (lock keyed per event loop, since snapshot background refreshes run
their own `asyncio.run`). Every Yahoo call site goes through it:
snapshot builders, `LeagueManagementService._get_yahoo_token` (now
async), This Week, waiver position, waiver wire, post-draft, league
scoring. 7 new tests (143 total pass). **Live-verified 2026-09-23:**
league 4's expired token renewed and saved (new expiry +1h), then Bye
Week Radar (real byes, e.g. Rashee Rice/Chiefs wk 5) and Matchups (0-2,
wk 3 upcoming vs Angeles Gang Gang) both returned real data.

**Remaining parity gaps:** lineup optimizer +
start/sit confidence (needs per-player projections, still unconfirmed);
Yahoo trade suggestions still AI-generated (ESPN's are real);
`league-aware-recommendations` `league_info` from legacy file loader.

---

# Handoff (2026-09-22, session 17) — Yahoo API unlocked + made real, ESPN/Yahoo parity push (in progress)

**Status:** working tree clean, pushed to `main` (`281e0c1`). Backend 136
tests pass; frontend build/lint clean (1 pre-existing unrelated
useAuth.tsx lint error). `/goal feature parity between ESPN and Yahoo`
is ACTIVE (Stop-hook enforced) — next session continues under it, don't
clear unless parity is actually done.

**Decision/finding:** Yahoo finally granted real Fantasy Sports API
access this session (confirmed live, App ID `3sPY0hJG`, no `.env`
change needed) after ~2.5 months blocked — see
[[project_yahoo_fantasy_api_locked]] for full history. This was the
FIRST time any real (non-403) Yahoo data ever flowed through this
codebase, which exposed a long chain of real, previously-unreachable
parsing/logic bugs, all found+fixed+live-verified against the founder's
real "Pro Bowl Fantasy" league (team "Failing at Fantasy"):
- Yahoo wraps every singular resource (game/league/team/user/player) as
  a LIST (attrs + one dict per sub-resource), not a flat dict — new
  `yahoo_service._flatten_resource()` (recursive) fixes this everywhere.
- `team` resources need Yahoo's `;out=standings` param for win/loss/points.
- Naive-vs-aware datetime crash on `yahoo_token_expires_at` (same bug
  class as the already-documented account-lockout bug) — fixed in
  `league_management_service.py` + `league_snapshots.py` + token-write
  side + 2 test fixtures.
- Frontend: Yahoo sends points as strings + real IEEE754 float drift —
  new `formatPoints()` in LeagueDetailPage.tsx.
- Real team auto-detection: guid-matching DOESN'T work (Yahoo masks
  every manager's guid as literal `"--hidden--"`, including the
  requester's own — always matched team #1 wrongly). Fixed using
  Yahoo's real `is_owned_by_current_login` flag via new
  `get_current_user_teams()`.
- `get_team_roster`/`get_available_players` + 5 call sites were passing
  bare `team_id` instead of the full Yahoo `team_key` — new
  `build_team_key()` helper. 2 of those calls were also missing the
  `access_token` arg entirely (guaranteed crash, dead until now).
- `get_team_roster` returned an empty roster: real players are nested
  under `roster["0"]["players"]`, not `roster["players"]`.
- `eligible_positions` is a real list, not a dict — switched to Yahoo's
  real `primary_position`/`display_position` fields.
- **Real Yahoo roster analysis** shipped (was honest "not yet
  implemented"): mirrors the existing Sleeper builder pattern, real
  composition grade (B, 86.7) through the shared `grade_roster()`,
  `projected_points` honestly 0.0 (Yahoo's roster endpoint has no real
  per-player projection, same accepted tradeoff as Sleeper).

**Parity gap map (from this session's audit):**
- ✅ now real for Yahoo: connect, standings, waiver recommendations
  (Sleeper-trending, personalized), roster analysis/grading, roster
  import (post-draft).
- ❌ still honest-stub, NOT yet built for Yahoo: **This Week** (matchup
  scoreboard + lineup optimizer + start/sit confidence) — the single
  biggest remaining gap, currently says "not implemented for YAHOO".
- ⚠️ pre-existing, NOT Yahoo-specific, not touched this session:
  Yahoo's trade-suggestions content is still the old AI-hallucinated
  placeholder format (only ESPN's trade path was ever made real, a
  separate earlier-session task); `league-aware-recommendations`'s
  displayed `league_info` reads a legacy hardcoded file loader (same bug
  class already fixed for `/standings`, just not this endpoint).

**This Week / Yahoo — mid-investigation when session ended, promising:**
Confirmed live (raw JSON captured) that Yahoo's `/league/{key}/scoreboard;week=N`
DOES expose real team-level `team_projected_points` (e.g. "203.66") AND
real `win_probability` (e.g. 0.67) per matchup — much better than
assumed. Was checking whether real PER-PLAYER projections also exist
(tried `/team/{key}/roster;week=N/players/stats` — request was sent but
response wasn't inspected before the session ended) when interrupted to
save progress. **Next step: finish checking that raw response** for a
per-player projected-points field. If real per-player projections
exist, a genuine Yahoo lineup optimizer + start/sit confidence (matching
`this_week_service.py`'s ESPN logic) becomes buildable; if not, still
worth shipping a real matchup scoreboard (opponent, real projected
team totals, real win probability) for Yahoo even without the
optimizer, rather than leaving the whole screen stubbed.

**Also noted, not yet fixed:** the guid `"--hidden--"` masking discovery
means any FUTURE Yahoo feature must not assume manager/user guids are
usable for identity matching — only `is_owned_by_current_login` (or
matching against the authenticated user's own team_key) is real.

---

# Handoff (2026-09-16, session 16) — optimizer v2, real trade finder, Sleeper roster analysis

**Status:** working tree clean, pushed to `main` (`42d17fb`), Render
auto-deploy triggered. Backend 136 tests pass (was 116); frontend
build/lint clean throughout.

**Three backlog items shipped, each tested + live-verified against real
data before moving to the next.**

**1) Optimizer v2 + start/sit confidence.** New `this_week_service.
start_sit_confidence()` -- per-starter tier (comfortable/moderate/
toss_up/risky/locked) from two real signals: the real projection gap to
that starter's own best bench alternative at the slot, and whether the
starter carries a live ESPN injury designation for a game not yet
played. Optimizer swaps get the same treatment (`confidence` field) --
a big point-gap swap into a questionable/doubtful replacement now reads
as `risky`, not equally trustworthy as a clean upgrade. No fabricated
inputs, pure arithmetic on data already flowing through the service.
Wired into `GET /leagues/{id}/this-week` + rendered on LeagueDetailPage
(starter rows + LINEUP CALL rail). 6 new tests. Live-verified against
the real Optis Titans league -- Ladd McConkey correctly flagged `risky`
despite a healthy margin, due to his real Questionable tag.

**2) Real trade finder (found + fixed a real fabrication bug).**
`_get_espn_trade_recommendations` was asking the AI to invent "3
realistic trade scenarios" knowing only `len(teams)` -- zero visibility
into any other team's actual roster, so `target_player`/`offer_players`
were free-form AI guesses, not real players anyone could trade for.
That's fabrication, not a heuristic. New `trade_finder_service.
find_trade_suggestions` (pure, unit-tested) runs over real data instead:
`get_league_teams` already returns every team's real roster (real
lineup slot, ESPN's own real season-long projection) in one call. Finds
a real bench player who out-projects one of my real starters, then a
real bench player of mine who out-projects one of THEIR real starters
at a different position, gated by a projection-gap margin + fairness
ratio -- every suggestion names two real rostered players in a real
two-way swap. Frontend renders the real you-send/you-receive/reasoning
shape with a "Real rosters" confidence badge; the still-AI-generated
Yahoo path is unchanged but now honestly labeled "AI-generated" instead
of looking identical. 9 new tests. Live-verified against the real Optis
Titans league.

**3) Real Sleeper roster analysis (found + fixed a real bug).** Was an
honest "not yet implemented for SLEEPER leagues" stub (standings already
had real Sleeper support, roster analysis didn't). New
`_build_sleeper_roster_analysis_snapshot` resolves Sleeper's raw
roster-id player lists against the real global player catalog
(`get_all_players`) and grades real composition through the shared
`grade_roster` engine, using Sleeper's real `roster_positions`
(`parse_league_settings`, already existed, just unused for this). No
fabricated per-player projection -- Sleeper's roster endpoints don't
expose one, so `projected_points` is honestly 0; `grade_roster` already
degrades gracefully to composition-only grading in that case. **Live-
verified against a real Sleeper league (Sleeper Friends League,
289646328504385536, connected+disconnected via the real API during
testing) and found a real bug in the process:** Sleeper's real
`injury_status` value `"NA"` (confirmed live against Sleeper's public
player catalog -- mostly inactive/practice-squad players with no real
team) was being flagged as an injury concern; fixed to treat it as
healthy like Sleeper's other real "no status" default (`None`). 6 new
tests. No frontend changes needed -- LeagueDetailPage's roster tab
already renders whatever shape the backend returns.

**Remaining on the ranked backlog (deliberately NOT started this
session -- asked the founder, they said stop here for now):** weekly
recap + shareable card (new feature -- needs a design decision on what
"shareable" means: image export? link? in-app view?), and consolidating
the 3 standalone analysis pages (`AdvancedAnalysisPage`/`AnalyticsPage`/
`HistoricalPage`, 2,869 lines combined). Before merging those three,
worth auditing what's real vs fabricated first -- `AnalyticsPage`'s ML
prediction code (`advanced_analytics_service.py`, real sklearn
RandomForest/GradientBoosting/KMeans) looked legitimate but depends on
per-player historical stats noted elsewhere in this codebase as sparse/
often-empty in this deployment; same honesty-first approach that caught
the trade-recommendation fabrication bug above should be applied before
any redesign work, not just a mechanical merge.

---

# Handoff (2026-09-15, session 15) — waiver bid tiers + weekly digest notifications

**Status:** working tree clean, pushed to `main` (`f025503`), Render
auto-deploy triggered. Backend 116 tests pass; frontend build/lint clean.

**Both backlog options from the last handoff shipped this session** (user
asked for both, not a pick-one).

**1) Priority-aware waiver bid tiers.** New `WaiverWireService.
compute_bid_tier(priority, waiver_position)` (pure, unit-tested) turns a
recommendation's real priority tier into an actionable claim suggestion by
reading it against the user's REAL ESPN waiver standing
(`espn_service_enhanced.get_waiver_position`, shipped session 12) --
never the tier in isolation. FAAB leagues: a suggested $ bid as a real
fraction of actual remaining budget (urgent 20% down to watch 0.5%,
clamped to the real budget). Rolling-priority leagues: use-claim /
hold-priority advice, based on the tier and whether the team's real
`waiver_rank` is currently favorable. Returns `None` (never a fabricated
placeholder) when no real waiver position is known -- non-ESPN league,
not connected, no `team_id`. Wired through both `waiver_wire.py`
personalization paths (`/recommendations`, `/league-aware-recommendations`)
and `league_management_service._get_espn_waiver_recs` (the League Detail
Waiver Wire tab). Frontend: `WaiverWirePage.tsx` recommendation cards and
`LeagueDetailPage.tsx`'s Waiver Wire tab both render the suggestion when
present. 7 new unit tests.

**2) Weekly digest notifications.** The #1-ranked backlog item --
notification center existed but was purely request-driven (piggybacks on
a page load), so a user who doesn't open the app mid-week never saw
anything. New `notification_service.generate_weekly_digest_for_user`:
one real notification per connected league (team_id configured),
summarizing the actual top live-Sleeper waiver target and (ESPN only)
real upcoming bye-week risk via the session-14 Bye Week Radar fix.
Dedupe-keyed per real ISO calendar week (`weekly_digest:{league.id}:
{year}-W{week}`) so a retried trigger is a no-op; best-effort per league
(one platform call failing never blocks another); skips a league
entirely rather than send an empty digest.

Trigger: this app has no background worker (Celery/Redis were removed
session 13) and Render's free tier has no cron, so the real external
trigger is **`.github/workflows/weekly-digest.yml`** (free GitHub Actions
scheduled workflow, Tuesday 13:00 UTC + manual dispatch, cold-start
retry logic) calling new `POST /notifications/generate-weekly-digest`.
That endpoint is NOT user-authenticated (fans out across every active
user, no logged-in session driving it) -- guarded instead by a shared
`X-Digest-Secret` header compared against new `DIGEST_CRON_SECRET`
setting; refuses every request when unset (never falls back to no auth).

**Manual setup DONE, verified live end-to-end (same session):** founder set
`DIGEST_CRON_SECRET` to the same real value in both the Render dashboard
and this repo's GitHub Actions secrets. Confirmed by curling the live
endpoint directly with that secret: `HTTP 200`,
`{"users_checked":1,"users_notified":1,"notifications_created":1}` against
production. Founder also confirmed seeing the resulting real notification
in the app on their phone. Fully working, nothing further needed here
beyond the normal Tuesday cron cadence going forward.

**Also fixed in passing:** `notification_service.py`'s module docstring
still claimed "this app has a Celery worker" -- stale since session 13's
Celery/Redis removal; corrected.

**Next:** verify the digest secret setup above actually fires end-to-end
once configured (check a real user's notification bell after the first
Tuesday run, or trigger manually). Then continue down the ranked backlog:
optimizer v2 + start/sit confidence, trade finder, Sleeper league
analysis, weekly recap + shareable card, consolidate the 3 analysis pages.

---

# Handoff (2026-09-15, session 14) — Bye Week Radar shipped, real espn_api fix

**Status:** working tree clean, pushed to `main` (`848fe1c`), Render
auto-deploy triggered. Backend 102 tests pass; frontend build/lint clean.

**What happened:** picked up the espn_api bye-week bug from session 12's
memory note ([[project_espn_api_bye_week_bug]]). The earlier note suspected
`on_bye_week`'s `player_team_cache` fallback in `box_player.py` — that
turned out to be a red herring. Root-caused it one level deeper: `League.
box_scores(week=N)` only actually fetches week N's data `if week <= self.
current_week`; for any future week it silently falls back to
`scoring_period = self.current_week` and returns the CURRENT week's data
mislabeled as the requested week. Confirmed live by diffing
`box_scores(week=2)` vs `box_scores(week=11)` during week 2 of the real
season — byte-for-byte identical. That's why every future-week bye lookup
came back wrong: it was never really evaluating that week.

**Fix:** sidestepped `box_scores()`/`on_bye_week` entirely rather than
patching the clamp. `espn_service_enhanced.get_bye_week_radar()` crosses
ESPN's own per-team `byeWeek` field (one HTTP call, `get_pro_schedule()`)
against `team.roster` (no week-clamping at all) — no dependency on the
broken path. Wired end-to-end: snapshot builder (ESPN-only, 3600s TTL) →
`GET /leagues/{id}/bye-week-radar` → new "Bye Week Radar" card added to
the Roster Analysis tab (additive, not a full repurpose — that's still an
open design option, see session 12's notes). Live-verified against the
real Optis Titans league (correctly flags Seahawks players' real week-11
bye) and in-browser in both themes.

**Next:** pick another item off the backlog — priority-aware waiver bid
tiers, or weekly digest notifications (highest retention leverage —
notification center exists, just not schedule-driven).

---

# Handoff (2026-09-15, session 13) — dead /blog router + scraper cleanup

**Status:** working tree clean, pushed to `main` (`268a791`), Render auto-deploy
triggered. Backend 102 tests pass.

**What happened:** picked "kill/verify the mock news scraper" off session 12's
backlog. Investigation found the actual fabrication (canned player-news
string, hardcoded trending topic) was **already fixed months ago** (`f791d8a`,
2026-08-23) — `scraper_service.py`'s mock methods already honestly returned
`[]`. What was left was **dead code**, not fake data: `blog.py` (7 routes)
and its sole backer `app/services/content_service.py` (an abandoned original
`ContentGenerationService`, name-colliding with the real one in
`content_generation_service.py`) had **zero frontend callers** — confirmed
via grep, the frontend only ever calls `/content/*`. Live-tested `blog.py`'s
own scrape methods too: `fantasypros.com/nfl/waiver-wire/` 404s,
`nfl.com/fantasy/` permanently redirects — 100% dead even if something did
call them.

**Shipped:** deleted `blog.py` + `content_service.py`, dropped the `/blog`
router registration, trimmed `scraper_service.py` to just the one method
still actually called (`scrape_player_news`, from
`content_generation_service.py`'s `player_analysis` path — still an honest
no-op, just no dead HTTP-scrape code around it anymore). Fixed a stale
comment in `players.py` referencing the old fabrication + a since-removed
method name. Updated `docs/guides/API_GUIDE.md` and
`docs/audits/DECOMMISSION_TASK_LIST.md` to mark this resolved — and while in
there, corrected a separately-already-fixed "`content-stats` always 500s"
doc claim that was also stale (fixed in `71cb1ab`, doc never updated).

**Next:** pick another item off session 12's list — Bye Week Radar (blocked
on the real `on_bye_week` espn_api bug, [[project_espn_api_bye_week_bug]]),
priority-aware waiver bid tiers, or weekly digest notifications (highest
retention leverage per the backlog — notification center exists, just not
schedule-driven).

---

# Handoff (2026-09-14, session 12) — waiver depth, H2H matchup, Overview cut

**Status:** working tree clean, all pushed to `main`, Render/Vercel auto-deployed.
Backend 102 tests pass; frontend build/lint clean throughout.

**Decisions:** (1) Waiver competition = real per-league signal (other teams'
actual rosters/lineups), never a fabricated "who's bidding" guess — ESPN's
API has no visibility into pending claims. (2) This Week keeps its
single-column "My Lineup" as default; H2H is an added toggle, not a
replacement. (3) Overview tab removed outright (panel review: 4 lenses all
converged — every real thing on it was duplicated or a dead stub). (4)
Bye Week Radar (the panel's pick for repurposing Roster Analysis) is
**not built** — found a real espn_api bug (`on_bye_week` wrong for future
weeks); shipping it would silently show wrong byes. See
[[project_espn_api_bye_week_bug]].

**Accomplishments:** waiver-position panel (FAAB/priority rank) + fixed a
real `acquisition_budget` bug; per-league position-pressure competition
badges (named teams, season + this-week signals); real drop-candidate +
value-delta on the Top Waiver Target card; This Week table got team/actual
columns + IR-below-bench; fixed invisible D/ST badge; real season-schedule
"Matchups" tab (rebuilt from dead code, uses `box_scores` not `scoreboard`
for live-accurate scores); side-by-side H2H matchup view; removed the dead
Overview tab + its unused `/insights` fetch.

**Key files:** `backend/app/services/{waiver_wire_service,league_competition,
league_management_service,espn_service_enhanced,this_week_service}.py`,
`backend/app/api/v1/endpoints/{leagues,waiver_wire}.py`,
`frontend/src/pages/{LeagueDetailPage,WaiverWirePage}.tsx`.

**Next:** either fix the espn_api bye-week bug and build Bye Week Radar for
real, or pick a different next item (options given to founder: priority-
aware waiver bid tiers, kill/verify the news scraper, weekly digest
notifications).

---

# Handoff (2026-09-09, session 11) — Render deploy, mobile pass, snapshot cache, ESPN-parity polish

**Snapshot cache (stale-while-revalidate)** shipped: new `league_snapshots`
table (migration `a1b2c3d4e5f6`, ALREADY applied to Supabase — Render shares
that DB so no deploy-time migration needed). `app/services/snapshot_cache.py`
`serve_swr()` + `app/services/league_snapshots.py` builders. Wired into
`/leagues/{id}/this-week`, `/roster-analysis`, `/standings` — they serve a
stored JSON copy instantly and background-refresh when stale (TTL: this_week
180s, others 900s). `?refresh=1` forces live. Response body gains a `_cache`
block. Frontend LeagueDetailPage: Refresh button forces live; This Week
re-fetches once 7s after a stale response; "UPDATED Nm AGO · SYNCING" line.
Measured: cache hit ~0.2s vs 1.5–3s fresh.

**ESPN-parity visual polish** shipped (scope chosen: logos+headshots+badges,
not the full H2H rebuild): `<PlayerAvatar>` (ESPN headshot + team-logo corner
badge, position-monogram fallback), `injuryTag()` in playerDisplay.ts
(Q/D/O/IR/SUS/PUP/DTD). Wired into This Week rows + roster tab. Backend added
`player_id` to `get_week_matchup` per-player payload.
NOTE the bigger ESPN gap still open: side-by-side H2H matchup layout (my
starters vs opponent's — `get_week_matchup` ALREADY returns `opponent_lineup`,
just unused), win-probability, live in-game scoring, kickoff times (needs the
`nfl_schedule` table). User wants to keep closing this gap.

**Mobile responsive pass** shipped earlier this session: headers stack below
`sm`, tab strips scroll (`.no-scrollbar`), `flex-wrap` button rows, card
padding `p-4 sm:p-6`, `body{overflow-x:hidden}`, This Week scoreboard reworked
(smaller fonts, break-words, min-w-0). Device-checked by the user via
screenshots — This Week scoreboard was the main fix.

**Render backend LIVE:** `https://fantasy-fb-assistant.onrender.com`
(`fcea809` Dockerfile $PORT + `.dockerignore`, `425a27d` render.yaml + pool).
Free tier → ~30-60s cold start. `render.yaml` has `autoDeploy: true`.

**Vercel:** `VITE_API_URL=https://fantasy-fb-assistant.onrender.com/api/v1`
set in Production; git push triggers the build that bakes it in. Verified the
live bundle points at onrender.

**Demo login:** Supabase has ONE user `demo@test.com` (id 1); password hash
matches none of the documented ones — founder logged in so they know it, or
reset via the one-liner in chat.

---

# Handoff (2026-09-08, session 11 start) — Render backend deploy + mobile responsive pass

**Render backend is LIVE:** `https://fantasy-fb-assistant.onrender.com` (health `/`
200, `/docs` 200, DB connected — login returns 401 not 503). Commits: `fcea809`
($PORT-aware Dockerfile CMD + `backend/.dockerignore`), `425a27d` (`render.yaml`
blueprint + DB pool 3+2). Free tier → ~30-60s cold start after 15min idle.

**Vercel:** `VITE_API_URL=https://fantasy-fb-assistant.onrender.com/api/v1` added to
Production env. The prior live bundle had `localhost:8000` baked in (Vite inlines at
build time) — that was the "network error" on the deployed site. The git push of
`c9bb1d6` triggers a fresh Production build that picks up VITE_API_URL, so the
deployed site should work after that deploy finishes. (Manual `npx vercel deploy
--prod` from repo root also works if needed.)

**Demo login:** Supabase DB has ONE user `demo@test.com` (id 1); its password hash
matches none of the documented passwords. Either reset it (DB write — blocked for
Claude in auto mode; run the one-liner in chat) or use whatever the founder set.

**`SECRET_KEY` on Render:** if copied from `.env` it's the literal dev placeholder.
Fine for demo; set a real random value before real use (forces re-login).

**Mobile responsive pass (`c9bb1d6`):** page headers stack below `sm`, tab strips
scroll horizontally (`.no-scrollbar` helper added to index.css), button/filter rows
`flex-wrap gap-*`, table cells `px-3 sm:px-6`, `body{overflow-x:hidden}` backstop.
Touched 10 page files. Build + lint clean. NOT visually verified on a real device —
the Chrome automation in this session couldn't produce a true mobile viewport
(screenshots rendered at desktop width regardless of window resize).

---

# Handoff (2026-09-08, session 10) — draft teardown COMPLETE (backend + frontend)

**CURRENT STATUS:** working tree clean except the untracked `Optis_*` / `ProBowl_*`
spreadsheets (left alone on purpose). All work pushed to `main`.
Backend tests 102 pass; frontend build + lint clean (1 pre-existing useAuth.tsx
lint error unchanged). This session (10): draft-assistant teardown done
(backend + frontend); nav re-cut done; ESPN analysis speed pass done;
`pool_pre_ping` added to the DB engine. **Next session: deploy backend to
Render — full plan below.**

Note: `test_auth.py::test_user_registration` flakes in the full-suite run
(passes in isolation and on re-run) — a pre-existing test-isolation issue,
not from these changes.

**Deployed-frontend + tunneled-backend attempt (session 10, did NOT land):**
Tried to point the deployed Vercel frontend at the local FastAPI via an
ngrok/cloudflare tunnel so login + ESPN could be tested against production.
- CORS was already fine (`backend/.env` `CORS_ORIGINS` includes the vercel URL).
- Login POST worked through the tunnel; `/auth/me` then 503'd. Root cause
  found + fixed: the SQLAlchemy engine had no `pool_pre_ping`, so stale
  Supabase/pgbouncer connections errored on the next request (committed).
- BUT the tunnel approach is blocked by this network: the browser can't
  reach `*.ngrok-free.app` / `*.trycloudflare.com` at all (plain `fetch()` →
  "Failed to fetch", requests never arrive at the tunnel; cloudflare's random
  subdomain returns NXDOMAIN from the LAN resolver 192.168.1.1). curl from a
  shell works; the browser/DNS filters tunnel domains. See
  [[project_tunnel_domains_blocked]].
- Cleaned up: tunnels killed, `VITE_API_URL` removed from Vercel, prod
  redeployed to the prior state (defaults to `localhost:8000`, i.e. deployed
  site still has no working backend).
---

## NEXT SESSION — deploy the FastAPI backend to Render

Founder set up a **Render account** (2026-09-08) for this. Goal: a real
public backend URL so the deployed Vercel frontend can do login + ESPN
against production (tunnels are DNS-blocked on this network —
[[project_tunnel_domains_blocked]]).

**What's already in place:**
- `backend/Dockerfile` exists (python:3.11-slim, installs `requirements.txt`,
  runs `uvicorn app.main:app`). **One edit needed:** the `CMD` hardcodes
  `--port 8000`; Render injects `$PORT` — change to
  `CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`.
- No `.dockerignore` — add one (`.env`, `venv/`, `__pycache__/`, `*.db*`,
  `.git/`) so local secrets/junk don't get baked into the image.
- App is stateless HTTP (no websockets/celery), CORS middleware reads
  `settings.CORS_ORIGINS`, engine now has `pool_pre_ping` (session 10).
- Health check path for Render: `GET /` (returns JSON 200).
- DB is Supabase; `backend/.env` `DATABASE_URL` currently uses the pooler
  host on `:5432`. For Render, consider Supabase's transaction-pooler
  (`:6543`, `?pgbouncer=true`) — but pgbouncer transaction mode breaks
  `pool_pre_ping`/prepared statements, so simplest is session-pooler `:5432`
  (what we have) with the SQLAlchemy pool kept small.

**Render setup steps:**
1. New → Web Service → connect the GitHub repo, **root directory `backend/`**,
   environment **Docker** (it'll find `backend/Dockerfile`). Free instance type.
2. Set env vars from `backend/.env` — the load-bearing ones: `DATABASE_URL`,
   `SECRET_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`
   (if used), all `SUPABASE_*`, `CORS_ORIGINS`, `FANTASYPROS_API_KEY` (if set),
   any `SMTP_*`. **Set `CORS_ORIGINS` to include the real Vercel URL**
   `https://fantasy-fb-assistant.vercel.app` (it already does locally).
3. Deploy. Note the URL (`https://<name>.onrender.com`). Hit
   `/docs` and `/api/v1/auth/me` (with a minted token) to smoke-test.
4. Run migrations once: `alembic upgrade head` — either via a Render "Job"
   / shell, or confirm the DB is already migrated (it's the same Supabase DB
   we run locally, so it already is — probably a no-op).
5. **Vercel:** `vercel env add VITE_API_URL production` →
   `https://<name>.onrender.com/api/v1` (must include `/api/v1`), then
   `vercel deploy --prod` from the **repo root** (Vercel root dir is
   `frontend/`, so deploying from inside `frontend/` fails with a
   double-path error — deploy from repo root, `.vercel/` is linked there).
6. Test on `https://fantasy-fb-assistant.vercel.app`: login with
   `demo@test.com` / `Password123`, then This Week / Waivers / Trades on the
   demo league (id 1, real ESPN "Optis Titans").

**Caveats:** Render free web services **spin down after ~15 min idle** →
first request after cold start takes ~30-60s. Fine for testing, annoying for
a demo. Also free tier = 750 instance-hours/mo (one service ≈ always-on is
within budget if it sleeps).

`vercel link` is already done at repo root + `frontend/` (`.vercel/`
gitignored). The **frontend** Vercel project also has a stale set of backend
env vars (DATABASE_URL, OPENAI_API_KEY, etc.) from an earlier abandoned
"backend on Vercel" attempt — harmless (unused, no `api/` dir), ignore or
delete them.

**Frontend teardown shipped as `fb37f71`:**
- deleted `DraftPage.tsx`, `LiveDraftPage.tsx`, `components/draft/`
- `api.ts` — removed `export const draft` + unused `MockDraftSettingsPayload` /
  `MockDraftResult`; kept `MockDraftRosterPlayer`, `PositionBreakdownEntry`,
  `ValueAnalysisEntry`, `DraftSessionSummary`, `DraftSessionDetail`, `users`
  (DraftHistoryPage still uses all of these)
- `App.tsx` — dropped the two lazy imports + routes; `/draft` and `/live-draft`
  now `<Navigate to="/leagues" replace />`
- `Navbar.tsx` — dropped Draft Assistant + Live Draft nav items
- `HomePage.tsx` — the "Draft Assistant" feature card is now "This Week" → `/leagues`;
  hero CTA + quick-action links repointed to `/leagues` / `/waiver-wire`
- `AuthPage.tsx` — new-user landing `/draft?welcome=1` → `/leagues?welcome=1`
  (LeaguesPage doesn't read `?welcome=1` yet — harmless no-op, worth wiring later)
- Verified: DraftPage/LiveDraftPage chunks gone from the build output.

**Nav re-cut DONE as `804757e` (session 10):** top nav = This Week · Leagues ·
Waivers · Trades · Players; "More" = Reports · Content · Analytics · Advanced
Analysis. New `ThisWeekRedirectPage` (`/this-week` → first league's This Week
tab, or `/leagues`), new `ReportsPage` (`/reports` hub for Post-Draft / Draft
History / Historical). Blog dropped from nav; ContentPage links to `/blog`.
Build + lint clean, verified in browser.

**ESPN analysis speed pass DONE (pushed, `8705af1`):** the `/leagues/:id`
"~25-30s to first render" perf note (session 8) is fixed. `get_comprehensive_
league_analysis` now takes `sections` + runs slices concurrently;
`/waiver-recommendations` and `/trade-suggestions` compute only their own
slice instead of the full 5 (each threw 4 away — and the page fires both).
Independent ESPN reads + per-position AI calls are gathered.
`espn_service_enhanced._get_league` got a per-key lock so concurrent slices
don't each build the League. Measured warm vs the real Optis Titans league:
waiver 4.6s, trade 3.1s, this-week 0.8s (were ~25-30s). 102 tests pass.
Note: `_analyze_espn_roster`/`_analyze_espn_matchup`/`_get_espn_league_standings`
are now only reachable via a no-`sections` call (none in the app today) —
the frontend's roster/standings come from their own lighter endpoints.

**NEXT — the ranked in-season backlog** (from the artifact): 1) weekly digest
notification/email cadence, 2) kill the mock news scraper (`scraper_service`
fabricates news/trending on live paths), 3) waiver claim planner w/ FAAB,
4) optimizer v2 + start/sit confidence, 5) trade finder, 6) Sleeper league
analysis, 7) weekly recap + shareable card, 8) consolidate the 3 analysis pages.

**Still open from before:**
- Charts not visually verified in a running browser (select players on
  AdvancedAnalysisPage in both themes — quick check).
- This Week optimizer is single-pass greedy, no matchup/edge input — v1.
- Yahoo Fantasy API still blocked at Yahoo's end (support ticket).

---


**Sessions 2–8's uncommitted work** committed + pushed as `1efe7f9` (60 files).

**Then open items 1–5 from session 8's list, done via 3 parallel agents:**
- `132bfa8` — **dark-mode contrast pass** (#2 + #5): new theme-aware `.pos-badge-*`
  classes (position badges were invisible on dark everywhere), `disabled:bg-ink-200`
  → `bg-surface-2`, AIAnalysis/ErrorBoundary/NotificationBell fixed-light values,
  LeaguesPage re-auth button → `bg-volt text-volt-ink`. Walked every data page in
  both themes with real Optis Titans data. LeagueDetailPage inspected, found clean.
- `8362eeb` — **chart theming** (#3): new `useChartColors()` hook (reads tokens off
  `<html>`, re-reads on `data-theme` change), `--viz-1..8` + `--viz-pos/warn/neg`
  palette in index.css, all 5 chart components converted, tooltips given
  surface/text `contentStyle`. Build passes; NOT rendered live in a browser
  (charts need player selection) — one outstanding visual check.
- `9083966` — **This Week screen** (#1) + **progressive league-detail render** (#4).
  New default tab in LeagueDetailPage wired to a real `GET /leagues/{id}/this-week`
  (ESPN weekly box-score projections, deterministic greedy lineup optimizer,
  honest non-ESPN messages). EDGE/projection-range/win-prob%/FAAB omitted, not
  faked. `loadLeagueData` now renders core sections first, waiver+trade fill in
  their own loading state, StrictMode-guarded by a reqId ref. 4 new tests (131 pass).
  Verified live in browser, both themes — scoreboard, field bar, optimizer,
  lineup table, LINEUP CALL rail all render correctly with real data.

Working tree clean except the untracked `Optis_*` / `ProBowl_*` spreadsheets.

**Session 9 continued — strategic pivot decided (NOT yet executed):**
Founder decided to **remove the draft assistant** and refocus the product on
in-season play (waivers / trades / weekly lineup / reports / content), and to
keep the deployed frontend on **Vercel's free tier** (bundle/perf work serves
this). Full write-up published as an artifact:
https://claude.ai/code/artifact/1c5aaa93-1db3-4ae4-9dd7-36f032e3128a
("The Season Is the Product") — audit of real-vs-scaffolding, the sequenced
teardown plan, the 4-pillar in-season model, retention mechanics, ranked
backlog, and the Vercel/perf constraint.

New memories: [[project_draft_assistant_decommission]], [[project_vercel_free_tier]].

**Teardown — founder approved the full cut list. BACKEND DONE, FRONTEND NOT STARTED.**

DONE (committed, backend tests green at 101, was 131):
- `6ed53e8` earlier committed the strategy-doc + memory updates.
- `d58b8d2` `Extract effective_position_requirements to a shared module` — the
  FLEX-aware helper moved from `draft_assistant_service` to new
  `app/services/roster_requirements.py` (pure function `effective_position_requirements`);
  `roster_grading.py`, `waiver_wire_service.py`, `post_draft_analysis_service.py`
  repointed. No behavior change.
- `2d40783` `Remove Live + Mock draft (backend)`:
  - deleted `backend/app/api/v1/endpoints/{draft,live_draft}.py`,
    `backend/app/services/{draft_assistant_service,mock_draft_service,draft_recommendation_fallback}.py`,
    tests `test_mock_draft_endpoints.py` / `test_mock_draft_service.py` / `test_yahoo_live_draft.py`
  - `router.py` — dropped the `/draft` and `/draft/live-draft` registrations
  - NEW `backend/app/services/player_pool.py` holds the two generic Sleeper
    helpers `draft.py` used to export (`is_on_active_roster`, `UNRANKED_SENTINEL`);
    `trade.py` import repointed there (aliased back to `_is_on_active_roster` /
    `_UNRANKED_SENTINEL` at the import so trade.py body was untouched)
  - `test_scoring_rules.py` — removed the `TestCalculatePlayerValuesRecalculation`
    class + its `DraftAssistantService` import (scoring_rules math still covered
    by the other classes)
- KEPT deliberately: `DraftSession` model + `app/schemas/draft_session.py` + the
  `User.draft_sessions` relationship + `user_service` draft-session methods +
  `/users/me/drafts` and `/users/me/drafts/{id}` (users.py) + all `/post-draft/*`
  routes + `post_draft_analysis_service.py`. The `auto_draft_assistant` bool
  column on `UserLeague` was left in place (harmless, unused — avoids a migration).
  ESPN rankings script untouched.

**NEXT — FRONTEND TEARDOWN (not started; my in-progress edit to `api.ts` was reverted, tree is clean):**
1. Delete `frontend/src/pages/DraftPage.tsx`, `frontend/src/pages/LiveDraftPage.tsx`,
   the whole `frontend/src/components/draft/` dir (only `DraftPickLog.tsx` + `index.ts`,
   used only by DraftPage).
2. `frontend/src/services/api.ts` — remove the `export const draft = { ... }` block
   and the now-unused `MockDraftSettingsPayload` + `MockDraftResult` interfaces.
   KEEP `MockDraftRosterPlayer`, `PositionBreakdownEntry`, `ValueAnalysisEntry`,
   `DraftSessionSummary`, `DraftSessionDetail`, and the `users` export
   (`getDraftHistory`/`getDraftDetail`) — DraftHistoryPage needs all of those.
3. `frontend/src/App.tsx` — remove the `DraftPage`/`LiveDraftPage` lazy imports and
   their two `<Route>`s; add redirects `/draft` and `/live-draft` → `/leagues`
   (This Week lives at `/leagues/:id`, so `/leagues` is the closest home).
4. `frontend/src/components/common/Navbar.tsx` — drop `{ name: 'Draft Assistant', href: '/draft' }`
   from `primaryNavigation` and `{ name: 'Live Draft', href: '/live-draft' }` from `moreNavigation`.
5. `frontend/src/pages/HomePage.tsx` — 3 links to `/draft` (lines ~18, ~87, ~178) → repoint to `/leagues`.
6. `frontend/src/pages/AuthPage.tsx` — `navigate('/draft?welcome=1')` → `navigate('/leagues?welcome=1')`.
7. Verify: `cd frontend && npm run build && npm run lint` (1 pre-existing useAuth.tsx
   lint error is OK). Check the bundle shrank (DraftPage/LiveDraftPage chunks gone).
8. Then commit + push, and do the fuller nav re-cut (This Week · Leagues · Waivers ·
   Trades · Players top nav; Post-Draft + Draft History + Historical → a "Reports"
   area; Blog merged into Content) as a SEPARATE follow-up commit — it's a design
   task, not part of the mechanical teardown.

**Backlog after teardown (ranked, from the artifact):** 1) weekly digest
notification/email cadence (highest retention leverage — notification center
exists, just not driven on a schedule), 2) kill the mock news scraper
(`scraper_service` returns fabricated news/trending on live paths), 3) waiver
claim planner w/ FAAB, 4) optimizer v2 + start/sit confidence, 5) trade finder,
6) Sleeper league analysis, 7) weekly recap + shareable card, 8) consolidate the
3 analysis pages.

**Still open from before:**
- Charts not visually verified in a running browser (select players on
  AdvancedAnalysisPage in both themes — quick check).
- This Week optimizer is single-pass greedy, no matchup/edge input — v1.
- Yahoo Fantasy API still blocked at Yahoo's end (support ticket).

---

# Handoff (2026-09-07, session 8) — Gridiron Terminal frontend build (started)

**Settled design direction** = "Gridiron Terminal" (see [[project_design_direction_gridiron_terminal]] + canvas https://claude.ai/code/artifact/5256ac5d-0797-4b66-94c1-3a30bc6f0a48, working files in `design/`). Began wiring it into the real `frontend/`.

**Foundation done this session (build + lint clean; lint's 1 error is the pre-existing useAuth.tsx one):**
- `frontend/src/index.css` — full token overhaul. `ink-*` remapped to a warm-neutral near-black ramp; `accent-*` remapped to turf green (readable on white); added `--color-volt` / `--color-volt-dark` / `--color-volt-ink`. Fonts → Barlow Condensed (display) + Space Grotesk (sans) + JetBrains Mono (stat). Added **dark mode**: `@custom-variant dark`, semantic surface vars (`--page/--surface/--surface-2/--hairline/--line/--text/--text-muted/--text-faint/--accent-ink/--field*`) that flip via `[data-theme]` + `prefers-color-scheme`, exposed as utilities through `@theme inline` (`bg-page`, `text-body`, `text-muted`, `border-hairline`, `border-line`, `text-accent-ink`, ...). Rebuilt `.yard-divider` (double hash rows, themed) + new `.field-backdrop`, `.stat-nums`.
- `frontend/index.html` — new Google Fonts; pre-paint inline script reads `localStorage['axis-theme']` → `<html data-theme>`.
- `frontend/src/hooks/useTheme.tsx` (new) — resolved light/dark + `toggle`; follows OS until explicit choice.
- `frontend/src/components/common/ThemeToggle.tsx` (new) — sun/moon button, lives in navbar.
- `frontend/src/App.tsx` — `bg-ink-50` → `bg-page text-body`.
- `frontend/src/components/common/Navbar.tsx` — full convert. Navbar is now the **always-dark "broadcast bug"** (`bg-ink-950`) in both themes; volt wordmark tile, volt active underline, volt Sign-In, ThemeToggle wired.
- `frontend/src/pages/HomePage.tsx` — full convert: Barlow hero, volt CTA, field backdrop, hash divider, hairline-grid feature cards, dark-aware surfaces. Verified both themes in browser (screenshots in session).

**NOT committed.** Stacks on the sessions 2–7 uncommitted pile.

**Session 8 continued — full page conversion + copy pass:**
- Mechanical dark-mode migration across ~30 page/component files via scripted class remap (`scratchpad/theme-migrate.mjs` + follow-up node one-liners): `bg-white`→`bg-surface`, `bg-ink-50/100`→`bg-surface-2`, `border-ink-200`→`border-hairline`, `border-ink-300`→`border-line`, `text-ink-900/800/700`→`text-body`, `text-ink-600/500`→`text-muted`, `text-ink-400/300`→`text-faint`, `text-accent-500/600/700/800/900`→`text-accent-ink`, `shadow-*` stripped, `font-black`→`font-bold`. Added `--highlight`/`--highlight-line` semantic tokens; `bg-accent-50/100`→`bg-highlight`. Swept stray `bg-gray-*`/`text-gray-*`/`bg-blue-*`/`text-blue-*`/`bg-orange-*`/`border-purple-*` → theme tokens. Stripped decorative emoji (🏈 📊 🤖 🔄 ⭐) from JSX.
- Copy rewrites (fantasy-technical-writer voice, per user: "design copy is better than the site's"): HomePage hero, LeaguesPage (header/empty-state/"What you get"), BlogPage (→"Analysis & Rankings", tightened subhead, "Generate a piece"), PlayersPage/WaiverWirePage/DraftPage empty+loading states, AuthPage (wordmark + one-liner), YahooCallbackPage (full restyle + terser copy).
- Build + lint clean throughout (lint's 1 error = pre-existing useAuth.tsx). Verified dark + light in browser on Home/Blog/Players/Draft/Leagues.

**Session 8 continued — full-site QA pass (backend + frontend up, demo token, every route walked in light + dark):**
Issues found and fixed:
1. **Primary buttons read muddy / half-disabled** (`bg-accent-500` dark turf + white text, ~22 files) → switched to `bg-volt text-volt-ink` / `hover:bg-volt-dark`. Filled-volt is now the primary-action treatment; outline/ghost for secondary. Much clearer hierarchy.
2. **PlayerCards were hollow** — default sort was "Relevance" (returns no proj/adp) so cards showed only name/team. Fixed: default sort → `consensus`; `PlayerCard` now shows a compact `RANK #n · PROJ · ADP · RISK` mono meta row + inline injury badge. "Player Rankings" now actually shows ranks.
3. **Leagues disconnect button looked like an error** (red `bg-danger-100` box + text `✕`) → subtle faint `XMarkIcon` button, danger only on hover. Modal close buttons: text `✕` → `XMarkIcon`.
4. **Content page had no H1** → added "Content Studio" heading + real subhead. Dashed-border quick-gen cards → solid hairline (was the only dashed-border in the app).
5. **Generic AI-slop subheads** rewritten: Players, Advanced Analytics, Historical Performance, Live Draft Assistant.
6. Emoji sweep widened (symbols/dingbats/pictographs) — confirmed the `⚖` on Trade Analyzer is a real `ScaleIcon`, not emoji.
7. `focus:ring-accent-500` → `focus:ring-volt` everywhere.
Verified in browser (light + dark): Home, Players, Leagues, Blog, Content, Historical, Analytics, Trade, Live Draft, Draft History, Post-Draft, Advanced Analysis. Build + lint clean.

**QA round 2 (user caught a miss):**
- **BUG: status-tinted surfaces had invisible text in dark mode.** `bg-{success,warning,danger}-50/100` and `text-{...}-700/800` were FIXED light values in `@theme` — so a playoff-line row (`bg-success-50` `<tr>` with `text-body` cells), Player Alert badges, error panels, etc. rendered as a pale light chip with near-invisible light text on the dark page. FIX: moved the `-50/-100` (soft bg) and `-700/-800` (tint-safe text) status shades into `@theme inline` backed by `--{status}-softer/-soft/-text` vars with real dark values (dark-tinted bg + light readable text). `-500/-600` stay fixed (icons, borders, solid fills). Verified: standings playoff rows + Player Alerts badges now readable in both themes.
- **BUG: `/leagues/:id?tab=standings` ignored the `tab` param** (always opened Overview) — the Leagues-page "Standings" button links with that param. FIX: `LeagueDetailPage` now reads `?tab=` via `useSearchParams` and seeds `activeTab`.
- **Perf (pre-existing, not fixed): `/leagues/:id` takes ~25-30s to first render.** It `Promise.allSettled`s 5 endpoints (roster/standings/insights/waiver/trade); each resolves in ≤6s alone but React StrictMode double-fires the fetch in dev and the ESPN-backed calls stack up. Worth: render standings/overview as soon as those 3 resolve instead of blocking on waiver+trade.

**Not a frontend bug (observed during QA):**
- `/leagues/1` "Loading league analysis" is slow/hangs — that's the real ESPN comprehensive-analysis endpoint making live ESPN API calls (session 6 feature). Loading state is honest; the backend call itself is the bottleneck.
- `/players/:id` via direct URL shows "we don't have this player loaded" — by design (detail page needs the Player object passed via router state from a list click).

**STILL open (next chunk):**
1. **"This Week" screen** — the flagship mock (matchup scoreboard, field slider, Optimize lineup, per-player EDGE, right rail) is NOT built. Belongs in `LeagueDetailPage` (884 lines, has existing roster/matchup/standings/waiver/trade tabs — needs a real integration, not a bolt-on).
2. **Data-table pages not visually verified in dark** — backend was down this session, so LeagueDetailPage rosters, WaiverWirePage rec cards, PlayersPage table, AdvancedAnalysisPage weren't seen with real data. Class migration was systematic so they *should* be right; needs a pass with the backend running.
3. **Recharts / chart components** still use hardcoded palettes (`components/charts/*`, `ChartTypes.ts` hex values, some inline `#6B7280` etc.) — not themed.
4. A few `text-white` on `bg-accent-500` buttons — turf green + white is ~4.6:1, acceptable but check large-text AA.
5. ~~Review & commit the diff~~ — **DONE** (session 9, `1efe7f9`, pushed).

---

# Handoff (2026-09-06, session 7)

**Yahoo login broken — root cause is on Yahoo's side, not ours.** OAuth token exchange succeeds (200, valid access token) but every `fantasysports.yahooapis.com` call 403s `"This application is not authorized to perform this action"`. Cause: Yahoo's developer portal no longer exposes the **Fantasy Sports (fspt) API permission** when creating/editing an app on this account — the create form only offers "OpenID Connect Permissions" and "TW Auction". Requesting `scope=fspt-w` then gets rejected at consent (`invalid_scope`) OR a token is issued with no fspt scope that 403s on every fantasy call. Confirmed by creating a fresh app (App ID `gc2Z4IAB`) — same missing permission. Original app is `3sPY0hJG`.

**Shipped this session (committed+pushed, `c977af2`, only these 3 files):**
- `backend/app/services/yahoo_service.py` — `authenticate()` logs the *granted* scope vs requested + warns when no `fspt`; `_error_detail()` maps the specific 403 to a plain-English explanation.
- `frontend/src/pages/YahooCallbackPage.tsx` + `LeaguesPage.tsx` — pass through & display Yahoo's real `error` / `error_description` instead of generic "Yahoo authentication failed". Needs Vercel redeploy (auto on push) to take effect since the callback page is static there.

**Next steps for Yahoo (all external / no code):**
1. Yahoo Developer Support ticket — the only real path. State: "Fantasy Sports API permission does not appear in API Permissions when creating/editing an app." Include App IDs `3sPY0hJG` and `gc2Z4IAB`. Days-to-weeks, not guaranteed.
2. Optional 2-min test: request the auth URL with NO `scope` param — Yahoo grants whatever the app actually has. Still 403 = app has zero fantasy access, nothing client-side fixes it. (Not built this session.)
3. Deprioritize — app not deployed publicly, ESPN analysis works, Sleeper needs no auth. Yahoo stays behind the honest "not connected" path until support responds.

**`backend/.env` currently holds the NEW app's creds** (Client ID starting `dj0yJmk9SU1IQUN0dUNlM1Bo...`, secret `140db9ee...`). Neither app works until Yahoo activates fspt. Confirmed live: consent screen returns `error=invalid_scope` for `scope=fspt-w`.

**Definitive Yahoo diagnosis (`220839b`, probe added):** reverted `.env` to old app `3sPY0hJG` (had to add the Vercel callback URL to its Redirect URIs in Yahoo console — was only registered for old ngrok URL). Old app: consent accepts `fspt-w`, issues token, but `granted scope: <none returned>` — token has ZERO fantasy scope. Every Fantasy endpoint 403s including bare `/fantasy/v2/game/nfl`. This is a hard server-side App-ID authorization block. **No code/config fix exists — Yahoo Developer Support ticket is the only path.** Ticket evidence ready in session 7 chat log.

**Also fixed this session (`9c6554e`, committed+pushed): Vercel SPA 404.** The deployed site had no `vercel.json`, so every path except `/` returned `404 NOT_FOUND` at Vercel's edge — refreshing `/leagues` 404'd and the OAuth popup's nav to `/yahoo/callback` 404'd (which is why connect hung on "Connecting..." with no error shown). Added `frontend/vercel.json` SPA rewrite. Verified live: all paths now 200. Vercel project root is `frontend/`, auto-deploys on push to `main`; `npx vercel` CLI is authed as `drod4eva`.

---

# Handoff (2026-09-05, session 6)

**Context:** user reported MarShawn Lloyd was recommended on the Waiver Wire despite not actually being available -- confirmed real, live: he's rostered by another team in the user's real ESPN league (Optis Titans), not a free agent.

**Root cause:** `WaiverWireService.get_live_trending_recommendations` sources candidates from Sleeper's *global* trending-add feed (players being added across all Sleeper leagues everywhere) and only ever excluded the user's own roster -- it had zero knowledge of which players are actually free agents in any *specific* connected league. A player trending broadly on Sleeper can easily already be owned by someone else in the user's real ESPN/Yahoo/Sleeper league. This affected every caller of the live waiver engine: the League Detail Waiver Wire tab (`league_management_service.py`'s `_get_espn_waiver_recs`/`_get_league_specific_waiver_recs`, from session 4) and both standalone Waiver Wire page endpoints (`waiver_wire.py`'s `/league-aware-recommendations/{league_id}` and `/recommendations?league_id=`).

**Fix:** added an optional `available_player_names` parameter to `get_live_trending_recommendations` (`backend/app/services/waiver_wire_service.py`) -- when supplied, any trending candidate not in that real, lower-cased name set is skipped outright (not just deprioritized; recommending an unavailable player is a correctness bug, not a ranking nuance). Wired real availability into every caller:
- **ESPN**: `espn_service_enhanced.get_available_players` (a real free-agent API, already existed, just unused for this purpose) -> name set.
- **Yahoo**: `yahoo_service.get_available_players` (real, `status=A` filter) -> name set.
- **Sleeper**: no dedicated free-agent endpoint exists, so availability is derived by excluding names of anyone rostered by *any* team in the league (not just the user's own), best-effort matched against the local `Player` table by `sleeper_id` -> name (this table is sparse/often-empty in this deployment, so this degrades gracefully to "no filter" rather than a broken one when it can't resolve names -- same honesty tradeoff already used elsewhere in this codebase for Sleeper).

All three of `league_management_service.py`'s two ESPN/Yahoo methods and `waiver_wire.py`'s shared `_fetch_connected_roster_and_settings` helper (now returns a 3-tuple: roster, settings, available names) were updated to fetch and pass this through. Failure to fetch availability degrades to the old unfiltered behavior (best-effort, consistent with this helper's existing fallback pattern), never raises.

**Verification:** live-verified against the real Optis Titans ESPN league -- MarShawn Lloyd confirmed NOT in ESPN's real free-agent list (`get_available_players`), and confirmed gone from all three affected endpoints' output after the fix (`/leagues/1/waiver-recommendations`, `/waiver-wire/recommendations?league_id=1`, and the direct service call). Cross-checked every remaining recommended player individually against the real free-agent list -- all genuine. Added 2 new regression tests (`TestRealAvailabilityFilter` in `test_waiver_wire_service.py`) covering the filter-applied and filter-omitted (backward-compat) cases. Full suite: 126 passed (up from 124). `npm run build` clean (no frontend changes needed -- this was entirely a backend correctness fix, existing response shapes unchanged).

**Not committed yet** — ask before committing/pushing. Changed files this session: `backend/app/services/waiver_wire_service.py`, `backend/app/services/league_management_service.py`, `backend/app/api/v1/endpoints/waiver_wire.py`, `backend/tests/test_waiver_wire_service.py`. Stacks on sessions 2-5's uncommitted work (only session 2's `6b3c230` is committed).

**Next task / open follow-ups:**
1. Sleeper's availability derivation is honestly weaker than ESPN/Yahoo's (depends on local `Player` table coverage, which is sparse) -- if a user's primary connected league is Sleeper, worth re-verifying this is actually catching real conflicts, not silently no-op'ing due to empty local data.
2. Review the growing uncommitted diff together and commit -- five sessions' worth of real fixes now stacked on the working tree.

**Key files:** `backend/app/services/waiver_wire_service.py` (`available_player_names` filter + `_player_full_name` helper), `backend/app/services/league_management_service.py` (ESPN/Yahoo free-agent fetch), `backend/app/api/v1/endpoints/waiver_wire.py` (`_fetch_connected_roster_and_settings` 3-tuple + ESPN/Yahoo/Sleeper availability derivation).
