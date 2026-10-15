"""Shared figure palette.

Set TS_MONO=1 for a black-and-white print palette; figures then go to
docs/figures/mono/ so the colour set stays untouched.
"""
from __future__ import annotations

import os

import matplotlib
from cycler import cycler

MONO = os.environ.get("TS_MONO") == "1"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIG = os.path.join(ROOT, "docs", "figures", "mono" if MONO else "")

if MONO:
    GREEN, ORANGE, GREY, BLUE, RED = "#000000", "#555555", "#999999", "#333333", "#000000"
    GRADE_COLORS = ["#e0e0e0", "#b3b3b3", "#808080", "#4d4d4d", "#000000"]
    LIGHT = "#c8c8c8"
    CMAP = "Greys"
    CMAP_COUNTS = "Greys"
    FILL, FILL_IO, FILL_DECIDE, FILL_STOP, FILL_GO = "#ffffff", "#f2f2f2", "#e6e6e6", "#d0d0d0", "#ffffff"
    EDGE = "#000000"
    BAR_EDGE = "black"
    HATCH = "////"
    LINESTYLES = ["-", "--", ":", "-."]
else:
    GREEN, ORANGE, GREY, BLUE, RED = "#0f8a5f", "#c26a1b", "#888888", "#2f6db5", "#b5392f"
    GRADE_COLORS = ["#9aa5a0", "#6fb59a", "#2f8f6b", "#d08a3a", "#b5392f"]
    LIGHT = "#9fd3bd"
    CMAP = "Greens"
    CMAP_COUNTS = "Blues"
    FILL, FILL_IO, FILL_DECIDE, FILL_STOP, FILL_GO = "#eef6f2", "#f3f3f3", "#fff3e3", "#fbe9e7", "#e2f3ec"
    EDGE = None
    BAR_EDGE = None
    HATCH = None
    LINESTYLES = ["-", "-", "-", "-"]

if MONO:
    # Defaults that would otherwise bring colour back (box-plot medians, unstyled lines).
    matplotlib.rcParams.update({
        "boxplot.medianprops.color": "black",
        "boxplot.flierprops.markeredgecolor": "black",
        "axes.prop_cycle": cycler(color=["#000000", "#555555", "#999999"]),
    })

# Words used in figure titles for the highlighted series.
CUE_WORD = "shaded" if MONO else "green"
DOSE_WORD = "vertical lines" if MONO else "orange"


def ls(i: int) -> str:
    """Line style for the i-th series: distinct in mono, solid in colour."""
    return LINESTYLES[i % len(LINESTYLES)]
