// Port of ml/tremorsense/conformal.py: the dual conformal safety gate.

export function predictionSet(p, qHat, ordinal = false) {
  let keep = [];
  p.forEach((v, k) => { if (1 - v <= qHat) keep.push(k); });
  if (!keep.length) keep = [p.indexOf(Math.max(...p))];
  if (ordinal) {
    const lo = Math.min(...keep), hi = Math.max(...keep);
    keep = [];
    for (let k = lo; k <= hi; k++) keep.push(k);
  }
  return keep;
}

export function gate(pActivity, pSeverity, cfg, stillIndex = 0) {
  const aSet = predictionSet(pActivity, cfg.q_activity);
  const sSet = predictionSet(pSeverity, cfg.q_severity, true);
  const lo = sSet[0], hi = sSet[sSet.length - 1];
  const info = { activitySet: aSet, severitySet: sSet, reason: "ok" };
  if (!(aSet.length === 1 && aSet[0] === stillIndex)) return { intensity: 0, ...info, reason: "not_still" };
  if (hi - lo > cfg.max_width) return { intensity: 0, ...info, reason: "uncertain" };
  if (lo < cfg.min_grade) return { intensity: 0, ...info, reason: "below_threshold" };
  return { intensity: lo, ...info };
}
