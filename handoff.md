# START HERE — Session 28 (2026-11-12): project review, security and cleanup pass

A whole-project review, then every recommendation carried out on branch `cleanup/review-recommendations` (pull request open against `main`; nothing deploys until it is merged).

- **Security:** registration closed unless the email is in `REGISTRATION_ALLOWED_EMAILS`; per-IP rate limits on login, register, password reset and every AI / vision route (`core/rate_limit.py`); refresh tokens no longer work as access tokens; trade routes need a login; the demo credentials came off the login form and the auto-created demo user is gone (the founder's account is user 1 and no longer uses that password); password reset gives the same answer for known and unknown emails.
- **Removed:** Analytics, Advanced Analysis and Game Situations (pages, endpoints, four services, the chart components, recharts). No auth on 16 of those routes, no tests, and they were the only users of scikit-learn, statsmodels, pandas and pulp. Their database tables and models are untouched.
- **Kept on purpose:** Post-Draft Analysis, Draft History and Content (the 2026-09-08 decision), Historical (Waivers and Reports use it), `docker-compose.yml` (stale, the founder's call).
- **Dependencies:** `requirements.txt` holds only what the app imports (22 lines to 13 packages); pytest moved to `requirements-dev.txt`, research libraries to `requirements-scripts.txt`; passlib replaced by bcrypt 5 directly. The trimmed set was installed into a clean virtualenv and passed every test.
- **CI:** `.github/workflows/ci.yml` runs pytest and the frontend lint, tests and build on every push and pull request, and Render now deploys only after it passes (`autoDeployTrigger: checksPass`).
- **Shared board:** only the owner account (user 1) or emails in `BOARD_UPLOAD_EMAILS` can replace the uploaded Betr / PrizePicks board.
- **Tests:** backend 304 to 337 (security, consensus ranking, position pressure, custom scoring, snapshot cache); frontend has its first tests (vitest, 21, Bets helpers and the Shows verdict).
- **Frontend:** `LeagueDetailPage` 1,723 to ~500 lines and `WaiverWirePage` 1,565 to ~400, split into one component per tab; lint is clean. Checked three ways: moved JSX is line-identical to the original, the tabs render real cached league data, and all eleven tabs were clicked through in the browser against a throwaway local database.
- **Shows:** VSiN MegaPod week 10 (12 picks) and the VSiN college week 11 compilation (11) imported.

## Next
- The founder: merge the pull request when ready; nothing reaches Render or Vercel until then. After the merge, check Render synced the Blueprint (Settings shows auto-deploy "After CI checks pass").
- Optional: set `REGISTRATION_ALLOWED_EMAILS` in Render to let someone new sign up (unset = closed, which is safe).
- Older sessions (12-21) are in `docs/archive/handoff-2026-sessions-12-21.md`.

# START HERE — Session 27 (2026-11-09): weeks 5-9 review; price-edge rule, TD recalibration, cloud board builds

> Session 26's notes below still hold for everything not mentioned here. Full record: BETTING_GUIDE "Weeks 5-9 review" + decisions log (2026-11-09).

- **Board builds moved off the Mac:** `.github/workflows/board-build.yml` → `POST /api/v1/betting/cron-build` (secret `DIGEST_CRON_SECRET`, same as the weekly digest), hourly 7am-10pm ET Thu-Mon + noon Tue/Wed. Tracking writes retry dropped DB connections (`_db_write_retry`). Why: the launchd job missed/failed most runs since 10-29, so week 8 got 82/1,037 closing lines and week 9 none.
- **Engine 2026-11-09.1, prop bets need a price edge** (`PROP_MIN_BOOK_EV` = 0): 116 of 119 live bets were model-only (Hard Rock worse than fair), predicted 54.4%, hit 46.6%; 2025 backtest the same (n=199). They now drop to watch → 0.5u fills. Expect ~3-4 real bets a week.
- **Engine 2026-11-09.2, anytime TD × 1.30** (`TD_RATE_CALIBRATION`): fit on 2025 only, held-out gain on 2026 live (Brier CI excludes 0). Longshots under 15% read ~1 pt high; capped at the raw price.
- **Shows:** imported VSiN Bills-Vikings MNF props (7; Jefferson "longest reception" lean not trackable); skipped Fantasy Alarm's Sunday week-9 stream (games played). FA's MNF stream (YD7hkNZImlw) had no captions yet.
- 58 betting tests pass; the cron endpoint was run end to end locally (200, 80 props, 15s). Pushed as d7ae216; the founder ran the GitHub workflow by hand: success, board saved. GitHub's scheduled runs were late/missing on day one (the weekly digest runs 5-7h late every week): check them; if unreliable, move the trigger to Supabase pg_cron + pg_net.
- **Betr replaces PrizePicks (founder, 2026-11-09): Hard Rock first, Betr second.** Paste flow built (`betr_board.py`, `POST /betting/betr-board`, paste box on the Betr tab); Bets tabs now Lines (default) → Betr → Shows → Entries → Record. Tested on the live MNF board text: 20/20 cards matched. Then, at the founder's request, read Betr's slip in Chrome (nothing placed, slip cleared): Perfect 3x/6x (2/3 picks, cross-game), Flex 2x/0.5x; 2+ teams required; special cards More-only; same-game picks pay less (2.8x, and 4x for a 3-pick) → Betr pairs/entries one pick per game, stacks off for Betr. Reading Betr via Chrome only when asked.
- **Betr by screenshot:** Betr's site blocks text selection, so screenshots are read by the vision models (`betr_screenshot.py`, `POST /betting/betr-screenshots`; paste an image into the box or upload several). OpenAI key authenticates; the local Anthropic key returns 401 (fallback down). Not yet tested on a real screenshot (costs ~a few cents a read).
- **`ODDS_PLAN` switch built, plan kept on paid:** `ODDS_PLAN=free` in Render (default `paid`) cuts to ~410 credits/month (5 core prop markets once per game, no closing fetch, lines daily). Real use on paid: ~2,200/month (19,204 left on 11-09). Flip it before the paid plan lapses, not after.
- **Board never blank on Monday night:** `odds_service.upcoming_games` rolls to next week once this week's games have all started (week + 1). Live games deliberately not priced (founder bets live, but pregame numbers can't price them). Instead a **Live now** panel keeps the card's picks for games under way at their pregame price (`betting_tracking.live_picks`), flagging old-engine model-only bets.
- Founder's Mac was off Oct 28 - Nov 8 (vacation): that, not sleep, is why weeks 8-9 lost their closing lines.

## Next
- Founder: deploy (push), and confirm `DIGEST_CRON_SECRET` is set in both Render env and the repo's Actions secrets; then run the workflow once by hand (Actions → Betting board build → Run workflow) and check the log shows HTTP 200.
- After weeks 10-12: first clean CLV read (open item 7), and judge engine 2026-11-09.x on its own rows (Results → current engine).

# START HERE — Session 26 (2026-10-21): Hard Rock bets in My entries (college too), shows imported

> Session 25's notes below still hold for everything not mentioned here.

- **Pushed** session 25's closing prop fetch (2daf958^) and **installed** `com.fantasyfootball.board-close` on the Mac (first run 2026-10-22 12:00; 19:30 covers TNF).
- **My entries form** now logs Hard Rock bets: PrizePicks / Hard Rock switch, straight or parlay, odds per leg, spreads typed as the book shows them. College Hard Rock bets (`sport: "cfb"`, game lines only, each leg's kickoff) grade from ESPN's college scoreboard; void 4 days after kickoff without a final.
- **Logged for the founder (week 7):** 5 college straight bets (ids 17-21: Toledo -2.5, Auburn +7.5, South Carolina -2.5, Liberty/Kennesaw St Over 50.5, Kennesaw St +9.5) and the NE +2.5 / Over 49.5 SGP (id 22, $9.76 to pay $34; leg prices unknown, -110 placeholders, neither leg can push).
- **Shows:** imported Fantasy Alarm x2 (NE @ CHI totals, Caleb Williams pass TDs lean) and VSiN college week 8 (11 picks); skipped VSiN's WSH @ SF props (game played).
- **Two stats of one player** (PrizePicks allows it; founder's entry 25, Roschon targets + rec yds): My entries and the ticket tray accept them; the tray prices the pair with `SAME_PLAYER_CORRELATION` (measured by `scripts/experiments/corr_same_player.py`, 8,398 player-weeks) and refuses unmeasured pairs. Generated suggestions stay one pick per player until the founder confirms which same-player combos PrizePicks accepts and at what payout.
- **Prop vs game-total correlation measured (2026-10-28):** `PROP_TOTAL_CORRELATION` in betting_model (passing yds +0.40, rec yds +0.16, receptions +0.12, rush yds +0.06), read by `leg_correlation` when a `game_total` leg meets a prop. Nothing recommended combines them yet, so ENGINE_VERSION unchanged. Same session: tune_from_results on 3,199 graded lines — every tier calibrated, blend beats books (Brier 0.2030 vs 0.2046), MODEL_WEIGHT stays 0.3.
- **Shows 2026-11-08 (week 9, before the 9:30 Madrid kickoff):** imported Beating the Book MegaPod (10; CAR +2.5 x3, ARI +8.5 x2), VSiN week 9 props (15), Fantasy Alarm's Friday Betting Playbook (8), Fezzik Fridays (NE, no number on air, stored at the 11-08 consensus -3 with `line_stated: false`). Skipped 17: everything for week 8, TNF JAX @ BAL, college weeks 9-10 (all played) and the FA DFS/start-sit show (no picks). A fresh fetch at 09:15 found nothing new; the Sunday FA stream wasn't up yet.
- **Shows 2026-10-29:** imported Fantasy Alarm TNF (4) and VSiN Panthers-Packers props (6).
- **Shows 2026-10-26 to 10-28:** imported VSiN Cowboys-Eagles props (7), Fantasy Alarm's TNF over (1), VSiN college week 9 compilation (14), Beating the Book MegaPod week 8 (12); skipped two NBA/NHL-only Betting Playbooks and the Sunday start/sit stream.
- **Shows 2026-10-23:** imported Action Network college (26), VSiN props (17), Fezzik Fridays (NFL 1 + college 2), Fantasy Alarm start/sit (2 leans). YouTube's bot check blocks both the transcript API and yt-dlp from the Mac, so the launchd fetch misses videos: get them in Chrome (YouTube's new panel uses `transcript-segment-view-model` elements; Chrome allows one automatic download per site, so later ones must be read off the page). Fantasy Alarm's 10-23 Betting Playbook (wc45KecI6K0) had no captions yet. The yt-dlp fallback in `fetch_show_transcripts.py` (used when the transcript API is IP-blocked) was committed 2026-10-28 at the founder's go-ahead; it doesn't get past the bot check either, so Chrome stays the backup.
- **Safest picks lesson:** Florida pays 1.2x for two goblins (confirmed again); the safest 2-pick (66%) loses ~21% there. Offered the founder two fixes (price the pair at the real payout / pair a goblin with a standard line); not decided.

## Next
- Founder's call on the Safest 2-pick change above.
- After week 7: first real CLV read, check the college entries graded.

# START HERE — Session 25 (2026-10-20): weeks 5-6 review, closing prop fetch, tracked tickets

> Session 24's notes below still hold for everything not mentioned here.

- **Week 6 fully graded** (MNF included). Read: BETTING_GUIDE section 9, "Weeks 5-6 results and tests". Bets 42-26 +33.8u (Hard Rock 34-19 +25.4u), likely mostly variance (same rules ~0 at Hard Rock on 2025 lines). `tune_from_results.py`: keep 0.30.
- **Closing prop fetch (not yet deployed):** `odds_service.PROP_CLOSE_LEAD` = 2h, one extra fetch per game (~240 credits/week); in the window `get_event_props` reads `odds_cache` before memory so Render and the Mac don't double-pay or write the older price over the close. `backend/scripts/build_board.py` + `backend/scripts/launchd/com.fantasyfootball.board-close.plist` (12:00, 15:30, 19:30). Run once 2026-10-20: works (6,193 credits left).
- **Tracked tickets:** `tracked_entries.tickets_from_entries` now saves the page's default distinct list (positive EV, max 6, < half shared picks), mirroring `PrizePicksEntries.tsx`.
- **Rejected after held-out tests:** PrizePicks Less correction (I'd told the founder 3-5 pts; on all near lines it's 1.4 and no shift beat noise in both directions), stake caps on EV 12%+, loosening the stale guard, requiring ESPN for passing.
- 289 backend tests pass.

## Next
- Commit + push (Render deploys the odds change), then the founder installs the launchd job (BETTING_GUIDE founder action 0). Until Render runs the new code, its own rebuilds could write the early price over a closing price.
- After week 7: first real CLV read (open item 7), passing-yards watch, Hard Rock-only record.

# START HERE — Session 24 (2026-10-15): props backtest, Render key, 7 new prop markets + alternates

> Session 23's notes below still hold for everything not mentioned here.

- **2025 props backtest done** (13,309 credits; BETTING_GUIDE section 9): projections add nothing over the books; only QB + own-receiver stacks hold up on real PrizePicks lines (Less/Less ~+6% as a 3-pick). No engine change from it; founder still to decide on Hard Rock prop units, a 36h-snapshot test, TD de-vig recalibration.
- **Render's `ODDS_API_KEY` updated** by the founder (~22:50 UTC). The old key had kept writing `credits = 5` to the shared `odds_cache`, which blocked every prop fetch this week. Confirm the stored `credits` stays ~6,400 after Render's next game-lines fetch.
- **Engine 2026-10-15.1: 16 prop markets** (7 more PrizePicks stats + alternate lines for the core 4), 16 credits a game. Details in BETTING_GUIDE section 4. PrizePicks uploads now keep those stats; the founder's 10/15 upload was re-parsed from `backend/2026-10-15-projections.json` (upload time kept). 282 backend tests pass; frontend builds.
- **Shows:** Fantasy Alarm TNF week 6 (6 picks) imported before kickoff.
- **Account ~6,420 credits** until the monthly reset.

## Next
- After Sunday: read graded `pp_leg` rows for alternate-line goblins/demons (does the Over-only de-vig hold?) and the new markets' calibration.
- Founder decisions listed in the first bullet.

# START HERE — Session 23 (2026-10-13): Odds credits schedule, Fantasy Alarm transcripts

> Session 22's notes below still hold for everything not mentioned here.

## State right now
- **Odds API credits: 7 left (2026-10-13), below the 60 reserve**, so no props until the monthly reset (date on the founder's the-odds-api.com account page). Game lines have ~3 fetches left.
- **New fetch schedule (`00d7e0f`, founder's call):** each game's props are fetched once, in the 36h before its kickoff (`odds_service.PROP_FETCH_LEAD`); game lines cache 12h; college lines refetch only Thu-Sat (`CFB_LINE_WEEKDAYS`). ~75 prop credits/week + ~170 lines/month ≈ the 500 limit. Founder chose 36h over 72h (same cost) for fresher prices; Sunday props appear Saturday. Measured: a prop market costs 1 credit/game with or without the PrizePicks book. Engine version unchanged (timing only). 278 backend tests pass.
- **Fantasy Alarm YouTube streams added to the transcript fetch (`9d8d4ed`):** `CHANNELS` in `fetch_show_transcripts.py`. Its Week 6 picks stream (`CPF3xJC9wqQ`, aired 10/13) had no captions yet (`post_live`); the fetcher retries every run. YouTube was IP-blocking transcript requests after a 40-video backfill; should clear.
- **Transcripts:** 13 old VSiN shows (weeks 2-5) backfilled and marked skipped (games played). 0 pending.

- **2026-10-15 update:** new Odds API key on the $30 tier (API reports 20,000 credits/month; founder said "200k", the API says 20K). Saved balance in `odds_cache` reset to 20000. Founder: keep the 36h/12h schedule (conservative, may unsubscribe later); spend the extra credits on analysis. Render's `ODDS_API_KEY` updated by the founder 2026-10-15 ~22:50 UTC. Until then Render's old key kept writing `credits = 5` to the shared `odds_cache`, which blocked every prop fetch (reserve 60) -- that's why week 6 had no props until the local rebuild at 22:43 UTC.
- **Shows imported 2026-10-15:** Fantasy Alarm Betting Playbook 10/13 (2) + 10/14 (4), VSiN college week 7 compilation (13, analysts unnamed), Beating the Book MegaPod week 6 (13). Teasers, team totals, NHL/MLB skipped. 0 pending.

- **Props backtest pilot done 2026-10-15 (251 credits; account 19,749):** `backend/scripts/backtest_props.py` (`fetch` spends credits, hard `--max-credits` cap + 2,000 reserve, every response cached in gitignored `backend/.cache/backtest/odds_hist/`; `run` is free and prices the cache with the shipped `evaluate_player_prop`, grades vs Sleeper stats, reports any-book and Hard Rock-only). Measured cost: **50 credits/game** (10/market), 1 per week's event list; all 7 books + Hard Rock + PrizePicks present in 2025 snapshots. Snapshot = kickoff - 3h. Pilot = 2025 week 11, first 5 games (a full week is ~15 games, ~750 credits; the "~250/week" figure in the proposal was really 5 games). 274 graded props. Too small to read: shipped bets 5-4 +6.0u; ESPN-vetoed bets 12-6; Brier books 0.1884 / Sleeper 0.1821 / blend 0.1855.

## Next
- **Full 2025 props backtest DONE 2026-10-15** (founder approved; 272 games, account now 6,442). Results in BETTING_GUIDE section 9, "Player props on real 2025 lines": projections add nothing over the books (Brier 0.2033 blend vs 0.2035 books); shipped bets +4.4% at any book via line shopping, −1.7% at Hard Rock only; ESPN check and EV bar show no value; Unders lean real but only beats vig on receptions at best-of-7; TD de-vig over-corrects mid-range. **No engine change made: founder to decide** (options: shrink/stop sportsbook prop units at Hard Rock, test 36h-ahead snapshots for the early-line question, recalibrate TD scale).
- **Follow-ups (same data, free, 2026-10-15):** line shopping alone and PrizePicks-vs-books discrepancies show no reliable edge 3h out; `_books_chance` overstates far-line chances by ~4-5 pts; TD fit `0.95×raw^1.06` beats the shipped scale above 15% raw but not significantly; **QB + own receiver stacks confirmed on real PrizePicks lines (+4.4 pts both More, +6.7 both Less)**, so Less/Less 3-pick stacks look ~+6%. Scripts: `scripts/experiments/props_hist_market_checks.py`, `props_hist_stacks.py`.
- If credits are still tight next month: NFL game lines once a day saves ~60/month.
- Offered, not built: Whisper transcription of uncaptioned streams (needs founder's OK to download audio).

# START HERE — Session 22 (2026-10-12): Week 5 read, two engine guards, VSiN transcript fetcher

> Session 21's wrap below still holds for everything not mentioned here.

## State right now
- **Engine `2026-10-12.2`** (two changes, both in BETTING_GUIDE section 3):
  - `.1` passing bets capped at 1u when ESPN projects the other side (`SPLIT_PROJECTION_MAX_UNITS`, closes open item 10).
  - `.2` part-time players (lagged snap share < 50%, `MOST_LIKELY_MIN_SNAP`) left out of Most likely to win. Held-out backtest backs it; it would NOT have caught week 5's misses (their earlier shares were 51-84%).
- **Week 5 read** (closes open item 6): BETTING_GUIDE section 9, "Week 5 results". Bets 21-15 +11.7u, 69% beat the close; passing 1-4; Unders beat predictions in every market (watch weeks 6-7, don't tune); Hard Rock-only 6-6 +1.3u.
- **VSiN YouTube transcripts:** `backend/scripts/fetch_show_transcripts.py` (deps in `backend/requirements-scripts.txt`, local only) saves new NFL/college picks shows to `backend/transcripts/`. Founder installed the launchd job 2026-10-12 (plist copy + install/remove steps in `backend/scripts/launchd/`). Imports stay by hand, before kickoff.
- **Shows:** VSiN Prop Points 10/12 (Bills @ Rams MNF, 6 picks) imported.
- **Import tracker + session-start hook:** `.claude/settings.json` runs `backend/scripts/transcript_status.py --hook` at every session start; pending transcripts (not in `backend/transcripts/import_log.json`) are listed for import. Picks JSON gets a `"transcript"` field; `--skip FILE --note` for ones with nothing to import. All handled 2026-10-12 (see Shows below).
- 274 backend tests pass.

- **Bets page review (UX + frontend designer), phase 1 built:** Audit opens on the latest mostly-settled week with sections folded to summary lines; no repeated lists (PrizePicks preview links, Shows tails list, Record sport switch); Shows folds Pass/Can't check; one Lines filter, started games folded; `ShowMore` caps long lists; muted one-line disclaimer, bankroll in ⓘ. Phases 2 and 3 also built (2026-10-12): ticket survives tab switches, tray collapsed, theme and search-speed fixes; shared format/pieces and one week stepper. See BETTING_GUIDE section 6.
- **Sportsbook bets in My entries:** `user_entries.py` committed (straight + parlay, Hard Rock Bet). The founder's three Week 5 Hard Rock bets are logged (ids 11-13).
- **Shows:** Week 5 MegaPod imported (Gil Alexander, Rams -3 MNF); Bucs-Cowboys props and college week 6 skipped (games played). 0 pending.

## Next
- Re-read weeks 6-7: the Under pattern, the 50-65% snap tier in Most likely, the Hard Rock-only record, CLV (open item 7).
- Not committed by this session (founder's own work): `scripts/fetch_nfl_prizepicks.mjs`, `backend/2026-10-12-projections.json`.
