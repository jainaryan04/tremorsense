// Everything stays on the device: dose presses and a per-minute severity log
// in localStorage. Nothing is uploaded.

const KEY = "tremorsense.v1";
const MAX_MINUTES = 60 * 24 * 14;

function blank() {
  return { doses: [], minutes: [], settings: { placementWatch: false, target: 0, haptics: true } };
}

export class Store {
  constructor() {
    try {
      this.d = { ...blank(), ...JSON.parse(localStorage.getItem(KEY) || "{}") };
    } catch {
      this.d = blank();
    }
    this.acc = null; // current minute accumulator
  }

  save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.d));
    } catch {
      /* storage full or blocked: keep working in memory */
    }
  }

  get settings() {
    return this.d.settings;
  }

  setSetting(k, v) {
    this.d.settings[k] = v;
    this.save();
  }

  addDose(t = Date.now()) {
    this.d.doses.push(t);
    this.save();
  }

  // Only decisions taken while the hand is still count towards the curve.
  addDecision(expectedGrade, t = Date.now()) {
    const minute = Math.floor(t / 60000) * 60000;
    if (!this.acc || this.acc.t !== minute) {
      this.flush();
      this.acc = { t: minute, sum: 0, n: 0 };
    }
    this.acc.sum += expectedGrade;
    this.acc.n += 1;
  }

  flush() {
    if (this.acc && this.acc.n >= 10) {
      this.d.minutes.push({ t: this.acc.t, s: +(this.acc.sum / this.acc.n).toFixed(3) });
      if (this.d.minutes.length > MAX_MINUTES) this.d.minutes.splice(0, this.d.minutes.length - MAX_MINUTES);
      this.save();
    }
    this.acc = null;
  }

  replaceLog(minutes, doses) {
    this.d.minutes = minutes;
    this.d.doses = doses;
    this.save();
  }

  clear() {
    const settings = this.d.settings;
    this.d = { ...blank(), settings };
    this.save();
  }

  csv() {
    const rows = ["type,time_iso,value"];
    for (const t of this.d.doses) rows.push(`dose,${new Date(t).toISOString()},1`);
    for (const m of this.d.minutes) rows.push(`severity,${new Date(m.t).toISOString()},${m.s}`);
    return rows.join("\n");
  }
}
