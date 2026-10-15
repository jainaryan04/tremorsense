"""Patient-specific levodopa response model and wearing-off forecast.

Each press of the "dose taken" button is a dose event. Tremor severity from
the classifier (expected UPDRS grade, averaged per minute, only while the
activity gate says the hand is still) is the observed effect. We fit a small
pharmacokinetic/pharmacodynamic model to that person's own data:

    plasma      C(t)  = sum_d  ka/(ka-ke) * (exp(-ke*(t-td)) - exp(-ka*(t-td)))
    effect site dCe/dt = ke0 * (C - Ce)
    severity    S(t)  = S0 - Emax * Ce^g / (EC50^g + Ce^g)

ke is fixed from levodopa's ~1.5 h plasma half-life; ka, ke0, Emax, EC50 and
S0 are fitted. The fitted curve then predicts when the last dose will wear
off, so the app can warn before tremor returns rather than after.

`web/js/medcurve.js` is the browser port (it fits with Nelder-Mead instead of
SciPy's least squares).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

KE = math.log(2) / 1.5   # 1/h
GAMMA = 3.0
DT_H = 1.0 / 60.0        # 1-minute grid
PARAM_NAMES = ["ka", "ke0", "emax", "ec50", "s0"]
LOWER = np.array([0.3, 0.1, 0.2, 0.05, 0.5])
UPPER = np.array([6.0, 4.0, 4.0, 2.0, 4.5])
INIT = np.array([1.5, 0.8, 1.8, 0.5, 2.8])


def plasma(t_h: np.ndarray, doses_h: np.ndarray, ka: float, ke: float = KE) -> np.ndarray:
    c = np.zeros_like(t_h)
    k = ka / (ka - ke) if abs(ka - ke) > 1e-6 else 1.0
    for td in doses_h:
        d = t_h - td
        m = d > 0
        c[m] += k * (np.exp(-ke * d[m]) - np.exp(-ka * d[m]))
    return c


def effect_site(c: np.ndarray, ke0: float) -> np.ndarray:
    ce = np.zeros_like(c)
    a = 1.0 - math.exp(-ke0 * DT_H)   # exact discretisation of the first-order lag
    for i in range(1, len(c)):
        ce[i] = ce[i - 1] + a * (c[i - 1] - ce[i - 1])
    return ce


def severity(t_h, doses_h, params, ke: float = KE, gamma: float = GAMMA) -> np.ndarray:
    """ke and gamma are fixed in the fitted model; the evaluation varies them
    in the simulated 'true' patients to test robustness to model mismatch."""
    ka, ke0, emax, ec50, s0 = params
    ce = effect_site(plasma(t_h, doses_h, ka, ke), ke0)
    ceg = np.power(np.maximum(ce, 0), gamma)
    return s0 - emax * ceg / (ec50 ** gamma + ceg)


def fit(t_h: np.ndarray, obs: np.ndarray, doses_h: np.ndarray, t_grid: np.ndarray | None = None):
    """Fit parameters to observations (NaN = no observation, e.g. not still)."""
    if t_grid is None:
        t_grid = np.arange(t_h.min(), t_h.max() + DT_H, DT_H)
    idx = np.clip(np.round((t_h - t_grid[0]) / DT_H).astype(int), 0, len(t_grid) - 1)
    ok = ~np.isnan(obs)

    def resid(p):
        return severity(t_grid, doses_h, p)[idx[ok]] - obs[ok]

    best = None
    for scale in (1.0, 0.6, 1.6):   # a few starts; the surface has shallow valleys
        r = least_squares(resid, np.clip(INIT * scale, LOWER, UPPER), bounds=(LOWER, UPPER), loss="soft_l1")
        if best is None or r.cost < best.cost:
            best = r
    return best.x


def wearing_off_time(t_from_h: float, doses_h, params, horizon_h: float = 8.0, frac: float = 0.5):
    """First time after the last dose's peak effect when severity climbs back
    above `frac` of the way from best (min) to baseline (S0)."""
    t = np.arange(t_from_h, t_from_h + horizon_h, DT_H)
    # include history so the effect compartment starts from the right state
    t_all = np.arange(min(doses_h) - DT_H, t_from_h + horizon_h, DT_H)
    s_all = severity(t_all, doses_h, params)
    s = s_all[-len(t):]
    i_min = int(np.argmin(s))
    s0 = params[4]
    thr = s[i_min] + frac * (s0 - s[i_min])
    after = np.where(s[i_min:] >= thr)[0]
    if len(after) == 0:
        return None
    return float(t[i_min + after[0]])
