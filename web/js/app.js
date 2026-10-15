import { Model } from "./model.js";
import { Engine, FS } from "./engine.js";
import { MotionSource, motionSupported, requestMotionPermission } from "./sensor.js";
import { Simulator } from "./simulator.js";
import { cue, canVibrate, confirmPulse } from "./haptics.js";
import { Store } from "./store.js";
import { drawTrace, drawChart } from "./charts.js";
import * as med from "./medcurve.js";

const $ = (id) => document.getElementById(id);
const store = new Store();
const sim = new Simulator();
let model, engine, motion, timer = null, source = "demo", running = false;
const trace = [], marks = [];
const TRACE_N = 2 * FS;
const ACT_LABEL = { still: "Still", voluntary: "Using hand", gait: "Walking", vehicle: "In a vehicle" };
const REASON = {
  not_still: "Cues paused: hand is moving",
  uncertain: "Cues paused: grade too uncertain",
  below_threshold: "No cue needed",
};

function segment(attr, onPick) {
  document.querySelectorAll(`[data-${attr}]`).forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(`[data-${attr}]`).forEach((o) => {
        o.classList.toggle("on", o === b);
        o.setAttribute("aria-checked", String(o === b));
      });
      onPick(b.dataset[attr]);
    });
  });
}

function showDecision(d) {
  $("grade").textContent = d.still ? d.grade : "–";
  const set = d.severitySet;
  $("grade-set").textContent = d.still
    ? `Possible grades ${set.length > 1 ? `${set[0]}–${set[set.length - 1]}` : set[0]} (99% coverage)`
    : "Grading paused while you move";
  $("activity").textContent = ACT_LABEL[d.activity] + (d.activityCertain ? "" : "?");
  $("ttype").textContent = d.type ? `${d.type === "parkinsonian" ? "Parkinsonian" : "Essential"} (${Math.round(d.typeP * 100)}%)` : "None";
  $("freq").textContent = d.grade > 0 ? `${d.peakHz.toFixed(1)} Hz` : "–";
  $("amp").textContent = d.grade > 0 ? `~${d.dispCm < 1 ? d.dispCm.toFixed(2) : d.dispCm.toFixed(1)} cm` : "–";
  const cs = $("cue-state");
  if (!$("haptics").checked) {
    cs.className = "cue-state";
    cs.textContent = "Cues off";
  } else if (d.cueIntensity > 0) {
    cs.className = "cue-state on";
    cs.textContent = `Cueing at grade ${d.cueIntensity} strength, locked to ${d.peakHz.toFixed(1)} Hz`;
  } else {
    cs.className = d.gateReason === "below_threshold" || d.gateReason === "ok" ? "cue-state" : "cue-state paused";
    cs.textContent = d.gateReason === "ok" ? "Confirming before cueing" : REASON[d.gateReason];
  }
  if (d.still) store.addDecision(d.expected);
  calibrator.record(d);
}

function onSample(s) {
  trace.push(s.signal);
  if (trace.length > TRACE_N) {
    trace.shift();
    for (let i = 0; i < marks.length; i++) marks[i]--;
    while (marks.length && marks[0] < 0) marks.shift();
  }
  if (s.fire && $("haptics").checked) marks.push(trace.length - 1);
}

function flash() {
  const f = $("flash");
  f.classList.add("on");
  setTimeout(() => f.classList.remove("on"), 70);
}

function render() {
  if (!running) return;
  drawTrace($("trace"), trace, marks);
  requestAnimationFrame(render);
}

// Tries 8 cue phases and keeps the one with the lowest tremor power.
const calibrator = {
  active: false, i: 0, scores: [], acc: [],
  start() {
    if (!running) return alert("Start monitoring first.");
    this.active = true; this.i = 0; this.scores = []; this.acc = [];
    engine.setTarget(0);
    $("calibrate").disabled = true;
    this.note();
  },
  note() {
    $("cal-note").textContent = `Trying phase ${this.i * 45}° (${this.i + 1} of 8)…`;
  },
  record(d) {
    if (!this.active) return;
    if (d.still) this.acc.push(d.logTremor);
    if (this.acc.length >= 6) {
      this.scores.push(this.acc.reduce((a, b) => a + b, 0) / this.acc.length);
      this.acc = [];
      this.i++;
      if (this.i === 8) return this.finish();
      engine.setTarget((this.i * Math.PI) / 4);
      this.note();
    }
  },
  finish() {
    this.active = false;
    const best = this.scores.indexOf(Math.min(...this.scores));
    setTarget(best * 45);
    $("calibrate").disabled = false;
    $("cal-note").textContent = source === "demo"
      ? `Picked ${best * 45}°. The demo hand doesn't respond to cues, so on a real patient this choice would differ.`
      : `Picked ${best * 45}°, where your tremor was lowest.`;
  },
};

