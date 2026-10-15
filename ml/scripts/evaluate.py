"""Evaluate every component on held-out synthetic subjects and write
`docs/results.json` plus figures in `docs/figures/`.

    cd ml && python -m scripts.train && python -m scripts.evaluate
"""
from __future__ import annotations

import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score

from tremorsense import conformal, dsp, medcurve, synth
from tremorsense.model import load_bundle
from tremorsense.phase import CueScheduler, PhaseTracker, circular_stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIG = os.path.join(ROOT, "docs", "figures")
STILL = synth.ACTIVITIES.index("still")


def r3(x):
    return float(round(x, 3))


def eval_classifier():
    z = np.load(os.path.join(ROOT, "ml", "data", "features.npz"))
    sp = np.load(os.path.join(ROOT, "ml", "data", "split.npz"))
    scaler, heads, bundle = load_bundle(os.path.join(ROOT, "web", "model", "model.json"))
    # Test = held-out subjects from the training run plus a larger, independently
    # generated cohort, so rare events like false cues are counted over many hours.
    extra_path = os.path.join(ROOT, "ml", "data", "test_features.npz")
    if not os.path.exists(extra_path):
        from scripts.train import build_features
        Xe, labe = build_features(300, 60, seed=2026)
        np.savez_compressed(extra_path, X=Xe, **labe)
    ze = np.load(extra_path)
    n0 = len(z["grade"])
    X = scaler(np.vstack([z["X"], ze["X"]]))
    raw = np.vstack([z["X"], ze["X"]])
    cat = lambda k: np.concatenate([z[k], ze[k]])
    grade, act, ttype = cat("grade"), cat("activity"), cat("type")
    subject = np.concatenate([z["subject"], ze["subject"] + 100000])
    pad = np.zeros(len(ze["grade"]), bool)
    te = np.concatenate([sp["te"], ~pad])
    tr = np.concatenate([sp["tr"], pad])
    sp = {"ca": np.concatenate([sp["ca"], pad])}
    still = act == STILL
    cf = bundle["conformal"]

    pa = heads["activity"].proba(X[te])
    m = te & still
    ps = heads["severity"].proba(X[m])
    yhat = ps.argmax(1)
    g = grade[m]
    m2 = m & (grade > 0)
    pt = heads["type"].proba(X[m2]).argmax(1)

    # Conformal coverage on test data.
    sev_sets = [conformal.prediction_set(p, cf["q_severity"], ordinal=True) for p in ps]
    act_sets = [conformal.prediction_set(p, cf["q_activity"]) for p in pa]
    sev_cov = np.mean([gi in s for gi, s in zip(g, sev_sets)])
    act_cov = np.mean([a in s for a, s in zip(act[te], act_sets)])

    # Compare three ways of deciding when to cue, on every test window.
    ps_all = heads["severity"].proba(X[te])
    g_te, a_te = grade[te], act[te]
    n = len(g_te)
    hours = n * dsp.HOP / dsp.FS / 3600.0
    # Baseline 1: fixed band-power threshold, like binary tremor detectors.
    log_ptr = raw[:, dsp.FEATURE_NAMES.index("log_p_tremor")]
    tr_still = tr & still
    cands = np.quantile(log_ptr[tr_still], np.linspace(0.05, 0.95, 91))
    best_t = max(cands, key=lambda t: np.mean((log_ptr[tr_still] > t) == (grade[tr_still] >= 2)))
    policies = {}
    policies["threshold"] = np.where(log_ptr[te] > best_t, 2, 0)
    # Baseline 2: softmax-confidence gate (the Review 1 design).
    conf_ok = (pa.argmax(1) == STILL) & (ps_all.max(1) >= 0.8) & (ps_all.argmax(1) >= 2)
    policies["softmax_gate"] = np.where(conf_ok, ps_all.argmax(1), 0)
    # Ours: dual conformal gate, intensity = lower end of the severity set.
    ours = np.array([conformal.gate(pa[i], ps_all[i], cf["q_activity"], cf["q_severity"],
                                    min_grade=cf["min_grade"], max_width=cf["max_width"])[0] for i in range(n)])
    policies["conformal_gate"] = ours

    should = (a_te == STILL) & (g_te >= 2)
    gate_rows = {}
    for k, inten in policies.items():
        fire = inten > 0
        false = fire & ~should
        over = fire & ((inten > g_te) | (a_te != STILL))
        gate_rows[k] = {
            "false_triggers_per_hour": r3(false.sum() / hours),
            "cues_with_no_tremor_per_hour": r3((fire & (g_te == 0)).sum() / hours),
            "cues_while_moving_per_hour": r3((fire & (a_te != STILL)).sum() / hours),
            "cues_on_slight_tremor_per_hour": r3((fire & (a_te == STILL) & (g_te == 1)).sum() / hours),
            "over_stimulation_rate": r3(over.sum() / max(fire.sum(), 1)),
            "sensitivity": r3((fire & should).sum() / should.sum()),
            "triggers": int(fire.sum()),
        }

    # Trade-off curves: sweep the softmax threshold and the conformal alpha.
    ca = sp["ca"]
    pa_c = heads["activity"].proba(X[ca])
    ps_c = heads["severity"].proba(X[ca & still])
    curve = {"softmax_gate": [], "conformal_gate": []}
    for t in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]:
        ok = (pa.argmax(1) == STILL) & (ps_all.max(1) >= t) & (ps_all.argmax(1) >= 2)
        curve["softmax_gate"].append({"param": t, "fth": r3((ok & ~should).sum() / hours), "sens": r3((ok & should).sum() / should.sum())})
    for a in [0.1, 0.05, 0.03, 0.02, 0.01, 0.005]:
        qa = conformal.calibrate(pa_c, act[ca], a)
        qs = conformal.calibrate(ps_c, grade[ca & still], a)
        ok = np.array([conformal.gate(pa[i], ps_all[i], qa, qs)[0] for i in range(n)]) > 0
        curve["conformal_gate"].append({"param": a, "fth": r3((ok & ~should).sum() / hours), "sens": r3((ok & should).sum() / should.sum())})
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    for k, c, lab in [("softmax_gate", "#999", "Softmax confidence gate"), ("conformal_gate", "#2a6", "Conformal gate (ours)")]:
        ax.plot([r["fth"] for r in curve[k]], [100 * r["sens"] for r in curve[k]], "o-", color=c, label=lab)
    ax.set_xlabel("False cues per hour")
    ax.set_ylabel("Cues delivered when needed (%)")
    ax.set_title("Safety vs. responsiveness")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "tradeoff.png"), dpi=200)
    plt.close(fig)

    cm = confusion_matrix(g, yhat, labels=[0, 1, 2, 3, 4])
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    ax.imshow(cm, cmap="Blues")
    for i in range(5):
        for j in range(5):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=9)
    ax.set_xlabel("Predicted UPDRS grade")
    ax.set_ylabel("True UPDRS grade")
    ax.set_title("Severity grading (held-out subjects)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "confusion.png"), dpi=200)
    plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(7.5, 3.0))
    names = {"threshold": "Fixed threshold", "softmax_gate": "Softmax gate", "conformal_gate": "Conformal gate"}
    keys = list(policies)
    axs[0].bar([names[k] for k in keys], [gate_rows[k]["false_triggers_per_hour"] for k in keys], color=["#999", "#bbb", "#2a6"])
    axs[0].set_title("False cues per hour")
    axs[1].bar([names[k] for k in keys], [100 * gate_rows[k]["over_stimulation_rate"] for k in keys], color=["#999", "#bbb", "#2a6"])
    axs[1].set_title("Over-stimulation (% of cues)")
    for a in axs:
        a.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "gate.png"), dpi=200)
    plt.close(fig)

    return {
        "test_subjects": int(len(np.unique(subject[te]))),
        "test_hours": r3(te.sum() * dsp.HOP / dsp.FS / 3600),
        "test_windows": int(te.sum()),
        "activity_accuracy": r3(np.mean(pa.argmax(1) == act[te])),
        "severity_accuracy": r3(np.mean(yhat == g)),
        "severity_within_1": r3(np.mean(np.abs(yhat - g) <= 1)),
        "severity_macro_f1": r3(f1_score(g, yhat, average="macro")),
        "type_accuracy": r3(np.mean(pt == ttype[m2] - 1)),
        "confusion": cm.tolist(),
        "conformal": {"alpha": cf["alpha"], "severity_coverage": r3(sev_cov), "activity_coverage": r3(act_cov),
                      "mean_severity_set_size": r3(np.mean([len(s) for s in sev_sets]))},
        "gate": gate_rows,
        "tradeoff": curve,
        "threshold_baseline_log_power": r3(best_t),
        "params": bundle["meta"]["params"],
        "model_kb": r3(os.path.getsize(os.path.join(ROOT, "web", "model", "model.json")) / 1024),
    }


