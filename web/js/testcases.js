// The 12 test cases from the Arduino demo (hardware/tremorsense_demo), run by
// the app. Each case makes a synthetic GY-61 signal of known frequency and
// size, in the ADC counts the Uno would send, so it goes through exactly the
// same path as live Arduino data: counts -> m/s^2 -> features -> model ->
// conformal safety gate -> phase-locked cues.
import { FS } from "./dsp.js";
import { CountsToAcc } from "./serial.js";

const TAU = 2 * Math.PI;

// seg: [seconds, Hz, peak-to-peak cm, walking, arm movement, tilt]
// rule: "never" = no cue at any time, "end" = cueing at the end at strength
// `cue`, "onoff" = cued during the case and off by the end.
export const CASES = [
  {
    name: "Hand at rest", seg: [[14, 5, 0, 0, 0, 0]], grade: 0, still: true, rule: "never",
    input: "Hand still, no tremor (sensor noise only)",
    expect: "No tremor, no cue",
    say: "Test 1: a still hand with only sensor noise. It must not report tremor or vibrate. It shows grade 0 and no cue.",
  },
  {
    name: "Slight tremor", seg: [[14, 5, 0.5, 0, 0, 0]], grade: 1, still: true, rule: "never", hz: 5,
    input: "5 Hz tremor, 0.5 cm peak-to-peak, hand still",
    expect: "Grade 1: logged, no cue (cues start at grade 2)",
    say: "Test 2: a slight tremor, 5 Hz and half a centimetre. It is graded 1 and logged, but not cued, because we only cue from grade 2, so the patient isn't buzzed for tremor that doesn't bother them.",
  },
  {
    name: "Mild tremor", seg: [[14, 5, 2, 0, 0, 0]], grade: 2, still: true, rule: "end", cue: 2, hz: 5,
    input: "5 Hz tremor, 2 cm, hand still",
    expect: "Grade 2, cue 2, pulses locked to the tremor",
    say: "Test 3: a 2 cm tremor. It grades 2 and the motor starts pulsing at the gentlest level. The pulses are locked to the tremor: the phase-lock value near 1 means every pulse lands at the same point of the cycle.",
  },
  {
    name: "Moderate tremor", seg: [[14, 5, 5, 0, 0, 0]], grade: 3, still: true, rule: "end", cue: 3, hz: 5,
    input: "5 Hz tremor, 5 cm, hand still",
    expect: "Grade 3, cue 3, pulses locked",
    say: "Test 4: 5 cm, grade 3, and the cue gets stronger. The grade comes from physics: acceleration divided by (2πf)² gives displacement in centimetres, which maps onto the clinical UPDRS bands. The model also gives a set of possible grades, and the cue uses the lowest one, so it never over-stimulates.",
  },
  {
    name: "Severe tremor", seg: [[14, 3.5, 12, 0, 0, 0]], grade: [3, 4], still: true, rule: "end", cue: "low", hz: 3.5,
    input: "3.5 Hz tremor, 12 cm, hand still",
    expect: "Grade 3 or 4 with possible grades 3–4; the cue uses the lower end, 3",
    say: "Test 5: a severe, slow tremor, 12 cm at 3.5 Hz, right at the border of grades 3 and 4. The model isn't sure, so it reports possible grades 3 to 4, and the safety gate cues at the lower end, grade 3. That is our dual conformal gate: when unsure, it never over-stimulates. Each pulse also lasts at most a third of a cycle.",
  },
  {
    name: "8 Hz tremor", seg: [[14, 8, 2, 0, 0, 0]], grade: 2, still: true, rule: "end", cue: 2, hz: 8,
    input: "8 Hz tremor (essential tremor range), 2 cm, hand still",
    expect: "Grade 2 at 8 Hz, cue 2, pulses follow the new frequency",
    say: "Test 6: an 8 Hz tremor, the range of essential tremor. The app tracks the new frequency, recognises the tremor type, and the pulses follow it.",
  },
  {
    name: "Walking", seg: [[14, 5, 2, 4, 0, 0]], still: false, rule: "never",
    input: "5 Hz tremor, 2 cm, while walking",
    expect: "Hand moving: cues paused, no cue at all",
    say: "Test 7: the same tremor while walking. The activity model sees the hand moving and the safety gate blocks every cue. Vibrating while someone walks could startle them or upset their balance.",
  },
  {
    name: "Using the arm", seg: [[14, 5, 2, 0, 5, 0]], still: false, rule: "never",
    input: "5 Hz tremor, 2 cm, while moving the arm",
    expect: "Hand moving: cues paused, no cue at all",
    say: "Test 8: the arm is being used, for example reaching for a cup. Again no cue: we only help when the hand is at rest, which is where Parkinson's rest tremor appears.",
  },
  {
    name: "Hand tilting", seg: [[14, 5, 5, 0, 0, 0.5]], grade: 3, still: true, rule: "end", cue: 3, hz: 5,
    input: "5 Hz tremor, 5 cm, hand slowly tilting",
    expect: "Grade 3, cue 3: tilting is not mistaken for movement",
    say: "Test 9: the hand slowly tilts while the tremor continues. Tilting turns gravity on each axis, which a simple device would take for movement. Ours still sees a resting hand and keeps cueing.",
  },
  {
    name: "Short burst", seg: [[2, 5, 5, 0, 0, 0], [12, 5, 0, 0, 0, 0]], grade: 0, still: true, rule: "never",
    input: "5 Hz tremor, 5 cm, for only 2 s, then rest",
    expect: "No cue: 2 of the last 3 decisions must agree",
    say: "Test 10: a tremor lasting only 2 seconds. A cue needs two of the last three decisions to agree and the grade set to be confident, so a brief twitch never triggers the motor.",
  },
  {
    name: "Tremor stops", seg: [[12, 5, 5, 0, 0, 0], [8, 5, 0, 0, 0, 0]], grade: 0, still: true, rule: "onoff",
    input: "5 Hz tremor, 5 cm for 12 s, then it stops",
    expect: "Cue 3 during the tremor, off a few seconds after it stops",
    say: "Test 11: the tremor stops after 12 seconds. The cue switches off within a few seconds, so the device doesn't keep stimulating once it isn't needed.",
  },
  {
    name: "Walking starts", seg: [[12, 5, 2, 0, 0, 0], [8, 5, 2, 4, 0, 0]], still: false, rule: "onoff",
    input: "5 Hz tremor, 2 cm; walking starts after 12 s",
    expect: "Cue 2 while still, then hand moving: cues paused",
    say: "Test 12: the patient starts walking during a tremor. The cue pauses as soon as walking is detected.",
  },
];

