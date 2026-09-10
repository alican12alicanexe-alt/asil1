# -*- coding: utf-8 -*-
"""Konvoy davranisi: kuralin sonucu ve kuralin gercekte urettigi kuplaj.

SOL   kuralin aralik uzerindeki etkisi (_sweep_convoy.py --headway [--stopping])
SAG   kuplajin kendisi - iz dosyasindan sayilan gercek metrikler:
      run.py scenarios/ring/scenario-convoy.yaml --headless --log express.csv
      run.py scenarios/ring/scenario-convoy-stopping.yaml --headless --log ...
      Bir tik kuplajli sayiliyor: reason "coupled to X" iceriyor ve
      ", uncoupled" icermiyor. convoy_stats.py bunlari cikariyor.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku
from matplotlib.figure import Figure
from style import SKY, ORANGE, INK, MUTED, GRID, quiet, save

STEPS = [u"hat hızı\nserbest", u"70 km/h\nsınırlı", u"70 km/h + öne\nyaklaşınca serbest"]
HEADWAY = {u"Duraksız": [25, 23, 17], u"Duraklamalı": [69, 68, 63]}

#: iz dosyasindan sayildi - convoy_stats.py
COUPLED_PCT = {u"Duraksız": 14.5, u"Duraklamalı": 8.6}
EPISODE_S = {u"Duraksız": (31, 135), u"Duraklamalı": (19, 30)}
COLOUR = {u"Duraksız": ORANGE, u"Duraklamalı": SKY}

fig = Figure(figsize=(13.2, 4.1))
left, mid, right = fig.subplots(1, 3, gridspec_kw={"width_ratios": [1.5, 1, 1]})

# --------------------------------------------------- kuralin aralik etkisi
for route, vals in HEADWAY.items():
    base = vals[0]
    left.plot(range(3), [100.0 * v / base for v in vals], "-o", linewidth=2.6,
              markersize=9, color=COLOUR[route], label=route, zorder=3)
    for i, v in enumerate(vals):
        left.annotate("%d s" % v, (i, 100.0 * v / base),
                      textcoords="offset points",
                      xytext=(0, 12 if route == u"Duraksız" else -22),
                      ha="center", fontsize=12.5, fontweight="bold",
                      color=COLOUR[route])
left.set_xticks(range(3))
left.set_xticklabels(STEPS, fontsize=11.5)
left.set_ylabel(u"aralık, başlangıcın %'si")
left.set_ylim(60, 112)
left.legend(loc="lower left", fontsize=12)
left.set_title(u"Kuralın aralığa etkisi", loc="left", pad=14)
quiet(left)

# ------------------------------------------------------ kuplajli gecen sure
routes = list(COUPLED_PCT)
mid.bar(range(2), [COUPLED_PCT[r] for r in routes], 0.5,
        color=[COLOUR[r] for r in routes], zorder=3)
for i, r in enumerate(routes):
    mid.text(i, COUPLED_PCT[r] + 0.4, u"%%%.1f" % COUPLED_PCT[r], ha="center",
             va="bottom", fontsize=19, fontweight="bold", color=COLOUR[r])
mid.set_xticks(range(2)); mid.set_xticklabels(routes, fontsize=13)
mid.set_ylabel(u"koşma süresinin %'si")
mid.set_ylim(0, 19)
mid.set_title(u"Kuplajlı geçen süre", loc="left", pad=14)
quiet(mid)

# ------------------------------------------------------- kuplaj sureleri
W = 0.34
for j, key in enumerate((0, 1)):
    xs = [i + (j - 0.5) * W for i in range(2)]
    vals = [EPISODE_S[r][key] for r in routes]
    right.bar(xs, vals, W, color=[COLOUR[r] for r in routes],
              alpha=1.0 if key == 0 else 0.45, zorder=3)
    for x, v, r in zip(xs, vals, routes):
        right.text(x, v + 3, "%d s" % v, ha="center", va="bottom",
                   fontsize=12.5, fontweight="bold", color=COLOUR[r])
right.set_xticks(range(2)); right.set_xticklabels(routes, fontsize=13)
right.set_ylabel(u"tek kuplajın süresi, s")
right.set_ylim(0, 165)
right.text(0.02, 0.96, u"koyu: ortalama    açık: en uzun", transform=right.transAxes,
           fontsize=11, color=MUTED, va="top")
right.set_title(u"Kuplaj ne kadar sürüyor", loc="left", pad=14)
quiet(right)

fig.subplots_adjust(left=0.065, right=0.99, top=0.84, bottom=0.16, wspace=0.34)
save(fig, "res-convoy")