def eval_phase(n_subj=60, secs=60, latency=0.04, seed=11):
    rng = np.random.default_rng(seed)
    n = int(secs * dsp.FS)
    plv_ours, plv_open, jit_ours, f_err = [], [], [], []
    example = None
    for k in range(n_subj):
        s = synth.make_subject(k, rng)
        grade = int(rng.integers(2, 5))
        acc, gyro, phi, f_true = synth.tremor(n, s.f0, synth.sample_p2p_cm(grade, rng), s, rng)
        acc = acc + rng.normal(scale=s.noise_acc, size=acc.shape)
        trk = PhaseTracker(f_init=6.0)
        sch = CueScheduler(target=0.0, latency_s=latency)
        fires, est = [], []
        for i in range(n):
            if i >= dsp.WIN and i % dsp.HOP == 0:
                f_pk, _, _ = dsp.peak_in(dsp.psd_trace(acc[i - dsp.WIN:i]), dsp.BAND_TREMOR)
                trk.set_anchor(f_pk)
            ph, f = trk.step(acc[i])
            est.append(f)
            if i > 5 * dsp.FS and sch.step(ph, f):
                fires.append(i)
        lat = int(round(latency * dsp.FS))
        fires = [i for i in fires if i + lat < n]
        true_at = phi[[i + lat for i in fires]]
        plv, _, cs = circular_stats(true_at)
        plv_ours.append(plv)
        jit_ours.append(cs / (2 * math.pi * s.f0) * 1000)
        f_err.append(np.mean(np.abs(np.array(est[int(5 * dsp.FS):]) - f_true[int(5 * dsp.FS):])))
        # Open loop: pulses at a fixed rate from the first window's peak frequency.
        f_pk, _, _ = dsp.peak_in(dsp.psd_trace(acc[:dsp.WIN]), dsp.BAND_TREMOR)
        t_open = np.arange(5 * dsp.FS, n - lat, dsp.FS / f_pk).astype(int)
        plv_open.append(circular_stats(phi[t_open + lat])[0])
        if example is None:
            example = (acc, phi, fires, trk)
    acc, phi, fires, _ = example
    t = np.arange(len(phi)) / dsp.FS
    sig = acc @ np.linalg.svd(acc, full_matrices=False)[2][0]
    fig, ax = plt.subplots(figsize=(7.5, 2.6))
    sl = (t > 20) & (t < 22)
    ax.plot(t[sl], sig[sl], lw=1.2, label="Tremor (dominant axis)")
    for i in fires:
        if 20 < t[i] + 0.04 < 22:
            ax.axvline(t[i] + 0.04, color="#2a6", lw=1, alpha=0.8)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("m/s²")
    ax.set_title("Phase-locked cues (green) land at the same point of every tremor cycle")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "phase.png"), dpi=200)
    plt.close(fig)
    return {"subjects": n_subj, "seconds_each": secs, "actuator_latency_ms": latency * 1000,
            "plv_phase_locked_mean": r3(np.mean(plv_ours)), "plv_open_loop_mean": r3(np.mean(plv_open)),
            "timing_jitter_ms_median": r3(np.median(jit_ours)),
            "frequency_error_hz_mean": r3(np.mean(f_err))}


