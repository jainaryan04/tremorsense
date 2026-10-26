// The demo test cases, run through the app's pipeline with the GY-61
// model: every case must pass, so the review demo can't fail on stage.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Model } from "../js/model.js";
import { Engine } from "../js/engine.js";
import { CASES, caseSamples, Checker } from "../js/testcases.js";

const gy61 = new Model(JSON.parse(readFileSync(new URL("../model/model_gy61.json", import.meta.url))));

for (const [i, c] of CASES.entries()) {
  test(`case ${i + 1}: ${c.name}`, () => {
    let gen;
    const chk = new Checker(c, 0.05);
    const eng = new Engine(gy61, { onDecision: (d) => chk.decision(d), onCue: () => chk.pulse(gen.phase, gen.hz) });
    eng.cueEnabled = true;
    eng.latencyS = 0.05;
    eng.reset();
    for (const s of caseSamples(c)) {
      gen = s.gen;
      eng.push(s.sample);
    }
    const d = chk.last;
    assert.equal(chk.failure(), null, `grade ${d.grade} set ${d.severitySet} ${d.activity} cue ${d.cueIntensity} pulses ${chk.pulses} lock ${chk.phaseLock.toFixed(2)}`);
  });
}

test("at least 4 cases cue, at every strength", () => {
  const cued = CASES.filter((c) => c.rule !== "never");
  assert.ok(cued.length >= 4, `${cued.length} cases cue`);
  assert.deepEqual([...new Set(cued.filter((c) => c.rule === "end").map((c) => c.cue))].sort(), [2, 3, 4]);
});
