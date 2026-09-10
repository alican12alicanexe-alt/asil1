# -*- coding: utf-8 -*-
"""Hareket egrileri - sunum icin. Ayarlari ustteki AYAR blogundan degistir.

    python3 _plot_motion.py                 -> motion.png
    python3 _plot_motion.py cikti.png       -> cikti.png

Hicbir egri elle cizilmiyor. Her nokta simulatorun kendi fonksiyonlarindan
tik tik integre edilerek uretiliyor:

    dynamics.achievable_accel   bir tikte gercekten uygulanabilen ivme
                                (ceki egrisi, aderans, Davis direnci, egim
                                 ve JERK SINIRI hepsi bunun icinde)
    driver.stopping_distance    surucunun planladigi toplam yetki
                                (fren + kabarma + tepki + emniyet payi)

Bu yuzden grafikte sert kose yok: hem kalkista hem frende ivme jerk
siniriyla yumusuyor. Jerk siniri stock.brake_buildup_s'ten turetiliyor
(dynamics.jerk_limit_ms3), yani asagida BRAKE_BUILDUP_S'i buyutursen egri
gorunur sekilde yayvanlasir.
"""
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from trainsim.core import dynamics
from trainsim.core.driver import stopping_distance
from trainsim.core.units import kmh_to_ms, ms_to_kmh
from trainsim.scenario.loader import load_scenario

# ===================================================================== AYAR

SCENARIO   = REPO + "/scenarios/ring"   # tren ve surucu buradan okunuyor
LINE_KMH   = 80.0        # baslangic hizi / hat hizi
DT         = 0.05        # integrasyon adimi, s. Kucultursen egri yumusar
                         # (0.05 ile 0.5 arasi fark gozle gorulmez, 1.0 kirar)

# Fren durumlari: (etiket, egim binde, acil fren mi, renk)
# Egim negatifse inis. Sunumda ucten fazlasi kalabalik yapiyor.
CASES = [
    (u"Servis freni, düz hat",        0.0,  False, "#355FA8"),
    (u"Servis freni, binde 15 iniş", -15.0, False, "#58B0E8"),
    (u"Acil fren, düz hat",           0.0,  True,  "#E8871F"),
]

# Bu ikisini None birakirsan senaryodan okunur. Elle deneyecegin degerler:
REACTION_S      = None   # surucu tepki suresi, s.  ATO icin 0.0 yaz
SAFETY_MARGIN_M = None   # tehlike noktasindan once durulan pay, m
BRAKE_BUILDUP_S = None   # fren kabarma suresi, s. Jerk sinirini bu belirler:
                         # jerk = service_brake / brake_buildup_s
                         # 2.0 -> 0.5 m/s3,  4.0 -> 0.25 m/s3 (cok daha yayvan)

SHOW_PLANNED    = True   # surucunun PLANLADIGI sabit oranli egriyi de ciz
                         # (kesikli). Gercek hareketle arasindaki fark
                         # kabarma payinin ne ise yaradigini gosterir.
SHOW_BANDS      = True   # tepki ve emniyet payi bantlari
LABEL_OFFSETS   = [3.5, 12.5, 3.5]   # ust uste binen toplam etiketlerini ayir

FIGSIZE   = (13.2, 3.9)  # sunumdaki resim kutusunun oranina gore
DPI       = 220
XLIM      = None         # None -> otomatik.  Elle: (0, 420)

# ================================================================ /AYAR

INK, MUTED, GRID = "#1B2430", "#6B7684", "#DFE3E8"


