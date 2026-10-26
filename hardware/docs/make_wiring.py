"""Draws the wiring diagrams for hardware/README.md (black and white).

    python3 hardware/docs/make_wiring.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({"font.size": 8, "font.family": "DejaVu Sans"})


def box(ax, x, y, w, h, title, fc="white", lw=1.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.6", fc=fc, ec="black", lw=lw))
    ax.text(x + w / 2, y + h + 0.8, title, ha="center", va="bottom", fontsize=9, weight="bold")


def pin(ax, x, y, label, side="right"):
    ax.plot([x], [y], "o", ms=3.5, color="black")
    if side == "right":
        ax.text(x - 0.8, y, label, ha="right", va="center", fontsize=7.5)
    else:
        ax.text(x + 0.8, y, label, ha="left", va="center", fontsize=7.5)


def wire(ax, pts, ls="-", lw=1.1, label=None, lpos=None):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color="black", ls=ls, lw=lw, solid_capstyle="round")
    if label:
        x, y = lpos
        ax.text(x, y, label, fontsize=6.8, ha="center", va="bottom", bbox=dict(fc="white", ec="none", pad=0.4))


def resistor(ax, x0, x1, y):
    """Zig-zag resistor between x0 and x1 on a horizontal wire."""
    import numpy as np
    xs = np.linspace(x0, x1, 13)
    ys = [y] + [y + (0.9 if i % 2 else -0.9) for i in range(1, 12)] + [y]
    ax.plot(xs, ys, color="black", lw=1.1)


def straight(name, title, left_title, right_title, rows, note=None):
    """One straight wire per row: left label -> right label.

    rows: (left, right, kind) with kind "" (wire), "gnd" (dashed),
    "res" (220 ohm resistor in the wire) or "nc" (not connected).
    """
    h = 2.6 * len(rows) + 10
    fig, ax = plt.subplots(figsize=(7.5, h * 0.155 + 0.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, h); ax.axis("off")
    top = h - 6
    bot = top - 2.6 * (len(rows) - 1)
    box(ax, 4, bot - 2.5, 24, top - bot + 5, left_title, fc="#f2f2f2")
    box(ax, 66, bot - 2.5, 28, top - bot + 5, right_title)
    for i, (l, r, kind) in enumerate(rows):
        y = top - 2.6 * i
        if kind == "nc":
            pin(ax, 66, y, r, side="left")
            ax.text(47, y, "not connected", ha="center", va="center", fontsize=7, style="italic")
            continue
        pin(ax, 28, y, l)
        pin(ax, 66, y, r, side="left")
        if kind == "res":
            wire(ax, [(28, y), (42, y)])
            resistor(ax, 42, 52, y)
            ax.text(47, y + 1.1, "220 Ω", ha="center", fontsize=6.8)
            wire(ax, [(52, y), (66, y)])
        else:
            wire(ax, [(28, y), (66, y)], ls=(0, (6, 2)) if kind == "gnd" else "-")
    if note:
        ax.text(50, 1.2, note, ha="center", fontsize=7.2, style="italic")
    ax.set_title(title, fontsize=10, weight="bold", pad=2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=200)
    plt.close(fig)


def steps():
    straight("step1_lcd.png", "Step 1: LCD (JHD162A, pins counted from the left, pin 1 marked on the board)",
             "Arduino Uno", "LCD pin", [
                 ("GND", "1 VSS", "gnd"), ("5V", "2 VDD", ""), ("D6", "3 V0 (contrast)", ""),
                 ("D12", "4 RS", ""), ("GND", "5 RW", "gnd"), ("D11", "6 E", ""),
                 ("", "7 D0", "nc"), ("", "8 D1", "nc"), ("", "9 D2", "nc"), ("", "10 D3", "nc"),
                 ("D5", "11 D4", ""), ("D4", "12 D5", ""), ("D3", "13 D6", ""), ("D2", "14 D7", ""),
                 ("5V", "15 A (backlight +)", "res"), ("GND", "16 K (backlight −)", "gnd")],
             note="Dashed = ground. Use the breadboard rails for 5V and GND.")
    straight("step2_accel.png", "Step 2: GY-61 accelerometer", "Arduino Uno", "GY-61 pin", [
        ("5V", "VCC", ""), ("A0", "X", ""), ("A1", "Y", ""), ("A2", "Z", ""), ("GND", "GND", "gnd")],
        note="Tape the GY-61 flat on the back of the hand, chip side up.")
    straight("step4_buzzer.png", "Step 4: piezo buzzer", "Arduino Uno", "Buzzer", [
        ("D8", "+ (longer leg / red)", ""), ("GND", "−", "gnd")])


def motor_detail():
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.set_xlim(0, 82); ax.set_ylim(0, 46); ax.axis("off")
    # IRF540 front view
    ax.add_patch(Rectangle((4, 18), 14, 16, fc="white", ec="black", lw=1.4))
    ax.add_patch(Rectangle((4, 34), 14, 5, fc="#d9d9d9", ec="black", lw=1.2))
    ax.add_patch(plt.Circle((11, 36.5), 1.2, fc="white", ec="black"))
    ax.text(11, 27, "IRF540\n(printed side\nfacing you)", ha="center", va="center", fontsize=7.5)
    for i, (x, p) in enumerate(zip([6.5, 11, 15.5], ["G", "D", "S"])):
        ax.plot([x, x], [18, 8], color="black", lw=2.2)
        ax.text(x, 6, p, ha="center", va="top", weight="bold")
    ax.text(11, 1.5, "Gate · Drain · Source", ha="center", fontsize=7.5)

    # Schematic
    X = 50
    ax.text(X, 43, "Uno 3.3V", ha="center", weight="bold")
    ax.text(X - 5, 39.5, "motor red wire", ha="right", fontsize=7)
    ax.plot([X, X], [42, 38], color="black")
    ax.add_patch(plt.Circle((X, 34), 4, fc="white", ec="black", lw=1.4))
    ax.text(X, 34, "M", ha="center", va="center", weight="bold", fontsize=11)
    ax.plot([X, X], [30, 24], color="black")
    # diode in parallel with motor
    ax.plot([X, X + 10, X + 10], [40, 40, 36.5], color="black")
    ax.plot([X + 10, X + 10, X], [31.5, 28, 28], color="black")
    ax.plot([X + 8, X + 12], [36.5, 36.5], color="black", lw=1.6)   # cathode bar (stripe)
    ax.fill([X + 8, X + 12, X + 10], [31.5, 31.5, 36.4], fc="white", ec="black", lw=1.2)
    ax.text(X + 13, 34, "1N4007\nstripe (bar) to 3.3V", fontsize=7.5, va="center")
    ax.text(X + 1, 26, "Drain", fontsize=7.5)
    ax.add_patch(Rectangle((X - 3, 16), 6, 8, fc="white", ec="black", lw=1.4))
    ax.text(X, 20, "IRF540", ha="center", va="center", fontsize=7)
    ax.plot([X, X], [16, 6], color="black")
    ax.text(X + 1, 11, "Source", fontsize=7.5)
    ax.text(X, 3.5, "GND", ha="center", weight="bold")
    ax.text(X - 5, 27, "motor blue/black wire", ha="right", fontsize=7)
    ax.plot([X - 3, X - 22], [20, 20], color="black")
    ax.text(X - 22.5, 20, "Uno D9", ha="right", va="center", weight="bold")
    ax.text(X - 12.5, 20.8, "Gate (220 Ω here if you have\na spare; a wire is fine)", ha="center", fontsize=6.8, va="bottom")
    ax.set_title("Step 3: vibration motor through the IRF540", fontsize=10, weight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "step3_motor.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    steps()
    motor_detail()
