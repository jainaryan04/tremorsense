// The on-device pipeline: 50 Hz samples in, one decision per second out, and
// phase-locked cue timing on every sample in between.
import { FS, WIN, HOP, features } from "./dsp.js";
import { gate } from "./conformal.js";
import { PhaseTracker, CueScheduler } from "./phase.js";

export const ACTIVITIES = ["still", "voluntary", "gait", "vehicle"];
export const TYPES = ["parkinsonian", "essential"];

export class Engine {
  constructor(model, { onDecision, onCue, onSample } = {}) {
    this.model = model;
    this.onDecision = onDecision || (() => {});
    this.onCue = onCue || (() => {});
    this.onSample = onSample || (() => {});
    this.placementWatch = false;
    this.cueEnabled = false;
    this.latencyS = 0.06;
    this.reset();
  }

  reset() {
    this.acc = [];
    this.gyro = [];
    this.n = 0;
    this.tracker = new PhaseTracker(5.0);
    this.scheduler = new CueScheduler(this.scheduler ? this.scheduler.target : 0, this.latencyS);
    this.recent = [];       // last few gate intensities, for debouncing
    this.activeIntensity = 0;
    this.last = null;
  }

  setTarget(phase) {
    this.scheduler.target = phase;
  }

  push({ acc, gyro }) {
    this.acc.push(acc);
    this.gyro.push(gyro);
    if (this.acc.length > WIN) {
      this.acc.shift();
      this.gyro.shift();
    }
    this.n++;
    const { phase, freq } = this.tracker.step(acc);
    const fire = this.scheduler.step(phase, freq);
    this.onSample({ acc, signal: this.tracker.last, phase, fire: fire && this.activeIntensity > 0 });
    if (fire && this.cueEnabled && this.activeIntensity > 0) this.onCue(this.activeIntensity, freq);
    if (this.acc.length === WIN && this.n % HOP === 0) this.decide();
  }

  decide() {
    const t0 = performance.now();
    const f = features(this.acc, this.gyro);
    const p = this.model.predict(f.vector, this.placementWatch);
    const g = gate(p.activity, p.severity, this.model.conformal);
    const ms = performance.now() - t0;
    this.tracker.setAnchor(f.peakHz);
    // A cue starts only after 2 of the last 3 decisions agree, and uses the
    // weakest of the agreeing intensities.
    this.recent.push(g.intensity);
    if (this.recent.length > 3) this.recent.shift();
    const pos = this.recent.filter((v) => v > 0);
    this.activeIntensity = pos.length >= 2 && g.intensity > 0 ? Math.min(...pos) : 0;
    const expected = p.severity.reduce((s, v, k) => s + v * k, 0);
    const grade = p.severity.indexOf(Math.max(...p.severity));
    const act = p.activity.indexOf(Math.max(...p.activity));
    this.last = {
      grade, expected, probs: p.severity, severitySet: g.severitySet,
      activity: ACTIVITIES[act], activityP: p.activity[act], activityCertain: g.activitySet.length === 1,
      still: g.reason !== "not_still",
      type: grade > 0 ? TYPES[p.type[0] >= p.type[1] ? 0 : 1] : null, typeP: Math.max(...p.type),
      peakHz: f.peakHz, dispCm: f.dispP2pCm, logTremor: f.vector[3],
      gateReason: g.reason, gateIntensity: g.intensity, cueIntensity: this.activeIntensity, ms,
    };
    this.onDecision(this.last);
  }
}

export { FS };
