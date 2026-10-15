// Port of ml/tremorsense/phase.py: online phase tracking and cue timing.
import { FS } from "./dsp.js";

const TAU = 2 * Math.PI;
const mod = (a, m) => ((a % m) + m) % m;

class Biquad {
  constructor(f0, q = 1.5) {
    this.z = [[0, 0, 0], [0, 0, 0]];
    this.set(f0, q);
  }

  set(f0, q = 1.5) {
    const w0 = (TAU * f0) / FS;
    const alpha = Math.sin(w0) / (2 * q);
    const a0 = 1 + alpha;
    this.b = [alpha / a0, 0, -alpha / a0];
    this.a = [1, (-2 * Math.cos(w0)) / a0, (1 - alpha) / a0];
  }

  step(x) {
    const y = [0, 0, 0];
    for (let i = 0; i < 3; i++) {
      y[i] = this.b[0] * x[i] + this.z[0][i];
      this.z[0][i] = this.b[1] * x[i] - this.a[1] * y[i] + this.z[1][i];
      this.z[1][i] = this.b[2] * x[i] - this.a[2] * y[i];
    }
    return y;
  }
}

export class PhaseTracker {
  constructor(fInit = 5.0, muW = 0.02, muF = 2e-4, anchor = 0.002) {
    this.bp = new Biquad(fInit);
    this.u = [1, 0, 0];
    this.omega = (TAU * fInit) / FS;
    this.theta = 0;
    this.w = [0, 0];
    this.power = 1e-3;
    this.muW = muW;
    this.muF = muF;
    this.anchor = anchor;
    this.fAnchor = fInit;
    this.last = 0;
  }

  setAnchor(fPeak) {
    this.fAnchor = Math.min(12.5, Math.max(3.5, fPeak));
    this.bp.set(this.fAnchor);
  }

  step(acc) {
    const y3 = this.bp.step(acc);
    const s = this.u[0] * y3[0] + this.u[1] * y3[1] + this.u[2] * y3[2];
    for (let i = 0; i < 3; i++) this.u[i] += (0.01 * s * (y3[i] - s * this.u[i])) / (this.power + 1e-9);
    const n = Math.hypot(...this.u) + 1e-12;
    for (let i = 0; i < 3; i++) this.u[i] /= n;
    this.power = 0.99 * this.power + 0.01 * s * s;
    const sn = s / Math.sqrt(this.power + 1e-12);
    this.last = sn;
    const x = [Math.sin(this.theta), Math.cos(this.theta)];
    const err = sn - (this.w[0] * x[0] + this.w[1] * x[1]);
    this.omega += 2 * this.muF * err * (this.w[0] * x[1] - this.w[1] * x[0]);
    this.omega += this.anchor * ((TAU * this.fAnchor) / FS - this.omega);
    this.omega = Math.min((TAU * 13) / FS, Math.max((TAU * 3) / FS, this.omega));
    this.w[0] += 2 * this.muW * x[0] * err;
    this.w[1] += 2 * this.muW * x[1] * err;
    this.theta = mod(this.theta + this.omega, TAU);
    const phase = mod(this.theta + Math.atan2(this.w[1], this.w[0]), TAU);
    return { phase, freq: this.freq() };
  }

  freq() {
    return (this.omega * FS) / TAU;
  }
}

export class CueScheduler {
  constructor(target = 0, latencyS = 0.04) {
    this.target = target;
    this.latencyS = latencyS;
    this.prev = null;
    this.refractory = 0;
  }

  step(phase, f) {
    const pred = mod(phase + TAU * f * this.latencyS, TAU);
    const rel = mod(pred - this.target, TAU);
    let fire = false;
    if (this.prev !== null && this.refractory <= 0 && rel < this.prev && this.prev - rel > Math.PI) {
      fire = true;
      this.refractory = Math.trunc((0.6 * FS) / Math.max(f, 1e-3));
    }
    this.refractory -= 1;
    this.prev = rel;
    return fire;
  }
}
