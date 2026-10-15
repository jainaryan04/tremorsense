// Per-decision latency of the full on-device pipeline (features + 3 heads +
// gate) and per-sample cost of the phase tracker. Writes into docs/results.json.
//   node web/test/bench.mjs
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { features } from "../js/dsp.js";
import { Model } from "../js/model.js";
import { gate } from "../js/conformal.js";
import { PhaseTracker, CueScheduler } from "../js/phase.js";
import { Simulator } from "../js/simulator.js";

const model = new Model(JSON.parse(readFileSync(new URL("../model/model.json", import.meta.url))));
const sim = new Simulator();
sim.set({ grade: 3 });
const buf = Array.from({ length: 200 }, () => sim.next());
const acc = buf.map((s) => s.acc), gyro = buf.map((s) => s.gyro);

for (let i = 0; i < 50; i++) features(acc, gyro); // warm up
const times = [];
for (let i = 0; i < 500; i++) {
  const t0 = performance.now();
  const f = features(acc, gyro);
  const p = model.predict(f.vector, false);
  gate(p.activity, p.severity, model.conformal);
  times.push(performance.now() - t0);
}
times.sort((a, b) => a - b);
const trk = new PhaseTracker(5), sch = new CueScheduler();
const t1 = performance.now();
for (let i = 0; i < 50000; i++) { const r = trk.step(acc[i % 200]); sch.step(r.phase, r.freq); }
const perSampleUs = ((performance.now() - t1) / 50000) * 1000;

const out = {
  runtime: `Node ${process.version} (V8, the engine in Chrome for Android), measured on a server CPU; expect a phone to be several times slower`,
  decision_ms_median: +times[250].toFixed(3),
  decision_ms_p99: +times[495].toFixed(3),
  phase_tracker_us_per_sample: +perSampleUs.toFixed(2),
  window_s: 4, decisions_per_s: 1,
  end_to_end_decision_latency_note: "A decision uses the last 4 s of signal; compute adds the time above.",
};
console.log(out);
const path = new URL("../../docs/results.json", import.meta.url);
const res = existsSync(path) ? JSON.parse(readFileSync(path)) : {};
res.latency = out;
writeFileSync(path, JSON.stringify(res, null, 1));
