// Arduino (USB) path: line parsing, count conversion, and the GY-61 model
// driving cues from simulated Uno data.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseLine, CountsToAcc, MS2_PER_COUNT } from "../js/serial.js";
import { Model } from "../js/model.js";
import { Engine } from "../js/engine.js";
import { Simulator } from "../js/simulator.js";

const gy61 = new Model(JSON.parse(readFileSync(new URL("../model/model_gy61.json", import.meta.url))));

test("parses Uno lines", () => {
  assert.deepEqual(parseLine("A,338,341,405\r"), { kind: "acc", counts: [338, 341, 405] });
  assert.deepEqual(parseLine("G,3,531,412,0,3"), { kind: "uno", grade: 3, freqHz: 5.31, dispCm: 4.12, moving: false, cue: 3 });
  assert.equal(parseLine("H,TremorSense-Uno,1").kind, "hello");
  assert.equal(parseLine("garbage"), null);
  assert.equal(parseLine("A,1,2"), null);
});

test("counts become gravity-free m/s^2", () => {
  const c = new CountsToAcc();
  let a;
  for (let i = 0; i < 500; i++) {
    const s = 20 * Math.sin((2 * Math.PI * 5 * i) / 50);
    a = c.step([338 + s, 338, 405]);
  }
  // Gravity (the constant part) is gone; the 5 Hz part keeps its size.
  assert.ok(Math.abs(a[1]) < 0.05 && Math.abs(a[2]) < 0.05, `residual ${a}`);
  let peak = 0;
  for (let i = 0; i < 50; i++) peak = Math.max(peak, Math.abs(c.step([338 + 20 * Math.sin((2 * Math.PI * 5 * i) / 50), 338, 405])[0]));
  assert.ok(Math.abs(peak - 20 * MS2_PER_COUNT) < 0.1 * 20 * MS2_PER_COUNT, `peak ${peak}`);
});

// Simulated hand -> what the Uno would send -> app pipeline.
function runUno(grade, activity, seconds) {
  const sim = new Simulator();
  sim.set({ grade, activity });
  const conv = new CountsToAcc();
  const cues = [];
  const decisions = [];
  const eng = new Engine(gy61, { onDecision: (d) => decisions.push(d), onCue: (i) => cues.push(i) });
  eng.cueEnabled = true;
  for (let i = 0; i < seconds * 50; i++) {
    const { acc } = sim.next();
    const counts = acc.map((v, k) => Math.round((v + (k === 2 ? 9.81 : 0)) / MS2_PER_COUNT + 338));
    eng.push({ acc: conv.step(counts), gyro: [0, 0, 0] });
  }
  return { cues, decisions: decisions.slice(10) };
}

test("GY-61 model cues a still grade-3 tremor at grade 3 or below", () => {
  const { cues, decisions } = runUno(3, "still", 40);
  assert.ok(cues.length > 50, `only ${cues.length} cues`);
  assert.ok(cues.every((i) => i <= 3), "cue stronger than the true grade");
  const right = decisions.filter((d) => d.grade === 3).length / decisions.length;
  assert.ok(right > 0.7, `grade 3 in ${right} of decisions`);
});

test("GY-61 model gives no cues while walking", () => {
  const { cues } = runUno(3, "gait", 40);
  assert.ok(cues.length < 10, `${cues.length} cues while walking`);
});