function setTarget(deg) {
  $("target").value = deg;
  $("target-out").textContent = `${deg}°`;
  engine.setTarget((deg * Math.PI) / 180);
  store.setSetting("target", deg);
}

async function start() {
  if (source === "sensors") {
    if (!motionSupported()) return note("This browser doesn't expose motion sensors. Try Chrome on Android or Safari on iPhone.");
    if (!(await requestMotionPermission())) return note("Motion access was declined. Allow it in the browser settings to use the sensors.");
    motion = new MotionSource((s) => engine.push(s));
    motion.start();
    note("Rest your hand with the phone held (or the watch on). Readings start after 4 seconds.");
    setTimeout(() => { if (running && motion && !motion.rawRate) note("No motion data yet. Sensors need HTTPS and a phone or watch, not a laptop."); }, 3000);
  } else {
    timer = setInterval(() => { for (let i = 0; i < 5; i++) engine.push(sim.next()); }, 100);
  }
  running = true;
  $("start").textContent = "Stop";
  $("start").classList.add("stop");
  $("status-pill").textContent = source === "demo" ? "Demo running" : "Monitoring";
  $("status-pill").classList.add("live");
  requestAnimationFrame(render);
}

function stop() {
  running = false;
  if (timer) clearInterval(timer);
  timer = null;
  if (motion) motion.stop();
  motion = null;
  store.flush();
  engine.reset();
  $("start").textContent = "Start monitoring";
  $("start").classList.remove("stop");
  $("status-pill").textContent = "Stopped";
  $("status-pill").classList.remove("live");
  updateMed();
}

function note(text) {
  const n = $("sensor-note");
  n.hidden = !text;
  n.textContent = text || "";
}

// ---- medication response ----
let fitCache = { key: "", params: null };

function updateMed() {
  const doses = store.d.doses, mins = store.d.minutes;
  const canvas = $("medchart");
  const now = Date.now();
  const tEnd = Math.max(now, mins.length ? mins[mins.length - 1].t : 0);
  const H = (t) => (t - tEnd) / 3600000; // hours relative to the latest data
  const x0 = -24, x1 = 6;
  const pts = mins.filter((m) => H(m.t) >= x0).map((m) => [H(m.t), m.s]);
  const series = [{ points: pts, color: getComputedStyle(document.documentElement).getPropertyValue("--muted"), dots: true }];
  const vlines = doses.filter((t) => H(t) >= x0).map((t) => ({ x: H(t) }));
  const forecast = $("forecast");

  const recent = mins.filter((m) => H(m.t) >= -48);
  const dosesH = doses.filter((t) => H(t) >= -54).map(H);
  const key = `${recent.length}:${dosesH.length}:${recent.length ? recent[recent.length - 1].t : 0}`;
  if (recent.length >= 60 && dosesH.length) {
    if (fitCache.key !== key) {
      fitCache = { key, params: med.fit(recent.map((m) => ({ t: H(m.t), s: m.s })), dosesH) };
    }
  } else {
    fitCache = { key, params: null };
  }
  const p = fitCache.params;
  if (p) {
    const g = med.grid(x0, x1);
    const s = med.severity(g, dosesH, p);
    series.push({ points: g.map((t, i) => [t, s[i]]), color: getComputedStyle(document.documentElement).getPropertyValue("--accent") });
    const last = Math.max(...dosesH);
    const wo = med.wearingOffTime(last, dosesH.filter((d) => d <= last), p);
    if (wo !== null) {
      const at = new Date(tEnd + wo * 3600000);
      const mins = Math.round((wo - H(now)) * 60);
      const when = at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      forecast.textContent = mins > 0
        ? `Your last dose is expected to wear off around ${when} (in ${Math.floor(mins / 60)} h ${mins % 60} min).`
        : `Your last dose likely wore off around ${when}.`;
      vlines.push({ x: wo, color: getComputedStyle(document.documentElement).getPropertyValue("--accent"), dash: [4, 4] });
    }
  } else {
    forecast.textContent = doses.length
      ? "Keep the device on while resting. The curve appears after about an hour of still readings."
      : "Log doses and wear the device for a few hours to see your response curve.";
  }
  drawChart(canvas, series, {
    x0, x1, y0: 0, y1: 4, vlines,
    xTicks: [[-24, "-24h"], [-12, "-12h"], [0, "now"], [6, "+6h"]],
  });
}

