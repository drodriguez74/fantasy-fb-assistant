"""Fit the key-number margin model (exp1 model C) on 2015-2024 and print the
constants betting_model.py ships: the SD (and its slope per 10 points of
total) and the log-weight for each exact favorite margin |k| <= 25.

    python scripts/experiments/exp1c_export.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from exp1_distribution import KEY_M, KM, fit, m_dist_B, m_dist_C  # noqa: E402
from gl_common import load  # noqa: E402

d = load()
f = d[d.fit]
sg = np.where(f.spread_line >= 0, 1, -1)
s, t, x = np.abs(f.spread_line.values), f.total_line.values, (f.margin * sg).values
thB = fit(m_dist_B, np.array([0, 1, np.log(13.5), 0]), s, t, x, KM)
thC = fit(m_dist_C, np.r_[thB, np.zeros(KEY_M)], s, t, x, KM, l2=0.5)
print(json.dumps({"sd_at_44": round(float(np.exp(thC[2])), 3), "sd_log_slope_per_10": round(float(thC[3]), 4),
                  "key_log_weights": [round(float(b), 4) for b in thC[4:]]}))
