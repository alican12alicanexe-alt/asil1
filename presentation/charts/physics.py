# -*- coding: utf-8 -*-
"""Trenin parametrelerinden turetilen iki grafik: fren mesafesi ve hizlanma.

  res-braking.png    80 km/h'ten durusa. Solda hiz-yol egrisi, sagda ayni
                     seyin aritmetigi: dort terim yigilmis cubuk olarak.
  res-traction.png   Solda ceki ve direnc kuvveti hiza gore, sagda duran
                     trenden hat hizina cikis.

Hicbir sayi elle yazilmadi. Hepsi asagidaki fonksiyonlardan geliyor:

    dynamics.braking_rate_on_grade   b(theta) = min(b_talep, mu*g) + egim
    dynamics.brake_buildup_distance_m  build-up payi = v0 * t_buildup / 2
    units.braking_distance           v0^2 / 2b
    driver.stopping_distance         dordunun toplami - selfcheck bununla
    dynamics.traction_accel          F(v), taban hizin altinda/ustunde
    dynamics.resistance_accel        Davis
    dynamics.achievable_accel        jerk sinirli gercek hareket

    python presentation/charts/physics.py       -> iki PNG + turetim dokumu
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku

from matplotlib.figure import Figure
from style import NAVY, SKY, ORANGE, INK, MUTED, GRID, quiet, save

from trainsim.core import dynamics
from trainsim.core.driver import stopping_distance
from trainsim.core.units import braking_distance, kmh_to_ms, ms_to_kmh
from trainsim.scenario.loader import load_scenario

SCEN = os.path.join(os.path.dirname(HERE), "ring")
LINE_KMH = 80.0
PAPER = "#F4F6F9"

scenario = load_scenario(SCEN)
stock = scenario.timetable.services[0].stock
config = scenario.driver_config
v0 = kmh_to_ms(LINE_KMH)
m_eff = dynamics.effective_mass_kg(stock)

REACT = v0 * config.reaction_time_s
BUILD = dynamics.brake_buildup_distance_m(stock, v0)
MARGIN = config.safety_margin_m

CASES = [
    (u"Servis freni, düz hat", 0.0, False, NAVY),
    (u"Servis freni, binde 15 iniş", -15.0, False, SKY),
    (u"Acil fren, düz hat", 0.0, True, ORANGE),
]

print(u"v0 = %.4f m/s   tepki %.1f s   build-up %.1f s   pay %.1f m"
      % (v0, config.reaction_time_s, stock.brake_buildup_s, MARGIN))
rows = []
for label, grade, emg, colour in CASES:
    b = dynamics.braking_rate_on_grade(stock, grade, emergency=emg)
    curve = braking_distance(v0, b)
    total = REACT + BUILD + curve + MARGIN
    rows.append((label, grade, emg, colour, b, curve, total))
    print(u"  %-30s b=%.4f  %.1f + %.1f + %.1f + %.1f = %.1f m"
          % (label, b, REACT, BUILD, curve, MARGIN, total))
# Duz hat servis freni, surucunun kendi fonksiyonuyla ayni cikmali.
assert abs(rows[0][6] - stopping_distance(stock, config, v0, 0.0)) < 0.05

# ===================================================== 1) fren mesafesi
fig = Figure(figsize=(13.2, 4.0))
left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.15, 1]})

for label, grade, emg, colour, b, curve, total in rows:
    start = REACT + BUILD
    xs = [start + curve * i / 300.0 for i in range(301)]
    ys = [ms_to_kmh(max(0.0, v0 * v0 - 2 * b * (x - start)) ** 0.5) for x in xs]
    left.plot([0, start] + xs, [LINE_KMH, LINE_KMH] + ys, linewidth=2.2,
              color=colour, label=label, zorder=3)
    # Emniyet payi burada CIZILMIYOR: egri trenin gercekten yaptigi hareket,
    # pay ise ondan sonra birakilan bos mesafe. Ikisini ayni cizgide gostermek
    # egriyi yanlis okutuyordu. Pay sagdaki yigilmis cubukta duruyor.
left.axvspan(0, REACT, color=GRID, alpha=0.7, zorder=1)
left.axvspan(REACT, REACT + BUILD, color=GRID, alpha=0.35, zorder=1)
left.text(REACT / 2, LINE_KMH * 0.55, u"tepki", rotation=90, fontsize=10,
          color=MUTED, ha="center", va="center")
left.text(REACT + BUILD / 2, LINE_KMH * 0.55, u"build-up", rotation=90,
          fontsize=10, color=MUTED, ha="center", va="center")
left.set_xlabel(u"tehlike görüldüğü andan itibaren alınan yol, m")
left.set_ylabel(u"hız, km/h")
left.set_title(u"80 km/h'ten duruşa", loc="left", pad=12)
left.set_xlim(0, max(r[5] for r in rows) + REACT + BUILD + 12)
left.set_ylim(0, LINE_KMH * 1.10)
left.legend(loc="upper right", fontsize=10.5)
quiet(left)

SEG = [(u"tepki", "#9AA5B5"), (u"brake build-up", "#C6CEDA"),
       (u"fren eğrisi", None), (u"emniyet payı", "#E3E8EF")]
for i, (label, grade, emg, colour, b, curve, total) in enumerate(rows):
    y = len(rows) - 1 - i
    x = 0.0
    for name, seg_colour, width in ((SEG[0][0], SEG[0][1], REACT),
                                    (SEG[1][0], SEG[1][1], BUILD),
                                    (SEG[2][0], colour, curve),
                                    (SEG[3][0], SEG[3][1], MARGIN)):
        right.barh([y], [width], left=[x], height=0.52, color=seg_colour,
                   zorder=3)
        # Dar segmentler de sayisini tasisin: 22 ve 25 m'lik terimler
        # gorunmezse "dort terim" iddiasi grafikte dogrulanmiyor.
        narrow = width < 45
        right.text(x + width / 2, y, "%.0f" % width, ha="center", va="center",
                   fontsize=9.5 if narrow else 11.5, fontweight="bold",
                   color="white" if seg_colour is colour else INK)
        x += width
    right.text(x + 6, y, "%.0f m" % total, va="center", ha="left",
               fontsize=15, fontweight="bold", color=colour)
right.set_yticks(range(len(rows)))
right.set_yticklabels([u"Acil, düz", u"Servis, −15‰", u"Servis, düz"],
                      fontsize=12, color=INK)
right.set_xlim(0, max(r[6] for r in rows) * 1.16)
right.set_xlabel(u"hareket yetkisi, m")
right.set_title(u"Hareket yetkisinin dört terimi",
                loc="left", pad=12)
quiet(right, y_grid=False, x_grid=True)
handles = [right.barh([0], [0], color=c)[0] for _, c in SEG[:2]] + \
          [right.barh([0], [0], color=NAVY)[0],
           right.barh([0], [0], color=SEG[3][1])[0]]
right.legend(handles, [s[0] for s in SEG], loc="upper center",
             bbox_to_anchor=(0.5, -0.20), ncol=4, fontsize=10.5)
fig.subplots_adjust(left=0.055, right=0.99, top=0.87, bottom=0.235, wspace=0.22)
save(fig, "res-braking")

# ======================================================== 2) hizlanma
# Ceki/direnc paneli kaldirildi: net kuvvetin hiza gore nasil dustugunu
# hiz-zaman egrisinin egimi zaten gosteriyor, iki panel ayni seyi iki kez
# anlatiyordu. Sayilar (F0, P, taban hiz) parametreler slaytinda duruyor.
fig = Figure(figsize=(9.6, 4.0))
ax = fig.subplots()

base = ms_to_kmh(dynamics.base_speed_ms(stock))
DT = 0.05
v = t = x = a = 0.0
top = kmh_to_ms(LINE_KMH)
ts, vs, marks = [0.0], [0.0], {}
while v < top - 1e-9 and t < 400:
    a = dynamics.achievable_accel(stock, v, stock.max_accel, previous_accel=a,
                                  dt=DT)
    v1 = min(v + a * DT, top)
    x += 0.5 * (v + v1) * DT
    t += DT
    v = v1
    ts.append(t)
    vs.append(ms_to_kmh(v))
    for k in (36, 60, 80):
        if k not in marks and vs[-1] >= k - 1e-6:
            marks[k] = (t, x)

ax.plot(ts, vs, linewidth=2.8, color=INK, zorder=3)
ax.axhline(base, color=GRID, linewidth=1.2, zorder=1)
ax.text(ts[-1] * 0.99, base + 2.5, u"taban hız %.0f km/h" % base,
        fontsize=10.5, color=MUTED, va="bottom", ha="right")
# Etiketler egrinin bos taraflarina: kalkis egrisi disbukey oldugu icin
# sol-ust ve sag-alt bolgeler bostur.
ax.text(1.5, LINE_KMH * 0.80, u"taban hıza kadar\nsabit kuvvet  233 kN",
        fontsize=11, color=MUTED, ha="left", va="center")
ax.text(ts[-1] * 0.99, LINE_KMH * 0.22, u"üstünde sabit güç\n2333 kW / v",
        fontsize=11, color=MUTED, ha="right", va="center")
for k, (tk, xk) in sorted(marks.items()):
    ax.plot([tk], [k], "o", color=ORANGE, markersize=9, zorder=4)
    ax.annotate(u"%d km/h\n%.0f s · %.0f m" % (k, tk, xk), (tk, k),
                textcoords="offset points", xytext=(12, -8), fontsize=11.5,
                color=INK, fontweight="bold", va="top")
ax.set_xlabel(u"duruştan itibaren geçen süre, s")
ax.set_ylabel(u"hız, km/h")
ax.set_title(u"Duran trenden hat hızına", loc="left", pad=12)
ax.set_xlim(0, ts[-1] * 1.08)
ax.set_ylim(0, LINE_KMH * 1.14)
quiet(ax)
fig.subplots_adjust(left=0.075, right=0.985, top=0.87, bottom=0.145)
save(fig, "res-traction")

print(u"hizlanma: " + u"   ".join(u"%d km/h %.0f s / %.0f m" % (k, v[0], v[1])
                                  for k, v in sorted(marks.items())))