def quiet(ax):
    """Cerceveyi kaldir, sadece yatay klavuz cizgileri birak."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=10.5, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.title.set_color(INK)
    ax.title.set_fontsize(13)
    ax.title.set_fontweight("bold")


def integrate(stock, v0, demand, grade, top=None, limit_s=600.0):
    """Tik tik gercek hareket. (t, x, v) listesi dondurur.

    demand > 0 kalkis, demand < 0 fren. Frende hiz sifira inince,
    kalkista ``top`` hizina varinca durur. achievable_accel jerk sinirini
    kendi uyguluyor - egrideki yumusakligin kaynagi bu.
    """
    t = x = 0.0
    v, a = v0, 0.0
    out = [(0.0, 0.0, v)]
    while t < limit_s:
        stopping = demand < 0 and v + demand * DT <= 1e-9
        a = dynamics.achievable_accel(stock, v, demand, grade_permille=grade,
                                      previous_accel=a, dt=DT,
                                      immediate=stopping)
        v1 = v + a * DT
        if v1 <= 0.0:
            if a < 0.0:                       # son kismi analitik kapat
                ts = v / -a
                x += 0.5 * v * ts
                t += ts
            out.append((t, x, 0.0))
            break
        if top is not None:
            v1 = min(v1, top)
        x += 0.5 * (v + v1) * DT
        t += DT
        v = v1
        out.append((t, x, v))
        if top is not None and v >= top - 1e-9:
            break
    return out


def main(target):
    scenario = load_scenario(SCENARIO)
    stock = scenario.timetable.services[0].stock
    config = scenario.driver_config

    if BRAKE_BUILDUP_S is not None:
        stock = stock.__class__(**dict(stock.__dict__,
                                       brake_buildup_s=BRAKE_BUILDUP_S))
    react_s = config.reaction_time_s if REACTION_S is None else REACTION_S
    margin = config.safety_margin_m if SAFETY_MARGIN_M is None else SAFETY_MARGIN_M

    v0 = kmh_to_ms(LINE_KMH)
    react_m = v0 * react_s

    fig = Figure(figsize=FIGSIZE)
    left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.55, 1]})

    # -------------------------------------------------- fren / hareket yetkisi
    far = 0.0
    for i, (label, grade, emergency, colour) in enumerate(CASES):
        demand = -(stock.emergency_brake if emergency else stock.service_brake)
        run = integrate(stock, v0, demand, grade)
        xs = [react_m + p[1] for p in run]
        ys = [ms_to_kmh(p[2]) for p in run]
        total = xs[-1] + margin
        far = max(far, total)

        left.plot([0.0, react_m] + xs, [LINE_KMH, LINE_KMH] + ys,
                  linewidth=2.2, color=colour, label=label, zorder=3)
        left.plot([xs[-1], total], [0, 0], linewidth=2.0, color=colour,
                  linestyle=(0, (2, 2)), zorder=3)
        left.plot([total], [0], "o", color=colour, markersize=8, zorder=4)
        dy = LABEL_OFFSETS[i] if i < len(LABEL_OFFSETS) else 3.5
        left.text(total, dy, "%.0f m" % total, color=colour, fontsize=12,
                  fontweight="bold", ha="center", va="bottom")

        if SHOW_PLANNED and grade == 0.0 and not emergency:
            # Surucunun planladigi egri: sabit oran + ayri bir kabarma payi.
            plan = stopping_distance(stock, config, v0, grade)
            rate = dynamics.braking_rate_on_grade(stock, grade,
                                                  emergency=emergency)
            build = dynamics.brake_buildup_distance_m(stock, v0)
            start = react_m + build
            span = plan - margin - start
            px = [start + span * k / 200.0 for k in range(201)]
            py = [ms_to_kmh(max(0.0, v0 * v0 - 2 * rate * (p - start)) ** 0.5)
                  for p in px]
            left.plot([0.0, start] + px, [LINE_KMH, LINE_KMH] + py,
                      linewidth=1.4, color=MUTED, linestyle=(0, (5, 3)),
                      zorder=2, label=u"Planlanan eğri (sabit oran)")
            far = max(far, plan)
            print("  planlanan  %6.1f m   (fren %.1f + kabarma %.1f + tepki "
                  "%.1f + pay %.1f)"
                  % (plan, plan - build - react_m - margin, build, react_m,
                     margin))
            print("  gercek     %6.1f m   jerk sinirli, %.1f s" % (total, run[-1][0]))

    if SHOW_BANDS:
        left.axvspan(0, react_m, color=GRID, alpha=0.55, zorder=1)
        left.text(react_m / 2.0, LINE_KMH * 0.58, u"tepki", rotation=90,
                  fontsize=11, color=MUTED, ha="center", va="center")
        left.text(react_m + 8, LINE_KMH * 0.58, u"fren eğrisi", fontsize=11,
                  color=MUTED)

    left.set_xlabel(u"tehlike görüldüğü andan itibaren alınan yol, m")
    left.set_ylabel(u"hız, km/h")
    left.set_title(u"Hareket yetkisi — %d km/h'ten duruşa" % LINE_KMH,
                   loc="left", pad=12)
    left.set_xlim(*(XLIM or (0, far * 1.06)))
    left.set_ylim(0, LINE_KMH * 1.10)
    left.legend(loc="upper right", fontsize=10.0, frameon=False)
    quiet(left)

    # ------------------------------------------------------------- kalkis
    top = kmh_to_ms(LINE_KMH)
    acc = integrate(stock, 0.0, stock.max_accel, 0.0, top=top)
    ts = [p[0] for p in acc]
    vs = [ms_to_kmh(p[2]) for p in acc]
    right.plot(ts, vs, linewidth=2.4, color=INK, zorder=3)

    base = ms_to_kmh(dynamics.base_speed_ms(stock))
    at_base = next(tt for tt, vv in zip(ts, vs) if vv >= base)
    right.axhline(base, color=GRID, linewidth=1.2, zorder=2)
    right.text(ts[-1] * 0.99, base + 2.0, u"taban hız %.0f km/h" % base,
               fontsize=10.5, color=MUTED, ha="right")
    right.plot([at_base], [base], "o", color="#E8871F", markersize=8, zorder=4)
    right.text(ts[-1] - 1.0, LINE_KMH - 12.0, u"%.0f km/h\n%.0f s · %.0f m"
               % (LINE_KMH, ts[-1], acc[-1][1]), fontsize=12,
               fontweight="bold", color=INK, ha="right", va="top")
    right.set_xlabel(u"duruştan itibaren geçen süre, s")
    right.set_ylabel(u"hız, km/h")
    right.set_title(u"Kalkış eğrisi", loc="left", pad=12)
    right.set_xlim(0, ts[-1] * 1.04)
    right.set_ylim(0, LINE_KMH * 1.10)
    quiet(right)

    fig.tight_layout(w_pad=3.0)
    fig.set_dpi(DPI)
    FigureCanvasAgg(fig).print_png(target)
    print("  kalkis     %6.1f m   %.0f s   (%d km/h'e)"
          % (acc[-1][1], ts[-1], LINE_KMH))
    print("yazildi: %s" % target)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "motion.png")
