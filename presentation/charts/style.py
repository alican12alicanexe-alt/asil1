"""One look for every chart in the deck, in ASELSAN's own colours.

The three systems always get the same three hues in the same order - never
cycled, never reassigned - so a reader who learns the colours on one slide
reads every later slide without going back to the legend. The palette is the
brand's navy and orange, lightened until it passes the CVD and lightness
checks (validate_palette.js: worst adjacent pair dE 23.7).
"""
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, rcParams

NAVY = "#355FA8"      # sabit blok
SKY = "#58B0E8"       # hareketli blok
ORANGE = "#E8871F"    # sanal kuplaj
SYSTEMS = [("Sabit blok", NAVY), ("Hareketli blok", SKY), ("Sanal kuplaj", ORANGE)]

INK = "#1D2A4D"       # primary text, from the deck
MUTED = "#5B6478"     # secondary text, from the deck
GRID = "#D6DAE3"      # the deck's own rule colour
SURFACE = "#FFFFFF"

rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "font.family": "DejaVu Sans",
    "font.size": 13,
    "text.color": INK,
    "axes.labelcolor": MUTED,
    "axes.edgecolor": GRID,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "legend.frameon": False,
    "svg.fonttype": "none",
})


def quiet(ax, x_grid=False, y_grid=True):
    """Recessive frame: no box, one axis of hairline grid, ticks off."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    if y_grid:
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    if x_grid:
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)


FIGURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")


def save(fig, name):
    os.makedirs(FIGURES, exist_ok=True)
    path = os.path.join(FIGURES, "%s.png" % name)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    print("wrote", path)
    return path
