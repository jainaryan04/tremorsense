// The 12 demo test cases, run through the app's pipeline with the GY-61
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

test("cases match the Arduino demo", () => {
  const h = readFileSync(new URL("../../hardware/tremorsense_demo/demo_cases.h", import.meta.url), "utf8");
  const rows = [...h.matchAll(/^\s*\{\{(\{[^}]*\}(?:, \{[^}]*\})?)\}/gm)].map((m) =>
    [...m[1].matchAll(/\{([^}]*)\}/g)].map((s) => s[1].split(",").map((v) => parseFloat(v))));
  assert.equal(rows.length, CASES.length);
  rows.forEach((segs, i) => assert.deepEqual(segs, CASES[i].seg, `case ${i + 1}`));
});
