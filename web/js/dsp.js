// Port of ml/tremorsense/dsp.py. Keep the two in step; web/test/parity.test.mjs
// checks this file against fixtures exported from the Python version.

export const FS = 50;
export const WIN = 200;
export const HOP = 50;
const NSEG = 128;
const NOVERLAP = 64;
const EPS = 1e-9;

export const BAND_LOW = [0.3, 3.0];
export const BAND_PD = [3.5, 7.5];
export const BAND_ET = [7.5, 12.5];
export const BAND_TREMOR = [3.5, 12.5];
const BAND_GAIT = [1.4, 2.5];
const BAND_ALL = [0.3, 20.0];

export const FEATURE_NAMES = [
  "log_p_low", "log_p_pd", "log_p_et", "log_p_tremor",
  "f_peak", "log_peak_power", "log_peak_prominence", "spectral_entropy",
  "tremor_fraction", "harmonic_ratio", "log_disp_p2p_cm", "gait_ratio",
  "f_low_peak", "log_gyro_tremor", "log_gyro_low", "gyro_f_peak",
  "log_acc_std", "log_jerk_rms", "log_tremor_low_ratio",
];

const NBIN = NSEG / 2 + 1;
const DF = FS / NSEG;
export const FREQS = Float64Array.from({ length: NBIN }, (_, k) => k * DF);
const HANN = Float64Array.from({ length: NSEG }, (_, k) => 0.5 - 0.5 * Math.cos((2 * Math.PI * k) / NSEG));
const HANN_POW = HANN.reduce((s, v) => s + v * v, 0);
const COS = new Float64Array(NBIN * NSEG);
const SIN = new Float64Array(NBIN * NSEG);
for (let k = 0; k < NBIN; k++) {
  for (let n = 0; n < NSEG; n++) {
    COS[k * NSEG + n] = Math.cos((2 * Math.PI * k * n) / NSEG);
    SIN[k * NSEG + n] = Math.sin((2 * Math.PI * k * n) / NSEG);
  }
}

export function welchPsd(x) {
  const acc = new Float64Array(NBIN);
  const seg = new Float64Array(NSEG);
  let count = 0;
  for (let s = 0; s + NSEG <= x.length; s += NSEG - NOVERLAP) {
    let mean = 0;
    for (let n = 0; n < NSEG; n++) mean += x[s + n];
    mean /= NSEG;
    for (let n = 0; n < NSEG; n++) seg[n] = (x[s + n] - mean) * HANN[n];
    for (let k = 0; k < NBIN; k++) {
      let re = 0, im = 0;
      const o = k * NSEG;
      for (let n = 0; n < NSEG; n++) {
        re += seg[n] * COS[o + n];
        im -= seg[n] * SIN[o + n];
      }
      let p = (re * re + im * im) / (FS * HANN_POW);
      if (k > 0 && k < NBIN - 1) p *= 2;
      acc[k] += p;
    }
    count++;
  }
  for (let k = 0; k < NBIN; k++) acc[k] /= count;
  return acc;
}

// xyz: array of [x, y, z] rows
export function psdTrace(xyz) {
  const out = new Float64Array(NBIN);
  for (let a = 0; a < 3; a++) {
    const p = welchPsd(xyz.map((r) => r[a]));
    for (let k = 0; k < NBIN; k++) out[k] += p[k];
  }
  return out;
}

const inBand = (f, [lo, hi]) => f >= lo && f < hi;

export function bandPower(p, band) {
  let s = 0;
  for (let k = 0; k < NBIN; k++) if (inBand(FREQS[k], band)) s += p[k];
  return s * DF;
}

export function peakIn(p, band) {
  let best = -1;
  for (let k = 0; k < NBIN; k++) if (inBand(FREQS[k], band) && (best < 0 || p[k] > p[best])) best = k;
  let delta = 0;
  if (best > 0 && best < NBIN - 1) {
    const a = Math.log(p[best - 1] + EPS), b = Math.log(p[best] + EPS), c = Math.log(p[best + 1] + EPS);
    const den = a - 2 * b + c;
    delta = Math.abs(den) > 1e-12 ? (0.5 * (a - c)) / den : 0;
    delta = Math.max(-0.5, Math.min(0.5, delta));
  }
  return { f: (best + delta) * DF, power: p[best], index: best };
}

function median(v) {
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}

function spectralEntropy(p, band) {
  const q = [];
  for (let k = 0; k < NBIN; k++) if (inBand(FREQS[k], band)) q.push(p[k]);
  const tot = q.reduce((s, v) => s + v, 0) + EPS;
  let h = 0;
  for (const v of q) {
    const r = v / tot;
    h -= r * Math.log(r + EPS);
  }
  return h / Math.log(q.length);
}

// acc: WIN rows of [x,y,z] m/s^2 (gravity removed); gyro: WIN rows deg/s
export function features(acc, gyro) {
  const pa = psdTrace(acc);
  const pg = psdTrace(gyro);
  const pLow = bandPower(pa, BAND_LOW);
  const pPd = bandPower(pa, BAND_PD);
  const pEt = bandPower(pa, BAND_ET);
  const pTr = bandPower(pa, BAND_TREMOR);
  const pAll = bandPower(pa, BAND_ALL);

  const pk = peakIn(pa, BAND_TREMOR);
  const trem = [];
  for (let k = 0; k < NBIN; k++) if (inBand(FREQS[k], BAND_TREMOR)) trem.push(pa[k]);
  const prominence = pk.power / (median(trem) + EPS);
  const ent = spectralEntropy(pa, BAND_ALL);
  const harm = bandPower(pa, [2 * pk.f - 0.6, 2 * pk.f + 0.6]) / (bandPower(pa, [pk.f - 0.6, pk.f + 0.6]) + EPS);

  const accAmp = Math.sqrt(2 * pTr);
  const dispP2pCm = ((2 * accAmp) / (2 * Math.PI * pk.f) ** 2) * 100;

  const gaitRatio = bandPower(pa, BAND_GAIT) / (pLow + EPS);
  const fLow = peakIn(pa, BAND_LOW).f;
  const gTr = bandPower(pg, BAND_TREMOR);
  const gLow = bandPower(pg, BAND_LOW);
  const gF = peakIn(pg, BAND_TREMOR).f;

  const mag = acc.map((r) => Math.hypot(r[0], r[1], r[2]));
  const mMean = mag.reduce((s, v) => s + v, 0) / mag.length;
  const mStd = Math.sqrt(mag.reduce((s, v) => s + (v - mMean) ** 2, 0) / mag.length);
  let j2 = 0;
  for (let i = 1; i < acc.length; i++) {
    for (let a = 0; a < 3; a++) j2 += ((acc[i][a] - acc[i - 1][a]) * FS) ** 2;
  }
  const jerkRms = Math.sqrt(j2 / (acc.length - 1));

  return {
    vector: [
      Math.log(pLow + EPS), Math.log(pPd + EPS), Math.log(pEt + EPS), Math.log(pTr + EPS),
      pk.f, Math.log(pk.power + EPS), Math.log(prominence + EPS), ent,
      pTr / (pAll + EPS), harm, Math.log(dispP2pCm + 1e-4), gaitRatio,
      fLow, Math.log(gTr + EPS), Math.log(gLow + EPS), gF,
      Math.log(mStd + EPS), Math.log(jerkRms + EPS), Math.log((pTr + EPS) / (pLow + EPS)),
    ],
    peakHz: pk.f,
    dispP2pCm,
  };
}
