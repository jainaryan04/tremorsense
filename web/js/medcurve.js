// Port of ml/tremorsense/medcurve.py. Fitting uses bounded Nelder-Mead with
// the same soft-L1 loss as SciPy's least_squares(loss="soft_l1").

export const KE = Math.log(2) / 1.5;
const GAMMA = 3;
export const DT_H = 1 / 60;
const LOWER = [0.3, 0.1, 0.2, 0.05, 0.5];
const UPPER = [6.0, 4.0, 4.0, 2.0, 4.5];
export const INIT = [1.5, 0.8, 1.8, 0.5, 2.8];

export function plasma(t, doses, ka) {
  const k = Math.abs(ka - KE) > 1e-6 ? ka / (ka - KE) : 1;
  return t.map((ti) => {
    let c = 0;
    for (const td of doses) {
      const d = ti - td;
      if (d > 0) c += k * (Math.exp(-KE * d) - Math.exp(-ka * d));
    }
    return c;
  });
}

export function effectSite(c, ke0) {
  const ce = new Array(c.length).fill(0);
  const a = 1 - Math.exp(-ke0 * DT_H);
  for (let i = 1; i < c.length; i++) ce[i] = ce[i - 1] + a * (c[i - 1] - ce[i - 1]);
  return ce;
}

export function severity(t, doses, [ka, ke0, emax, ec50, s0]) {
  const ce = effectSite(plasma(t, doses, ka), ke0);
  return ce.map((v) => {
    const g = Math.max(v, 0) ** GAMMA;
    return s0 - (emax * g) / (ec50 ** GAMMA + g);
  });
}

export function grid(t0, t1) {
  const n = Math.floor((t1 - t0) / DT_H) + 1;
  return Array.from({ length: n }, (_, i) => t0 + i * DT_H);
}

const toUnit = (p) => p.map((v, i) => (v - LOWER[i]) / (UPPER[i] - LOWER[i]));
const fromUnit = (u) => u.map((v, i) => LOWER[i] + Math.min(1, Math.max(0, v)) * (UPPER[i] - LOWER[i]));

function nelderMead(f, x0, { iters = 600, step = 0.1 } = {}) {
  const n = x0.length;
  let pts = [x0, ...x0.map((_, i) => x0.map((v, j) => (j === i ? v + step : v)))];
  let vals = pts.map(f);
  for (let it = 0; it < iters; it++) {
    const order = vals.map((v, i) => i).sort((a, b) => vals[a] - vals[b]);
    pts = order.map((i) => pts[i]);
    vals = order.map((i) => vals[i]);
    const c = Array(n).fill(0);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) c[j] += pts[i][j] / n;
    const lerp = (a, b, t) => a.map((v, j) => v + t * (b[j] - v));
    const xr = lerp(c, pts[n], -1);
    const fr = f(xr);
    if (fr < vals[0]) {
      const xe = lerp(c, pts[n], -2);
      const fe = f(xe);
      [pts[n], vals[n]] = fe < fr ? [xe, fe] : [xr, fr];
    } else if (fr < vals[n - 1]) {
      [pts[n], vals[n]] = [xr, fr];
    } else {
      const xc = lerp(c, pts[n], 0.5);
      const fc = f(xc);
      if (fc < vals[n]) [pts[n], vals[n]] = [xc, fc];
      else {
        for (let i = 1; i <= n; i++) {
          pts[i] = lerp(pts[0], pts[i], 0.5);
          vals[i] = f(pts[i]);
        }
      }
    }
    if (Math.abs(vals[n] - vals[0]) < 1e-9) break;
  }
  return { x: pts[0], fx: vals[0] };
}

// obs: [{t (hours), s (severity)}], doses: [hours]
export function fit(obs, doses) {
  if (obs.length < 30 || !doses.length) return null;
  const t0 = Math.min(obs[0].t, ...doses) - DT_H;
  const t = grid(t0, obs[obs.length - 1].t);
  const idx = obs.map((o) => Math.min(t.length - 1, Math.max(0, Math.round((o.t - t0) / DT_H))));
  const loss = (u) => {
    const s = severity(t, doses, fromUnit(u));
    let l = 0;
    for (let i = 0; i < obs.length; i++) {
      const r = s[idx[i]] - obs[i].s;
      l += 2 * (Math.sqrt(1 + r * r) - 1);
    }
    // keep the simplex inside the box
    return l + u.reduce((a, v) => a + (v < 0 ? -v : v > 1 ? v - 1 : 0) * 1e3, 0);
  };
  let best = null;
  for (const scale of [1.0, 0.6, 1.6]) {
    const start = toUnit(INIT.map((v, i) => Math.min(UPPER[i], Math.max(LOWER[i], v * scale))));
    const r = nelderMead(loss, start);
    if (!best || r.fx < best.fx) best = r;
  }
  return fromUnit(best.x);
}

export function wearingOffTime(tFrom, doses, params, horizon = 8, frac = 0.5) {
  const tAll = grid(Math.min(...doses) - DT_H, tFrom + horizon);
  const sAll = severity(tAll, doses, params);
  const start = tAll.findIndex((v) => v >= tFrom);
  const t = tAll.slice(start), s = sAll.slice(start);
  let iMin = 0;
  for (let i = 1; i < s.length; i++) if (s[i] < s[iMin]) iMin = i;
  const thr = s[iMin] + frac * (params[4] - s[iMin]);
  for (let i = iMin; i < s.length; i++) if (s[i] >= thr) return t[i];
  return null;
}
