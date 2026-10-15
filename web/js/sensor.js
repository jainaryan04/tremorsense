// Phone / watch motion sensors via the DeviceMotion API, resampled to a
// steady 50 Hz stream of {acc: [x,y,z] m/s^2 without gravity, gyro: deg/s}.
import { FS } from "./dsp.js";

export function motionSupported() {
  return typeof window !== "undefined" && "DeviceMotionEvent" in window;
}

// iOS asks for permission, and only from a user gesture.
export async function requestMotionPermission() {
  const DME = window.DeviceMotionEvent;
  if (DME && typeof DME.requestPermission === "function") {
    return (await DME.requestPermission()) === "granted";
  }
  return true;
}

export class MotionSource {
  constructor(onSample) {
    this.onSample = onSample;
    this.prev = null;
    this.nextT = null;
    this.gravity = null;
    this.handler = (e) => this.handle(e);
    this.rawRate = 0;
    this._count = 0;
    this._t0 = 0;
  }

  start() {
    window.addEventListener("devicemotion", this.handler);
  }

  stop() {
    window.removeEventListener("devicemotion", this.handler);
    this.prev = null;
    this.nextT = null;
  }

  handle(e) {
    const t = e.timeStamp / 1000;
    let acc;
    if (e.acceleration && e.acceleration.x !== null) {
      acc = [e.acceleration.x, e.acceleration.y, e.acceleration.z];
    } else if (e.accelerationIncludingGravity) {
      // Some Android devices only give acceleration with gravity: remove a
      // slowly tracked gravity estimate (first-order low-pass, ~0.3 Hz).
      const g = e.accelerationIncludingGravity;
      const raw = [g.x || 0, g.y || 0, g.z || 0];
      if (!this.gravity) this.gravity = raw.slice();
      const dt = this.prev ? Math.max(1e-3, t - this.prev.t) : 1 / 60;
      const a = 1 - Math.exp(-2 * Math.PI * 0.3 * dt);
      this.gravity = this.gravity.map((v, i) => v + a * (raw[i] - v));
      acc = raw.map((v, i) => v - this.gravity[i]);
    } else {
      return;
    }
    const r = e.rotationRate || {};
    const gyro = [r.alpha || 0, r.beta || 0, r.gamma || 0];
    const cur = { t, acc, gyro };

    this._count++;
    if (!this._t0) this._t0 = t;
    if (t - this._t0 > 2) {
      this.rawRate = this._count / (t - this._t0);
      this._count = 0;
      this._t0 = t;
    }

    if (!this.prev) {
      this.prev = cur;
      this.nextT = t;
      return;
    }
    // Linear interpolation onto the 50 Hz grid.
    while (this.nextT <= t) {
      const w = (this.nextT - this.prev.t) / Math.max(1e-6, t - this.prev.t);
      const lerp = (a, b) => a.map((v, i) => v + w * (b[i] - v));
      this.onSample({ acc: lerp(this.prev.acc, acc), gyro: lerp(this.prev.gyro, gyro) });
      this.nextT += 1 / FS;
    }
    this.prev = cur;
  }
}
