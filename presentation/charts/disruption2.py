# -*- coding: utf-8 -*-
"""Bozucu etki - her sistem KENDI headway'inde, ve ayni tarifede.

Iki panel ayni olcumun iki okumasi:

  sol   ayni tarife (78 s). Operator bugun hareketli blokla bunu kosuyor;
        sanal kuplaj takilirsa hicbir sey yeniden zamanlanmadan ne kazanir?
  sag   her sistem kendi tum-yesil sinirinda. MB 78 s, VC 71 s. Ikisinde de
        pay kalmamis - kontrol deneyi budur.

Sayilar run.py --propagation ciktilarindan, scratchpad/dis altinda.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku
from matplotlib.figure import Figure
from style import SKY, ORANGE, INK, MUTED, GRID, quiet, save

#            kapi arizasi (yayilan),  iki olay birden (toplam)
MB78 = (982, 1162)
VC78 = (829, 1020)
VC71 = (976, 1156)

CATS = [u"Kapı arızası\nyayılan gecikme", u"İki olay birden\ntoplam gecikme"]

PANELS = [
    (u"Aynı tarife — ikisi de 78 s",
     [(u"Hareketli blok", MB78, SKY), (u"Sanal kuplaj", VC78, ORANGE)],
     u"Yeniden zamanlama yok: sadece cihaz değişiyor"),
    (u"Her sistem kendi sınırında — 78 s / 71 s",
     [(u"Hareketli blok  78 s", MB78, SKY), (u"Sanal kuplaj  71 s", VC71, ORANGE)],
     u"İkisinde de pay yok: %9 daha sık tren koşuyor"),
]

fig = Figure(figsize=(13.2, 4.2))
axes = fig.subplots(1, 2, sharey=True)
W = 0.34

for ax, (title, series, sub) in zip(axes, PANELS):
    for si, (name, vals, colour) in enumerate(series):
        xs = [i + (si - 0.5) * W for i in range(len(CATS))]
        ax.bar(xs, vals, W, color=colour, zorder=3,
               label=name if ax is axes[0] else None)
        for x, v in zip(xs, vals):
            ax.text(x, v + 22, "%d s" % v, ha="center", va="bottom",
                    fontsize=13, fontweight="bold", color=colour)
    # the delta, written where the eye already is
    for i in range(len(CATS)):
        a, b = series[0][1][i], series[1][1][i]
        pct = (b - a) / float(a) * 100.0
        ax.text(i, max(a, b) + 175, u"%+d s   %%%.0f" % (b - a, abs(pct)),
                ha="center", va="bottom", fontsize=12.5, color=INK,
                fontweight="bold")
    ax.set_xticks(range(len(CATS)))
    ax.set_xticklabels(CATS, fontsize=12)
    ax.set_title(title, loc="left", pad=26)
    ax.text(0.0, 1.045, sub, transform=ax.transAxes, fontsize=11.5,
            color=MUTED, va="bottom")
    ax.set_ylim(0, 1720)
    quiet(ax)

axes[0].set_ylabel(u"gecikme, s")
axes[0].legend(loc="upper left", fontsize=12.5)
fig.subplots_adjust(top=0.80, bottom=0.18, wspace=0.08)
save(fig, "disruption2")
