"""Conformal safety gate for haptic intervention.

Split conformal prediction turns the model's class probabilities into a
*prediction set* that contains the true class with probability >= 1 - alpha,
whatever the model's errors look like, provided calibration and use data are
exchangeable. TremorSense uses two such sets:

* an activity set: the haptic cue may only fire when it is exactly {still};
* a severity set, made contiguous because UPDRS grades are ordinal.

The cue intensity is the *lower end* of the severity set. If the true grade is
in the set, the cue can never be stronger than the true severity, so the
over-stimulation rate is bounded by alpha. A set that spans more than
`max_width` grades means the model does not know enough, and the device stays
silent instead of guessing.
"""
from __future__ import annotations

import math

import numpy as np


def calibrate(probs: np.ndarray, labels: np.ndarray, alpha: float) -> float:
    """Return the LAC threshold q_hat from held-out calibration data."""
    n = len(labels)
    scores = 1.0 - probs[np.arange(n), labels]
    k = min(n, math.ceil((n + 1) * (1 - alpha)))
    return float(np.sort(scores)[k - 1])


def prediction_set(p: np.ndarray, q_hat: float, ordinal: bool = False) -> list[int]:
    keep = [k for k in range(len(p)) if 1.0 - p[k] <= q_hat]
    if not keep:
        keep = [int(np.argmax(p))]
    if ordinal:
        keep = list(range(min(keep), max(keep) + 1))
    return keep


def gate(p_activity, p_severity, q_act, q_sev, still_index=0, min_grade=2, max_width=1):
    """Decide whether and how strongly to cue.

    Returns (intensity, info). intensity is 0 for no cue, else the conservative
    UPDRS grade (2..4) used to scale the cue.
    """
    a_set = prediction_set(p_activity, q_act)
    s_set = prediction_set(p_severity, q_sev, ordinal=True)
    lo, hi = s_set[0], s_set[-1]
    info = {"activity_set": a_set, "severity_set": s_set, "reason": "ok"}
    if a_set != [still_index]:
        info["reason"] = "not_still"
        return 0, info
    if hi - lo > max_width:
        info["reason"] = "uncertain"
        return 0, info
    if lo < min_grade:
        info["reason"] = "below_threshold"
        return 0, info
    return lo, info
