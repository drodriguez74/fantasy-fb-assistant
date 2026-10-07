"""Experiment 2: an independent ratings model (margin Elo with a QB-change
adjustment; offense/defense points ratings for totals) and a situational
regression (rest, bye, travel, divisional, neutral, QB change; wind, cold,
dome, early season for totals). Does any of it beat or add to the closing
line out-of-sample?

    python scripts/experiments/exp2_ratings.py

Protocol: ratings run online from 1999 (each game predicted only from
earlier games). Their 4-5 hyperparameters are grid-tuned on 2015-2024
margin/total MSE; the stacking regressions (residual vs the close) are
fitted on 2015-2024. Everything is scored on 2025 REG + 2026 wk1-4, and
-- because 336 games can't resolve a 2-3% edge -- the raw ratings are
also scored on 2006-2014 (odds available, never used for tuning).
Bets use the live rule: blend MODEL_WEIGHT*model + (1-w)*market (market =
rounded N(close, 13.5/13.0)), bet a side if EV >= 3% at its closing price
and the model favors it. Weather is the recorded game-time value (a
slightly optimistic stand-in for the pregame forecast).
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.dirname(__file__))
from gl_common import bet_report, boot_ci, ev, load  # noqa: E402

FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
TZ = {**{t: 0 for t in "ATL BAL BUF CAR CIN CLE DET IND JAX MIA NE NYG NYJ PHI PIT TB WAS".split()},
      **{t: -1 for t in "CHI DAL GB HOU KC MIN NO TEN".split()}, "DEN": -2, "ARI": -2.5,
      **{t: -3 for t in "LA LAC LV SEA SF".split()}}
SD_M, SD_T = 13.5, 13.0


def prep():
    d = load()
    for c in ("home_team", "away_team"):
        d[c] = d[c].replace(FRANCHISE)
    d = d.sort_values(["season", "week", "gameday", "gametime"]).reset_index(drop=True)
    # QB "backup" flag: starter isn't the team's most frequent starter over its previous 10 games.
    hist = {}
    bh, ba, ch, ca = [], [], [], []
    for r in d.itertuples():
        for team, qb, b, c in ((r.home_team, r.home_qb_id, bh, ch), (r.away_team, r.away_qb_id, ba, ca)):
            prev = hist.get(team, [])[-10:]
            if prev and isinstance(qb, str):
                main = max(set(prev), key=prev.count)
                b.append(int(qb != main and prev.count(qb) < 3))
                c.append(int(qb != prev[-1]))
            else:
                b.append(0)
                c.append(0)
            if isinstance(qb, str):
                hist.setdefault(team, []).append(qb)
    d["bk_h"], d["bk_a"], d["qbchg_h"], d["qbchg_a"] = bh, ba, ch, ca
    d["neutral"] = (d.location == "Neutral").astype(int)
    d["rest_diff"] = (d.home_rest - d.away_rest).clip(-7, 7)
    d["bye_h"], d["bye_a"] = (d.home_rest >= 12).astype(int), (d.away_rest >= 12).astype(int)
    d["short_a"] = (d.away_rest <= 5).astype(int)
    d["tz_diff"] = d.away_team.map(TZ) - d.home_team.map(TZ)   # >0: away team travelled west
    d["outdoor"] = d.roof.isin(["outdoors", "open"]).astype(int)
    d["wind15"] = ((d.wind.fillna(0) >= 15) & (d.outdoor == 1)).astype(int)
    d["wind_x"] = np.where(d.outdoor == 1, d.wind.fillna(d.wind.median()), 0)
    d["cold"] = ((d.temp.fillna(60) <= 32) & (d.outdoor == 1)).astype(int)
    d["early"] = (d.week <= 4).astype(int)
    d["late"] = (d.week >= 14).astype(int)
    return d


def margin_elo(d, k, rev, hfa, qb, clip=28):
    R, last_season, pred = {}, None, np.zeros(len(d))
    for i, r in enumerate(d.itertuples()):
        if r.season != last_season:
            R = {t: v * (1 - rev) for t, v in R.items()}
            last_season = r.season
        rh, ra = R.get(r.home_team, 0.0), R.get(r.away_team, 0.0)
        p = rh - ra + hfa * (1 - r.neutral) + qb * (r.bk_a - r.bk_h)
        pred[i] = p
        e = np.clip(r.margin, -clip, clip) - p
        R[r.home_team], R[r.away_team] = rh + k * e, ra - k * e
    return pred


def points_ratings(d, k, rev, hfa=1.5):
    O, D, last, pred = {}, {}, None, np.zeros(len(d))
    mu = 22.0
    for i, r in enumerate(d.itertuples()):
        if r.season != last:
            O = {t: v * (1 - rev) for t, v in O.items()}
            D = {t: v * (1 - rev) for t, v in D.items()}
            last = r.season
        h = mu + O.get(r.home_team, 0) - D.get(r.away_team, 0) + hfa / 2
        a = mu + O.get(r.away_team, 0) - D.get(r.home_team, 0) - hfa / 2
        pred[i] = h + a
        eh, ea = r.home_score - h, r.away_score - a
        O[r.home_team] = O.get(r.home_team, 0) + k * eh
        D[r.away_team] = D.get(r.away_team, 0) - k * eh
        O[r.away_team] = O.get(r.away_team, 0) + k * ea
        D[r.home_team] = D.get(r.home_team, 0) - k * ea
        mu += 0.005 * (eh + ea) / 2       # slow league-scoring drift
    return pred


def rn_gt(mu, c, sd):
    """P(round(N(mu, sd)) > c) and P(== c) for line c (whole or half)."""
    mu, c = np.asarray(mu, float), np.asarray(c, float)
    whole = c == np.round(c)
    gt = np.where(whole, 1 - norm.cdf((c + 0.5 - mu) / sd), 1 - norm.cdf((c - mu) / sd))
    eq = np.where(whole, norm.cdf((c + 0.5 - mu) / sd) - norm.cdf((c - 0.5 - mu) / sd), 0.0)
    return gt, eq


def live_rule_bets(df, model_mean, kind, w):
    """Bets the live rule would make at closing prices. Returns rows."""
    if kind == "spread":
        line, sd, res = df.spread_line.values, SD_M, df.margin.values      # home covers if margin > spread_line
        prices = (df.home_spread_odds.values, df.away_spread_odds.values)
    else:
        line, sd, res = df.total_line.values, SD_T, df.points.values
        prices = (df.over_odds.values, df.under_odds.values)
    mk_gt, mk_eq = rn_gt(line, line, sd)
    md_gt, md_eq = rn_gt(model_mean, line, sd)
    out = []
    for side in (0, 1):   # 0: home/over (outcome > line), 1: away/under
        p_mkt = mk_gt if side == 0 else 1 - mk_gt - mk_eq
        p_mod = md_gt if side == 0 else 1 - md_gt - md_eq
        pb = w * p_mod + (1 - w) * p_mkt
        e = ev(pb, mk_eq, prices[side])
        sel = (e >= 0.03) & (p_mod > p_mkt)
        win = (res > line) if side == 0 else (res < line)
        out.append(pd.DataFrame({"win": win[sel], "push": (res == line)[sel], "price": prices[side][sel],
                                 "side": side, "season": df.season.values[sel]}))
    return pd.concat(out)


def brier_vs_market(df, model_mean, kind):
    if kind == "spread":
        line, res, sd, mk = df.spread_line.values, df.margin.values, SD_M, df.mkt_home.values
    else:
        line, res, sd, mk = df.total_line.values, df.points.values, SD_T, df.mkt_over.values
    gt, eq = rn_gt(model_mean, line, sd)
    p = gt / (1 - eq)
    keep = res != line
    y = (res > line)[keep]
    bm, bk = (p[keep] - y) ** 2, (mk[keep] - y) ** 2
    lo, hi = boot_ci(bm - bk)
    return f"Brier model {bm.mean():.4f} vs market {bk.mean():.4f}  diff {np.mean(bm - bk):+.4f} [{lo:+.4f},{hi:+.4f}] n={keep.sum()}"


def mse_line(df, pred, kind):
    res = df.margin.values if kind == "spread" else df.points.values
    line = df.spread_line.values if kind == "spread" else df.total_line.values
    a, b = (res - pred) ** 2, (res - line) ** 2
    lo, hi = boot_ci(a - b)
    return f"RMSE model {np.sqrt(a.mean()):.2f} vs close {np.sqrt(b.mean()):.2f} (MSE diff {np.mean(a - b):+.1f} [{lo:+.1f},{hi:+.1f}])"


def ols(X, y):
    X1 = np.c_[np.ones(len(X)), X]
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    s2 = resid @ resid / (len(y) - X1.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X1.T @ X1)))
    return beta, se


def main():
    d = prep()
    fit = d.fit.values
    oos = d.oos.values
    early_test = d.season.between(2006, 2014).values

    # ---- tune margin Elo on 2015-2024 margin MSE
    best = None
    for k, rev, hfa, qb in itertools.product((0.04, 0.06, 0.08, 0.10), (0.25, 0.4, 0.55), (1.0, 1.5, 2.0), (0, 3, 5)):
        p = margin_elo(d, k, rev, hfa, qb)
        m = np.mean((d.margin.values[fit] - p[fit]) ** 2)
        if best is None or m < best[0]:
            best = (m, k, rev, hfa, qb)
    _, k, rev, hfa, qb = best
    d["elo"] = margin_elo(d, k, rev, hfa, qb)
    print(f"Margin Elo tuned on 2015-24: K={k} season-reversion={rev} HFA={hfa} backup-QB penalty={qb}")

    bestt = None
    for kk, rv in itertools.product((0.03, 0.05, 0.08, 0.12), (0.25, 0.4, 0.6)):
        p = points_ratings(d, kk, rv)
        m = np.mean((d.points.values[fit] - p[fit]) ** 2)
        if bestt is None or m < bestt[0]:
            bestt = (m, kk, rv)
    d["ptsr"] = points_ratings(d, bestt[1], bestt[2])
    print(f"Points ratings tuned on 2015-24: K={bestt[1]} reversion={bestt[2]}")

    for label, mask in (("2006-2014 (never tuned on)", early_test), ("2015-2024 (tuning period)", fit),
                        ("OOS 2025-26", oos)):
        x = d[mask]
        print(f"\n== {label}: {len(x)} games")
        print("  spread raw Elo :", mse_line(x, x.elo.values, "spread"))
        print("                  ", brier_vs_market(x, x.elo.values, "spread"))
        print("  total ratings  :", mse_line(x, x.ptsr.values, "total"))
        print("                  ", brier_vs_market(x, x.ptsr.values, "total"))
        for w in (0.15, 0.30):
            print("  " + bet_report(f"live rule w={w} spreads (Elo)", **_cols(live_rule_bets(x, x.elo.values, "spread", w))))
            print("  " + bet_report(f"live rule w={w} totals (ratings)", **_cols(live_rule_bets(x, x.ptsr.values, "total", w))))

    # ---- stacking regressions on the residual vs the close (fit 2015-2024)
    d["elo_gap"] = d.elo - d.spread_line
    d["elo_gap_early"] = d.elo_gap * d.early
    d["tot_gap"] = d.ptsr - d.total_line
    feats_s = ["elo_gap", "elo_gap_early", "rest_diff", "bye_h", "bye_a", "short_a", "div_game", "neutral", "tz_diff",
               "bk_h", "bk_a", "qbchg_h", "qbchg_a"]
    feats_t = ["tot_gap", "wind15", "wind_x", "cold", "outdoor", "div_game", "early", "late", "total_line", "bk_h", "bk_a"]
    for kind, feats, target, line in (("spread", feats_s, "margin", "spread_line"), ("total", feats_t, "points", "total_line")):
        F = d[fit]
        beta, se = ols(F[feats].values.astype(float), (F[target] - F[line]).values)
        print(f"\nStacked {kind} regression, residual (result - close) fitted 2015-24, n={len(F)}: coef (t-stat)")
        print("  " + ", ".join(f"{n} {b:+.3f} ({b / s:+.1f})" for n, b, s in zip(["const"] + feats, beta, se)))
        for label, mask in (("OOS 2025-26", oos),):
            x = d[mask]
            pred = x[line].values + np.c_[np.ones(len(x)), x[feats].values.astype(float)] @ beta
            print(f"  {label}: " + mse_line(x, pred, kind))
            print(f"  {label}: " + brier_vs_market(x, pred, kind))
            for w in (0.3, 1.0):
                print("  " + bet_report(f"{label} live rule w={w}", **_cols(live_rule_bets(x, pred, kind, w))))
        # Single-feature, larger-sample checks: fit on 2006-2014, test 2015-2026 (rest of data).
        a, b = d[early_test], d[d.season >= 2015]
        beta2, se2 = ols(a[feats].values.astype(float), (a[target] - a[line]).values)
        pred = b[line].values + np.c_[np.ones(len(b)), b[feats].values.astype(float)] @ beta2
        print(f"  fit 2006-14, test 2015-26 (n={len(b)}): " + mse_line(b, pred, kind))
        print(f"  fit 2006-14, test 2015-26: " + brier_vs_market(b, pred, kind))
        print("  " + bet_report("fit 2006-14 test 2015-26 w=1.0", **_cols(live_rule_bets(b, pred, kind, 1.0))))

    # ---- simple single-factor angles, ATS / O-U at closing prices, all seasons with odds
    print("\nSingle-factor angles (flat 1u at the closing price; 2006-2024 | OOS 2025-26)")
    angles = {
        "Under, outdoor wind >= 15": ("total", 1, d.wind15 == 1),
        "Under, outdoor wind >= 20": ("total", 1, (d.wind_x >= 20) & (d.outdoor == 1)),
        "Under, divisional": ("total", 1, d.div_game == 1),
        "Under, total >= 50": ("total", 1, d.total_line >= 50),
        "Over, weeks 1-4": ("total", 0, d.early == 1),
        "Under, weeks 14+": ("total", 1, d.late == 1),
        "Home dog": ("spread", 0, d.spread_line < 0),
        "Road dog +7 or more": ("spread", 1, d.spread_line >= 7),
        "Home off bye vs non-bye": ("spread", 0, (d.bye_h == 1) & (d.bye_a == 0)),
        "Away team, backup QB (bk_a)": ("spread", 1, d.bk_a == 1),
        "Opp of backup QB home": ("spread", 1, d.bk_h == 1),
        "East home team vs West-coast visitor": ("spread", 0, d.tz_diff <= -3),
        "Elo disagrees >= 3 pts, Elo side": ("elo", None, (d.elo - d.spread_line).abs() >= 3),
    }
    for name, (kind, side, mask) in angles.items():
        txt = []
        for per in (d.season.between(2006, 2024), d.oos):
            x = d[mask & per]
            if kind == "elo":
                home = (x.elo > x.spread_line).values
                win = np.where(home, x.margin > x.spread_line, x.margin < x.spread_line)
                price = np.where(home, x.home_spread_odds, x.away_spread_odds)
                push = (x.margin == x.spread_line).values
            elif kind == "spread":
                win = (x.margin > x.spread_line) if side == 0 else (x.margin < x.spread_line)
                price = x.home_spread_odds if side == 0 else x.away_spread_odds
                push = x.margin == x.spread_line
            else:
                win = (x.points > x.total_line) if side == 0 else (x.points < x.total_line)
                price = x.over_odds if side == 0 else x.under_odds
                push = x.points == x.total_line
            txt.append(bet_report("", win, push, price).strip())
        print(f"  {name:38} {txt[0]}\n  {'':38} OOS: {txt[1]}")


def _cols(b):
    return {"win": b.win.values, "push": b.push.values, "price": b.price.values}


if __name__ == "__main__":
    main()
