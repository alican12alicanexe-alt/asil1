# -*- coding: utf-8 -*-
"""Test aginin semasi. Istasyon adlari ve km'leri infrastructure.yaml'dan.

Cizim olcekli degil, topolojik: cift hatli kapali cevrim, iki ucunda donus
kavisi. Istasyonlar km'lerine gore yerlestirildi, yani aralarindaki oran
gercek.
"""
import re
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku
from matplotlib.figure import Figure
from matplotlib.patches import Arc, FancyArrowPatch
from style import NAVY, SKY, ORANGE, INK, MUTED, GRID, save

INFRA = os.path.join(os.path.dirname(HERE), "ring",
                     "infrastructure.yaml")
text = open(INFRA, encoding="utf-8").read()
STATIONS = [(m.group(1), float(m.group(2))) for m in
            re.finditer(r'name:\s*"([^"]+)",\s*km:\s*([\d.]+)', text)]
assert len(STATIONS) == 11, len(STATIONS)

LO, HI = 0.6, 35.4          # cevrimin dondugu km'ler (HS_WEST / HS_EAST)
X0, X1 = 0.10, 0.90         # cizimdeki karsiliklari
UP, DN = 0.66, 0.34


def px(km):
    return X0 + (X1 - X0) * (km - LO) / (HI - LO)


fig = Figure(figsize=(13.2, 3.4))
ax = fig.subplots()
ax.set_xlim(0, 1); ax.set_ylim(0.02, 1.0); ax.axis("off")

for y, colour in ((UP, NAVY), (DN, SKY)):
    ax.plot([X0, X1], [y, y], color=colour, linewidth=4.0, zorder=2,
            solid_capstyle="round")
r = (UP - DN) / 2.0
for cx, t1, t2, label, ha in ((X1, -90, 90, "HS_EAST", "left"),
                              (X0, 90, 270, "HS_WEST", "right")):
    ax.add_patch(Arc((cx, (UP + DN) / 2.0), r * 2 * 0.62, r * 2, theta1=t1,
                     theta2=t2, edgecolor=MUTED, linewidth=3.0, zorder=2))
    ax.text(cx + (0.035 if ha == "left" else -0.035), (UP + DN) / 2.0, label,
            fontsize=10.5, color=MUTED, ha=ha, va="center")

for i, (name, km) in enumerate(STATIONS):
    x = px(km)
    for y in (UP, DN):
        ax.plot([x], [y], "o", color="white", markersize=11, zorder=3)
        ax.plot([x], [y], "o", color=INK, markersize=7.5, zorder=4)
    ax.plot([x, x], [DN, UP], color=GRID, linewidth=1.0, zorder=1)
    ax.text(x, UP + 0.075, name, rotation=38, fontsize=10.5, color=INK,
            ha="left", va="bottom", rotation_mode="anchor")
    ax.text(x, DN - 0.055, "%.1f" % km, fontsize=9, color=MUTED, ha="center",
            va="top")

ax.text(0.50, UP - 0.045, u"UP  \u2192", fontsize=11.5,
        fontweight="bold", color=NAVY, ha="center", va="top")
ax.text(0.50, DN + 0.045, u"\u2190  DN", fontsize=11.5,
        fontweight="bold", color=SKY, ha="center", va="bottom")
ax.text(0.5, 0.055,
        u"70 km tur   ·   11 istasyon, her turda 22 duruş   ·   "
        u"km 0.6 – 35.4 arası çift hat   ·   900 m blok",
        fontsize=12, color=MUTED, ha="center", va="center")
fig.subplots_adjust(0.005, 0, 0.995, 1)
save(fig, "network")