function loadDemoData() {
  // Three days of a simulated patient, ending now.
  const truth = [1.4, 0.7, 2.1, 0.45, 3.2];
  const end = Date.now();
  const start = end - 72 * 3600000;
  const day0 = new Date(start); day0.setHours(0, 0, 0, 0);
  const doses = [];
  for (let d = 0; d < 4; d++) {
    for (const h of [7, 11, 15, 19]) {
      const t = day0.getTime() + (d * 24 + h + (Math.random() - 0.5) * 0.6) * 3600000;
      if (t > start && t < end - 1800000) doses.push(t);
    }
  }
  const H = (t) => (t - start) / 3600000;
  const g = med.grid(0, 72);
  const s = med.severity(g, doses.map(H), truth);
  const minutes = [];
  g.forEach((t, i) => {
    const clock = new Date(start + t * 3600000).getHours();
    if (clock < 6 || clock >= 23 || Math.random() < 0.4) return;
    const v = s[i] + (Math.random() + Math.random() + Math.random() - 1.5) * 0.6;
    minutes.push({ t: Math.round(start + t * 3600000), s: Math.max(0, Math.min(4, +v.toFixed(3))) });
  });
  store.replaceLog(minutes, doses);
  updateMed();
}

async function init() {
  model = await Model.load("model/model.json");
  engine = new Engine(model, {
    onDecision: showDecision,
    onSample,
    onCue: (intensity, f) => cue(intensity, f, flash),
  });
  const st = store.settings;
  engine.placementWatch = !!st.placementWatch;
  if (st.placementWatch) document.querySelector('[data-placement="watch"]').click();
  $("haptics").checked = st.haptics !== false;
  engine.cueEnabled = $("haptics").checked;
  setTarget(st.target || 0);
  $("vib-note").hidden = canVibrate();

  segment("source", (v) => {
    if (running) stop();
    source = v;
    $("demo-panel").hidden = v !== "demo";
    note("");
  });
  segment("placement", (v) => {
    engine.placementWatch = v === "watch";
    store.setSetting("placementWatch", engine.placementWatch);
  });
  segment("grade", (v) => sim.set({ grade: +v }));
  segment("type", (v) => sim.set({ type: v }));
  segment("activity", (v) => sim.set({ activity: v }));
  $("start").addEventListener("click", () => (running ? stop() : start()));
  $("haptics").addEventListener("change", (e) => {
    engine.cueEnabled = e.target.checked;
    store.setSetting("haptics", e.target.checked);
  });
  $("target").addEventListener("input", (e) => setTarget(+e.target.value));
  $("calibrate").addEventListener("click", () => calibrator.start());
  $("dose").addEventListener("click", () => {
    store.addDose();
    confirmPulse();
    $("dose").textContent = "Dose logged ✓";
    setTimeout(() => ($("dose").textContent = "I took my dose"), 1500);
    updateMed();
  });
  $("demo-data").addEventListener("click", loadDemoData);
  $("export").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([store.csv()], { type: "text/csv" }));
    a.download = "tremorsense.csv";
    a.click();
  });
  $("clear").addEventListener("click", () => {
    if (confirm("Delete all logged doses and readings on this device?")) {
      store.clear();
      updateMed();
    }
  });
  window.addEventListener("resize", updateMed);
  setInterval(() => { if (running) updateMed(); }, 60000);
  updateMed();

  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
  window.__tremorsense = { engine, sim, store, start, stop };
}

init();
