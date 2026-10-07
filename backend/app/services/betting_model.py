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

Game props (spreads, totals) are simulated as margin ~ N(consensus spread,
13.5) and total ~ N(consensus total, 13.0) -- the long-run NFL spread and
total error. Centered on consensus, they find edges only where one book's
line or price is off the market (line shopping), never by out-predicting it.

Calibration constants are standard published magnitudes, not fitted to
this app's results yet; they should be tuned once graded results exist.
"""
import zlib
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

N_SIMS = 20_000
PROJECTION_ERROR = 0.30      # sd of the true mean around the projection, as a share of it
MODEL_WEIGHT = 0.30          # weight on the projection model vs the de-vigged market
KELLY_FRACTION = 0.25
MIN_EV = 0.03                # 3% expected return per dollar staked
MAX_UNITS = 3.0
UNIT_STEP = 0.5
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
SPREAD_SD = 13.5
TOTAL_SD = 13.0


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


def simulate_stat(market: str, mean: float, seed_text: str, n: int = N_SIMS) -> np.ndarray:
    """Simulated outcomes for one player stat whose projected mean is
    `mean`, including uncertainty in the projection itself."""
    rng = _rng(seed_text)
    true_mean = np.clip(rng.normal(mean, PROJECTION_ERROR * mean, n), 0.01, None)
    if market in YARDS_CV:
        shape = 1 / yards_cv(market, mean) ** 2
        return rng.gamma(shape, true_mean / shape)
    return rng.poisson(true_mean).astype(float)


def yards_cv(market: str, mean: float) -> float:
    """Volume-scaled coefficient of variation (see YARDS_CV)."""
    cv = YARDS_CV[market] * (YARDS_REF_MEAN[market] / max(mean, 1.0)) ** VOLUME_EXPONENT
    return float(min(MAX_YARDS_CV, max(YARDS_CV[market] * 0.8, cv)))


def prob_over(samples: np.ndarray, line: float) -> Tuple[float, float]:
    """(P(over), P(push)) for a line; pushes only possible on whole lines."""
    over = float(np.mean(samples > line))
    push = float(np.mean(samples == line)) if float(line).is_integer() else 0.0
    return over, push


def simulate_game(consensus_home_spread: float, consensus_total: float, seed_text: str, n: int = N_SIMS,
                  margin_sd: float = SPREAD_SD, total_sd: float = TOTAL_SD):
    """(home margin, total points) draws centered on the consensus lines.
    Rounded to whole points so key-number pushes (3, 7, 47...) occur."""
    rng = _rng(seed_text)
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


def fit_projection_scale(market: str, pairs: List[Tuple[float, float]]) -> float:
    """Multiplier for this slate's projections in `market`. `pairs` are
    (projection, market center): the market's 50% line for yards and
    receptions, the fair P(score) for anytime TD."""
    lo, hi = PROJECTION_SCALE_BOUNDS
    pairs = [(proj, c) for proj, c in pairs if proj > 0]
    if len(pairs) < CENTERING_MIN_PROPS:
        return 1.0
    if market == "player_anytime_td":
        ratios = [-np.log(1 - p) / proj for proj, p in pairs if 0 < p < 1]
        return round(float(np.clip(np.median(ratios), lo, hi)), 3) if ratios else 1.0

    def median_p_over(k: float) -> float:
        return float(np.median([
            prob_over(simulate_stat(market, proj * k, f"center|{market}|{i}", n=CENTERING_SIMS), line)[0]
            for i, (proj, line) in enumerate(pairs)
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
# A favorite that covers usually means more points, so the favorite's margin
# and the total are drawn with correlation COVER_TOTAL_RHO for combos.
COVER_TOTAL_RHO = 0.15


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
                        margin_sd: float = SPREAD_SD, total_sd: float = TOTAL_SD):
    """(home margin, total) draws with correlation rho, rounded to whole
    points (key-number pushes)."""
    rng = _rng(seed_text)
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + np.sqrt(1 - rho * rho) * rng.standard_normal(n)
    return np.round(home_margin + margin_sd * z1), np.round(total + total_sd * z2)


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


def price_offer(p_win: float, price: float, p_push: float = 0.0) -> Dict[str, float]:
    e = ev(p_win, price, p_push)
    units = kelly_units(p_win, price, p_push) if e >= MIN_EV else 0.0
    return {
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
# Standard same-game-parlay magnitudes, not fitted yet -- calibrate from
# results. Keys are (market a, market b, same team?); different games are 0.
_PASS, _RUSH, _REC_YDS, _RECS = "player_pass_yds", "player_rush_yds", "player_reception_yds", "player_receptions"
LEG_CORRELATION = {
    # Teammates: a QB's yards are his receivers' yards.
    (_PASS, _REC_YDS, True): 0.45,
    (_PASS, _RECS, True): 0.35,
    (_PASS, _RUSH, True): -0.10,     # run-heavy script = fewer dropbacks
    (_RUSH, _RUSH, True): -0.20,     # backs split the carries
    (_REC_YDS, _REC_YDS, True): 0.05,
    # Opponents: shootouts lift both passing games; a team running out the
    # clock is usually ahead of an opponent forced to throw.
    (_PASS, _PASS, False): 0.25,
    (_PASS, _REC_YDS, False): 0.15,
    (_PASS, _RECS, False): 0.10,
    (_REC_YDS, _REC_YDS, False): 0.10,
    (_PASS, _RUSH, False): 0.10,
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
