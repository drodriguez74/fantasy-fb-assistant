"""Pure pricing math for player and game props: odds conversion, de-vigging,
Monte Carlo outcome simulation, expected value and Kelly unit sizing.

Method (what a recommendation means)
------------------------------------
1. Market fair probability. Each book's two-way price is converted to
   implied probabilities and de-vigged (multiplicative normalization so
   over + under = 1); books quoting the same line are averaged. The
   betting market is the sharpest public estimate there is, so it anchors
   everything.
2. Model probability (player props). A two-level Monte Carlo around the
   player's projected stat line (Sleeper's weekly projection):
   - parameter uncertainty: the true mean is drawn around the projection
     (a projection is itself an estimate, sd PROJECTION_ERROR of it);
   - outcome noise: yards ~ gamma with a market-specific coefficient of
     variation (passing yards are steadier than receiving yards);
     receptions and touchdowns ~ Poisson.
   P(over) is the share of simulations above the line.
3. Shrinkage. Final probability = MODEL_WEIGHT * model + (1 - MODEL_WEIGHT)
   * market. Projections lose to closing lines over large samples, so the
   model only gets to lean on the market, not override it.
4. Edge and size. Expected value at the best available price; stake by
   fractional (quarter) Kelly, expressed in units where 1 unit = 1% of
   bankroll, rounded to 0.5 and capped at MAX_UNITS. A bet is recommended
   only when EV >= MIN_EV and the model and market agree on the side.
   More units = larger estimated edge relative to price = more confidence.

Game props (spreads, totals): the NFL margin follows a key-number
distribution (a normal around the consensus spread, SD 13.26, reweighted so
games land on 3, 7, 6, 10 and 14 as often as they really do -- fitted on
2015-2024 closing lines, see KEY_MARGIN_LOG_WEIGHTS); totals ~ N(consensus,
13.0). Centered on consensus, they find edges only where one book's line or
price is off the market (line shopping), never by out-predicting it. The
Sleeper game model gets no weight in the NFL (GAME_MODEL_WEIGHT): on real
closing lines it carried no information (2025 + 2026 backtests).

Calibration constants are standard published magnitudes, not fitted to
this app's results yet; they should be tuned once graded results exist.
"""
import zlib
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

# Stamped on every tracked pick, tracked ticket and logged entry so the
# record can be judged per engine version (Results "Current engine only").
# Bump it whenever pricing changes. 2026-10-07.3: market-only NFL game lines
# with key-number spreads, measured correlations, zero-catch and zero-rush
# games. Rows from before versioning have NULL ("pre-versioning").
ENGINE_VERSION = "2026-10-07.3"

N_SIMS = 20_000
PROJECTION_ERROR = 0.30      # sd of the true mean around the projection, as a share of it
# Per-market overrides, fitted by scripts/backtest_projections.py (see
# PROJECTION_ERROR_BY_MARKET / DUD_PROB below the outcome-spread constants).
MODEL_WEIGHT = 0.30          # weight on the projection model vs the de-vigged market
KELLY_FRACTION = 0.25
MIN_EV = 0.03                # 3% expected return per dollar staked
MAX_UNITS = 3.0
UNIT_STEP = 0.5
# The weekly card always shows at least MIN_CARD_PICKS picks (the founder's
# call: people bet every week). When fewer bets clear MIN_EV, the best
# remaining lines fill the card at a flat FILL_UNITS, labeled "Best
# available" (confidence "fill") and tracked as their own tier in Results so
# they can be judged separately from real bets.
MIN_CARD_PICKS = 3
FILL_UNITS = 0.5
# "Most likely to win": PrizePicks picks whose calibrated win chance is at
# least MOST_LIKELY_MIN. That clears the per-pick break-even of a 2-pick
# Power at 3x (57.7%) and with one goblin at 2.6x (62%). Standard sportsbook
# lines at ~-110 can't get there; goblins (lowered lines) can. The 2025
# backtest showed these high-probability estimates are well calibrated
# (P(at least half the projection): model vs real 69.2/67.8% rec yds,
# 74.9/76.3% rush, 90.7/92.1% pass). Tracked (kind "pp_leg") and checked
# predicted vs actual in Results.
MOST_LIKELY_MIN = 0.70
MOST_LIKELY_COUNT = 5
# Anytime TD is quoted "Yes" only, so it can't be de-vigged pairwise. Summed
# over a full game, the books' Yes prices imply ~5.5-7.5 rushing/receiving
# TDs where ~4-5 actually happen: the hold is ~30-40%, not a few percent,
# and assuming a small one turned every longshot into fake value. Instead
# each game's implied scoring rates are scaled so they sum to the TDs its
# Vegas total implies (TD_PER_POINT: rushing + receiving TDs per point
# scored, ~2.3 per ~22-point team game; LISTED_TD_SHARE: the share scored
# by players with a listed prop). Games with a partial prop list use the
# slate's median scale; with nothing to go on, ONE_SIDED_HOLD.
TD_PER_POINT = 0.105
LISTED_TD_SHARE = 0.95
MIN_LISTED_TD_PLAYERS = 15
ONE_SIDED_HOLD = 0.35        # fallback overround on the scoring rate

