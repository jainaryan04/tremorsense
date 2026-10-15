// Streaming demo signal so the app can be shown without a patient. It follows
// the same physics as ml/tremorsense/synth.py (UPDRS displacement bands,
// PD 4-6.5 Hz, ET 6-11 Hz, walking / deliberate movement / vehicle confounders).
import { FS } from "./dsp.js";

const TAU = 2 * Math.PI;
const P2P_CM = { 0: 0, 1: 0.45, 2: 1.9, 3: 5.8, 4: 14 };

function gauss() {
  let u = 0, v = 0;
  while (!u) u = Math.random();
  while (!v) v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v);
}

function unit() {
  const v = [gauss(), gauss(), gauss()];
  const n = Math.hypot(...v);
  return v.map((x) => x / n);
}

// RBJ biquad, low- or high-pass, Q = 1/sqrt(2).
function biquad(kind, f0) {
  const w0 = (TAU * f0) / FS, al = Math.sin(w0) / Math.SQRT2, c = Math.cos(w0), a0 = 1 + al;
  const b = kind === "low" ? [(1 - c) / 2, 1 - c, (1 - c) / 2] : [(1 + c) / 2, -(1 + c), (1 + c) / 2];
  return { b: b.map((v) => v / a0), a: [(-2 * c) / a0, (1 - al) / a0], z: [[0, 0], [0, 0], [0, 0]] };
}

class BandNoise {
  // White noise through a 4th-order band-pass (two high-pass and two
  // low-pass sections, like the Butterworth filter in synth.py), scaled to
  // unit RMS per axis by a running power estimate.
  constructor(lo, hi) {
    this.stages = [biquad("high", lo), biquad("high", lo), biquad("low", hi), biquad("low", hi)];
    this.ms = 0;
    for (let i = 0; i < 1500; i++) this.step();
  }

  step() {
    const y = [0, 1, 2].map((i) => {
      let x = gauss();
      for (const st of this.stages) {
        const v = st.b[0] * x + st.z[i][0];
        st.z[i][0] = st.b[1] * x - st.a[0] * v + st.z[i][1];
        st.z[i][1] = st.b[2] * x - st.a[1] * v;
        x = v;
      }
      return x;
    });
    this.ms = 0.995 * this.ms + 0.005 * (y[0] ** 2 + y[1] ** 2 + y[2] ** 2) / 3;
    const k = 1 / Math.sqrt(this.ms + 1e-12);
    return y.map((v) => v * k);
  }
}

export class Simulator {
  constructor() {
    this.grade = 2;
    this.type = "parkinsonian";
    this.activity = "still";
    this.phi = 0;
    this.t = 0;
    this.f0 = 5.2;
    this.dir = unit();
    this.dir2 = unit();
    this.rot = unit();
    this.vol = new BandNoise(0.3, 2.5);
    this.veh = new BandNoise(2.0, 15.0);
    this.sway = new BandNoise(0.2, 1.0);
    this.gaitNoise = new BandNoise(0.5, 10.0);
    this.cad = 1.9;
    this.ampScale = 1; // set by the medication demo
  }

  set({ grade, type, activity }) {
    if (grade !== undefined) this.grade = grade;
    if (type !== undefined) {
      this.type = type;
      this.f0 = type === "parkinsonian" ? 5.2 : 8.0;
    }
    if (activity !== undefined) this.activity = activity;
  }

  next() {
    const dt = 1 / FS;
    this.t += dt;
    const f = this.f0 + 0.25 * Math.sin(TAU * 0.03 * this.t);
    this.phi = (this.phi + TAU * f * dt) % TAU;
    let gain = 1;
    if (this.activity === "voluntary") gain = this.type === "parkinsonian" ? 0.35 : 1.2;
    if (this.activity === "gait") gain = this.type === "parkinsonian" ? 0.6 : 0.5;
    const am = 1 + 0.2 * Math.sin(TAU * 0.12 * this.t);
    const aDisp = ((P2P_CM[this.grade] / 100) / 2) * 0.95 * am * gain * this.ampScale;
    const w = TAU * f;
    const lin = -aDisp * w * w * Math.sin(this.phi);
    const ell = -0.3 * aDisp * w * w * Math.cos(this.phi);
    const rot = ((w * aDisp) / 0.12) * Math.cos(this.phi) * (180 / Math.PI);
    const acc = [0, 1, 2].map((i) => lin * this.dir[i] + ell * this.dir2[i] + 0.04 * gauss());
    const gyro = [0, 1, 2].map((i) => rot * this.rot[i] + 0.6 * gauss());

    if (this.activity === "voluntary") {
      const v = this.vol.step();
      for (let i = 0; i < 3; i++) { acc[i] += 1.4 * v[i]; gyro[i] += 43 * v[(i + 1) % 3]; }
    } else if (this.activity === "gait") {
      const s = Math.sin(TAU * this.cad * this.t), s2 = Math.sin(2 * TAU * this.cad * this.t), sw = Math.sin(Math.PI * this.cad * this.t);
      for (let i = 0; i < 3; i++) {
        acc[i] += 3 * s * this.dir2[i] + 1.2 * s2 * this.dir2[i] + 2 * sw * this.rot[i];
        gyro[i] += 100 * Math.cos(Math.PI * this.cad * this.t) * this.dir[i];
      }
      const n = this.gaitNoise.step();
      for (let i = 0; i < 3; i++) acc[i] += 0.17 * n[i];
    } else if (this.activity === "vehicle") {
      const v = this.veh.step(), sw = this.sway.step();
      for (let i = 0; i < 3; i++) { acc[i] += 0.55 * v[i] + 0.3 * sw[i]; gyro[i] += 3.5 * v[(i + 2) % 3]; }
    }
    return { acc, gyro };
  }
}
