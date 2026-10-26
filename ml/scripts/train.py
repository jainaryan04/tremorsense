"""Generate synthetic data, train the three heads, calibrate the conformal gate,
and export the bundle the web app loads.

    cd ml && python -m scripts.train
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np

from tremorsense import conformal, dsp, synth
from tremorsense.model import Head, Scaler, save_bundle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ALPHA = 0.01
# Phone/watch IMU, or the GY-61 (ADXL335) on the Arduino: acceleration only,
# 10-bit ADC, +-3.6 g range.
SENSORS = {
    "phone": ("features.npz", "model.json"),
    "gy61": ("features_gy61.npz", "model_gy61.json"),
}
G = 9.81
GY61_STEP = G * (5.0 / 1023) / 0.33   # m/s^2 per ADC count


def as_gy61(acc, rng):
    """What the Uno sees: clipped at +-3.6 g with gravity on a random axis,
    quantised to ADC counts with about half a count of noise, and no gyro."""
    g = G * synth._unit(rng)
    tot = np.clip(acc + g, -3.6 * G, 3.6 * G)
    q = np.round(tot / GY61_STEP + rng.normal(scale=0.6, size=tot.shape)) * GY61_STEP
    return q - q.mean(0)


def build_features(n_subjects, wps, seed, sensor="phone"):
    t = time.time()
    d = synth.dataset(n_subjects, wps, seed)
    if sensor == "gy61":
        rng = np.random.default_rng(seed + 1)
        d["acc"] = [as_gy61(a, rng) for a in d["acc"]]
        d["gyro"] = [np.zeros_like(g) for g in d["gyro"]]
    X = np.stack([dsp.features(a, g) for a, g in zip(d["acc"], d["gyro"])])
    X = np.hstack([X, d["placement"][:, None].astype(float)])
    print(f"features {X.shape} in {time.time() - t:.1f}s")
    return X, {k: v for k, v in d.items() if k not in ("acc", "gyro")}


def split_by_subject(subject, seed, frac=(0.6, 0.2, 0.2)):
    ids = np.unique(subject)
    rng = np.random.default_rng(seed)
    rng.shuffle(ids)
    a = int(frac[0] * len(ids))
    b = a + int(frac[1] * len(ids))
    return (np.isin(subject, ids[:a]), np.isin(subject, ids[a:b]), np.isin(subject, ids[b:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", type=int, default=400)
    ap.add_argument("--windows", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--sensor", choices=list(SENSORS), default="phone")
    args = ap.parse_args()
    cache_name, bundle_name = SENSORS[args.sensor]
    CACHE = os.path.join(ROOT, "ml", "data", cache_name)
    BUNDLE = os.path.join(ROOT, "web", "model", bundle_name)

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if args.rebuild or not os.path.exists(CACHE):
        X, lab = build_features(args.subjects, args.windows, args.seed, args.sensor)
        np.savez_compressed(CACHE, X=X, **lab)
    z = np.load(CACHE)
    X, grade, ttype, act, subj = z["X"], z["grade"], z["type"], z["activity"], z["subject"]

    tr, ca, te = split_by_subject(subj, args.seed)
    scaler = Scaler.fit(X[tr])
    Xs = scaler(X)
    still = act == synth.ACTIVITIES.index("still")

    heads = {
        "activity": Head.train(Xs[tr], act[tr], synth.ACTIVITIES, seed=1),
        "severity": Head.train(Xs[tr & still], grade[tr & still], [0, 1, 2, 3, 4], seed=2),
        "type": Head.train(Xs[tr & still & (grade > 0)], ttype[tr & still & (grade > 0)] - 1,
                           ["parkinsonian", "essential"], hidden=(16,), seed=3),
    }

    q_act = conformal.calibrate(heads["activity"].proba(Xs[ca]), act[ca], ALPHA)
    q_sev = conformal.calibrate(heads["severity"].proba(Xs[ca & still]), grade[ca & still], ALPHA)
    conf = {"alpha": ALPHA, "q_activity": q_act, "q_severity": q_sev, "min_grade": 2, "max_width": 1,
            "n_cal_activity": int(ca.sum()), "n_cal_severity": int((ca & still).sum())}
    meta = {"sensor": args.sensor, "fs": dsp.FS, "win": dsp.WIN, "hop": dsp.HOP, "trained_on": "synthetic (see ml/tremorsense/synth.py)",
            "subjects": args.subjects, "seed": args.seed,
            "params": {k: h.n_params() for k, h in heads.items()}}
    save_bundle(BUNDLE, scaler, heads, conf, meta)
    if args.sensor == "phone":
        np.savez_compressed(os.path.join(ROOT, "ml", "data", "split.npz"), tr=tr, ca=ca, te=te)
    else:
        # Held-out subjects of this split, as a quick check of the variant.
        sev = heads["severity"].proba(Xs[te & still])
        sets = [conformal.prediction_set(p, q_sev, ordinal=True) for p in sev]
        y = grade[te & still]
        print(f"held-out: grade exact {np.mean(sev.argmax(1) == y):.3f}, within 1 {np.mean(np.abs(sev.argmax(1) - y) <= 1):.3f}, "
              f"activity {np.mean(heads['activity'].proba(Xs[te]).argmax(1) == act[te]):.3f}, "
              f"grade-set coverage {np.mean([v in st for v, st in zip(y, sets)]):.3f}")
    print("conformal", conf)
    print("params", meta["params"], "->", BUNDLE, f"{os.path.getsize(BUNDLE) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
