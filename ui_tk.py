# -*- coding: utf-8 -*-
"""Bir hatti birden fazla sinyalizasyon sistemi altinda kosturup karsilastir.

    python ui_tk.py

app.py ile ayni isi yapiyor, ama tarayici yok, sunucu yok, port yok, pip yok.
Sadece tkinter - Python'un kendi icinde geliyor. Kurulumun engellendigi ya da
localhost'un guvenlik duvarina takildigi bir makinede calisan tek surum bu.

Grafik de tkinter'in kendi Canvas'ina ciziliyor; matplotlib de gerekmiyor.

Kosular ayri bir is parcaciginda donuyor, sonuclar kuyrukla geri geliyor:
tek parcacikta kossaydi 12000 saniyelik bir tur boyunca pencere donardi.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

#: PyInstaller ile paketlendiginde senaryolar gecici bir klasore aciliyor ve
#: __file__ artik depoyu gostermiyor; _MEIPASS o klasoru veriyor.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from trainsim.analysis import kpi, trace                       # noqa: E402
from trainsim.core import signalling                           # noqa: E402
from trainsim.core.units import format_delay                   # noqa: E402
from trainsim.scenario.loader import (ScenarioError,           # noqa: E402
                                      build_simulation, load_scenario)

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

#: Sunumun paleti, sonra tekrar basa donuyor.
TRACK_COLOURS = ["#355FA8", "#58B0E8", "#E8871F", "#5B6478", "#7B9FD4",
                 "#9AD0F2", "#F0A855", "#2A4478"]
INK, MUTED, GRID, PAPER = "#1D2A4D", "#5B6478", "#D6DAE3", "#FFFFFF"


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


# ------------------------------------------------------------------- the graph

def plot_box(width, height):
    """Cizim alani: (sol, ust, sag, alt). Eksen etiketlerine yer birakiyor."""
    return 56, 14, max(60, width - 14), max(20, height - 30)


def scaler(lo, hi, start, end):
    """Veri araligini piksel araligina tasiyan fonksiyon. Sifir genislikteki
    aralik ortaya dusuyor - tek noktali bir kosu boluyordu."""
    span = hi - lo
    if span <= 0:
        middle = (start + end) / 2.0
        return lambda value: middle
    return lambda value: start + (value - lo) * (end - start) / span


def draw_train_graph(canvas, rows, title):
    """Yatayda zaman, dikeyde hat boyunca mesafe, tren basina bir cizgi -
    demiryolunun en eski resmi."""
    canvas.delete("all")
    width = int(canvas.winfo_width()) or 700
    height = int(canvas.winfo_height()) or 320
    left, top, right, bottom = plot_box(width, height)

    paths = {}
    for row in rows:
        paths.setdefault(row[COL["train"]], []).append(
            (row[COL["time_s"]], row[COL["chainage_m"]]))
    if not paths:
        canvas.create_text(width / 2, height / 2, text="veri yok", fill=MUTED)
        return

    origin = min(p[0] for points in paths.values() for p in points)
    minutes = [(t - origin) / 60.0 for points in paths.values() for t, _ in points]
    kms = [c / 1000.0 for points in paths.values() for _, c in points]
    to_x = scaler(min(minutes), max(minutes), left, right)
    to_y = scaler(min(kms), max(kms), bottom, top)          # yukari dogru artiyor

    canvas.create_rectangle(left, top, right, bottom, outline=GRID, fill=PAPER)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = left + (right - left) * fraction
        y = bottom - (bottom - top) * fraction
        canvas.create_line(x, top, x, bottom, fill=GRID)
        canvas.create_line(left, y, right, y, fill=GRID)
        canvas.create_text(x, bottom + 12, fill=MUTED, font=("", 8),
                           text="%.0f" % (min(minutes) + (max(minutes) - min(minutes)) * fraction))
        canvas.create_text(left - 6, y, anchor="e", fill=MUTED, font=("", 8),
                           text="%.0f" % (min(kms) + (max(kms) - min(kms)) * fraction))

    for index, train_id in enumerate(sorted(paths)):
        points = []
        for t, c in paths[train_id]:
            points.extend((to_x((t - origin) / 60.0), to_y(c / 1000.0)))
        if len(points) >= 4:
            canvas.create_line(*points, width=1.4,
                               fill=TRACK_COLOURS[index % len(TRACK_COLOURS)])

    canvas.create_text(left, top - 6, anchor="sw", text=title, fill=INK,
                       font=("", 9, "bold"))
    canvas.create_text((left + right) / 2, height - 6, text="kosunun kacinci dakikasi",
                       fill=MUTED, font=("", 8))


# ---------------------------------------------------------------------- the app

class App(object):

    COLUMNS = [("system", "Sistem", 200), ("journey", "Sefer süresi", 90),
               ("delta", "Farkı", 80), ("delay", "Ort. gecikme", 100),
               ("restrained", "Kısıtlı geçen", 100), ("headway", "En dar aralık", 105),
               ("authority", "Ort. yetki", 90), ("done", "Biten", 70),
               ("violations", "İhlal", 60)]

    def __init__(self, root):
        self.root = root
        self.results = []
        self.messages = queue.Queue()
        self.scenarios = scenario_paths()
        root.title("trainsim")
        root.geometry("1180x760")

        panel = ttk.Frame(root, padding=10)
        panel.pack(side="left", fill="y")
        board = ttk.Frame(root, padding=(0, 10, 10, 10))
        board.pack(side="right", fill="both", expand=True)

        ttk.Label(panel, text="Senaryo").pack(anchor="w")
        self.scenario = ttk.Combobox(panel, values=list(self.scenarios),
                                     state="readonly", width=34)
        self.scenario.pack(fill="x", pady=(0, 10))
        if self.scenarios:
            self.scenario.current(0)

        ttk.Label(panel, text="Koşu süresi (s, boş = senaryonunki)").pack(anchor="w")
        self.duration = ttk.Entry(panel, width=34)
        self.duration.pack(fill="x", pady=(0, 10))

        ttk.Label(panel, text="Sinyalizasyon").pack(anchor="w")
        self.systems = {}
        for name in signalling.LADDER:
            chosen = tk.BooleanVar(value=name in ("fixed_block_3aspect",
                                                  "etcs_moving_block",
                                                  "virtual_coupling"))
            ttk.Checkbutton(panel, text=TURKISH.get(name, name),
                            variable=chosen).pack(anchor="w")
            self.systems[name] = chosen

        self.as_fitted = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, variable=self.as_fitted,
                        text="Senaryonun kendi donanımıyla").pack(anchor="w",
                                                                  pady=(8, 0))

        self.run_button = ttk.Button(panel, text="Karşılaştır", command=self.start)
        self.run_button.pack(fill="x", pady=(14, 4))
        ttk.Button(panel, text="İzle (şematik)", command=self.watch).pack(fill="x")

        self.status = ttk.Label(panel, text="", foreground=MUTED, wraplength=240)
        self.status.pack(anchor="w", pady=(12, 0))

        self.table = ttk.Treeview(board, columns=[c[0] for c in self.COLUMNS],
                                  show="headings", height=8)
        for key, heading, width in self.COLUMNS:
            self.table.heading(key, text=heading)
            self.table.column(key, width=width, anchor="w")
        self.table.pack(fill="x")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.redraw())

        self.canvas = tk.Canvas(board, background=PAPER, highlightthickness=1,
                                highlightbackground=GRID)
        self.canvas.pack(fill="both", expand=True, pady=(10, 0))
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        root.after(120, self.drain)

    # -------------------------------------------------------------- actions

    def start(self):
        chosen = [n for n, v in self.systems.items() if v.get()]
        if not self.scenario.get() or not chosen:
            messagebox.showinfo("trainsim", "Bir senaryo ve en az bir sistem seç.")
            return
        try:
            duration = float(self.duration.get() or 0)
        except ValueError:
            messagebox.showerror("trainsim", "Koşu süresi bir sayı olmalı.")
            return
        self.run_button.state(["disabled"])
        self.results = []
        self.table.delete(*self.table.get_children())
        path = self.scenarios[self.scenario.get()]
        threading.Thread(target=self.work, daemon=True,
                         args=(path, chosen, duration, self.as_fitted.get())).start()

    def work(self, path, chosen, duration, as_fitted):
        """Is parcacigi. Tk'ye dokunmuyor - her sey kuyruktan geciyor."""
        try:
            for name in chosen:
                self.messages.put(("status", "%s koşuyor..."
                                   % TURKISH.get(name, name)))
                self.messages.put(("result", run_one(path, name, duration, as_fitted)))
        except ScenarioError as exc:
            self.messages.put(("error", str(exc)))
        except Exception as exc:                       # kullanici gorsun, log'a degil
            self.messages.put(("error", "%s: %s" % (type(exc).__name__, exc)))
        self.messages.put(("done", None))

    def drain(self):
        """Kuyrugu bosalt. Tk'ye sadece burasi dokunuyor."""
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                elif kind == "result":
                    self.results.append(payload)
                    self.add_row(payload)
                elif kind == "error":
                    self.status.configure(text="")
                    messagebox.showerror("trainsim", payload)
                elif kind == "done":
                    self.status.configure(
                        text="bitti - bir satır seç, grafiği o koşuya döner")
                    self.run_button.state(["!disabled"])
                    if self.results and not self.table.selection():
                        self.table.selection_set(self.table.get_children()[0])
        except queue.Empty:
            pass
        self.root.after(120, self.drain)

    def add_row(self, result):
        metrics = result["metrics"]
        baseline = self.results[0]["metrics"]
        if metrics is baseline:
            delta = "-"
        else:
            difference = metrics.mean_journey_s - baseline.mean_journey_s
            delta = "aynı" if abs(difference) < 0.5 else format_delay(difference)
        self.table.insert("", "end", values=(
            TURKISH.get(metrics.system, metrics.system),
            mmss(metrics.mean_journey_s),
            delta,
            "%.1f s" % metrics.mean_delay_s,
            "%d s" % round(metrics.total_restrained_s),
            "%d s" % round(metrics.min_headway_s) if metrics.min_headway_s else "-",
            "%d m" % round(metrics.mean_authority_m),
            "%d/%d" % (metrics.completed, metrics.services),
            metrics.violations))

    def redraw(self):
        selected = self.table.selection()
        if not selected or not self.results:
            return
        index = self.table.index(selected[0])
        if index < len(self.results):
            result = self.results[index]
            draw_train_graph(self.canvas, result["rows"],
                             TURKISH.get(result["name"], result["name"]))

    def watch(self):
        """Sematik gorunum kendi tk.Tk() kokunu aciyor (schematic_tk.py:66), o
        yuzden bu pencerenin icinde degil ayri bir surecte kosuyor.

        Kendimizi --watch ile yeniden cagiriyoruz: exe olarak paketlendiginde
        sys.executable exe'nin kendisi olur ve yaninda run.py bulunmaz."""
        if not self.scenario.get():
            return
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(os.path.abspath(__file__))
        command += ["--watch", self.scenarios[self.scenario.get()]]
        subprocess.Popen(command, cwd=HERE)


