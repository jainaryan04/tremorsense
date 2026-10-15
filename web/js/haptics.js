// Haptic output. The Web Vibration API cannot set motor strength, so the
// severity-scaled intensity is encoded as pulse length. Browsers without it
// (iOS Safari) get a visual cue instead.

export const canVibrate = () => typeof navigator !== "undefined" && typeof navigator.vibrate === "function";

const PULSE_MS = { 2: 18, 3: 30, 4: 45 };

export function cue(intensity, freqHz, onVisual) {
  // Never longer than a third of a tremor cycle, so the pulse stays phase-specific.
  const ms = Math.min(PULSE_MS[intensity] || 18, Math.floor(1000 / (3 * Math.max(freqHz, 3))));
  if (canVibrate()) navigator.vibrate(ms);
  if (onVisual) onVisual(intensity, ms);
}

export function confirmPulse() {
  if (canVibrate()) navigator.vibrate([40, 60, 40]);
}
