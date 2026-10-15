"""Online tremor phase tracking and phase-locked cue timing.

Pipeline, per sample at 50 Hz:
1. Band-pass each accelerometer axis around the current tremor frequency
   (a biquad band-pass has zero phase shift at its centre frequency).
2. Project the 3-axis signal onto its dominant direction, learned online with
   Oja's rule, so the method works in any device orientation.
3. Track frequency and phase with a weighted-frequency Fourier linear
   combiner (WFLC, Riviere et al. 1998), re-anchored to the spectral peak
   from the window analysis.
4. Predict the phase one actuator latency ahead and fire a short cue when
   the predicted phase crosses the target phase, at most once per cycle.

`web/js/phase.js` is the browser port of this module.
"""
from __future__ import annotations

import math

import numpy as np

from .dsp import FS


class Biquad:
    """RBJ band-pass (constant 0 dB peak gain)."""

    def __init__(self, f0: float, q: float = 1.5):
        self.z = np.zeros((2, 3))
        self.set(f0, q)

    def set(self, f0: float, q: float = 1.5):
        w0 = 2 * math.pi * f0 / FS
        alpha = math.sin(w0) / (2 * q)
        a0 = 1 + alpha
        self.b = np.array([alpha, 0.0, -alpha]) / a0
        self.a = np.array([1.0, -2 * math.cos(w0) / a0, (1 - alpha) / a0])

    def step(self, x: np.ndarray) -> np.ndarray:
        # Transposed direct form II, vectorised over 3 axes.
        y = self.b[0] * x + self.z[0]
        self.z[0] = self.b[1] * x - self.a[1] * y + self.z[1]
        self.z[1] = self.b[2] * x - self.a[2] * y
        return y


class PhaseTracker:
    def __init__(self, f_init: float = 5.0, mu_w: float = 0.02, mu_f: float = 2e-4,
                 anchor: float = 0.002):
        self.bp = Biquad(f_init)
        self.u = np.array([1.0, 0.0, 0.0])
        self.omega = 2 * math.pi * f_init / FS   # rad / sample
        self.theta = 0.0
        self.w = np.zeros(2)
        self.power = 1e-3
        self.mu_w, self.mu_f, self.anchor = mu_w, mu_f, anchor
        self.f_anchor = f_init

    def set_anchor(self, f_peak: float):
        self.f_anchor = float(np.clip(f_peak, 3.5, 12.5))
        self.bp.set(self.f_anchor)

    def step(self, acc_xyz: np.ndarray):
        y3 = self.bp.step(np.asarray(acc_xyz, float))
        # Oja's rule for the dominant axis.
        s = float(self.u @ y3)
        self.u += 0.01 * s * (y3 - s * self.u) / (self.power + 1e-9)
        self.u /= np.linalg.norm(self.u) + 1e-12
        self.power = 0.99 * self.power + 0.01 * s * s
        sn = s / math.sqrt(self.power + 1e-12)
        # WFLC update.
        x = np.array([math.sin(self.theta), math.cos(self.theta)])
        err = sn - float(self.w @ x)
        self.omega += 2 * self.mu_f * err * (self.w[0] * x[1] - self.w[1] * x[0])
        self.omega += self.anchor * (2 * math.pi * self.f_anchor / FS - self.omega)
        self.omega = float(np.clip(self.omega, 2 * math.pi * 3.0 / FS, 2 * math.pi * 13.0 / FS))
        self.w += 2 * self.mu_w * x * err
        self.theta = (self.theta + self.omega) % (2 * math.pi)
        phase = (self.theta + math.atan2(self.w[1], self.w[0])) % (2 * math.pi)
        return phase, self.freq()

    def freq(self) -> float:
        return self.omega * FS / (2 * math.pi)


class CueScheduler:
    """Fires when the phase predicted `latency_s` ahead crosses `target`."""

    def __init__(self, target: float = 0.0, latency_s: float = 0.04):
        self.target = target
        self.latency_s = latency_s
        self.prev = None
        self.refractory = 0

    def step(self, phase: float, f: float) -> bool:
        pred = (phase + 2 * math.pi * f * self.latency_s) % (2 * math.pi)
        rel = (pred - self.target) % (2 * math.pi)
        fire = False
        if self.prev is not None and self.refractory <= 0 and rel < self.prev and self.prev - rel > math.pi:
            fire = True  # wrapped past the target
            self.refractory = int(0.6 * FS / max(f, 1e-3))
        self.refractory -= 1
        self.prev = rel
        return fire


def circular_stats(angles: np.ndarray):
    z = np.exp(1j * np.asarray(angles))
    m = z.mean()
    plv = float(abs(m))
    circ_std = float(math.sqrt(-2 * math.log(max(plv, 1e-12))))
    return plv, float(np.angle(m)), circ_std
