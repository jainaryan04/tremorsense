import math

import numpy as np
import pytest

from tremorsense import conformal, dsp, medcurve, synth
from tremorsense.phase import CueScheduler, PhaseTracker, circular_stats


def sine_window(f, p2p_cm, axis, n=dsp.WIN):
    t = np.arange(n) / dsp.FS
    a = -(p2p_cm / 100 / 2) * (2 * np.pi * f) ** 2 * np.sin(2 * np.pi * f * t)
    acc = np.outer(a, axis)
    return acc, np.zeros((n, 3))


@pytest.mark.parametrize("f", [4.5, 6.0, 9.0])
def test_peak_frequency_and_displacement(f):
    acc, gyro = sine_window(f, 2.0, np.array([0.0, 0.0, 1.0]))
    x = dsp.features(acc, gyro)
    assert abs(x[dsp.FEATURE_NAMES.index("f_peak")] - f) < 0.2
    disp = math.exp(x[dsp.FEATURE_NAMES.index("log_disp_p2p_cm")])
    assert 1.6 < disp < 2.4  # recovers the 2 cm peak-to-peak displacement


def test_features_ignore_orientation():
    a1, g = sine_window(5.0, 3.0, np.array([1.0, 0.0, 0.0]))
    a2, _ = sine_window(5.0, 3.0, np.array([0.3, -0.5, 0.81]) / np.linalg.norm([0.3, -0.5, 0.81]))
    assert np.allclose(dsp.features(a1, g), dsp.features(a2, g), atol=1e-6)


def test_conformal_coverage_holds():
    rng = np.random.default_rng(0)
    n, k = 4000, 5
    logits = rng.normal(size=(n, k))
    y = np.array([rng.choice(k, p=np.exp(l) / np.exp(l).sum()) for l in logits])
    p = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    q = conformal.calibrate(p[:2000], y[:2000], 0.1)
    cov = np.mean([y[i] in conformal.prediction_set(p[i], q) for i in range(2000, n)])
    assert cov >= 0.88


def test_gate_rules():
    still = np.array([0.98, 0.01, 0.005, 0.005])
    walking = np.array([0.1, 0.1, 0.75, 0.05])
    sev3 = np.array([0.0, 0.0, 0.05, 0.9, 0.05])
    wide = np.array([0.0, 0.3, 0.1, 0.3, 0.3])
    assert conformal.gate(still, sev3, 0.5, 0.5)[0] == 3
    assert conformal.gate(walking, sev3, 0.5, 0.5)[1]["reason"] == "not_still"
    assert conformal.gate(still, wide, 0.5, 0.75)[1]["reason"] == "uncertain"
    # intensity is the lower end of the set: never above any plausible grade
    inten, info = conformal.gate(still, np.array([0, 0, 0.45, 0.55, 0]), 0.5, 0.6)
    assert inten == 2 and info["severity_set"] == [2, 3]


def test_phase_locking_on_clean_tremor():
    rng = np.random.default_rng(1)
    s = synth.make_subject(0, rng)
    acc, _, phi, _ = synth.tremor(3000, 5.5, 3.0, s, rng)
    trk, sch = PhaseTracker(5.0), CueScheduler(0.0, 0.04)
    trk.set_anchor(5.5)
    fires = [i for i in range(3000) if sch.step(*trk.step(acc[i])) and i > 300]
    plv, _, _ = circular_stats(phi[[min(i + 2, 2999) for i in fires]])
    assert plv > 0.8
    assert 0.7 < len(fires) / (2700 / dsp.FS * 5.5) <= 1.05  # about one cue per cycle


def test_medcurve_fit_recovers_parameters():
    rng = np.random.default_rng(2)
    true = np.array([1.8, 0.7, 2.0, 0.5, 3.0])
    doses = np.array([7.0, 11.0, 15.0, 19.0, 31.0, 35.0])
    t = np.arange(6, 40, medcurve.DT_H)
    obs = medcurve.severity(t, doses, true) + rng.normal(scale=0.3, size=len(t))
    p = medcurve.fit(t, obs, doses, t_grid=t)
    r = np.corrcoef(medcurve.severity(t, doses, p), medcurve.severity(t, doses, true))[0, 1]
    assert r > 0.98
    wo_t, wo_p = medcurve.wearing_off_time(35, doses, true), medcurve.wearing_off_time(35, doses, p)
    assert abs(wo_t - wo_p) < 0.5


def test_synthetic_grades_match_updrs_bands():
    rng = np.random.default_rng(3)
    for g, (lo, hi) in synth.GRADE_P2P_CM.items():
        for _ in range(20):
            assert lo <= synth.sample_p2p_cm(g, rng) <= hi