def selfcheck():
    """Olceklemenin iki ucu ve sifir genislikteki aralik."""
    to_x = scaler(0.0, 10.0, 100.0, 200.0)
    assert to_x(0.0) == 100.0 and to_x(10.0) == 200.0 and to_x(5.0) == 150.0
    flat = scaler(3.0, 3.0, 100.0, 200.0)
    assert flat(3.0) == 150.0, "tek noktali kosu bolme hatasi vermemeli"
    to_y = scaler(0.0, 10.0, 300.0, 20.0)                  # dikeyde ters
    assert to_y(0.0) == 300.0 and to_y(10.0) == 20.0
    left, top, right, bottom = plot_box(700, 320)
    assert left < right and top < bottom
    assert plot_box(10, 10)[0] < plot_box(10, 10)[2], "kucuk pencerede de cizilebilmeli"
    print("selfcheck tamam")


def watch_scenario(path):
    """Sematik gorunumu ac. App.watch bunun icin kendini yeniden cagiriyor."""
    from trainsim.viz.schematic_tk import TkSchematicView
    scenario = load_scenario(path)
    TkSchematicView(scenario, build_simulation(scenario),
                    speed=float(scenario.view.get("speed", 30))).run()


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif "--watch" in sys.argv:
        watch_scenario(sys.argv[sys.argv.index("--watch") + 1])
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
