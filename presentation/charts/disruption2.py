# -*- coding: utf-8 -*-
"""Bozucu etki - iki ayri grafik, ikisi ayni olcumun iki okumasi.

  res-disruption-a.png   ayni tarife (ikisi de 78 s). Isletmecinin bugun
                         hareketli blokla kostugu tarife; sanal kuplaj
                         takilirsa yeniden zamanlama yapmadan ne kazanir?
  res-disruption-b.png   her sistem kendi tum-yesil sinirinda: MB 78 s,
                         VC 71 s. Ikisinde de pay kalmamis - kontrol deneyi.

Iki grafik ayni y eksenini kullanir, boylece yan yana ya da art arda
gosterildiginde cubuk yuksekligi karsilastirilabilir.

SAYILAR (run.py --propagation ciktisindaki "knock-on delay" satiri):

    python run.py presentation/ring/scenario-78-dwell.yaml --propagation \
        --system etcs_moving_block
    python run.py presentation/ring/scenario-78-dwell.yaml --propagation \
        --system virtual_coupling
    python run.py presentation/ring/scenario-71-dwell.yaml --propagation \
        --system virtual_coupling
    ... ayni sekilde -both.yaml icin

Kapi arizasi: R06 servisi Golbasi 2'de 90 s fazla bekliyor, birincil
gecikme 180 s. "Iki olay birden" satirinda hiz kisitlamasi da devrede
oldugu icin rapor tum gecikmeyi birincil sayar; orada okunan sey toplamdir.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku

from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch
from style import SKY, ORANGE, INK, MUTED, GRID, quiet, save

#            kapi arizasi (yayilan),  iki olay birden (toplam)
MB78 = (982, 1162)
VC78 = (829, 1020)
VC71 = (976, 1156)

CATS = [u"Kapı arızası\nyayılan gecikme", u"İki olay birden\ntoplam gecikme"]
TOP = 1600.0          # iki grafikte de ayni eksen
W = 0.30

FIGURES = [
    ("res-disruption-a",
     u"Aynı tarife — ikisi de 78 s",
     u"Yeniden zamanlama yok, yalnızca araç donanımı değişiyor",
     [(u"Hareketli blok", MB78, SKY), (u"Sanal kuplaj", VC78, ORANGE)]),
    ("res-disruption-b",
     u"Her sistem kendi sınırında — 78 s / 71 s",
     u"İkisinde de pay yok: sanal kuplaj %9 daha sık tren koşuyor",
     [(u"Hareketli blok  78 s", MB78, SKY), (u"Sanal kuplaj  71 s", VC71, ORANGE)]),
]

for name, title, subtitle, series in FIGURES:
    fig = Figure(figsize=(6.6, 4.8))
    ax = fig.subplots()

    for si, (label, vals, colour) in enumerate(series):
        xs = [i + (si - 0.5) * W for i in range(len(CATS))]
        ax.bar(xs, vals, W, color=colour, zorder=3, label=label)
        for x, v in zip(xs, vals):
            ax.text(x, v + TOP * 0.015, "%d s" % v, ha="center", va="bottom",
                    fontsize=13.5, fontweight="bold", color=colour)

    # Farki iki cubugu birlestiren bir okla goster: hangi ciftе ait oldugu
    # boylece belirsiz kalmiyor. Etiket okun ustunde, ortada.
    for i in range(len(CATS)):
        a, b = series[0][1][i], series[1][1][i]
        y = max(a, b) + TOP * 0.115
        ax.add_patch(FancyArrowPatch((i - 0.5 * W, y), (i + 0.5 * W, y),
                                     arrowstyle="-|>", mutation_scale=13,
                                     color=INK, linewidth=1.3, zorder=4,
                                     shrinkA=0, shrinkB=0))
        ax.text(i, y + TOP * 0.022,
                u"%+d s   %%%.0f" % (b - a, abs((b - a) / float(a) * 100.0)),
                ha="center", va="bottom", fontsize=13, fontweight="bold",
                color=INK)

    ax.set_xticks(range(len(CATS)))
    ax.set_xticklabels(CATS, fontsize=11.5)
    ax.set_ylabel(u"gecikme, s")
    ax.set_ylim(0, TOP)
    ax.set_title(title, loc="left", pad=30)
    ax.text(0.0, 1.075, subtitle, transform=ax.transAxes, fontsize=11,
            color=MUTED, va="bottom")
    # Gosterge eksenin altinda: ust kose fark etiketlerinin yeri.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.155),
              ncol=2, fontsize=11.5)
    quiet(ax)
    fig.subplots_adjust(left=0.135, right=0.98, top=0.80, bottom=0.27)
    save(fig, name)
