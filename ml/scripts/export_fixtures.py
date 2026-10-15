"""Export reference outputs from the Python modules so the browser port can be
checked against them (`web/test/parity.test.mjs`).

    cd ml && python -m scripts.export_fixtures
"""
from __future__ import annotations

import json
import os

import numpy as np

from tremorsense import conformal, dsp, medcurve, synth
from tremorsense.model import load_bundle
from tremorsense.phase import CueScheduler, PhaseTracker

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    rng = np.random.default_rng(123)
    scaler, heads, bundle = load_bundle(os.path.join(ROOT, "web", "model", "model.json"))
    cf = bundle["conformal"]
    windows = []
    for grade, act in [(0, "still"), (2, "still"), (4, "still"), (3, "gait"), (1, "vehicle"), (2, "voluntary")]:
        s = synth.make_subject(0, rng)
        acc, gyro, _ = synth.window(s, grade, act, rng)
        f = dsp.features(acc, gyro)
        x = scaler(np.append(f, 1.0 if s.placement == "watch" else 0.0))
        pa, ps = heads["activity"].proba(x)[0], heads["severity"].proba(x)[0]
        inten, info = conformal.gate(pa, ps, cf["q_activity"], cf["q_severity"], min_grade=cf["min_grade"], max_width=cf["max_width"])
        windows.append({"acc": acc.round(6).tolist(), "gyro": gyro.round(6).tolist(),
                        "placement_watch": s.placement == "watch",
                        "features": f.tolist(), "activity": pa.tolist(), "severity": ps.tolist(),
                        "type": heads["type"].proba(x)[0].tolist(), "intensity": int(inten),
                        "severity_set": info["severity_set"], "activity_set": info["activity_set"]})

    s = synth.make_subject(1, rng)
    acc, _, _, _ = synth.tremor(500, 5.2, 3.0, s, rng)
    acc = acc.round(6)
    trk, sch = PhaseTracker(5.0), CueScheduler(0.0, 0.04)
    trk.set_anchor(5.2)
    phases, fires = [], []
    for i, a in enumerate(acc):
        ph, f = trk.step(a)
        phases.append(ph)
        if sch.step(ph, f):
            fires.append(i)

    params = [1.7, 0.9, 2.0, 0.45, 3.1]
    doses = [7.0, 11.2, 15.1]
    t = np.arange(6.0, 20.0, medcurve.DT_H)
    sev = medcurve.severity(t, np.array(doses), params)
    wo = medcurve.wearing_off_time(15.1, np.array(doses), params)

    out = {"windows": windows,
           "phase": {"acc": acc.tolist(), "anchor": 5.2, "phases": phases, "fires": fires},
           "medcurve": {"params": params, "doses": doses, "t0": 6.0, "severity": sev.tolist(), "wearing_off": wo}}
    path = os.path.join(ROOT, "web", "test", "fixtures.json")
    with open(path, "w") as f:
        json.dump(out, f)
    print("wrote", path)


if __name__ == "__main__":
    main()