# Projection-vs-market sanity check. When the projection sits far from the
# market's line it is almost always the projection that's stale (a role
# change, injury news) rather than the market that's wrong, so the prop is
# flagged and gets no units. Yardage/receptions: relative gap to the line
# (lines below the floor use the floor, so a 3-yard vs 11.5-yard gap isn't
# read as 280%). Touchdowns: ratio of projected to market-implied TD rate.
MAX_LINE_GAP = 0.35
LINE_GAP_FLOOR = {"player_pass_yds": 100.0, "player_rush_yds": 20.0, "player_reception_yds": 20.0, "player_receptions": 2.0}
MAX_TD_RATIO = 1.6

# Outcome spread for gamma-distributed yardage, as coefficient of variation
# at a typical starter's volume (YARDS_REF_MEAN). Low-volume yardage is
# noisier (a QB projected for 12 rushing yards is a scramble or two), so CV
# scales like mean^-VOLUME_EXPONENT. Pure sum-over-attempts math says 0.5,
# but that over-skewed low-volume props: on the week-5 slate, after
# centering, receiving props with lines under 25 got P(over) ~0.39 vs ~0.52
# for 50+, while the market's line-to-projection ratio was flat across
# volume. 0.25 flattens it while keeping low volume noisier. Capped at
# MAX_YARDS_CV.
YARDS_CV = {
    "player_pass_yds": 0.28,
    "player_rush_yds": 0.55,
    "player_reception_yds": 0.65,
}
YARDS_REF_MEAN = {
    "player_pass_yds": 240.0,
    "player_rush_yds": 60.0,
    "player_reception_yds": 60.0,
}
VOLUME_EXPONENT = 0.25
MAX_YARDS_CV = 1.5

# Projection error per market (falls back to PROJECTION_ERROR). Both this and
# DUD_PROB are left empty on purpose: scripts/backtest_projections.py fitted
# them on the 2025 season (4,755 player-weeks) and found no out-of-sample gain
# over the current settings (validation pinball within +/-0.8%, mixed sign),
# and duds made the goblin-relevant tail worse. Rerun it each season.
PROJECTION_ERROR_BY_MARKET: Dict[str, float] = {}

# "Dud" games for yardage: an early exit, a benching or a blowout script
# leaves a player far below any normal-game spread. With probability
# DUD_PROB[market] the outcome is a small fraction (0-DUD_FRACTION) of the
# true mean; other outcomes are scaled up so the mean is unchanged.
DUD_PROB: Dict[str, float] = {}
DUD_FRACTION = 0.25


def projection_error(market: str) -> float:
    return PROJECTION_ERROR_BY_MARKET.get(market, PROJECTION_ERROR)


def apply_duds(outcomes: np.ndarray, true_mean: np.ndarray, p: float, rng: np.random.Generator) -> np.ndarray:
    """Replace a share p of outcomes with dud games, keeping the mean."""
    if p <= 0:
        return outcomes
    dud = rng.random(outcomes.shape) < p
    scaled = outcomes * (1 - p * DUD_FRACTION / 2) / (1 - p)
    return np.where(dud, true_mean * rng.uniform(0, DUD_FRACTION, outcomes.shape), scaled)
SPREAD_SD = 13.26   # NFL closing-spread error, 2015-2024 (was 13.5; the close has sharpened)
TOTAL_SD = 13.0     # measured 13.2-13.3; unchanged

