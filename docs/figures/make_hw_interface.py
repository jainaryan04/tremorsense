"""Interfacing diagram of the hardware prototype (black and white).
    python3 docs/figures/make_hw_interface.py
Writes docs/figures/mono/hw_interface.png.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mono", "hw_interface.png")
KEY = "#e6e6e6"

fig, ax = plt.subplots(figsize=(9, 6.4))
ax.set_xlim(0, 100); ax.set_ylim(0, 72); ax.axis("off")


def box(x, y, w, h, text, fc="#ffffff", bold=False, ls="-", size=8.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec="#000", lw=1.2, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, weight="bold" if bold else "normal")


def arrow(x1, y1, x2, y2, text=None, dx=0.8, ha="left", both=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<|-|>" if both else "-|>", color="#000", lw=1.1))
    if text:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2, text, fontsize=7.2, color="#333", va="center", ha=ha)


# Group outlines
ax.add_patch(FancyBboxPatch((1, 1), 48, 69, boxstyle="round,pad=0.3,rounding_size=1.5", fc="none", ec="#000", lw=0.9, ls="--"))
ax.text(3, 68, "Wearable unit (Arduino Uno prototype)", fontsize=8.5, weight="bold", va="top")
ax.add_patch(FancyBboxPatch((60.5, 1), 38.5, 69, boxstyle="round,pad=0.3,rounding_size=1.5", fc="none", ec="#000", lw=0.9, ls="--"))
ax.text(62.5, 68, "Host: TremorSense web app (laptop / phone)", fontsize=8.5, weight="bold", va="top")

# Sensor and input path
box(4, 56, 20, 7, "GY-61 (ADXL335)\n3-axis accelerometer\n±3 g, 0.33 V/g", size=7.5)
arrow(24.5, 59.5, 30, 59.5, "X, Y, Z\nanalog", dx=0, ha="center")
ax.texts[-1].set_position((27.2, 62.5))
box(30, 56, 17, 7, "Uno ADC A0–A2\n10-bit, 50 Hz\n(timer-paced)", size=7.5)
arrow(39, 56, 39, 50.5)
box(4, 39, 43, 11, "Firmware (ATmega328P, 21 KB flash, 1.5 KB RAM)\n"
    "Gravity removal · Goertzel spectrum 0.5–12 Hz (2 s blocks)\n"
    "Displacement → UPDRS grade · movement check\n"
    "Band-pass zero-crossing phase tracker → pulse timer", fc=KEY, bold=False, size=7.5)
ax.text(26, 37.2, "standalone mode: decides cues on its own", ha="center", fontsize=7, style="italic")

# Outputs
arrow(12, 39, 12, 30)
box(4, 22, 15, 8, "D9 PWM → IRF540\nMOSFET → coin motor\n(1N4007 flyback)", size=7.2)
arrow(26, 39, 26, 30)
box(19.5, 22, 13, 8, "D2–D5, D11, D12\n→ 16×2 LCD\n(D6 → contrast)", size=7.2)
arrow(40, 39, 40, 30)
box(33, 22, 14, 8, "D8 → piezo\nbuzzer\n(chirps, cue-on beep)", size=7.2)
box(4, 8, 43, 9, "Patient's hand: phase-locked vibration cue\nLCD: grade, frequency, cue, test status\nBuzzer: start-up, cue on, alerts", fc="#f3f3f3", size=7.5)
arrow(11.5, 22, 11.5, 17.3); arrow(26, 22, 26, 17.3); arrow(40.5, 22, 40.5, 17.3)

# USB link (elbow wires through the channel between the two units)
L = dict(color="#000", lw=1.1)
ax.plot([48.5, 52, 52], [47, 47, 59.5], **L)
arrow(52, 59.5, 62.5, 59.5)
ax.text(55.5, 62.3, "A: raw x, y, z\n50 Hz", ha="center", fontsize=7.2, color="#333")
ax.plot([62.5, 57, 57], [23.5, 23.5, 42], **L)
arrow(57, 42, 48.5, 42)
ax.text(54.5, 33, "P: pulse\nT, L: LCD\nB: tone\nM: app on", ha="center", va="center", fontsize=7.2, color="#333",
        bbox=dict(fc="white", ec="none", pad=0.4))
ax.text(54.8, 52.5, "USB\nserial\n115,200\nbaud", ha="center", va="center", fontsize=7.2, weight="bold")

# Host pipeline
box(63, 56, 34, 7, "Web Serial port + ready handshake\ncounts → m/s² (0-g offset, 0.33 V/g)", size=7.5)
arrow(80, 56, 80, 52)
box(63, 45, 34, 7, "Spectral features + tiny neural heads\n(activity · UPDRS grade · tremor type)", size=7.5)
arrow(80, 45, 80, 41)
box(63, 32, 34, 9, "Dual conformal safety gate (α = 0.01)\nactivity set = {still}, grade set ≤ 2 wide\nintensity = lower bound of grade set", fc=KEY, bold=True, size=7.5)
arrow(80, 32, 80, 28)
box(63, 19, 34, 9, "Phase tracker + latency-compensated timer\npulse: duty 200 / 230 / 255,\n45 / 55 / 65 ms (≤ ⅓ cycle)", size=7.5)
box(63, 4, 34, 10, "Test-case generator (bench validation):\nknown synthetic GY-61 counts replace\nthe sensor at the same entry point", ls="--", size=7.5)
ax.plot([97.4, 98.4, 98.4], [9, 9, 59.5], color="#000", lw=0.9, ls="--")
arrow(98.4, 59.5, 97.4, 59.5)

fig.tight_layout()
fig.savefig(OUT, dpi=220)
print("saved", OUT)
