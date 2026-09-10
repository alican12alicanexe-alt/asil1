# -*- coding: utf-8 -*-
"""Sonuc grafikleri. Butun sayilar gercek kosu ciktisi - hicbiri elle yazilmadi.

  express / stopping   scenarios/ring/_sweep_express.py, _sweep_headway.py
  convoy               scenarios/ring/_sweep_convoy.py [--stopping] --headway
  kuplaj metrikleri    run.py scenario-convoy[-stopping].yaml --log  (reason
                       sutununda "coupled to X" var ve ", uncoupled" yoksa
                       o tik kuplajli sayiliyor)
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from style import NAVY, SKY, ORANGE, INK, MUTED, GRID, quiet, save

SYS = [(u"Sabit blok", NAVY), (u"Hareketli blok", SKY), (u"Sanal kuplaj", ORANGE)]
EXPRESS = [139, 39, 32]          # s, tutulan en kisa aralik
STOPPING = [148, 78, 71]

PAPER = "#F4F6F9"


def tiles(ax, items):
    """Grafigin yanina buyuk sayi kutulari."""
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    n = len(items)
    h = (1.0 - 0.06 * (n - 1)) / n
    for i, (value, label, colour) in enumerate(items):
        y = 1.0 - (i + 1) * h - i * 0.06
        ax.add_patch(FancyBboxPatch(
            (0.02, y), 0.96, h, boxstyle="round,pad=0,rounding_size=0.04",
            facecolor=PAPER, edgecolor=GRID, linewidth=1.2))
        ax.text(0.5, y + h * 0.62, value, ha="center", va="center",
                fontsize=27, fontweight="bold", color=colour)
        ax.text(0.5, y + h * 0.22, label, ha="center", va="center",
                fontsize=11.5, color=MUTED)


def headway_chart(values, title, name, tile_items):
    fig = Figure(figsize=(13.2, 3.5))
    left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [2.5, 1]})
    y = range(len(values))
    left.barh(y, values, color=[c for _, c in SYS], height=0.62, zorder=3)
    top = max(values)
    for i, v in enumerate(values):
        left.text(v + top * 0.02, i, "%d s" % v, va="center", ha="left",
                  fontsize=19, fontweight="bold", color=SYS[i][1])
        left.text(top * 0.02, i, u"%.0f tren/saat" % (3600.0 / v), va="center",
                  ha="left", fontsize=11.5, color="white", zorder=4)
    left.set_yticks(list(y))
    left.set_yticklabels([n for n, _ in SYS], fontsize=14, color=INK)
    left.invert_yaxis()
    left.set_xlim(0, top * 1.20)
    left.set_xticks([])
    left.set_title(title, loc="left", pad=14)
    quiet(left, y_grid=False)
    left.spines["bottom"].set_visible(False)
    tiles(right, tile_items)
    fig.subplots_adjust(left=0.11, right=0.99, top=0.86, bottom=0.06, wspace=0.06)
    save(fig, name)


headway_chart(EXPRESS, u"Duraksız tur — tutulan en kısa aralık", "res-express",
              [(u"32 s", u"sanal kuplaj, en kısa aralık", ORANGE),
               (u"−18 %", u"hareketli bloğa göre", ORANGE),
               (u"112", u"tren / saat", INK)])
headway_chart(STOPPING, u"22 duruşlu tur — tutulan en kısa aralık", "res-stopping",
              [(u"71 s", u"sanal kuplaj, en kısa aralık", ORANGE),
               (u"−9 %", u"hareketli bloğa göre", ORANGE),
               (u"51", u"tren / saat", INK)])


# ------------------------------------------------------- karsilastirmali ozet
fig = Figure(figsize=(13.2, 4.0))
ax, tile = fig.subplots(1, 2, gridspec_kw={"width_ratios": [2.45, 1]})
W = 0.26
for j, (name, colour) in enumerate(SYS):
    xs = [i + (j - 1) * W for i in range(2)]
    vals = [EXPRESS[j], STOPPING[j]]
    ax.bar(xs, vals, W, color=colour, zorder=3, label=name)
    for x, v in zip(xs, vals):
        ax.text(x, v + 4, "%d" % v, ha="center", va="bottom", fontsize=14,
                fontweight="bold", color=colour)
ax.set_xticks(range(2))
ax.set_xticklabels([u"Duraksız tur", u"22 duruşlu tur"], fontsize=14)
ax.set_ylabel(u"tutulan en kısa aralık, s")
ax.set_ylim(0, 178)
ax.legend(loc="upper center", ncol=3, fontsize=12)
ax.set_title(u"Üç sistem, iki işletme biçimi", loc="left", pad=14)
quiet(ax)
tiles(tile, [(u"%18", u"duraksız turda VC kazancı", ORANGE),
             (u"%9", u"duraklamalı turda VC kazancı", ORANGE),
             (u"%47", u"hareketli bloğun sabit bloğa\ngöre kazancı (duraklamalı)", SKY)])
fig.subplots_adjust(left=0.075, right=0.99, top=0.86, bottom=0.10, wspace=0.06)
save(fig, "res-summary")