# NFL margins pile up on key numbers: a favorite wins by exactly 3 about 9.7%
# of the time at spreads of 2.5-3.5, where a rounded normal says 3.0%, and a
# closing spread of exactly 3 pushes 11%. Log-weights on each exact favorite
# margin |k| = 0..25 multiply a binned normal (scripts/experiments/
# exp1c_export.py, fitted on 2015-2024; out-of-sample on 2025-26 the exact-
# margin log-loss improved by 0.137 [0.080, 0.193]). Ties (k = 0) are rare.
KEY_MARGIN_LOG_WEIGHTS = (
    -1.853, -0.1327, -0.1017, 1.0847, -0.0993, -0.055, 0.44, 0.6435, -0.0008, -0.8608,
    0.1888, -0.5733, -0.664, -0.5903, 0.4809, -0.5862, -0.1514, 0.2015, -0.0468, -0.6384,
    0.0233, 0.179, -0.6442, -0.0829, 0.2228, -0.0669,
)
_MARGINS = np.arange(-70, 71)
_MARGIN_WEIGHTS = np.exp(np.array([KEY_MARGIN_LOG_WEIGHTS[abs(k)] if abs(k) < len(KEY_MARGIN_LOG_WEIGHTS) else 0.0
                                   for k in _MARGINS]))


# ---------------------------------------------------------------------------
# Odds conversion
# ---------------------------------------------------------------------------

def american_to_decimal(price: float) -> float:
    return 1 + (price / 100 if price > 0 else 100 / -price)


def implied_prob(price: float) -> float:
    return 1 / american_to_decimal(price)


def devig_pair(over_price: float, under_price: float) -> Tuple[float, float]:
    """Two-way prices -> fair probabilities summing to 1 (multiplicative)."""
    a, b = implied_prob(over_price), implied_prob(under_price)
    return a / (a + b), b / (a + b)


def ev(p_win: float, price: float, p_push: float = 0.0) -> float:
    """Expected profit per 1 unit staked at American `price`."""
    p_loss = max(0.0, 1 - p_win - p_push)
    return p_win * (american_to_decimal(price) - 1) - p_loss


def kelly_units(p_win: float, price: float, p_push: float = 0.0) -> float:
    """Quarter-Kelly stake in units (1u = 1% of bankroll), rounded down to
    UNIT_STEP and capped at MAX_UNITS. 0 when there's no edge."""
    b = american_to_decimal(price) - 1
    p_loss = max(0.0, 1 - p_win - p_push)
    if b <= 0:
        return 0.0
    f = (b * p_win - p_loss) / b
    if f <= 0:
        return 0.0
    units = f * KELLY_FRACTION * 100
    return float(min(MAX_UNITS, np.floor(units / UNIT_STEP) * UNIT_STEP))


def confidence_label(units: float) -> str:
    if units >= 2.5:
        return "high"
    if units >= 1.5:
        return "strong"
    if units >= 0.5:
        return "lean"
    return "none"


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def _rng(seed_text: str) -> np.random.Generator:
    # Stable per-prop seed (crc32, not hash(): str hashing is randomized per
    # process) so the board doesn't reshuffle on every refresh.
    return np.random.default_rng(zlib.crc32(seed_text.encode()))


def _zero_inflation(true_mean: np.ndarray, p_zero: float) -> float:
    """Extra zero mass pi for a Poisson count with the mean preserved
    (rate true_mean / (1 - pi)) so that P(0) is about p_zero, counting the
    zeros the projection uncertainty in true_mean already makes; 0 if a
    plain Poisson already has that many zeros."""
    pi = 0.0
    for _ in range(8):
        base = float(np.mean(np.exp(-true_mean / (1 - pi))))
        pi = max(0.0, min(0.9, (p_zero - base) / (1 - base)))
    return pi


def simulate_stat(market: str, mean: float, seed_text: str, n: int = N_SIMS,
                  p_zero: Optional[float] = None) -> np.ndarray:
    """Simulated outcomes for one player stat whose projected mean is
    `mean`, including uncertainty in the projection itself. p_zero
    (receivers): the chance of a zero-catch game (zero_catch_prob) --
    receiving yards are 0 that often and receptions get the same zero mass,
    with the other outcomes scaled so the mean is unchanged."""
    rng = _rng(seed_text)
    true_mean = np.clip(rng.normal(mean, projection_error(market) * mean, n), 0.01, None)
    if p_zero and market in ZERO_MASS_MARKETS:
        if market == "player_receptions":
            pi = _zero_inflation(true_mean, p_zero)
            counts = rng.poisson(true_mean / (1 - pi)).astype(float)
            return np.where(rng.random(n) < pi, 0.0, counts)
        # Given at least one catch the mean is higher, so (volume rule) the spread is tighter.
        shape = 1 / yards_cv(market, mean / (1 - p_zero)) ** 2
        yards = rng.gamma(shape, true_mean / (1 - p_zero) / shape)
        return np.where(rng.random(n) < p_zero, 0.0, yards)
    if market in YARDS_CV:
        shape = 1 / yards_cv(market, mean) ** 2
        return apply_duds(rng.gamma(shape, true_mean / shape), true_mean, DUD_PROB.get(market, 0.0), rng)
    return rng.poisson(true_mean).astype(float)


