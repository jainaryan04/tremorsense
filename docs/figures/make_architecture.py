import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(9, 6.2))
ax.set_xlim(-4, 100); ax.set_ylim(0, 70); ax.axis("off")

def box(x, y, w, h, text, fc="#eef6f2", ec="#0f8a5f", bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.3, weight="bold" if bold else "normal", wrap=True)

def arrow(x1, y1, x2, y2, text=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color="#333", lw=1.1))
    if text:
        ax.text((x1 + x2) / 2 + 0.8, (y1 + y2) / 2, text, fontsize=7.2, color="#555", va="center")

box(30, 62, 40, 6, "Phone / smartwatch IMU (accelerometer + gyroscope)\nDeviceMotion API, any rate → resampled to 50 Hz", fc="#f3f3f3", ec="#666", bold=True)
arrow(40, 62, 22, 55); arrow(60, 62, 78, 55)

ax.text(4, 58.5, "Every sample (20 ms)", ha="left", fontsize=8, color="#0f8a5f", weight="bold")
box(5, 47, 34, 7, "Band-pass at tracked tremor peak\n+ Oja's-rule dominant-axis projection")
arrow(22, 47, 22, 42)
box(5, 35, 34, 7, "WFLC phase & frequency tracker\n(re-anchored to spectral peak each second)")
arrow(22, 35, 22, 30)
box(5, 23, 34, 7, "Latency-compensated cue scheduler:\nfire when φ(t + L) crosses target φ*")

ax.text(96, 58.5, "Every second (4 s window)", ha="right", fontsize=8, color="#0f8a5f", weight="bold")
box(61, 47, 34, 7, "Orientation-invariant PSD features (19)\n+ physics displacement d = a / (2πf)²")
arrow(78, 47, 78, 42)
box(61, 35, 34, 7, "Three tiny MLP heads (2,923 params):\nactivity · UPDRS grade 0–4 · tremor type")
arrow(78, 35, 78, 30)
box(61, 23, 34, 7, "Dual conformal safety gate (α = 0.01)\nactivity set = {still}, grade set ≤ 2 wide\nintensity = lower bound · debounce 2 of 3", fc="#fff3e3", ec="#c26a1b", bold=True)
arrow(61, 26.5, 39.5, 26.5, None)
ax.text(50, 28.2, "gated intensity", ha="center", fontsize=7.2, color="#555")
arrow(61, 50.5, 39.5, 50.5)
ax.text(50, 52.2, "tremor peak f", ha="center", fontsize=7.2, color="#555")

arrow(22, 23, 22, 17)
box(5, 9, 34, 7, "Vibration motor\npulse ≤ ⅓ cycle, length ∝ intensity\n(screen flash if no motor API)", fc="#f3f3f3", ec="#666")
box(5, 0.5, 34, 6, "Per-user phase sweep: 8 targets,\nkeep φ* with lowest tremor power")
ax.annotate("", xy=(4.4, 26.5), xytext=(4.4, 3.5), arrowprops=dict(arrowstyle="-|>", color="#999", lw=0.9, ls="--", connectionstyle="arc3,rad=-0.35"))
ax.text(-3.5, 15, "sets φ*", fontsize=7.2, color="#555", rotation=90, va="center")

arrow(78, 23, 78, 17)
box(61, 9, 34, 7, "Per-minute severity log (still only)\n+ one-tap dose log (on-device storage)")
arrow(78, 9, 78, 6.8)
box(60, 0.5, 36, 6, "Personal PK/PD fit (absorption → effect site → Emax)\n→ wear-off forecast & early alert", fc="#fff3e3", ec="#c26a1b", bold=True)

fig.tight_layout()
fig.savefig("/home/claude/tremorsense/docs/figures/architecture.png", dpi=220)
