# -*- coding: utf-8 -*-
"""Bozucu etki - iki ayri grafik.

  res-disruption-a.png   UC BOZUCU ETKI, AYNI TARIFEDE (ikisi de 78 s).
                         Isletmecinin bugun hareketli blokla kostugu tarife;
                         sanal kuplaj takilirsa yeniden zamanlama yapmadan
                         hangi olayda ne kazanir?
  res-disruption-b.png   HER SISTEM KENDI TUM-YESIL SINIRINDA: MB 78 s,
                         VC 71 s. Ikisinde de pay kalmamis - kontrol deneyi.

Ikisi de TOPLAM gecikmeyi olcer (birincil + yayilan), cunku hiz kisitlamasi
icin yayilan/birincil ayrimi anlamsiz: kisitlama HATTIN kendisine uygulaniyor,
uzerinden gecen her tren dogrudan etkilenmis sayiliyor ve rapor tum gecikmeyi
birincil gosteriyor. Toplam, ucunde de ayni seyi olcen tek buyukluk.

Kapi arizasinin yayilan gecikmesi ayrica kayda deger ve konusmaci notunda:
MB 982 s, VC 829 s - %16 daha az. Buradaki %13 toplam uzerinden.

SAYILAR:
    python run.py presentation/ring/scenario-78-dwell.yaml --propagation \
        --system etcs_moving_block          -> birincil 180 + yayilan 982
    python run.py presentation/ring/scenario-78-tsr.yaml --headless \
        --system etcs_moving_block          -> varis gecikmeleri toplami 455
    ... ayni sekilde virtual_coupling ve -both.yaml / 71 s icin.

Hiz kisitlamasi -tsr dosyalarinda --headless ile olculur, --propagation ile
degil: yukaridaki sebeple rapor her seyi birincil sayar.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku

from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch
from style import SKY, ORANGE, INK, MUTED, GRID, quiet, save

#: toplam gecikme, s.  (hiz kisitlamasi, kapi arizasi, ikisi birden)
MB78 = (455, 1162, 1162)
VC78 = (455, 1009, 1020)
#: kendi sinirinda - hiz kisitlamasi satiri karsilastirilabilir degil
MB78_CTL = (1162, 1162)
VC71_CTL = (1156, 1156)

TOP = 1600.0          # iki grafikte de ayni eksen
W = 0.30

FIGURES = [
    ("res-disruption-a",
     u"Üç bozucu etki, aynı tarifede — ikisi de 78 s",
     u"Yeniden zamanlama yok, yalnızca araç donanımı değişiyor",
     [u"Hız kısıtlaması\n40 km/h, 3 km, 1 saat",
      u"Kapı arızası\n90 s aşım",
      u"İkisi birden"],
     [(u"Hareketli blok", MB78, SKY), (u"Sanal kuplaj", VC78, ORANGE)]),
    ("res-disruption-b",
     u"Her sistem kendi sınırında — 78 s / 71 s",
     u"İkisinde de pay yok: sanal kuplaj %9 daha sık tren koşuyor",
     [u"Kapı arızası\n90 s aşım", u"İkisi birden"],
     [(u"Hareketli blok  78 s", MB78_CTL, SKY),
      (u"Sanal kuplaj  71 s", VC71_CTL, ORANGE)]),
]

for name, title, subtitle, cats, series in FIGURES:
    fig = Figure(figsize=(6.9 if len(cats) == 3 else 6.0, 4.8))
    ax = fig.subplots()

    for si, (label, vals, colour) in enumerate(series):
        xs = [i + (si - 0.5) * W for i in range(len(cats))]
        ax.bar(xs, vals, W, color=colour, zorder=3, label=label)
        for x, v in zip(xs, vals):
            ax.text(x, v + TOP * 0.015, "%d s" % v, ha="center", va="bottom",
                    fontsize=13, fontweight="bold", color=colour)

    # Farki iki cubugu birlestiren bir okla goster: hangi cifte ait oldugu
    # boylece belirsiz kalmiyor. Etiket okun ustunde, ortada.
    for i in range(len(cats)):
        a, b = series[0][1][i], series[1][1][i]
        y = max(a, b) + TOP * 0.115
        ax.add_patch(FancyArrowPatch((i - 0.5 * W, y), (i + 0.5 * W, y),
                                     arrowstyle="-|>", mutation_scale=12,
                                     color=INK, linewidth=1.3, zorder=4,
                                     shrinkA=0, shrinkB=0))
        text = (u"fark yok" if a == b else
                u"%+d s   %%%.0f" % (b - a, abs((b - a) / float(a) * 100.0)))
        ax.text(i, y + TOP * 0.022, text, ha="center", va="bottom",
                fontsize=12.5, fontweight="bold", color=INK)

    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, fontsize=11)
    ax.set_ylabel(u"toplam gecikme, s")
    ax.set_ylim(0, TOP)
    ax.set_title(title, loc="left", pad=30)
    ax.text(0.0, 1.075, subtitle, transform=ax.transAxes, fontsize=10.5,
            color=MUTED, va="bottom")
    # Gosterge eksenin altinda: ust kose fark etiketlerinin yeri.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.185),
              ncol=2, fontsize=11)
    quiet(ax)
    if len(cats) == 2:
        ax.text(0.5, -0.375, u"Hız kısıtlaması bu karşılaştırmada yok: iki tarife\n"
                            u"kısıtlamaya farklı sayıda tren sokuyor.",
                transform=ax.transAxes, fontsize=9.5, color=MUTED,
                ha="center", va="top", style="italic")
    fig.subplots_adjust(left=0.135, right=0.98, top=0.80,
                        bottom=0.29 if len(cats) == 3 else 0.40)
    save(fig, name)
