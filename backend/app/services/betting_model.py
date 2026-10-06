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
ONE_SIDED_HOLD = 0.07        # assumed overround on "Yes"-only markets (anytime TD)

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
# at a typical starter's volume (YARDS_REF_MEAN). Yardage is a sum over
# attempts, so its CV scales like 1/sqrt(mean): a QB projected for 12
# rushing yards (a scramble or two, maybe a kneel) is far noisier than a
# lead back projected for 70. Capped at MAX_YARDS_CV.
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
    cv = YARDS_CV[market] * np.sqrt(YARDS_REF_MEAN[market] / max(mean, 1.0))
    return float(min(MAX_YARDS_CV, max(YARDS_CV[market] * 0.8, cv)))


def prob_over(samples: np.ndarray, line: float) -> Tuple[float, float]:
    """(P(over), P(push)) for a line; pushes only possible on whole lines."""
    over = float(np.mean(samples > line))
    push = float(np.mean(samples == line)) if float(line).is_integer() else 0.0
    return over, push


def simulate_game(consensus_home_spread: float, consensus_total: float, seed_text: str, n: int = N_SIMS):
    """(home margin, total points) draws centered on the consensus lines.
    Rounded to whole points so key-number pushes (3, 7, 47...) occur."""
    rng = _rng(seed_text)
    margin = np.round(rng.normal(-consensus_home_spread, SPREAD_SD, n))
    total = np.round(rng.normal(consensus_total, TOTAL_SD, n))
    return margin, total


# ---------------------------------------------------------------------------
# Pricing an offer
# ---------------------------------------------------------------------------

def blend(p_model: Optional[float], p_market: float) -> float:
    if p_model is None:
        return p_market
    return MODEL_WEIGHT * p_model + (1 - MODEL_WEIGHT) * p_market


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
