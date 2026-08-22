# Style Guide — Fantasy Football Assistant

Synthesized from three independent specialist passes on the actual running app (not the code in the abstract): a **Creative Director** review of the visual system, a **Sr. Fantasy Data Scientist** review of how real numbers get presented, and a **Super Fan** review of voice/copy against how real players actually talk about their leagues. Full source specs are referenced inline; this document is the single applied standard going forward — new pages and components should conform to it rather than to whatever the nearest existing page happens to do.

## Verdict

The "Friday Night Lights" palette (`frontend/src/index.css`'s `@theme` block — `ink`/`accent`/`success`/`warning`/`danger`) is a good, disciplined system, correctly identified as the sole live source of design tokens (`tailwind.config.js` is confirmed inert — no `@config` directive loads it). The problem isn't the system, it's coverage: only 6 files are fully clean, and the two pages carrying the most real computed data (Waiver Wire, Trade Analyzer) are also two of the least converted. Two real bugs surfaced independently by two different lenses: position/injury badge color logic is implemented three separate times with diverging results (a TE badge is a different color depending which page you're on), and the Analytics optimizer solves a real linear program over a fake, hardcoded roster. The copy problem is narrower than the color problem — vocabulary is genuinely native throughout, but the sentences around that vocabulary read as generic SaaS template rather than something written by people who play.

---

## 1. Color System

**Tokens** (`frontend/src/index.css` `@theme`): `ink-50…950` (11-step navy neutral), `accent-50…900` (9-step rust, brand color at `accent-500` `#c2560b`), `success/warning/danger-{50,100,500,600,700,800}` (6-step semantic scale).

**Usage rules** (confirmed from the cleanest existing pages — `LeaguesPage.tsx`, `Navbar.tsx`, `PlayersPage.tsx`):
- `accent-500` = default interactive fill (buttons, focus rings, spinners); `accent-600` = hover; `accent-300` = hover-border accent on cards.
- `success`/`warning`/`danger` are reserved for **categorical status meaning only** — injury state, error/warning banners. They must never represent a continuous score (see §2) or the semantic ramp stops meaning one consistent thing.
- Position badges (QB/RB/WR/TE/K/DEF) are **not** brand or semantic color — they're a fixed categorical palette of their own, defined once in `playerDisplay.ts` (§6) and nowhere else.