def wearing_off_true(t_from, doses, truth, horizon_h=8.0, frac=0.5):
    t = np.arange(t_from, t_from + horizon_h, medcurve.DT_H)
    t_all = np.arange(min(doses) - medcurve.DT_H, t_from + horizon_h, medcurve.DT_H)
    s = truth(t_all, doses)[-len(t):]
    i = int(np.argmin(s))
    s0 = truth(np.array([min(doses) - 1.0]), doses)[0]
    thr = s[i] + frac * (s0 - s[i])
    after = np.where(s[i:] >= thr)[0]
    return None if len(after) == 0 else float(t[i + after[0]])


def eval_medcurve(n_pat=100, seed=5):
    rng = np.random.default_rng(seed)
    pop = np.array([1.5, 0.8, 1.8, 0.5, 2.8])  # population prior (= fit initial guess)
    t = np.arange(0, 72, medcurve.DT_H)
    mae_fit, mae_pop, rs, rs_pop = [], [], [], []
    example = None
    for k in range(n_pat):
        true = np.array([rng.uniform(0.8, 3.0), rng.uniform(0.3, 1.5), rng.uniform(1.2, 2.8),
                         rng.uniform(0.25, 0.8), rng.uniform(2.2, 3.8)])
        doses = []
        for day in range(3):
            for h0 in (7, 11, 15, 19):
                doses.append(day * 24 + h0 + rng.normal(scale=0.4))
        doses = np.array(doses)
        # The simulated patient deliberately differs from the fitted model:
        # half-life 1-2.5 h (fit assumes 1.5 h), Hill slope 2-5 (fit assumes 3),
        # and a slow daily drift in baseline tremor that the model lacks.
        ke = math.log(2) / rng.uniform(1.0, 2.5)
        gamma = rng.uniform(2.0, 5.0)
        drift = 0.25 * np.sin(2 * np.pi * (t - rng.uniform(0, 24)) / 24)
        truth = lambda tt, dd: medcurve.severity(tt, dd, true, ke=ke, gamma=gamma)
        s_true = truth(t, doses) + drift
        obs = s_true + rng.normal(scale=0.45, size=len(t))
        obs[rng.random(len(t)) < 0.4] = np.nan          # not still -> no reading
        obs[(np.mod(t, 24) < 6) | (np.mod(t, 24) > 23)] = np.nan  # asleep
        train = t < 48
        p = medcurve.fit(t[train], obs[train], doses[doses < 48], t_grid=t[train])
        day3 = t >= 48
        s_fit = medcurve.severity(t, doses, p)
        s_pop = medcurve.severity(t, doses, pop)
        rs.append(np.corrcoef(s_fit[day3], s_true[day3])[0, 1])
        rs_pop.append(np.corrcoef(s_pop[day3], s_true[day3])[0, 1])
        for d in doses[doses >= 48]:
            wo_true = wearing_off_true(d, doses[doses <= d], truth)
            wo_fit = medcurve.wearing_off_time(d, doses[doses <= d], p)
            wo_pop = medcurve.wearing_off_time(d, doses[doses <= d], pop)
            if None not in (wo_true, wo_fit, wo_pop):
                mae_fit.append(abs(wo_fit - wo_true) * 60)
                mae_pop.append(abs(wo_pop - wo_true) * 60)
        if example is None:
            example = (t, obs, s_true, s_fit, doses)
    t, obs, s_true, s_fit, doses = example
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    sl = (t >= 46) & (t <= 66)
    ax.plot(t[sl], obs[sl], ".", ms=1.5, color="#bbb", label="Per-minute severity (noisy)")
    ax.plot(t[sl], s_true[sl], color="#333", lw=1.2, label="True response")
    ax.plot(t[sl], s_fit[sl], color="#2a6", lw=1.6, ls="--", label="Fitted on days 1-2, forecast day 3")
    for d in doses:
        if 46 <= d <= 66:
            ax.axvline(d, color="#c60", lw=0.8)
    ax.axvline(48, color="k", lw=0.6, ls=":")
    ax.set_xlabel("Hours since start (orange = dose button)")
    ax.set_ylabel("UPDRS tremor")
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "medcurve.png"), dpi=200)
    plt.close(fig)
    return {"patients": n_pat, "fit_days": 2, "forecast_day": 3,
            "model_mismatch": "true half-life 1-2.5 h, Hill slope 2-5, +-0.25 daily baseline drift; fit assumes fixed 1.5 h and 3",
            "curve_r_personal_median": r3(np.median(rs)), "curve_r_population_median": r3(np.median(rs_pop)),
            "wearing_off_mae_min_personal": r3(np.mean(mae_fit)),
            "wearing_off_mae_min_population": r3(np.mean(mae_pop)),
            "wearing_off_within_30min_personal": r3(np.mean(np.array(mae_fit) <= 30)),
            "doses_scored": len(mae_fit)}


def main():
    os.makedirs(FIG, exist_ok=True)
    res = {"note": "All results are on synthetic data from ml/tremorsense/synth.py. Clinical validation is pending."}
    res["classifier"] = eval_classifier()
    print(json.dumps(res["classifier"], indent=1))
    res["phase"] = eval_phase()
    print(json.dumps(res["phase"], indent=1))
    res["medcurve"] = eval_medcurve()
    print(json.dumps(res["medcurve"], indent=1))
    path = os.path.join(ROOT, "docs", "results.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    old.update(res)
    with open(path, "w") as f:
        json.dump(old, f, indent=1)


if __name__ == "__main__":
    main()
