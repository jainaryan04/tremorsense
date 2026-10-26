// Haptic output. The Web Vibration API cannot set motor strength, so the
// severity-scaled intensity is encoded as pulse length. Browsers without it
// (iOS Safari) get a visual cue instead.

export const canVibrate = () => typeof navigator !== "undefined" && typeof navigator.vibrate === "function";

const PULSE_MS = { 2: 18, 3: 30, 4: 45 };

// Never longer than a third of a tremor cycle, so the pulse stays phase-specific.
export const pulseMs = (intensity, freqHz) =>
  Math.min(PULSE_MS[intensity] || 18, Math.floor(1000 / (3 * Math.max(freqHz, 3))));

// Motor PWM duty on the Arduino, which (unlike the Vibration API) can set strength.
export const UNO_DUTY = { 2: 200, 3: 230, 4: 255 };

// The coin motor needs about 40 ms to spin up, so phone-length pulses barely
// move it. On the Arduino pulses are longer, still at most a third of a cycle.
const UNO_MS = { 2: 45, 3: 55, 4: 65 };

export const unoPulse = (intensity, freqHz) => ({
  duty: UNO_DUTY[intensity] || 0,
  ms: Math.min(UNO_MS[intensity] || 45, Math.floor(1000 / (3 * Math.max(freqHz, 3)))),
});

export function cue(intensity, freqHz, onVisual) {
  const ms = pulseMs(intensity, freqHz);
  if (canVibrate()) navigator.vibrate(ms);
  if (onVisual) onVisual(intensity, ms);
}

export function confirmPulse() {
  if (canVibrate()) navigator.vibrate([40, 60, 40]);
}
