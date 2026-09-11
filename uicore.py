# -*- coding: utf-8 -*-
"""Arayuzlerin ortak yani: senaryo bulma, kosu, olcekleme, palet.

ui_tk.py ve ui_qt.py ayni hesabi yapiyor, sadece farkli bir araca ciziyor.
Burada ne tkinter var ne Qt - ikisi de bunu ice aktariyor.
"""
import os
import sys

#: PyInstaller ile paketlendiginde senaryolar gecici bir klasore aciliyor ve
#: __file__ artik depoyu gostermiyor; _MEIPASS o klasoru veriyor.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from trainsim.analysis import kpi, trace                       # noqa: E402
from trainsim.core import signalling                           # noqa: E402
from trainsim.scenario.loader import build_simulation, load_scenario   # noqa: E402

COL = {name: index for index, name in enumerate(trace.COLUMNS)}
#: Her besinci benzetim saniyesi bir tren grafigi icin fazlasiyla yeterli.
SAMPLE_S = 5.0

TURKISH = {
    "fixed_block_3aspect": "Sabit blok (3 aspektli)",
    "etcs_l1": "ETCS Seviye 1",
    "etcs_l2": "ETCS Seviye 2",
    "etcs_hybrid_l3": "ETCS Hibrit Seviye 3",
    "etcs_moving_block": "Hareketli blok (ETCS L3)",
    "virtual_coupling": "Sanal kuplaj",
}

# ------------------------------------------------------------------- palet
# Sunumun paleti: grafikler, slaytlar ve arayuz ayni dili konusuyor.

INK = "#1D2A4D"        # kenar menu, baslik metni
INK_SOFT = "#2C3A63"   # kenar menude bir tik acik - ayirici yerine
NAVY = "#355FA8"       # sabit blok
SKY = "#58B0E8"        # hareketli blok
ORANGE = "#E8871F"     # sanal kuplaj, vurgu
ORANGE_DIM = "#C9741A"
MUTED = "#5B6478"
GRID = "#D6DAE3"
PAPER = "#F4F6F9"      # icerik zemini
CARD = "#FFFFFF"
STRIPE = "#F7F9FC"
ON_INK = "#C7D0E6"     # koyu zemindeki ikincil metin

TRACK_COLOURS = [NAVY, SKY, ORANGE, MUTED, "#7B9FD4", "#9AD0F2", "#F0A855",
                 "#2A4478"]


def scenario_paths():
    """scenarios/ altindaki her scenario*.yaml, {etiket: yol}."""
    found = {}
    root = os.path.join(HERE, "scenarios")
    for railway in sorted(os.listdir(root)):
        directory = os.path.join(root, railway)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if filename.startswith("scenario") and filename.endswith(".yaml"):
                found["%s / %s" % (railway, filename[:-5])] = os.path.join(
                    directory, filename)
    return found


def mmss(seconds):
    if not seconds:
        return "-"
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def run_one(path, name, duration_s, as_fitted):
    """Tek sistem, tek kosu. Senaryo her seferinde yeniden okunuyor: bir
    sinyalizasyon sistemi durum tutabilir, tarife de bir oncekinden bir sey
    tasimamali."""
    scenario = load_scenario(path)
    scenario.signalling_spec = {"system": name}
    if not as_fitted:
        signalling.fit_timetable(scenario.timetable, name)
        scenario.driver_config = signalling.fit_driver(scenario.driver_config, name)
    sim = build_simulation(scenario,
                           {"duration_s": duration_s} if duration_s else {})
    recorder = trace.TraceRecorder(interval_s=SAMPLE_S)
    sim.step_hooks.append(recorder)
    return {"name": name, "metrics": kpi.measure(sim), "rows": recorder.rows}


# ------------------------------------------------------------------- grafik

def plot_box(width, height):
    """Cizim alani: (sol, ust, sag, alt). Eksen etiketlerine yer birakiyor."""
    return 58, 30, max(62, width - 18), max(36, height - 34)


def scaler(lo, hi, start, end):
    """Veri araligini piksel araligina tasiyan fonksiyon. Sifir genislikteki
    aralik ortaya dusuyor - tek noktali bir kosu boluyordu."""
    span = hi - lo
    if span <= 0:
        middle = (start + end) / 2.0
        return lambda value: middle
    return lambda value: start + (value - lo) * (end - start) / span


def series(rows):
    """Trace satirlarindan tren basina [(dakika, km)] ve sinirlar.

    Zaman kosunun basindan sayiliyor, mesafe km'ye ceviriliyor - ciziciye
    giden sey bu, piksel hesabi cizicinin isi."""
    raw = {}
    for row in rows:
        raw.setdefault(row[COL["train"]], []).append(
            (row[COL["time_s"]], row[COL["chainage_m"]]))
    if not raw:
        return {}, (0.0, 0.0, 0.0, 0.0)
    origin = min(point[0] for points in raw.values() for point in points)
    paths = dict((train, [((t - origin) / 60.0, c / 1000.0) for t, c in points])
                 for train, points in raw.items())
    xs = [x for points in paths.values() for x, _ in points]
    ys = [y for points in paths.values() for _, y in points]
    return paths, (min(xs), max(xs), min(ys), max(ys))


def selfcheck():
    """Olceklemenin iki ucu, sifir genislikteki aralik, bos kosu."""
    to_x = scaler(0.0, 10.0, 100.0, 200.0)
    assert to_x(0.0) == 100.0 and to_x(10.0) == 200.0 and to_x(5.0) == 150.0
    flat = scaler(3.0, 3.0, 100.0, 200.0)
    assert flat(3.0) == 150.0, "tek noktali kosu bolme hatasi vermemeli"
    to_y = scaler(0.0, 10.0, 300.0, 20.0)                  # dikeyde ters
    assert to_y(0.0) == 300.0 and to_y(10.0) == 20.0
    left, top, right, bottom = plot_box(760, 320)
    assert left < right and top < bottom
    assert plot_box(10, 10)[0] < plot_box(10, 10)[2], "kucuk pencerede de cizilebilmeli"

    blank = [None] * len(trace.COLUMNS)

    def row(train, time_s, chainage_m):
        made = list(blank)
        made[COL["train"]] = train
        made[COL["time_s"]] = time_s
        made[COL["chainage_m"]] = chainage_m
        return made

    paths, (lo_x, hi_x, lo_y, hi_y) = series(
        [row("A", 600.0, 0.0), row("A", 660.0, 1500.0), row("B", 720.0, 300.0)])
    assert sorted(paths) == ["A", "B"]
    assert paths["A"][0] == (0.0, 0.0), "zaman kosunun basindan sayilmali"
    assert paths["A"][1] == (1.0, 1.5), "saniye dakikaya, metre km'ye"
    assert (lo_x, hi_x, lo_y, hi_y) == (0.0, 2.0, 0.0, 1.5)
    assert series([]) == ({}, (0.0, 0.0, 0.0, 0.0)), "bos kosu patlamamali"
    print("uicore selfcheck tamam")


if __name__ == "__main__":
    selfcheck()