**Gaps to close:**
- No pressed/active state token exists (`active:bg-accent-700` should be defined before it's needed ad hoc).
- No disabled-state token — every disabled button today bolts `disabled:opacity-50` onto whatever base color it has, including stock `bg-blue-600`. Standardize: `disabled:bg-ink-200 disabled:text-ink-400 disabled:cursor-not-allowed`.
- Dark mode does not exist (`body { color-scheme: light }` is hardcoded). The `ink` ramp is dark-mode-ready in principle since it's already a navy scale, but would need inverted semantic mapping — flagged as a known future gap, not attempted now.

---

## 2. Data Confidence — the "how real is this number" pattern

The app now computes genuinely real numbers (Sleeper add-count-derived waiver confidence, rank-based trade value, live `search_rank`), but historically displayed nearly all of them as bare `"73% confidence"` text — visually indistinguishable from the fabricated placeholder scores this app spent real effort removing elsewhere. A raw percentage reads as fake regardless of whether it is, because that's exactly what the fake version looked like.

**Standard component: `DataConfidenceBadge`** — a small inline badge placed next to any computed number's label, three states:

| State | Style | Meaning |
|---|---|---|
| **Computed** | `bg-ink-100 text-ink-600`, no icon | A direct, deterministic calculation from real data (waiver confidence, trade value, draft rank). Not a claim of accuracy — just "not guessed." |
| **Heuristic** | `bg-warning-100 text-warning-800`, `InformationCircleIcon` | A real calculation standing in for something more sophisticated the app doesn't yet do (e.g. trade value as inverse rank). |
| **Insufficient data** | `bg-ink-50 text-ink-400 border border-dashed border-ink-200`, `ExclamationTriangleIcon` | The honest empty state — ML predictions/clustering before the historical table populates. |

**Confidence/score display rule:** pair every confidence number with (a) a horizontal bar and (b) the real underlying quantity it derives from, in that priority order — the bar alone is still just a fancier percentage; the underlying number (e.g. "2,847 adds · 24h" next to a waiver confidence bar) is what makes it read as genuinely computed rather than decorated. Use `accent-500` fill on `ink-100` track for these bars universally — confidence is a continuous score, not a good/bad state, so it does not belong in the `success`/`warning`/`danger` ramp. The `ValueBar` pattern already built in `TradeAnalyzerPage.tsx` is the reference implementation — reuse and extend it rather than building a second bar component.

**Tiering:** `search_rank` exists per player but every list renders as a flat sequence with no sense of how close together ranks actually are. Insert a gap-based tier divider (computed client-side: within a position group sorted by rank, break whenever the gap to the next player exceeds ~1.5x the running median gap) rendered as `border-t border-ink-200` with a centered `bg-ink-50 text-ink-500 text-xs` label ("Tier 2") — not a colored row background, which would fight the injury/risk color already on the row. Highest-leverage placement: the Draft "Available Players" panel (the actual decision list during a live pick).

**Trend indicators:** waiver trending is real (Sleeper's live add-count feed) — recolor the existing arrow icons from raw `text-green-500`/`text-red-500` to `success-600`/`danger-600`, and extend the same arrow-only convention (no sparkline — this app has no historical time series to back one, and a fake-looking sparkline would reintroduce exactly the fabrication problem this section exists to prevent) to the Players list, which currently has no trend signal despite the same data being available.

**Stat tiles** (Analytics/Optimization results): a solved LP has one answer, not a trend — three flat tiles (`bg-white border border-ink-200 rounded-lg p-4`, `text-ink-500 text-xs uppercase` label, `text-ink-900 text-2xl font-semibold` value) for Total Salary / Projected Points / Objective Value. No gauge, no sparkline.

**Rule that generalizes across all of the above:** never visually equalize a working feature and a stub. Tag every tab/section with the confidence-badge vocabulary above rather than defaulting to "Computed" out of optimism — check the real backend state before badging.

---

## 3. Typography

No type scale currently exists — `index.css` sets only a body font stack (`Inter, system-ui`). Sizing today is ad-hoc utility scatter across the codebase. Formalizing observed usage rather than inventing new ground:

| Role | Class | Weight |
|---|---|---|
| Page title | `text-2xl md:text-3xl` | `font-bold` |
| Section heading | `text-lg` / `text-xl` | `font-semibold` |
| Card title | `text-lg` | `font-semibold` |
| Body | `text-sm` | `font-normal` / `font-medium` |
| Caption/meta | `text-xs` | `font-medium` |

`text-4xl` (currently only the HomePage hero) stays a deliberate one-off, not part of the scale.

---

## 4. Spacing & Elevation

**Spacing** is already reasonably consistent — codify explicitly rather than change: page container `p-6`, card `p-4`, inline cluster `gap-2`, section stack `space-y-6`.

**Elevation** — not actually "one shadow tier" as implied by the CSS comments; 4 tiers are in active ad-hoc use. Standardize on the two-tier resting/hover model already used correctly in `PlayerCard.tsx`: resting = `shadow-sm border border-ink-200`, hover = `hover:shadow-md hover:border-accent-300`. Bare `shadow` and `shadow-lg` are leftover pre-redesign values and should be migrated to this pair as pages get touched, not used in new work.

**Radius**: `rounded-lg` for cards, `rounded-md` for inputs/buttons, `rounded-full` for badges/avatars/spinners.

---

## 5. Iconography

Heroicons `24/outline`, consistently, everywhere — keep this 100% (no `solid` variant mixing). `ExclamationTriangleIcon` is the standard warning/pending icon. Gap: injury status today is color/text only, never paired with an icon, unlike every other warning context in the app — pairing `ExclamationTriangleIcon` with OUT/DOUBTFUL/IR badges would bring injury indicators in line with how warnings are shown everywhere else.

---

## 6. Component Patterns — the canonical reference implementations

Copy these exact patterns when building or fixing a page; don't reinvent per-page.

- **Buttons**: `bg-accent-500 text-white px-4 py-2 rounded-md hover:bg-accent-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed`, `focus:ring-2 focus:ring-accent-500`.
- **Forms**: `border border-ink-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500`.
- **Loading spinners**: `animate-spin rounded-full border-b-2 border-accent-500`.
- **Error states**: `bg-danger-50 border border-danger-200 text-danger-700`.
- **Status badges (position + injury) — single source of truth**: `frontend/src/components/players/playerDisplay.ts` is the canonical, and only, place position-color and injury-status-color logic may live. It was previously reimplemented independently in `PlayersPage.tsx` (byte-for-byte duplicate) and `DraftBoard.tsx` (diverging — TE/K colors swapped relative to the canonical mapping, meaning the same player's badge visibly changed color depending which page you viewed it from). Both are being consolidated to import from `playerDisplay.ts` rather than reimplement it (tracked fix, see Rollout below). Any new surface that needs a position or injury badge imports from `playerDisplay.ts` — it does not write its own color map.
- **Empty states**: no strong existing pattern to copy (only one real example, plain gray text) — new empty states should pair a short, specific sentence (not "No data found") with `text-ink-500`, and reserve an icon for empty states that represent a genuinely unusual condition rather than a normal "you have nothing yet" state.

---

## 7. Voice & Copy

Vocabulary throughout the app is genuinely native — "Waiver Wire," "PPR," "Bye Week," "Trending," "ADP" all read as written by people who know the game, and that should be actively protected, not "improved." The gap is entirely in the sentences surrounding that vocabulary, which default to generic SaaS-onboarding register ("AI-powered," "Smart," "Comprehensive," "Intelligence").

**Working rule for every rewrite:** name an actual stake or a concrete mechanism, never an adjective. `"Smart recommendations"` says nothing a real player would repeat to a friend; `"Who's available, who's trending, and who you should drop to make room"` does. Test: would this sentence survive being said out loud in a league group chat? If not, it's copy filler.

**Two hard constraints, given this app just went through a real pass to strip overclaiming "AI-powered" labels off template/heuristic content** — any copy rewrite must stay inside these, not just be punchier:
1. Never add confidence-boosting language that outruns the underlying math. The waiver `confidence_score` is a weighted composite, not a probability — "tough matchup" is honest, "lock of the week" is not.
2. Never imply prediction from backward-looking data. `trending_count` is a live add-rate stat, not a forecast — "Trending — 2,847 adds today" is honest, "Primed for a breakout" is not, unless it's tied to an actual projection field.

Where an "AI" label is currently used and the call is real (verify against the actual endpoint before touching the label — e.g. `DraftPage.tsx`'s "AI Recommendations" genuinely calls `ai_service.generate_draft_recommendation`), leave it alone. The problem this section addresses is genericness, not falseness.

Concrete rewrites already identified as ready to ship (see `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/WaiverWirePage.tsx`, and the full specialist spec for the complete list):
- HomePage hero: replace "Your AI-powered companion for dominating your PPR fantasy football league" with something that names a real stake instead of a cliché, while keeping "PPR" as accurate native terminology rather than the whole hero's hook.
- WaiverWirePage header: "Waiver Wire Intelligence" / "Smart recommendations, trending players, and weekly analysis" → "Waiver Wire" / "Who's available, who's trending, and who you should drop to make room."
- DraftPage: "Team {n} is picking..." → "Team {n} is on the clock..." (the actual phrase every real draft room uses).

---

## 8. Rollout — Gap Audit

28 files still carry raw stock-Tailwind color classes instead of the tokens above (full per-file hit counts captured in the source Creative Director spec). Converting all of them in one pass isn't the right shape of work — this section tracks what's fixed now vs. deliberately deferred.

**Fixed as part of this style-guide pass** (see task tracker / commit history for status):
- Position/injury badge consolidation to `playerDisplay.ts` as sole source of truth (`PlayersPage.tsx`, `DraftBoard.tsx` and its sibling Draft components).
- `AnalyticsPage.tsx` optimizer wired to real player data instead of the hardcoded `sampleLineupPlayers` array.
- `WaiverWirePage.tsx` — full token migration, confidence-bar + `DataConfidenceBadge`, copy rewrite. Chosen because three independent specialist lenses (visual, data, voice) flagged it as the single highest-priority remaining page, and it's the highest-frequency weekly touchpoint in the app.
- `HomePage.tsx` — token migration + hero/feature-card copy rewrite. Highest-traffic first-impression page in the app.

**Deliberately deferred** (tracked, not silently dropped): the remaining ~24 files, in the order the Creative Director spec ranks them by stock-color hit count — `AdvancedAnalysisPage.tsx` (185), `HistoricalPage.tsx` (147), `LeagueDetailPage.tsx` (131), `PostDraftAnalysisPage.tsx` (96), `ContentPage.tsx` (81), `BlogPage.tsx` (71), `LiveDraftPage.tsx` (58), `TradeAnalyzerPage.tsx` (55), `BlogPostPage.tsx` (42), and the smaller component-level files below 35 hits each. Convert opportunistically as each page gets touched for other reasons, using this document as the standard, rather than as a dedicated future sweep — a mechanical find/replace pass without design judgment would just relocate the debt, not resolve it.

**Genuinely clean already** (0 stock-color hits, confirmed): `PlayersPage.tsx`, `PlayerDetailPage.tsx`, `LeaguesPage.tsx`, `Navbar.tsx`, `PageLoader.tsx`, `PlayerCard.tsx`.
