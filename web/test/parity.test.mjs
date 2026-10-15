// Checks the browser modules against outputs of the Python reference.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { features } from "../js/dsp.js";
import { Model } from "../js/model.js";
import { gate } from "../js/conformal.js";
import { PhaseTracker, CueScheduler } from "../js/phase.js";
import { severity, grid, wearingOffTime, fit } from "../js/medcurve.js";

const fx = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url)));
const model = new Model(JSON.parse(readFileSync(new URL("../model/model.json", import.meta.url))));

const close = (a, b, tol, msg) => {
  assert.equal(a.length, b.length, msg);
  a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) <= tol * (1 + Math.abs(b[i])), `${msg}[${i}]: ${v} vs ${b[i]}`));
};

test("features match Python", () => {
  fx.windows.forEach((w, i) => close(features(w.acc, w.gyro).vector, w.features, 1e-6, `window ${i}`));
});

test("model probabilities and gate match Python", () => {
  fx.windows.forEach((w, i) => {
    const p = model.predict(w.features, w.placement_watch);
    close(p.activity, w.activity, 1e-5, `activity ${i}`);
    close(p.severity, w.severity, 1e-5, `severity ${i}`);
    close(p.type, w.type, 1e-5, `type ${i}`);
    const g = gate(p.activity, p.severity, model.conformal);
    assert.equal(g.intensity, w.intensity, `intensity ${i}`);
    assert.deepEqual(g.severitySet, w.severity_set);
    assert.deepEqual(g.activitySet, w.activity_set);
  });
});

test("phase tracker and cue timing match Python", () => {
  const trk = new PhaseTracker(5.0);
  const sch = new CueScheduler(0, 0.04);
  trk.setAnchor(fx.phase.anchor);
  const phases = [], fires = [];
  fx.phase.acc.forEach((a, i) => {
    const { phase, freq } = trk.step(a);
    phases.push(phase);
    if (sch.step(phase, freq)) fires.push(i);
  });
  close(phases, fx.phase.phases, 1e-6, "phase");
  assert.deepEqual(fires, fx.phase.fires);
});

test("medication response curve matches Python", () => {
  const m = fx.medcurve;
  const t = grid(m.t0, m.t0 + (m.severity.length - 1) / 60);
  close(severity(t, m.doses, m.params), m.severity, 1e-6, "severity");
  const wo = wearingOffTime(15.1, m.doses, m.params);
  assert.ok(Math.abs(wo - m.wearing_off) < 2 / 60, `wearing off ${wo} vs ${m.wearing_off}`);
});

test("fit recovers the response curve from noisy observations", () => {
  const m = fx.medcurve;
  const t = grid(6, 30);
  const doses = [7, 11, 15, 19, 31];
  const truth = severity(t, doses, m.params);
  let seed = 1;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const obs = [];
  t.forEach((ti, i) => { if (rand() < 0.5) obs.push({ t: ti, s: truth[i] + (rand() - 0.5) * 0.8 }); });
  const p = fit(obs, doses.filter((d) => d < 30));
  const est = severity(t, doses, p);
  const mean = (v) => v.reduce((a, b) => a + b, 0) / v.length;
  const ma = mean(est), mb = mean(truth);
  let sab = 0, saa = 0, sbb = 0;
  est.forEach((v, i) => { sab += (v - ma) * (truth[i] - mb); saa += (v - ma) ** 2; sbb += (truth[i] - mb) ** 2; });
  assert.ok(sab / Math.sqrt(saa * sbb) > 0.95);
});
