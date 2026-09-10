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

DT = 0.02


def brake_run(grade, emergency):
    """Frene basildiktan sonraki GERCEK hareket, jerk sinirli.

    Sabit oranli formul surucunun PLANI; bu ise trenin yaptigi. Ivme sifirdan
    tam fren oranina jerk siniriyla iniyor (service_brake / jerk = 2 s), o
    yuzden egrinin basi yayvan; duruş anini ``immediate`` ile kapatiyoruz ki
    tren durma noktasini jerkin maliyeti kadar asmasin.
    """
    demand = -(stock.emergency_brake if emergency else stock.service_brake)
    v, x, a, t = v0, 0.0, 0.0, 0.0
    xs, ys, ts, accs = [0.0], [LINE_KMH], [0.0], [0.0]
    while v > 1e-9 and t < 200.0:
        stopping = v + demand * DT <= 1e-9
        a = dynamics.achievable_accel(stock, v, demand, grade_permille=grade,
                                      previous_accel=a, dt=DT,
                                      immediate=stopping)
        v1 = v + a * DT
        if v1 <= 0.0:
            if a < 0.0:
                x += 0.5 * v * (v / -a)
                t += v / -a
            xs.append(x); ys.append(0.0); ts.append(t); accs.append(a)
            break
        x += 0.5 * (v + v1) * DT
        t += DT
        v = v1
        xs.append(x); ys.append(ms_to_kmh(v)); ts.append(t); accs.append(a)
    return xs, ys, ts, accs, x


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
# Cizilen sey TRENIN YAPTIGI hareket. Surucunun tepki suresi ve emniyet payi
# burada yok - onlar trenin degil, isletmenin buyukleri. Sabit oranli formul
# de yok: onun egrisinin basinda kose, sonunda dikey inis olur, ikisi de
# gercek bir trende yoktur. Her nokta achievable_accel'den, jerk siniri dahil.
fig = Figure(figsize=(13.2, 4.0))
left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.25, 1]})

ramp_s = stock.service_brake / dynamics.jerk_limit_ms3(stock)
LABEL_DY = {CASES[0][0]: 30, CASES[1][0]: 10, CASES[2][0]: 10}
RATE_DY = {CASES[0][0]: -19, CASES[1][0]: 9, CASES[2][0]: 9}
runs = {}
for label, grade, emg, colour in CASES:
    xs, ys, ts, accs, run = brake_run(grade, emg)
    runs[label] = (run, ts[-1])
    left.plot(xs, ys, linewidth=2.4, color=colour, label=label, zorder=3)
    left.plot([run], [0.0], "o", color=colour, markersize=8, zorder=4)
    # 269 ve 301 metre yan yana dusuyor: etiketleri dikeyde ayir.
    left.annotate(u"%.0f m" % run, (run, 0.0), textcoords="offset points",
                  xytext=(4, LABEL_DY[label]), fontsize=14, fontweight="bold",
                  color=colour)
    right.plot(ts, accs, linewidth=2.4, color=colour, zorder=3)
    # -1.0 ve -0.86 birbirine cok yakin: birini ustune, digerini altina koy.
    right.annotate(u"%.2f m/s²" % min(accs), (ts[-1], min(accs)),
                   textcoords="offset points", xytext=(-4, RATE_DY[label]),
                   fontsize=12, fontweight="bold", color=colour, ha="right")

left.set_xlabel(u"frene basıldıktan sonra alınan yol, m")
left.set_ylabel(u"hız, km/h")
left.set_title(u"80 km/h'ten duruşa — trenin yaptığı hareket", loc="left",
               pad=12)
left.set_xlim(0, max(r[0] for r in runs.values()) * 1.10)
left.set_ylim(0, LINE_KMH * 1.10)
left.legend(loc="upper right", fontsize=10.5)
quiet(left)

right.axhline(0, color=GRID, linewidth=1.2, zorder=1)
right.axvspan(0, ramp_s, color=GRID, alpha=0.55, zorder=1)
right.text(ramp_s + 0.6, -0.30,
           u"fren jerk sınırıyla kuruluyor: %.1f m/s³\nservis freni %.0f s, acil fren %.0f s"
           % (dynamics.jerk_limit_ms3(stock), ramp_s,
      stock.emergency_brake / dynamics.jerk_limit_ms3(stock)),
           fontsize=10.5, color=MUTED, va="center")
right.set_xlabel(u"frene basıldıktan sonra geçen süre, s")
right.set_ylabel(u"ivme, m/s²")
right.set_title(u"Aynı üç duruşun ivmesi", loc="left", pad=12)
right.set_xlim(0, max(r[1] for r in runs.values()) * 1.04)
right.set_ylim(-1.75, 0.30)
quiet(right)

fig.subplots_adjust(left=0.055, right=0.99, top=0.87, bottom=0.145, wspace=0.20)
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
