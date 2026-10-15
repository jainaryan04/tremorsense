"""Extra figures for the documentation and the invention disclosure.

    cd ml && python -m scripts.figures
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch
from sklearn.metrics import confusion_matrix

from tremorsense import conformal, dsp, medcurve, synth
from tremorsense.model import load_bundle
from tremorsense.phase import CueScheduler, PhaseTracker

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIG = os.path.join(ROOT, "docs", "figures")
GREEN, ORANGE, GREY, BLUE, RED = "#0f8a5f", "#c26a1b", "#888888", "#2f6db5", "#b5392f"
GRADE_COLORS = ["#9aa5a0", "#6fb59a", "#2f8f6b", "#d08a3a", "#b5392f"]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, name), dpi=200)
    plt.close(fig)


def load():
    z = np.load(os.path.join(ROOT, "ml", "data", "test_features.npz"))
    scaler, heads, bundle = load_bundle(os.path.join(ROOT, "web", "model", "model.json"))
    return z, scaler, heads, bundle


def fig_signals(rng):
    s = synth.make_subject(0, rng)
    s.f0 = 5.2
    fig, axs = plt.subplots(4, 1, figsize=(7.5, 6.2), sharex=True)
    t = np.arange(dsp.WIN) / dsp.FS
    for ax, act, lab in zip(axs, synth.ACTIVITIES, ["Resting (grade 2 Parkinsonian tremor)", "Using the hand (same patient)", "Walking (same patient)", "Riding in a vehicle (same patient)"]):
        acc, gyro, _ = synth.window(s, 2, act, rng)
        for i, c in enumerate([BLUE, GREEN, ORANGE]):
            ax.plot(t, acc[:, i], lw=0.8, color=c, label="xyz"[i])
        ax.set_title(lab, fontsize=9, loc="left")
        ax.set_ylabel("m/s²")
    axs[0].legend(ncol=3, fontsize=7, loc="upper right")
    axs[-1].set_xlabel("Time (s)")
    save(fig, "signals_by_activity.png")


def fig_spectra(rng):
    fig, axs = plt.subplots(1, 2, figsize=(7.5, 3.0))
    s = synth.make_subject(1, rng)
    s.f0, s.ttype = 5.0, "parkinsonian"
    for g in range(5):
        P = np.mean([dsp.psd_trace(synth.window(s, g, "still", rng)[0]) for _ in range(10)], axis=0)
        axs[0].semilogy(dsp.FREQS, P + 1e-6, color=GRADE_COLORS[g], label=f"Grade {g}")
    axs[0].set_title("Spectrum grows with UPDRS grade")
    for ttype, f0, c in [("parkinsonian", 5.0, GREEN), ("essential", 8.5, ORANGE)]:
        s.ttype, s.f0 = ttype, f0
        P = np.mean([dsp.psd_trace(synth.window(s, 2, "still", rng)[0]) for _ in range(10)], axis=0)
        axs[1].semilogy(dsp.FREQS, P + 1e-6, color=c, label=ttype.capitalize())
    axs[1].axvspan(*dsp.BAND_PD, color=GREEN, alpha=0.08)
    axs[1].axvspan(*dsp.BAND_ET, color=ORANGE, alpha=0.08)
    axs[1].set_title("Parkinsonian vs essential tremor")
    for a in axs:
        a.set_xlim(0, 20)
        a.set_xlabel("Frequency (Hz)")
        a.legend(fontsize=7)
    axs[0].set_ylabel("PSD (m²/s⁴/Hz)")
    save(fig, "spectra.png")


def fig_displacement(z):
    est = np.exp(z["X"][:, dsp.FEATURE_NAMES.index("log_disp_p2p_cm")])
    still = (z["activity"] == 0) & (z["grade"] > 0)
    true = z["p2p"][still]
    e = est[still]
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    for g in range(1, 5):
        m = z["grade"][still] == g
        ax.scatter(true[m], e[m], s=3, alpha=0.35, color=GRADE_COLORS[g], label=f"Grade {g}")
    for b in (1, 3, 10):
        ax.axvline(b, color="#ccc", lw=0.8, ls="--")
        ax.axhline(b, color="#ccc", lw=0.8, ls="--")
    ax.plot([0.1, 20], [0.1, 20], color="k", lw=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("True hand displacement, peak-to-peak (cm)")
    ax.set_ylabel("Recovered from phone/watch acceleration (cm)")
    ax.set_title("Displacement recovered by physics\n(dashed lines: UPDRS band edges)")
    r = np.corrcoef(np.log(true), np.log(e))[0, 1]
    ax.text(0.12, 12, f"log-log r = {r:.3f}", fontsize=8)
    ax.legend(fontsize=7, markerscale=3, loc="lower right")
    save(fig, "displacement_recovery.png")
    return float(r)


def fig_features(z):
    still = z["activity"] == 0
    fig, axs = plt.subplots(1, 3, figsize=(7.5, 2.8))
    d = z["X"][:, dsp.FEATURE_NAMES.index("log_disp_p2p_cm")]
    axs[0].boxplot([d[still & (z["grade"] == g)] for g in range(5)], tick_labels=list(range(5)), showfliers=False)
    axs[0].set_title("log displacement by grade")
    axs[0].set_xlabel("UPDRS grade")
    fp = z["X"][:, dsp.FEATURE_NAMES.index("f_peak")]
    axs[1].hist(fp[still & (z["type"] == 1)], bins=40, color=GREEN, alpha=0.6, label="Parkinsonian")
    axs[1].hist(fp[still & (z["type"] == 2)], bins=40, color=ORANGE, alpha=0.6, label="Essential")
    axs[1].set_title("Peak frequency by tremor type")
    axs[1].set_xlabel("Hz")
    axs[1].legend(fontsize=7)
    gr = z["X"][:, dsp.FEATURE_NAMES.index("gait_ratio")]
    axs[2].boxplot([gr[z["activity"] == a] for a in range(4)], tick_labels=["still", "hand", "walk", "vehicle"], showfliers=False)
    axs[2].set_title("Gait-cadence ratio by activity")
    save(fig, "feature_distributions.png")


def fig_confusions(z, scaler, heads):
    X = scaler(z["X"])
    pa = heads["activity"].proba(X).argmax(1)
    still_t = (z["activity"] == 0) & (z["grade"] > 0)
    pt = heads["type"].proba(X[still_t]).argmax(1)
    fig, axs = plt.subplots(1, 2, figsize=(7.5, 3.3), gridspec_kw={"width_ratios": [1.3, 1]})
    for ax, cm, labels, title in [
        (axs[0], confusion_matrix(z["activity"], pa), ["Still", "Hand use", "Walking", "Vehicle"], "Activity"),
        (axs[1], confusion_matrix(z["type"][still_t] - 1, pt), ["Parkinsonian", "Essential"], "Tremor type"),
    ]:
        cmn = cm / cm.sum(1, keepdims=True)
        ax.imshow(cmn, cmap="Greens", vmin=0, vmax=1)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{100 * cmn[i, j]:.1f}%", ha="center", va="center", fontsize=7.5, color="white" if cmn[i, j] > 0.5 else "black")
        ax.set_xticks(range(len(labels)), labels, rotation=20, fontsize=7.5)
        ax.set_yticks(range(len(labels)), labels, fontsize=7.5)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(title)
    save(fig, "confusion_activity_type.png")


def fig_conformal(z, scaler, heads, bundle):
    sp = np.load(os.path.join(ROOT, "ml", "data", "split.npz"))
    zt = np.load(os.path.join(ROOT, "ml", "data", "features.npz"))
    ca = sp["ca"] & (zt["activity"] == 0)
    pc = heads["severity"].proba(scaler(zt["X"][ca]))
    yc = zt["grade"][ca]
    still = z["activity"] == 0
    pt = heads["severity"].proba(scaler(z["X"][still]))
    yt = z["grade"][still]
    alphas = [0.2, 0.1, 0.05, 0.03, 0.02, 0.01, 0.005]
    cov, size = [], []
    for a in alphas:
        q = conformal.calibrate(pc, yc, a)
        sets = [conformal.prediction_set(p, q, ordinal=True) for p in pt]
        cov.append(np.mean([y in s for y, s in zip(yt, sets)]))
        size.append(np.mean([len(s) for s in sets]))
    fig, axs = plt.subplots(1, 2, figsize=(7.5, 3.0))
    nominal = [1 - a for a in alphas]
    axs[0].plot(nominal, nominal, color="k", lw=0.8, ls="--", label="Guaranteed minimum")
    axs[0].plot(nominal, cov, "o-", color=GREEN, label="Measured on test subjects")
    axs[0].set_xlabel("Target coverage 1 − α")
    axs[0].set_ylabel("Actual coverage")
    axs[0].set_title("Coverage guarantee holds")
    axs[0].legend(fontsize=7)
    q = bundle["conformal"]["q_severity"]
    sizes = [len(conformal.prediction_set(p, q, ordinal=True)) for p in pt]
    vals, counts = np.unique(sizes, return_counts=True)
    axs[1].bar([str(v) for v in vals], 100 * counts / counts.sum(), color=GREEN)
    axs[1].set_xlabel("Number of grades in the set (α = 0.01)")
    axs[1].set_ylabel("% of decisions")
    axs[1].set_title("Most decisions are a single grade")
    save(fig, "conformal_coverage.png")
    return dict(zip([str(a) for a in alphas], [round(c, 4) for c in cov]))


def fig_placement(z, scaler, heads):
    still = z["activity"] == 0
    X = scaler(z["X"][still])
    yhat = heads["severity"].proba(X).argmax(1)
    y = z["grade"][still]
    pl = z["placement"][still]
    tt = z["type"][still]
    groups = [("Phone in hand", pl == 0), ("Watch on wrist", pl == 1), ("Parkinsonian", tt == 1), ("Essential", tt == 2), ("No tremor", tt == 0)]
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    acc = [100 * np.mean(yhat[m] == y[m]) for _, m in groups]
    w1 = [100 * np.mean(np.abs(yhat[m] - y[m]) <= 1) for _, m in groups]
    x = np.arange(len(groups))
    ax.bar(x - 0.2, acc, 0.4, color=GREEN, label="Exact grade")
    ax.bar(x + 0.2, w1, 0.4, color="#9fd3bd", label="Within ±1")
    for i, v in enumerate(acc):
        ax.text(i - 0.2, v + 1, f"{v:.0f}", ha="center", fontsize=7)
    ax.set_xticks(x, [g for g, _ in groups])
    ax.set_ylim(0, 110)
    ax.set_ylabel("%")
    ax.set_title("Severity accuracy by placement and tremor type")
    ax.legend(fontsize=7, loc="lower right")
    save(fig, "accuracy_by_group.png")


def fig_importance(z, scaler, heads, rng):
    still = z["activity"] == 0
    X = scaler(np.asarray(z["X"][still]))
    y = z["grade"][still]
    base = np.mean(heads["severity"].proba(X).argmax(1) == y)
    drops = []
    for j in range(X.shape[1]):
        Xp = X.copy()
        Xp[:, j] = rng.permutation(Xp[:, j])
        drops.append(base - np.mean(heads["severity"].proba(Xp).argmax(1) == y))
    names = dsp.FEATURE_NAMES + ["placement_watch"]
    order = np.argsort(drops)[::-1][:12]
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.barh([names[i] for i in order][::-1], [100 * drops[i] for i in order][::-1], color=GREEN)
    ax.set_xlabel("Accuracy lost when the feature is shuffled (points)")
    ax.set_title("What the severity model relies on")
    save(fig, "feature_importance.png")


def fig_session(scaler, heads, bundle, rng):
    """A continuous 6-minute session with changing activity and severity."""
    cf = bundle["conformal"]
    s = synth.make_subject(5, rng)
    s.ttype, s.f0, s.placement, s.scale = "parkinsonian", 5.3, "phone", 0.95
    plan = [(60, 2, "still"), (40, 2, "gait"), (60, 3, "still"), (40, 3, "vehicle"), (40, 2, "voluntary"), (60, 1, "still"), (60, 4, "still")]
    acc_all, gyro_all, truth = [], [], []
    for secs, g, act in plan:
        a, gy, _ = synth.window(s, g, act, rng, n=int(secs * dsp.FS))
        acc_all.append(a); gyro_all.append(gy)
        truth += [(g, act)] * secs
    acc = np.vstack(acc_all); gyro = np.vstack(gyro_all)
    t, grades, lo, hi, inten, acts = [], [], [], [], [], []
    recent = []
    for st, a, g in dsp.windows(acc, gyro):
        x = scaler(np.append(dsp.features(a, g), 0.0))
        pa, ps = heads["activity"].proba(x)[0], heads["severity"].proba(x)[0]
        i, info = conformal.gate(pa, ps, cf["q_activity"], cf["q_severity"])
        recent = (recent + [i])[-3:]
        pos = [v for v in recent if v > 0]
        active = min(pos) if len(pos) >= 2 and i > 0 else 0
        t.append((st + dsp.WIN) / dsp.FS)
        grades.append(int(ps.argmax()))
        lo.append(info["severity_set"][0]); hi.append(info["severity_set"][-1])
        inten.append(active)
        acts.append(int(pa.argmax()))
    t = np.array(t)
    tg = np.array([truth[min(int(v) - 1, len(truth) - 1)][0] for v in t])
    ta = [truth[min(int(v) - 1, len(truth) - 1)][1] for v in t]
    fig, axs = plt.subplots(3, 1, figsize=(7.5, 5.4), sharex=True, gridspec_kw={"height_ratios": [1.2, 1.4, 0.9]})
    tt = np.arange(len(acc)) / dsp.FS
    axs[0].plot(tt, np.linalg.norm(acc, axis=1), lw=0.3, color=GREY)
    axs[0].set_ylabel("|acc| m/s²")
    x0 = 0
    for secs, g, act in plan:
        axs[0].text(x0 + secs / 2, axs[0].get_ylim()[1] * 0.97, {"still": "rest", "gait": "walk", "vehicle": "bus", "voluntary": "hand use"}[act] + f"\ngrade {g}", ha="center", fontsize=7, va="top")
        for a in axs:
            a.axvline(x0, color="#ddd", lw=0.8)
        x0 += secs
    axs[1].step(t, tg, where="post", color="k", lw=1, label="True grade")
    axs[1].fill_between(t, np.array(lo) - 0.15, np.array(hi) + 0.15, step="post", color=GREEN, alpha=0.2, label="Conformal grade set")
    axs[1].step(t, grades, where="post", color=GREEN, lw=1, label="Predicted grade")
    moving = np.array([v != "still" for v in ta])
    axs[1].fill_between(t, -0.5, 4.5, where=moving, color=ORANGE, alpha=0.08, step="post", label="Moving (grade not used)")
    axs[1].set_ylim(-0.5, 4.5)
    axs[1].set_ylabel("UPDRS grade")
    axs[1].legend(fontsize=6.5, ncol=4, loc="upper left")
    axs[2].step(t, inten, where="post", color=ORANGE, lw=1.4)
    axs[2].set_ylim(-0.3, 4.3)
    axs[2].set_yticks([0, 2, 3, 4], ["off", "2", "3", "4"])
    axs[2].set_ylabel("Cue strength")
    axs[2].set_xlabel("Time (s)")
    axs[0].set_title("A continuous 6-minute session: grading, gating and cueing")
    save(fig, "session_timeline.png")


def fig_phase(rng):
    n = int(40 * dsp.FS)
    errs_locked, errs_open, plvs = [], [], []
    conv = None
    for k in range(40):
        s = synth.make_subject(100 + k, rng)
        acc, _, phi, f_true = synth.tremor(n, s.f0, synth.sample_p2p_cm(int(rng.integers(2, 5)), rng), s, rng)
        acc = acc + rng.normal(scale=s.noise_acc, size=acc.shape)
        trk, sch = PhaseTracker(6.0), CueScheduler(0.0, 0.04)
        fires, est = [], []
        for i in range(n):
            if i >= dsp.WIN and i % dsp.HOP == 0:
                trk.set_anchor(dsp.peak_in(dsp.psd_trace(acc[i - dsp.WIN:i]), dsp.BAND_TREMOR)[0])
            ph, f = trk.step(acc[i])
            est.append(f)
            if i > 5 * dsp.FS and sch.step(ph, f):
                fires.append(i)
        lat = 2
        ang = np.array([phi[i + lat] for i in fires if i + lat < n])
        mean = np.angle(np.mean(np.exp(1j * ang)))
        errs_locked += list(np.angle(np.exp(1j * (ang - mean))))
        f_pk = dsp.peak_in(dsp.psd_trace(acc[:dsp.WIN]), dsp.BAND_TREMOR)[0]
        t_open = np.arange(5 * dsp.FS, n - lat, dsp.FS / f_pk).astype(int)
        ao = phi[t_open + lat]
        errs_open += list(np.angle(np.exp(1j * (ao - np.angle(np.mean(np.exp(1j * ao)))))))
        if conv is None:
            conv = (np.arange(n) / dsp.FS, np.array(est), f_true)
    fig = plt.figure(figsize=(7.5, 3.2))
    for i, (errs, title, c) in enumerate([(errs_locked, "Phase-locked (ours)", GREEN), (errs_open, "Open-loop vibration", GREY)]):
        ax = fig.add_subplot(1, 3, i + 1, projection="polar")
        ax.hist(errs, bins=36, color=c, alpha=0.8)
        ax.set_yticklabels([])
        ax.set_title(title, fontsize=9, pad=12)
    ax = fig.add_subplot(1, 3, 3)
    tt, est, ft = conv
    ax.plot(tt, ft, color="k", lw=1, label="True frequency")
    ax.plot(tt, est, color=GREEN, lw=1, label="Tracked")
    ax.set_xlim(0, 20)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Hz")
    ax.set_title("Tracker locks on within seconds", fontsize=9)
    ax.legend(fontsize=7)
    save(fig, "phase_analysis.png")


def fig_timing_diagram():
    f, L = 5.0, 0.04
    t = np.linspace(0, 0.6, 600)
    y = np.sin(2 * np.pi * f * t)
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    ax.plot(t * 1000, y, color="k", lw=1.4, label="Tremor (dominant axis)")
    target = 0.0
    for k in range(3):
        t_hit = (k + (target / (2 * np.pi))) / f + 0.05
        ax.axvspan((t_hit) * 1000, (t_hit + 1 / (3 * f) * 0.5) * 1000, color=GREEN, alpha=0.25)
        ax.annotate("", xy=(t_hit * 1000, 1.25), xytext=((t_hit - L) * 1000, 1.25), arrowprops=dict(arrowstyle="->", color=ORANGE))
        ax.plot([(t_hit - L) * 1000] * 2, [-1.1, 1.3], color=ORANGE, lw=0.8, ls="--")
    ax.text(10, 1.45, "command sent (dashed) one latency L before the target phase; motor pulse (green) ≤ ⅓ cycle", fontsize=8)
    ax.set_ylim(-1.3, 1.7)
    ax.set_xlabel("Time (ms)")
    ax.set_yticks([])
    ax.set_title("Latency-compensated phase-locked cue timing (5 Hz tremor, L = 40 ms)")
    save(fig, "cue_timing_diagram.png")


def fig_pkpd():
    t = np.arange(0, 10, medcurve.DT_H)
    p = [1.5, 0.8, 2.0, 0.5, 3.0]
    c = medcurve.plasma(t, np.array([1.0]), p[0])
    ce = medcurve.effect_site(c, p[1])
    s = medcurve.severity(t, np.array([1.0]), p)
    fig, axs = plt.subplots(1, 3, figsize=(7.5, 2.6))
    axs[0].plot(t, c, color=BLUE); axs[0].set_title("1. Plasma level C(t)")
    axs[1].plot(t, ce, color=ORANGE); axs[1].set_title("2. Effect-site level Ce(t)")
    axs[2].plot(t, s, color=GREEN); axs[2].set_title("3. Tremor severity S(t)")
    wo = medcurve.wearing_off_time(1.0, np.array([1.0]), p)
    axs[2].axvline(wo, color=RED, ls="--", lw=1)
    axs[2].text(wo + 0.1, 2.9, "forecast\nwear-off", color=RED, fontsize=7, va="top")
    for a in axs:
        a.axvline(1.0, color=ORANGE, lw=0.6)
        a.set_xlabel("Hours (dose at 1 h)")
    save(fig, "pkpd_stages.png")


def fig_med_eval(rng):
    t = np.arange(0, 72, medcurve.DT_H)
    pop = np.array([1.5, 0.8, 1.8, 0.5, 2.8])
    err_p, err_q, r_p, r_q, examples = [], [], [], [], []
    for k in range(40):
        true = np.array([rng.uniform(0.8, 3.0), rng.uniform(0.3, 1.5), rng.uniform(1.2, 2.8), rng.uniform(0.25, 0.8), rng.uniform(2.2, 3.8)])
        ke = math.log(2) / rng.uniform(1.0, 2.5)
        gamma = rng.uniform(2.0, 5.0)
        doses = np.array([d * 24 + h + rng.normal(scale=0.4) for d in range(3) for h in (7, 11, 15, 19)])
        drift = 0.25 * np.sin(2 * np.pi * (t - rng.uniform(0, 24)) / 24)
        s_true = medcurve.severity(t, doses, true, ke=ke, gamma=gamma) + drift
        obs = s_true + rng.normal(scale=0.45, size=len(t))
        obs[rng.random(len(t)) < 0.4] = np.nan
        obs[(np.mod(t, 24) < 6) | (np.mod(t, 24) > 23)] = np.nan
        tr = t < 48
        p = medcurve.fit(t[tr], obs[tr], doses[doses < 48], t_grid=t[tr])
        d3 = t >= 48
        sf, sp = medcurve.severity(t, doses, p), medcurve.severity(t, doses, pop)
        r_p.append(np.corrcoef(sf[d3], s_true[d3])[0, 1]); r_q.append(np.corrcoef(sp[d3], s_true[d3])[0, 1])
        if len(examples) < 3:
            examples.append((obs, s_true, sf, sp, doses))
    fig, axs = plt.subplots(3, 1, figsize=(7.5, 6.0), sharex=True)
    for ax, (obs, st, sf, sp, doses) in zip(axs, examples):
        sl = (t >= 30) & (t <= 72)
        ax.plot(t[sl], obs[sl], ".", ms=1, color="#c8c8c8")
        ax.plot(t[sl], st[sl], color="k", lw=1, label="True response")
        ax.plot(t[sl], sp[sl], color=GREY, lw=1, ls=":", label="Population model")
        ax.plot(t[sl], sf[sl], color=GREEN, lw=1.4, ls="--", label="Personal fit (days 1–2)")
        for d in doses[(doses > 30)]:
            ax.axvline(d, color=ORANGE, lw=0.6)
        ax.axvspan(48, 72, color=GREEN, alpha=0.04)
        ax.set_ylabel("Severity")
    axs[0].legend(fontsize=7, ncol=3, loc="upper left")
    axs[0].set_title("Three simulated patients: day 3 (shaded) is a true forecast")
    axs[-1].set_xlabel("Hours since start")
    save(fig, "medcurve_examples.png")
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    ax.boxplot([r_q, r_p], tick_labels=["Population model", "Personal fit"], showfliers=True)
    ax.set_ylabel("Correlation with true day-3 curve")
    ax.axhline(0.75, color=RED, ls="--", lw=0.8)
    ax.text(1.5, 0.76, "Review 1 target 0.75", fontsize=7, color=RED, ha="center")
    ax.set_title("Personal fitting beats a population model")
    save(fig, "medcurve_correlation.png")


def box(ax, x, y, w, h, text, fc="#eef6f2", ec=GREEN, fs=8, bold=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.3,rounding_size=0.8", fc=fc, ec=ec, lw=1.2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal")


def arrow(ax, x1, y1, x2, y2, label=None, side=0.8):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color="#333", lw=1))
    if label:
        if y1 == y2:
            ax.text((x1 + x2) / 2, y1 + 1.6, label, fontsize=7.5, color="#555", ha="center")
        else:
            ax.text((x1 + x2) / 2 + side, (y1 + y2) / 2, label, fontsize=7.5, color="#555", va="center")


def fig_gate_flowchart():
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    box(ax, 50, 94, 60, 7, "Window probabilities p_activity, p_grade", fc="#f3f3f3", ec="#666", bold=True)
    arrow(ax, 50, 90.5, 50, 85.5)
    box(ax, 50, 81, 66, 8, "Activity set A = {k : 1 − p_k ≤ q̂_act}\nGrade set S = contiguous {k : 1 − p_k ≤ q̂_sev}")
    arrow(ax, 50, 77, 50, 72)
    box(ax, 50, 68, 34, 7, "Is A exactly {still}?", fc="#fff3e3", ec=ORANGE)
    arrow(ax, 67, 68, 82, 68, "no", side=-3)
    box(ax, 89, 68, 18, 7, "No cue\n(moving)", fc="#fbe9e7", ec=RED)
    arrow(ax, 50, 64.5, 50, 58.5, "yes")
    box(ax, 50, 55, 34, 7, "max(S) − min(S) ≤ 1 ?", fc="#fff3e3", ec=ORANGE)
    arrow(ax, 67, 55, 82, 55, "no", side=-3)
    box(ax, 89, 55, 18, 7, "No cue\n(uncertain)", fc="#fbe9e7", ec=RED)
    arrow(ax, 50, 51.5, 50, 45.5, "yes")
    box(ax, 50, 42, 34, 7, "min(S) ≥ 2 ?", fc="#fff3e3", ec=ORANGE)
    arrow(ax, 67, 42, 82, 42, "no", side=-3)
    box(ax, 89, 42, 18, 7, "No cue\n(mild)", fc="#f3f3f3", ec="#666")
    arrow(ax, 50, 38.5, 50, 32.5, "yes")
    box(ax, 50, 29, 46, 7, "Candidate intensity I = min(S)")
    arrow(ax, 50, 25.5, 50, 19.5)
    box(ax, 50, 16, 52, 7, "2 of last 3 decisions positive?\nuse weakest agreeing intensity", fc="#fff3e3", ec=ORANGE)
    arrow(ax, 50, 12.5, 50, 7.5)
    box(ax, 50, 4, 52, 6, "Enable phase-locked cues at intensity I", fc="#e2f3ec", ec=GREEN, bold=True)
    ax.text(3, 30, "Guarantee:\nif the true grade is in S\n(probability ≥ 1 − α),\nthen I ≤ true grade.", fontsize=8, color=GREEN)
    save(fig, "gate_flowchart.png")


def fig_user_flow():
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.set_xlim(0, 100); ax.set_ylim(0, 44); ax.axis("off")
    steps = [(10, "Open app\n(installable,\noffline)"), (28, "Choose phone\nin hand or\nwatch on wrist"), (46, "Start\nmonitoring"), (64, "Live grade,\ntype, frequency,\ncue state"), (84, "Phase-locked\ncues when the\ngate allows")]
    for x, t in steps:
        box(ax, x, 33, 15, 13, t, fs=7.5)
    for a, b in zip(steps, steps[1:]):
        arrow(ax, a[0] + 7.5, 33, b[0] - 7.5, 33)
    steps2 = [(28, "Tap 'I took\nmy dose'"), (46, "Per-minute\nseverity while\nstill"), (64, "Personal curve\nfitted on device"), (84, "Wear-off\nforecast and\nearly warning")]
    for x, t in steps2:
        box(ax, x, 10, 15, 13, t, fs=7.5, fc="#fff3e3", ec=ORANGE)
    for a, b in zip(steps2, steps2[1:]):
        arrow(ax, a[0] + 7.5, 10, b[0] - 7.5, 10)
    arrow(ax, 64, 26.5, 46, 16.5)
    box(ax, 10, 10, 15, 13, "Export CSV\nfor the\nneurologist", fs=7.5, fc="#f3f3f3", ec="#666")
    arrow(ax, 20.5, 10, 17.5, 10)
    save(fig, "user_flow.png")


def fig_dataset(z):
    fig, axs = plt.subplots(1, 2, figsize=(7.5, 2.6))
    g, n = np.unique(z["grade"], return_counts=True)
    axs[0].bar([str(v) for v in g], n, color=GRADE_COLORS)
    axs[0].set_title("Test windows by UPDRS grade")
    a, n = np.unique(z["activity"], return_counts=True)
    axs[1].bar(["Still", "Hand use", "Walking", "Vehicle"], n, color=[GREEN, BLUE, ORANGE, GREY])
    axs[1].set_title("Test windows by activity")
    save(fig, "dataset_distribution.png")


def main():
    rng = np.random.default_rng(42)
    z, scaler, heads, bundle = load()
    fig_signals(rng)
    fig_spectra(rng)
    r = fig_displacement(z)
    fig_features(z)
    fig_confusions(z, scaler, heads)
    cov = fig_conformal(z, scaler, heads, bundle)
    fig_placement(z, scaler, heads)
    fig_importance(z, scaler, heads, rng)
    fig_session(scaler, heads, bundle, rng)
    fig_phase(rng)
    fig_timing_diagram()
    fig_pkpd()
    fig_med_eval(rng)
    fig_gate_flowchart()
    fig_user_flow()
    fig_dataset(z)
    print("displacement log-log r", r, "coverage", cov)


if __name__ == "__main__":
    main()
