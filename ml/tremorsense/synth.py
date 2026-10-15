"""Physics-grounded synthetic IMU generator.

There is no patient data in this project yet, so every model here is trained
and evaluated on signals generated from published tremor characteristics:

* MDS-UPDRS item 3.17 grades rest-tremor amplitude by peak-to-peak hand
  displacement: 1 = <1 cm, 2 = 1-3 cm, 3 = 3-10 cm, 4 = >10 cm.
* Parkinsonian rest tremor sits around 4-6.5 Hz, essential tremor around
  6-11 Hz (the two ranges overlap on purpose, as they do clinically).
* Physiological tremor (8-12 Hz, sub-millimetre) is always present.

Displacement d(t) = A/2 * sin(phi(t)) along a random direction becomes
acceleration -(A/2) * (2*pi*f)^2 * sin(phi). Confounders that cause false
positives in published smartwatch work (walking, deliberate movement,
riding in a vehicle) are generated as separate activity classes.

Results produced from this data are simulation results and are labelled so.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfiltfilt

from .dsp import FS, WIN

GRADE_P2P_CM = {1: (0.15, 1.0), 2: (1.0, 3.0), 3: (3.0, 10.0), 4: (10.0, 16.0)}
ACTIVITIES = ["still", "voluntary", "gait", "vehicle"]
TYPES = ["none", "parkinsonian", "essential"]
ACTIVITY_P = [0.55, 0.20, 0.15, 0.10]


def _unit(rng) -> np.ndarray:
    v = rng.normal(size=3)
    return v / np.linalg.norm(v)


def _perp(u, rng) -> np.ndarray:
    v = np.cross(u, _unit(rng))
    return v / np.linalg.norm(v)


def _bandnoise(n, lo, hi, rms, rng, dims=3):
    sos = butter(4, [lo, hi], btype="band", fs=FS, output="sos")
    x = sosfiltfilt(sos, rng.normal(size=(n + 200, dims)), axis=0)[100:-100]
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-12) * rms


@dataclass
class Subject:
    sid: int
    ttype: str            # "parkinsonian" | "essential"
    f0: float             # Hz, characteristic tremor frequency
    base_grade: int       # 0..4
    placement: str        # "watch" | "phone"
    scale: float          # measured / true hand displacement at this placement
    lever_m: float        # wrist-to-hand lever arm for the rotational component
    harmonic: float
    noise_acc: float
    noise_gyro: float


def make_subject(sid: int, rng) -> Subject:
    ttype = rng.choice(["parkinsonian", "essential"])
    f0 = rng.uniform(4.0, 6.5) if ttype == "parkinsonian" else rng.uniform(6.0, 11.0)
    placement = rng.choice(["watch", "phone"])
    scale = rng.uniform(0.55, 0.9) if placement == "watch" else rng.uniform(0.85, 1.05)
    return Subject(sid, str(ttype), f0, int(rng.integers(0, 5)), str(placement), scale,
                   rng.uniform(0.08, 0.15), rng.uniform(0.0, 0.15),
                   rng.uniform(0.02, 0.06), rng.uniform(0.3, 1.0))


def sample_p2p_cm(grade: int, rng) -> float:
    if grade == 0:
        return 0.0
    lo, hi = GRADE_P2P_CM[grade]
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def tremor(n, f0, p2p_cm, subj: Subject, rng, amp_env=None, t0=0.0):
    """Tremor acceleration and rotation rate, plus the true instantaneous phase.

    amp_env: optional per-sample multiplier on displacement (for slow
    medication-driven changes in long recordings).
    """
    t = t0 + np.arange(n) / FS
    # Frequency wanders slowly (+-0.3 Hz), amplitude waxes and wanes.
    drift = np.cumsum(rng.normal(scale=0.02, size=n))
    drift = 0.3 * np.tanh(drift - drift.mean())
    f = f0 + drift
    phi = rng.uniform(0, 2 * np.pi) + 2 * np.pi * np.cumsum(f) / FS
    am = 1.0 + 0.2 * np.sin(2 * np.pi * rng.uniform(0.05, 0.2) * t + rng.uniform(0, 6.3))
    a_disp = p2p_cm / 100.0 / 2.0 * subj.scale * am
    if amp_env is not None:
        a_disp = a_disp * amp_env
    w = 2 * np.pi * f
    u, v = _unit(rng), None
    v = _perp(u, rng)
    lin = -a_disp * w ** 2 * np.sin(phi)
    lin2 = -subj.harmonic * a_disp * (2 * w) ** 2 * np.sin(2 * phi + 0.7)
    ell = 0.3 * (-a_disp * w ** 2 * np.cos(phi))           # slight elliptical path
    acc = np.outer(lin + lin2, u) + np.outer(ell, v)
    rot = np.degrees(w * a_disp / subj.lever_m * np.cos(phi))  # deg/s
    gyro = np.outer(rot, _perp(u, rng))
    return acc, gyro, np.mod(phi, 2 * np.pi), f


def activity_signal(n, activity, rng):
    acc = np.zeros((n, 3))
    gyro = np.zeros((n, 3))
    t = np.arange(n) / FS
    if activity == "voluntary":
        acc += _bandnoise(n, 0.3, 2.5, rng.uniform(0.8, 4.0), rng)
        gyro += _bandnoise(n, 0.3, 2.5, rng.uniform(30, 120), rng)
        if rng.random() < 0.3:  # tapping / typing bursts
            burst = (rng.random(n) < 0.04).astype(float)
            acc += np.outer(burst, _unit(rng)) * rng.uniform(2, 6)
    elif activity == "gait":
        fc = rng.uniform(1.6, 2.2)
        up, fw = _unit(rng), None
        fw = _perp(up, rng)
        ph = rng.uniform(0, 6.3)
        vert = rng.uniform(2, 4) * np.sin(2 * np.pi * fc * t + ph) + rng.uniform(0.5, 2) * np.sin(4 * np.pi * fc * t)
        swing = rng.uniform(1, 3) * np.sin(np.pi * fc * t + ph)
        acc += np.outer(vert, up) + np.outer(swing, fw)
        gyro += np.outer(rng.uniform(50, 150) * np.cos(np.pi * fc * t + ph), _unit(rng))
        acc += _bandnoise(n, 0.5, 10, 0.3, rng)
    elif activity == "vehicle":
        acc += _bandnoise(n, 2.0, 15.0, rng.uniform(0.3, 1.5), rng)
        acc += _bandnoise(n, 0.2, 1.0, rng.uniform(0.2, 0.8), rng)
        gyro += _bandnoise(n, 0.5, 10.0, rng.uniform(2, 10), rng)
    return acc, gyro


def tremor_gain(ttype: str, activity: str, rng) -> float:
    """How much of the 'at rest/posture' tremor shows during an activity."""
    if activity == "still":
        return 1.0
    if ttype == "parkinsonian":       # rest tremor is suppressed by movement
        return rng.uniform(0.1, 0.6) if activity == "voluntary" else rng.uniform(0.3, 1.0)
    return rng.uniform(1.0, 1.5) if activity == "voluntary" else rng.uniform(0.3, 0.8)


def window(subj: Subject, grade: int, activity: str, rng, n: int = WIN):
    p2p = sample_p2p_cm(grade, rng)
    acc, gyro = activity_signal(n, activity, rng)
    if grade > 0:
        ta, tg, _, _ = tremor(n, subj.f0, p2p * tremor_gain(subj.ttype, activity, rng), subj, rng)
        acc += ta
        gyro += tg
    # Physiological tremor, always present.
    pa, pg, _, _ = tremor(n, rng.uniform(8, 12), rng.uniform(0.005, 0.03), subj, rng)
    acc += pa + rng.normal(scale=subj.noise_acc, size=(n, 3))
    gyro += pg + rng.normal(scale=subj.noise_gyro, size=(n, 3))
    return acc, gyro, p2p


def dataset(n_subjects: int, windows_per_subject: int, seed: int):
    """Returns per-window arrays: acc, gyro, grade, type, activity, subject, placement, p2p."""
    rng = np.random.default_rng(seed)
    out = {k: [] for k in ["acc", "gyro", "grade", "type", "activity", "subject", "placement", "p2p"]}
    for sid in range(n_subjects):
        s = make_subject(sid, rng)
        for _ in range(windows_per_subject):
            g = int(np.clip(s.base_grade + rng.integers(-1, 2), 0, 4))
            act = str(rng.choice(ACTIVITIES, p=ACTIVITY_P))
            acc, gyro, p2p = window(s, g, act, rng)
            out["acc"].append(acc)
            out["gyro"].append(gyro)
            out["grade"].append(g)
            out["type"].append(TYPES.index(s.ttype) if g > 0 else 0)
            out["activity"].append(ACTIVITIES.index(act))
            out["subject"].append(sid)
            out["placement"].append(1 if s.placement == "watch" else 0)
            out["p2p"].append(p2p)
    return {k: np.asarray(v) for k, v in out.items()}