# Zero-catch games: receivers are shut out far more often than a Poisson
# count says (26% real for 1.5-2.5 projected catches in 2025), and the gamma
# yardage model had no zero mass, so low receiving-yard lines (goblins) were
# overconfident for low-volume receivers (84% modeled vs 66% real at 20% of
# the projection, 1-2 catches). P(0 catches) = logistic(a + b ln(projected
# receptions)), fitted on 2025 wk 4-10 (scripts/experiments/zero_catch.py).
ZERO_CATCH_MARKETS = frozenset({"player_reception_yds", "player_receptions"})
# Markets simulate_stat can give a zero-game mass (p_zero): the receiver
# markets above, and rushing yards (zero_rush_prob).
ZERO_MASS_MARKETS = ZERO_CATCH_MARKETS | {"player_rush_yds"}

# Zero-rushing games: QBs finish a start at zero or negative rushing yards
# ~19% of the time (kneel-downs, no scrambles) and backups/receivers often
# get no carries; the gamma model had no such mass, so low rushing lines were
# overconfident (QBs projected 5-10 yds cleared Over 0.5 61% of the time vs
# 94% modeled -- a fake 3u "bet" on Goff Over 0.5). P(rushing yds <= 0) =
# logistic(a + b ln(projected rushing yds)), one pooled fit for all
# positions on 2025 wk 4-10 (scripts/experiments/zero_rush.py; QB and RB/WR
# fits were nearly identical). Out of sample, rushing-yards Brier improved
# on all six position x season sets (five with CIs excluding 0); low lines
# moved from 70-86% modeled to within a few points of real.
ZERO_RUSH_COEF = (2.5899, -1.4836)  # (a, b)


def zero_rush_prob(projected_rush_yds: Optional[float]) -> Optional[float]:
    """P(a game with zero or negative rushing yards) for this projection."""
    a, b = ZERO_RUSH_COEF
    if a is None or not projected_rush_yds or projected_rush_yds <= 0:
        return None
    return float(1 / (1 + np.exp(-(a + b * np.log(projected_rush_yds)))))
# Out of sample (2025 wk 11-17, 2026 wk 1-4, 2024 wk 4-17) the fitted zero
# rate matched reality (e.g. 36.6% vs 37.5% for 0.5-2 projected catches),
# receivers under 3 projected catches scored better on every held-out set
# (receiving-yards Brier -0.006 / -0.008 / -0.009, CIs excluding 0), lines at
# 20-40% of the projection went from 75% modeled to 59-61% (real 61%), and
# receivers at 3+ catches were unchanged.
ZERO_CATCH_COEF = (-0.393, -1.8579)  # (a, b)


def zero_catch_prob(projected_receptions: Optional[float]) -> Optional[float]:
    """P(a zero-catch game) for a receiver projected for this many catches."""
    a, b = ZERO_CATCH_COEF
    if a is None or not projected_receptions or projected_receptions <= 0:
        return None
    return float(1 / (1 + np.exp(-(a + b * np.log(projected_receptions)))))


def yards_cv(market: str, mean: float) -> float:
    """Volume-scaled coefficient of variation (see YARDS_CV)."""
    cv = YARDS_CV[market] * (YARDS_REF_MEAN[market] / max(mean, 1.0)) ** VOLUME_EXPONENT
    return float(min(MAX_YARDS_CV, max(YARDS_CV[market] * 0.8, cv)))


def prob_over(samples: np.ndarray, line: float) -> Tuple[float, float]:
    """(P(over), P(push)) for a line; pushes only possible on whole lines."""
    over = float(np.mean(samples > line))
    push = float(np.mean(samples == line)) if float(line).is_integer() else 0.0
    return over, push


