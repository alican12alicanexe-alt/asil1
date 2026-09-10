# -*- coding: utf-8 -*-
"""Egimli varyant: yukselti profili ve egimin neye mal oldugu.

Cevrim kapali oldugu icin egimler tur boyunca birbirini goturuyor - ayni on
egim listesi iki hatta da yazildigi ve pariteler ters yonde okundugu icin
yukselti insaat geregi kapaniyor. Olculen: UP +18.1 m, DN -18.1 m.

Bulgu: egim TUR SURESINE neredeyse hicbir sey eklemiyor (79:10 -> 79:13),
ama FREN MESAFESINE 39 metre ekliyor ve blok payini 61 metreden 22 metreye
dusuruyor. Egim zaman degil, PAY yiyor.

    python run.py scenarios/ring/scenario-grade.yaml --check     blok payi
    python stats.py scenarios/ring/scenario-grade.yaml           tur, egim
    python run.py scenarios/ring --check                         duz karsilik
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku

from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from style import NAVY, SKY, ORANGE, INK, MUTED, GRID, quiet, save
from trainsim.scenario.loader import load_scenario

SCEN = os.path.join(os.path.dirname(HERE), "ring", "scenario-grade.yaml")
PAPER = "#F4F6F9"

# Yukselti TUR BOYUNCA, trenin gittigi sirada integre ediliyor. Segmentleri
# km yonunde toplamak yanlis sonuc verir: DN hatti ters yonde gecildigi icin
# egimin isareti seyahat yonune gore okunmali. Trenin kendi yolu (path.entries)
# zaten seyahat sirasinda, o yuzden dogru olan bu.
train = load_scenario(SCEN).timetable.services[0].create_train()

# Egim profili: her segmentin binde egimi, tur boyunca alinan yola gore.
# Yukselti degil egim ciziliyor - bir demiryolu profilinde okunan buyukluk bu,
# ve ruling gradient dogrudan gorunuyor. Yukseltinin kapandigi ayrica
# hesaplaniyor (net degisim) ve not olarak yaziliyor.
xs, gs, marks = [], [], []
height, seen = 0.0, None
for e in train.path.entries:
    span = e.end_m - e.start_m
    height += span * e.segment.grade_permille / 1000.0
    xs.extend([e.start_m / 1000.0, e.end_m / 1000.0])
    gs.extend([e.segment.grade_permille, e.segment.grade_permille])
    if e.segment.track != seen:
        marks.append((e.start_m / 1000.0, e.segment.track))
        seen = e.segment.track

fig = Figure(figsize=(13.2, 4.0))
left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.7, 1]})

left.fill_between(xs, 0, gs, where=[g >= 0 for g in gs], color=NAVY, alpha=0.16,
                  step=None, zorder=2)
left.fill_between(xs, 0, gs, where=[g <= 0 for g in gs], color=ORANGE,
                  alpha=0.16, zorder=2)
left.plot(xs, gs, linewidth=1.8, color=INK, zorder=3)
left.axhline(0, color=GRID, linewidth=1.4, zorder=1)
for value, colour, va, dy in ((max(gs), NAVY, "bottom", 7),
                              (min(gs), ORANGE, "top", -7)):
    left.axhline(value, color=colour, linewidth=1.0, linestyle=(0, (5, 4)),
                 zorder=1)
    # Sagda hat gecis etiketleri var; ruling etiketleri sola.
    left.text(xs[0] + 0.4, value + (1.2 if dy > 0 else -1.2),
              u"ruling  %+d ‰" % value, fontsize=12, fontweight="bold",
              color=colour, ha="left", va=va)
for km, track in marks[1:]:
    left.axvline(km, color=GRID, linewidth=1.0, zorder=1)
    left.text(km + 0.5, max(gs) + 2.6, track, fontsize=10.5, color=MUTED)
left.set_xlabel(u"tur başından itibaren alınan yol, km")
left.set_ylabel(u"eğim, ‰")
left.set_title(u"Eğim profili — bir tur", loc="left", pad=26)
left.set_ylim(min(gs) - 5, max(gs) + 6)
left.text(0.0, 1.045,
          u"tur boyunca net yükselti değişimi  %+.2f m — çevrim kapanıyor"
          % height, transform=left.transAxes, fontsize=11, color=MUTED,
          va="bottom")
quiet(left)

TILES = [
    (u"79:10  →  79:13", u"tur süresi   (+3 s)", INK),
    (u"339  →  378 m", u"gereken blok boyu   (+39 m)", ORANGE),
    (u"+61  →  +22 m", u"en dar bloktaki pay", ORANGE),
]
right.set_xlim(0, 1); right.set_ylim(0, 1); right.axis("off")
h = (1.0 - 0.06 * 2) / 3.0
for i, (value, label, colour) in enumerate(TILES):
    y = 1.0 - (i + 1) * h - i * 0.06
    right.add_patch(FancyBboxPatch((0.02, y), 0.96, h,
                                   boxstyle="round,pad=0,rounding_size=0.04",
                                   facecolor=PAPER, edgecolor=GRID,
                                   linewidth=1.2))
    right.text(0.5, y + h * 0.62, value, ha="center", va="center", fontsize=21,
               fontweight="bold", color=colour)
    right.text(0.5, y + h * 0.22, label, ha="center", va="center", fontsize=11.5,
               color=MUTED)

fig.subplots_adjust(left=0.055, right=0.99, top=0.82, bottom=0.145, wspace=0.10)
save(fig, "res-gradient")

print(u"tur %.1f km   net yukselti %+.2f m   egim %+d .. %+d binde"
      % (xs[-1], height, min(gs), max(gs)))
