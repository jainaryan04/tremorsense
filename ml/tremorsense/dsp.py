"""Signal processing and feature extraction.

This module is the reference implementation. `web/js/dsp.js` is a line-for-line
port and is checked against it by `web/test/parity.test.mjs`, so any change here
must be mirrored there and the fixtures regenerated (`python -m scripts.export_fixtures`).

All spectral features use the trace of the 3-axis power spectral density
(PSD_x + PSD_y + PSD_z). The trace is invariant to sensor orientation, so the
same features work whether the phone is held, pocketed or the watch is worn
on either wrist.
"""
from __future__ import annotations

import numpy as np

FS = 50.0            # Hz, every input stream is resampled to this rate
WIN = 200            # samples, 4 s analysis window
HOP = 50             # samples, 1 s hop -> one decision per second
NSEG = 128           # Welch segment length
NOVERLAP = 64        # Welch overlap

BAND_LOW = (0.3, 3.0)      # voluntary movement / gait
BAND_PD = (3.5, 7.5)       # Parkinsonian rest tremor
BAND_ET = (7.5, 12.5)      # essential / postural tremor
BAND_TREMOR = (3.5, 12.5)
BAND_GAIT = (1.4, 2.5)
BAND_ALL = (0.3, 20.0)
EPS = 1e-9

FEATURE_NAMES = [
    "log_p_low", "log_p_pd", "log_p_et", "log_p_tremor",
    "f_peak", "log_peak_power", "log_peak_prominence", "spectral_entropy",
    "tremor_fraction", "harmonic_ratio", "log_disp_p2p_cm", "gait_ratio",
    "f_low_peak", "log_gyro_tremor", "log_gyro_low", "gyro_f_peak",
    "log_acc_std", "log_jerk_rms", "log_tremor_low_ratio",
]


def hann(n: int) -> np.ndarray:
    # Periodic Hann, same formula as the JS port.
    k = np.arange(n)
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * k / n)


_HANN = hann(NSEG)
_HANN_POW = float(np.sum(_HANN ** 2))
FREQS = np.arange(NSEG // 2 + 1) * FS / NSEG
DF = FS / NSEG


def welch_psd(x: np.ndarray) -> np.ndarray:
    """One-sided Welch PSD of a 1-D signal (mean removed per segment)."""
    starts = range(0, len(x) - NSEG + 1, NSEG - NOVERLAP)
    acc = np.zeros(NSEG // 2 + 1)
    n = 0
    for s in starts:
        seg = x[s:s + NSEG]
        seg = (seg - seg.mean()) * _HANN
        spec = np.abs(np.fft.rfft(seg)) ** 2 / (FS * _HANN_POW)
        spec[1:-1] *= 2.0
        acc += spec
        n += 1
    return acc / n


def psd_trace(xyz: np.ndarray) -> np.ndarray:
    """Orientation-invariant PSD: sum of per-axis PSDs. xyz has shape (N, 3)."""
    return sum(welch_psd(xyz[:, i]) for i in range(3))


def band_mask(lo: float, hi: float) -> np.ndarray:
    return (FREQS >= lo) & (FREQS < hi)


def band_power(p: np.ndarray, band) -> float:
    return float(np.sum(p[band_mask(*band)]) * DF)


def peak_in(p: np.ndarray, band):
    idx = np.where(band_mask(*band))[0]
    i = idx[int(np.argmax(p[idx]))]
    # Parabolic interpolation on the log spectrum for sub-bin frequency.
    if 0 < i < len(p) - 1:
        a, b, c = np.log(p[i - 1] + EPS), np.log(p[i] + EPS), np.log(p[i + 1] + EPS)
        den = a - 2 * b + c
        delta = 0.5 * (a - c) / den if abs(den) > 1e-12 else 0.0
        delta = float(np.clip(delta, -0.5, 0.5))
    else:
        delta = 0.0
    return (i + delta) * DF, float(p[i]), i


def spectral_entropy(p: np.ndarray, band) -> float:
    q = p[band_mask(*band)]
    q = q / (q.sum() + EPS)
    return float(-np.sum(q * np.log(q + EPS)) / np.log(len(q)))


def features(acc: np.ndarray, gyro: np.ndarray) -> np.ndarray:
    """Feature vector for one window.

    acc:  (WIN, 3) user acceleration, gravity removed, m/s^2
    gyro: (WIN, 3) rotation rate, deg/s
    """
    pa = psd_trace(acc)
    pg = psd_trace(gyro)

    p_low = band_power(pa, BAND_LOW)
    p_pd = band_power(pa, BAND_PD)
    p_et = band_power(pa, BAND_ET)
    p_tr = band_power(pa, BAND_TREMOR)
    p_all = band_power(pa, BAND_ALL)

    f_peak, peak_pow, _ = peak_in(pa, BAND_TREMOR)
    med = float(np.median(pa[band_mask(*BAND_TREMOR)]))
    prominence = peak_pow / (med + EPS)
    ent = spectral_entropy(pa, BAND_ALL)

    h_lo, h_hi = 2 * f_peak - 0.6, 2 * f_peak + 0.6
    harm = band_power(pa, (h_lo, h_hi)) / (band_power(pa, (f_peak - 0.6, f_peak + 0.6)) + EPS)

    # Physics: a sinusoid of acceleration amplitude a at frequency f has
    # displacement amplitude a / (2*pi*f)^2. Peak-to-peak = 2x amplitude.
    acc_amp = np.sqrt(2.0 * p_tr)
    disp_p2p_cm = 2.0 * acc_amp / (2.0 * np.pi * f_peak) ** 2 * 100.0

    gait_ratio = band_power(pa, BAND_GAIT) / (p_low + EPS)
    f_low, _, _ = peak_in(pa, BAND_LOW)
    g_tr = band_power(pg, BAND_TREMOR)
    g_low = band_power(pg, BAND_LOW)
    g_f, _, _ = peak_in(pg, BAND_TREMOR)

    mag = np.sqrt(np.sum(acc ** 2, axis=1))
    jerk = np.diff(acc, axis=0) * FS
    jerk_rms = float(np.sqrt(np.mean(np.sum(jerk ** 2, axis=1))))

    return np.array([
        np.log(p_low + EPS), np.log(p_pd + EPS), np.log(p_et + EPS), np.log(p_tr + EPS),
        f_peak, np.log(peak_pow + EPS), np.log(prominence + EPS), ent,
        p_tr / (p_all + EPS), harm, np.log(disp_p2p_cm + 1e-4), gait_ratio,
        f_low, np.log(g_tr + EPS), np.log(g_low + EPS), g_f,
        np.log(float(np.std(mag)) + EPS), np.log(jerk_rms + EPS), np.log((p_tr + EPS) / (p_low + EPS)),
    ], dtype=np.float64)


def windows(acc: np.ndarray, gyro: np.ndarray, win: int = WIN, hop: int = HOP):
    for s in range(0, len(acc) - win + 1, hop):
        yield s, acc[s:s + win], gyro[s:s + win]