def margin_pmf(location: float, sd: float = SPREAD_SD) -> np.ndarray:
    """P(home margin = k) for k in _MARGINS: a binned normal at `location`
    reweighted by the key-number weights."""
    from scipy.special import ndtr  # light; not scipy.stats (Render memory)
    p = ndtr((_MARGINS + 0.5 - location) / sd) - ndtr((_MARGINS - 0.5 - location) / sd)
    p = p * _MARGIN_WEIGHTS
    return p / p.sum()


def market_margin_pmf(home_spread: float, sd: float = SPREAD_SD) -> np.ndarray:
    """Key-number margin distribution centered on the market: the location
    at which the home side's no-push cover chance at the consensus spread
    is 50% (the reweighting moves the mean, so it's solved, not assumed)."""
    lo, hi = -home_spread - 8, -home_spread + 8
    for _ in range(30):
        mid = (lo + hi) / 2
        p = margin_pmf(mid, sd)
        win, loss = p[_MARGINS + home_spread > 0].sum(), p[_MARGINS + home_spread < 0].sum()
        lo, hi = (mid, hi) if win < loss else (lo, mid)
    return margin_pmf((lo + hi) / 2, sd)


def _margins_from_uniform(pmf: np.ndarray, u: np.ndarray) -> np.ndarray:
    return _MARGINS[np.minimum(np.searchsorted(np.cumsum(pmf), u), len(_MARGINS) - 1)].astype(float)


def simulate_game(consensus_home_spread: float, consensus_total: float, seed_text: str, n: int = N_SIMS,
                  margin_sd: float = SPREAD_SD, total_sd: float = TOTAL_SD, key_numbers: bool = False):
    """(home margin, total points) draws centered on the consensus lines.
    Rounded to whole points so key-number pushes (3, 7, 47...) occur.
    key_numbers (NFL): margins follow the key-number distribution centered
    on the market (market_margin_pmf)."""
    rng = _rng(seed_text)
    if key_numbers:
        margin = _margins_from_uniform(market_margin_pmf(consensus_home_spread, margin_sd), rng.random(n))
    else:
        margin = np.round(rng.normal(-consensus_home_spread, margin_sd, n))
    total = np.round(rng.normal(consensus_total, total_sd, n))
    return margin, total


def td_rate(p: float) -> float:
    """Poisson scoring rate implied by P(at least one TD)."""
    return float(-np.log(1 - min(max(p, 0.0), 0.99)))


def td_rate_scale(implied_probs: List[float], game_total: Optional[float]) -> Optional[float]:
    """Factor that brings a game's implied TD scoring rates down to what its
    Vegas total supports. None without a total or a full prop list."""
    if not game_total or len(implied_probs) < MIN_LISTED_TD_PLAYERS:
        return None
    implied = sum(td_rate(p) for p in implied_probs)
    return float(min(1.0, TD_PER_POINT * game_total * LISTED_TD_SHARE / implied)) if implied > 0 else None


def td_fair_prob(implied_p: float, rate_scale: Optional[float]) -> float:
    """Fair P(score) from the books' Yes price (implied probability)."""
    scale = rate_scale if rate_scale is not None else 1 / (1 + ONE_SIDED_HOLD)
    return float(1 - np.exp(-td_rate(implied_p) * scale))