export const caseSeconds = (c) => c.seg.reduce((s, g) => s + g[0], 0);

// Synthetic GY-61 output in ADC counts (same signal as the Arduino demo).
export class Generator {
  constructor(c) {
    this.c = c;
    this.t = 0;
    this.phase = 0;
    this.seed = 12345;
  }

  get done() {
    return this.t >= caseSeconds(this.c) - 0.5 / FS;
  }

  segment() {
    let end = 0;
    for (const g of this.c.seg) {
      end += g[0];
      if (this.t < end) return g;
    }
    return this.c.seg[this.c.seg.length - 1];
  }

  get hz() {
    return this.segment()[1];
  }

  noise() {
    this.seed = (Math.imul(this.seed, 1664525) + 1013904223) >>> 0;
    const u1 = (this.seed >>> 8) / 16777216;
    this.seed = (Math.imul(this.seed, 1664525) + 1013904223) >>> 0;
    const u2 = (this.seed >>> 8) / 16777216;
    return u1 + u2 - 1;
  }

  counts() {
    const [, hz, p2p, walk, vol, tiltK] = this.segment();
    const t = this.t;
    this.phase = (this.phase + (TAU * hz) / FS) % TAU;
    const amp = (p2p / 200) * (TAU * hz) ** 2;
    const trem = amp * Math.sin(this.phase);
    const w = walk * (Math.sin(TAU * 1.8 * t) + 0.4 * Math.sin(TAU * 3.6 * t + 0.7));
    const v = vol * (Math.sin(TAU * 0.7 * t) + 0.5 * Math.sin(TAU * 1.3 * t + 1));
    const tilt = tiltK * (0.25 * Math.sin(TAU * 0.5 * t) + 0.15 * Math.sin(TAU * 0.9 * t));
    const g = [9.81 * Math.sin(tilt), 0, 9.81 * Math.cos(tilt)];
    const dir = [0.6, 0.3, 0.74], vdir = [0.5, 0.6, 0.62];
    const out = [0, 1, 2].map((i) => {
      const a = g[i] + dir[i] * trem + (i === 0 ? w : i === 2 ? 0.5 * w : 0) + vdir[i] * v;
      const gs = Math.max(-3.6, Math.min(3.6, a / 9.81));
      const c = Math.round(((1.65 + 0.33 * gs) / 5) * 1023 + this.noise());
      return Math.max(0, Math.min(1023, c));
    });
    this.t += 1 / FS;
    return out;
  }
}

// Collects what the app did during a case and decides pass or fail.
export class Checker {
  constructor(c, latencyS) {
    this.c = c;
    this.latencyS = latencyS;
    this.last = null;
    this.cueSeen = false;
    this.pulses = 0;
    this.C = 0;
    this.S = 0;
  }

  decision(d) {
    this.last = d;
    if (d.cueIntensity) this.cueSeen = true;
  }

  // Phase of the tremor that the pulse aims at (one latency after it starts).
  pulse(phase, hz) {
    const ph = phase + TAU * hz * this.latencyS;
    this.C += Math.cos(ph);
    this.S += Math.sin(ph);
    this.pulses++;
  }

  get phaseLock() {
    return this.pulses ? Math.hypot(this.C, this.S) / this.pulses : 0;
  }

  // Why it failed, or null when it passed.
  failure() {
    const c = this.c, d = this.last;
    if (!d) return "no decision";
    if (d.still !== c.still) return c.still ? "false movement" : "movement missed";
    const grades = [].concat(c.grade ?? []);
    if (c.still && grades.length && !grades.includes(d.grade)) return "wrong grade";
    if (c.hz && Math.abs(d.peakHz - c.hz) > 0.3) return "wrong frequency";
    if (c.rule === "never" && (this.pulses || this.cueSeen)) return "cued, should not";
    if (c.rule === "end") {
      // "low": the cue must be the lowest grade the model can't rule out.
      if (d.cueIntensity !== (c.cue === "low" ? Math.max(2, d.severitySet[0]) : c.cue)) return "wrong cue";
      if (this.phaseLock < 0.8) return "not phase locked";
    }
    if (c.rule === "onoff") {
      if (!this.cueSeen || !this.pulses) return "never cued";
      if (d.cueIntensity) return "cue did not stop";
    }
    return null;
  }
}

// One case's samples, as the app's engine takes them, with the generator
// (for the tremor phase at each pulse).
export function* caseSamples(c) {
  const gen = new Generator(c);
  const conv = new CountsToAcc();
  while (!gen.done) {
    const counts = gen.counts();
    yield { sample: { acc: conv.step(counts), gyro: [0, 0, 0] }, gen };
  }
}