# PrizePicks multi-pick entries. Payouts are PrizePicks' standard published
# multipliers for all-standard lineups; they vary by state and change over
# time, so the page lets the user override them. Flex maps hits -> payout.
POWER_PAYOUTS = {2: 3.0, 3: 6.0, 4: 10.0, 5: 20.0, 6: 37.5}  # 2-pick 3x confirmed (Florida)
FLEX_PAYOUTS = {
    2: {2: 2.0, 1: 0.5},   # confirmed in the founder's Florida app, 2026-10-07
    3: {3: 3.0, 2: 1.0},
    4: {4: 6.0, 3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}
ENTRY_SIMS = 20_000


def hit_count_distribution(probs: List[float], corr: Optional[np.ndarray] = None, seed_text: str = "entry") -> np.ndarray:
    """P(exactly k legs hit), k = 0..n. Exact (Poisson-binomial) for
    unrelated legs; a Gaussian-copula simulation when `corr` has same-game
    correlations."""
    n = len(probs)
    if corr is None or not np.any(corr[~np.eye(n, dtype=bool)]):
        dist = np.zeros(n + 1)
        dist[0] = 1.0
        for p in probs:
            dist[1:] = dist[1:] * (1 - p) + dist[:-1] * p
            dist[0] *= 1 - p
        return dist
    from statistics import NormalDist
    try:
        chol = np.linalg.cholesky(corr)
    except np.linalg.LinAlgError:
        return hit_count_distribution(probs, None)
    z = _rng(seed_text).standard_normal((ENTRY_SIMS, n)) @ chol.T
    thresholds = np.array([NormalDist().inv_cdf(min(max(p, 1e-6), 1 - 1e-6)) for p in probs])
    hits = (z < thresholds).sum(axis=1)
    return np.bincount(hits, minlength=n + 1) / ENTRY_SIMS


def entry_ev(dist: np.ndarray, payouts: Dict[int, float]) -> float:
    """Expected profit per $1 for an entry paying payouts[hits]."""
    return float(sum(dist[k] * m for k, m in payouts.items() if k < len(dist)) - 1)


# ---------------------------------------------------------------------------
# Slate centering
# ---------------------------------------------------------------------------
# Sleeper's projections sit systematically off the market by stat type
# (week 5: receiving yards ~14% above the books' lines, passing yards ~1%
# below). Uncorrected, that bias becomes a fake edge on one side of nearly
# every prop -- the model picked the Under on 56 of 73 PrizePicks legs while
# projecting 62 of 87 players above their line. Shrinking the outcome spread
# can't fix it (it would take receiving-yard CVs of ~0.33, far tighter than
# real weekly results, and passing yards can't be matched at any CV), so
# instead each market's projections are scaled per slate so that, on the
# median prop, the model agrees with the market. What's left is relative:
# a player projected unusually far from his line compared with the rest.
CENTERING_MIN_PROPS = 8           # fewer props than this: no centering (scale 1)
PROJECTION_SCALE_BOUNDS = (0.6, 1.6)
CENTERING_SIMS = 4000


def fit_projection_scale(market: str, pairs: List[Tuple]) -> float:
    """Multiplier for this slate's projections in `market`. `pairs` are
    (projection, market center[, p_zero]): the market's 50% line for yards
    and receptions, the fair P(score) for anytime TD; p_zero is a receiver's
    zero-catch chance, so centering simulates exactly what pricing does."""
    lo, hi = PROJECTION_SCALE_BOUNDS
    pairs = [(t[0], t[1], t[2] if len(t) > 2 else None) for t in pairs if t[0] > 0]
    if len(pairs) < CENTERING_MIN_PROPS:
        return 1.0
    if market == "player_anytime_td":
        ratios = [-np.log(1 - p) / proj for proj, p, _ in pairs if 0 < p < 1]
        return round(float(np.clip(np.median(ratios), lo, hi)), 3) if ratios else 1.0

    def median_p_over(k: float) -> float:
        return float(np.median([
            prob_over(simulate_stat(market, proj * k, f"center|{market}|{i}", n=CENTERING_SIMS, p_zero=pz), line)[0]
            for i, (proj, line, pz) in enumerate(pairs)
        ]))

    for _ in range(14):  # bisection: P(over) rises with the scale
        mid = (lo + hi) / 2
        if median_p_over(mid) < 0.5:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


# ---------------------------------------------------------------------------
# Game model (spreads, totals, cover + total combos)
# ---------------------------------------------------------------------------
# Independent views of each game, blended with the consensus like props:
# - margin: projected team points from Sleeper's player projections
#   (6 x rushing/receiving TDs + kicker points), cross-checked by ESPN's
#   matchup predictor (its win probability converted to a margin);
# - total: the same Sleeper team points, cross-checked by ESPN's player
#   projections. On the week-5 slate Sleeper's totals tracked the market at
#   0.93 correlation (margins 0.97) yet differed by up to 4 points.
# The favorite's margin and the total are drawn with correlation
# COVER_TOTAL_RHO for combos. Measured on 2015-2025 closing lines (3,024
# games): margin error vs total error +0.030 [-0.006, +0.065]; "favorite
# covers" vs "over" -0.009 (scripts/experiments/corr_cover_total.py). The
# old 0.15 priced favorite-cover + Over ~2 points too likely.
COVER_TOTAL_RHO = 0.03
# The Sleeper game model's weight vs the market for NFL spreads and totals.
# On real closing lines (2025 + 2026 wk 1-4, 116 bets at 53-62-1) it carried
# no information: recalibration slope 0.11 (spreads) / -0.05 (totals), and
# any weight above 0 scored worse than the line alone out of sample
# (scripts/backtest_game_lines.py, scripts/experiments/exp3_weight_recal.py).
# At 0 a game-line bet comes only from a book off the market (line shopping).
GAME_MODEL_WEIGHT = 0.0


# College games are less predictable than the NFL: wider margin and total
# errors (standard published magnitudes, not fitted).
CFB_SPREAD_SD = 15.5
CFB_TOTAL_SD = 15.0
# College spreads rest on one unvalidated source (ESPN's predictor, which
# disagreed with the market by 5+ points on many week-6 games and produced
# 15 "bets" at the NFL settings), so it gets half the weight and a 1u cap
# until graded results earn more.
CFB_MODEL_WEIGHT = 0.15
CFB_MAX_UNITS = 1.0


def margin_from_win_prob(p_home: float, sd: float = SPREAD_SD) -> float:
    """Expected home margin implied by a win probability (normal margin)."""
    from statistics import NormalDist
    return float(NormalDist().inv_cdf(min(max(p_home, 0.01), 0.99)) * sd)


def simulate_game_joint(home_margin: float, total: float, rho: float, seed_text: str, n: int = N_SIMS,
                        margin_sd: float = SPREAD_SD, total_sd: float = TOTAL_SD, key_numbers: bool = False):
    """(home margin, total) draws with correlation rho, rounded to whole
    points (key-number pushes). key_numbers: the margin follows the
    key-number distribution centered on home_margin's spread (Gaussian
    copula, so rho still applies)."""
    from scipy.special import ndtr  # light; not scipy.stats (Render memory)
    rng = _rng(seed_text)
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(1 - rho * rho) * rng.standard_normal(n)
    if key_numbers:
        margin = _margins_from_uniform(market_margin_pmf(-home_margin, margin_sd), ndtr(z1))
    else:
        margin = np.round(home_margin + margin_sd * z1)
    return margin, np.round(total + total_sd * z2)


def fair_american(p: float) -> Optional[int]:
    """American odds with no vig for probability p."""
    if not 0 < p < 1:
        return None
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


# ---------------------------------------------------------------------------
# Pricing an offer
# ---------------------------------------------------------------------------

def blend(p_model: Optional[float], p_market: float, weight: float = MODEL_WEIGHT) -> float:
    if p_model is None:
        return p_market
    return weight * p_model + (1 - weight) * p_market


def worst_price(p_win: float, p_push: float = 0.0, min_ev: float = MIN_EV) -> Optional[int]:
    """The longest-odds price (American) at which a side still clears
    min_ev -- what a bettor can accept if the line moves. None if no price
    would (p_win too low)."""
    if p_win <= 0:
        return None
    decimal = 1 + (min_ev + max(0.0, 1 - p_win - p_push)) / p_win
    if decimal <= 1.0001:
        return None
    american = (decimal - 1) * 100 if decimal >= 2 else -100 / (decimal - 1)
    # Round toward the safe side (a slightly better price than the exact cutoff).
    return int(np.ceil(american)) if american > 0 else int(np.ceil(american))


def price_offer(p_win: float, price: float, p_push: float = 0.0) -> Dict[str, float]:
    e = ev(p_win, price, p_push)
    units = kelly_units(p_win, price, p_push) if e >= MIN_EV else 0.0
    return {
        # For a bet: still worth it down to this price if the line moves.
        "min_price": worst_price(p_win, p_push) if units > 0 else None,
        "p_win": round(p_win, 4),
        "p_push": round(p_push, 4),
        "ev": round(e, 4),
        "units": units,
        "confidence": confidence_label(units),
    }


def projection_outlier(market: str, projection: float, market_line: Optional[float] = None,
                       market_td_prob: Optional[float] = None) -> bool:
    """True when the projection disagrees with the market by more than
    the sanity bounds above (see MAX_LINE_GAP / MAX_TD_RATIO)."""
    if market == "player_anytime_td":
        if not market_td_prob or market_td_prob >= 1:
            return True
        market_rate = -np.log(1 - market_td_prob)  # Poisson rate implied by P(>=1 TD)
        ratio = projection / market_rate if market_rate > 0 else float("inf")
        return bool(ratio > MAX_TD_RATIO or ratio < 1 / MAX_TD_RATIO)  # plain bool: JSON-serializable
    if market_line is None:
        return True
    scale = max(market_line, LINE_GAP_FLOOR.get(market, 1.0))
    return bool(abs(projection - market_line) / scale > MAX_LINE_GAP)


def median(values: Iterable[float]) -> Optional[float]:
    vals: List[float] = [float(v) for v in values]
    return float(np.median(vals)) if vals else None


# ---------------------------------------------------------------------------
# PrizePicks pick'em (2-pick Power Play)
# ---------------------------------------------------------------------------
# A 2-pick Power Play pays 3x and needs both legs to hit. Priced as a
# +200 bet on the joint probability, so the same EV / Kelly / unit rules
# apply. With independent legs each one needs sqrt(1/3) = 57.7% to break
# even; PrizePicks' standard line is not a priced market, so the edge comes
# from the books' fair probability at PrizePicks' number, not from the line.
POWER_PLAY_2_PRICE = 200
POWER_PLAY_2_BREAKEVEN = (1 / 3) ** 0.5

# Correlation of two players' stat outcomes in the same game (as latent
# Gaussian correlation, Over/Over orientation; an Under flips the sign).
# Measured on 2024-2026 Sleeper projections vs actual stats (Over/Under a
# projection-centered line; scripts/experiments/corr_props.py, game-
# clustered bootstrap CIs, n = pairs). The old guessed opponent values were
# 2-3x too high and added fake EV to same-game More/More pairs. Pairs
# measured as noise (|rho| < 0.03 with a CI spanning 0) are left at 0.
# Keys are (market a, market b, same team?); different games are 0.
_PASS, _RUSH, _REC_YDS, _RECS = "player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions"
LEG_CORRELATION = {
    # Teammates: a QB's yards are his receivers' yards.
    (_PASS, _REC_YDS, True): 0.38,   # [0.34, 0.42], n=4,508 (WR/TE; RB receivers 0.32)
    (_PASS, _RECS, True): 0.32,      # [0.27, 0.36], n=4,126
    (_PASS, _RUSH, True): -0.08,     # [-0.14, -0.01], n=1,943: run-heavy script = fewer dropbacks
    (_RUSH, _REC_YDS, True): -0.04,  # [-0.07, -0.01], n=7,301
    # Opponents: shootouts lift both passing games a little; the team that's
    # ahead runs while the other throws, so opposing backs move apart.
    (_PASS, _PASS, False): 0.08,     # [-0.05, 0.20], n=601 (normal-score 0.12 [0.04, 0.19])
    (_PASS, _REC_YDS, False): 0.06,  # [0.01, 0.11], n=4,504
    (_PASS, _RECS, False): 0.05,     # [0.00, 0.11], n=4,121
    (_REC_YDS, _REC_YDS, False): 0.04,  # [0.00, 0.07], n=8,469
    (_RUSH, _RUSH, False): -0.19,    # [-0.26, -0.12], n=1,579
}


def leg_correlation(market_a: str, market_b: str, same_game: bool, same_team: bool) -> float:
    """Latent correlation between two Over legs (see LEG_CORRELATION)."""
    if not same_game:
        return 0.0
    return LEG_CORRELATION.get((market_a, market_b, same_team),
                               LEG_CORRELATION.get((market_b, market_a, same_team), 0.0))


def joint_prob(p_a: float, p_b: float, rho: float) -> float:
    """P(both legs hit) under a Gaussian copula with latent correlation rho;
    p_a * p_b when rho is 0. Deterministic quadrature (no sampling noise)."""
    from statistics import NormalDist
    if rho == 0.0:
        return p_a * p_b
    nd = NormalDist()
    a = nd.inv_cdf(min(max(p_a, 1e-6), 1 - 1e-6))
    b = nd.inv_cdf(min(max(p_b, 1e-6), 1 - 1e-6))
    # P(Z1 < a, Z2 < b) = integral over z < a of phi(z) * Phi((b - rho z) / sqrt(1 - rho^2))
    z = np.linspace(-8.0, a, 1201)
    s = np.sqrt(1 - rho * rho)
    inner = np.array([nd.cdf(v) for v in (b - rho * z) / s])
    phi = np.exp(-z * z / 2) / np.sqrt(2 * np.pi)
    return float(np.trapezoid(phi * inner, z))
