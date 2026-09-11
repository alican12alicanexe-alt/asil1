# -*- coding: utf-8 -*-
"""Bir hatti birden fazla sinyalizasyon sistemi altinda kosturup karsilastir.

    python ui_tk.py

Tarayici yok, sunucu yok, port yok, pip yok - sadece tkinter, yani Python'un
kendi icinde geleni. Kurulumun engellendigi ya da localhost'un guvenlik
duvarina takildigi bir makinede calisan surum bu. Grafik de matplotlib'e
gitmiyor, Canvas'a ciziliyor.

GORUNUM

tkinter'in "eski" durmasinin sebebi tkinter degil, varsayilan temasi. Burada
``clam`` kullaniliyor: native gorunmuyor ama her rengi, her kenari, her satir
yuksekligini veriyor - bir tema secmek yerine bir arayuz tasarlayabiliyorsun.
Windows'taki bulanikligin sebebi ayri: surec DPI farkindaligini bildirmedigi
icin sistem pencereyi buyutup bulanik birakiyor. set_dpi_awareness() onu
kapatiyor ve tek basina en buyuk farki o yapiyor.

Renkler sunumun paleti, yani grafikler ve slaytlar ayni dili konusuyor.

Kosular ayri bir is parcaciginda donuyor, sonuclar kuyrukla geri geliyor: tek
parcacikta kossaydi 12000 saniyelik bir tur boyunca pencere donardi.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

from uicore import (CARD, GRID, HERE, INK, INK_SOFT, MUTED, ON_INK, ORANGE,
                    ORANGE_DIM, PAPER, STRIPE, TRACK_COLOURS, TURKISH,
                    mmss, plot_box, run_one, scaler, scenario_paths, series)
from trainsim.core import signalling
from trainsim.core.units import format_delay
from trainsim.scenario.loader import ScenarioError, build_simulation, load_scenario


def set_dpi_awareness():
    """Windows'ta pencereyi bulanik buyutmeyi birak - en buyuk tek kazanc."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass                                   # Windows disi, ya da eski surum


def pick_font():
    """Sistemde varsa Segoe UI, yoksa tkinter'in kendi secimi."""
    families = set(tkfont.families())
    for name in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans"):
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


# ------------------------------------------------------------------- the graph

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


def draw_train_graph(canvas, rows, title, font):
    """Yatayda zaman, dikeyde hat boyunca mesafe, tren basina bir cizgi -
    demiryolunun en eski resmi."""
    canvas.delete("all")
    width = int(canvas.winfo_width()) or 760
    height = int(canvas.winfo_height()) or 320
    left, top, right, bottom = plot_box(width, height)

    canvas.create_text(18, 16, anchor="w", text=title, fill=INK,
                       font=(font, 11, "bold"))

    paths, (lo_x, hi_x, lo_y, hi_y) = series(rows)
    if not paths:
        canvas.create_text(width / 2, height / 2, fill=MUTED, font=(font, 10),
                           text="bir koşu seç")
        return
    to_x = scaler(lo_x, hi_x, left, right)
    to_y = scaler(lo_y, hi_y, bottom, top)                  # yukari dogru artiyor

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        x, y = to_x(lo_x + (hi_x - lo_x) * fraction), to_y(lo_y + (hi_y - lo_y) * fraction)
        canvas.create_line(x, top, x, bottom, fill=GRID)
        canvas.create_line(left, y, right, y, fill=GRID)
        canvas.create_text(x, bottom + 14, fill=MUTED, font=(font, 8),
                           text="%.0f" % (lo_x + (hi_x - lo_x) * fraction))
        canvas.create_text(left - 8, y, anchor="e", fill=MUTED, font=(font, 8),
                           text="%.0f" % (lo_y + (hi_y - lo_y) * fraction))

    for index, train_id in enumerate(sorted(paths)):
        points = []
        for minute, km in paths[train_id]:
            points.extend((to_x(minute), to_y(km)))
        if len(points) >= 4:
            canvas.create_line(*points, width=1.5, capstyle="round",
                               fill=TRACK_COLOURS[index % len(TRACK_COLOURS)])

    canvas.create_text(left, top - 8, anchor="sw", fill=MUTED, font=(font, 8),
                       text="hat boyunca km")
    canvas.create_text(right, bottom + 28, anchor="e", fill=MUTED, font=(font, 8),
                       text="koşunun kaçıncı dakikası")


# ------------------------------------------------------------------- the chrome

def build_theme(style, font):
    """clam'i temel alip her seyi yeniden boyuyoruz. clam secilmesinin sebebi
    native gorunmesi degil - tam tersi, tek yeniden boyanabilen tema o."""
    style.theme_use("clam")

    style.configure("Side.TFrame", background=INK)
    style.configure("Body.TFrame", background=PAPER)
    style.configure("Card.TFrame", background=CARD)

    style.configure("SideTitle.TLabel", background=INK, foreground="#FFFFFF",
                    font=(font, 17, "bold"))
    style.configure("SideNote.TLabel", background=INK, foreground=ON_INK,
                    font=(font, 9))
    style.configure("SideHead.TLabel", background=INK, foreground=ON_INK,
                    font=(font, 8, "bold"))
    style.configure("Head.TLabel", background=PAPER, foreground=INK,
                    font=(font, 13, "bold"))
    style.configure("Note.TLabel", background=PAPER, foreground=MUTED,
                    font=(font, 9))

    # Duz, kenarligi olmayan butonlar. clam'de kenarligi kaldirmanin yolu
    # borderwidth degil relief - ikisi birden verilmezse ince bir cerceve kaliyor.
    style.configure("Accent.TButton", background=ORANGE, foreground="#FFFFFF",
                    font=(font, 10, "bold"), borderwidth=0, relief="flat",
                    padding=(10, 9), focuscolor=ORANGE)
    style.map("Accent.TButton",
              background=[("pressed", ORANGE_DIM), ("active", ORANGE_DIM),
                          ("disabled", INK_SOFT)],
              foreground=[("disabled", ON_INK)])
    style.configure("Ghost.TButton", background=INK_SOFT, foreground="#FFFFFF",
                    font=(font, 10), borderwidth=0, relief="flat",
                    padding=(10, 8), focuscolor=INK_SOFT)
    style.map("Ghost.TButton", background=[("pressed", INK), ("active", "#3A4C7E")])

    style.configure("Side.TCheckbutton", background=INK, foreground="#FFFFFF",
                    font=(font, 10), focuscolor=INK, indicatorcolor=INK_SOFT,
                    indicatorbackground=INK_SOFT)
    style.map("Side.TCheckbutton",
              background=[("active", INK)], foreground=[("active", "#FFFFFF")],
              indicatorcolor=[("selected", ORANGE)])

    style.configure("Side.TCombobox", fieldbackground=INK_SOFT, background=INK_SOFT,
                    foreground="#FFFFFF", arrowcolor=ON_INK, borderwidth=0,
                    relief="flat", padding=6)
    style.map("Side.TCombobox", fieldbackground=[("readonly", INK_SOFT)],
              foreground=[("readonly", "#FFFFFF")])
    style.configure("Side.TEntry", fieldbackground=INK_SOFT, foreground="#FFFFFF",
                    insertcolor="#FFFFFF", borderwidth=0, relief="flat", padding=6)

    # Kenarliksiz tablo: satir yuksekligi ve baslik cizgisi disinda her sey duz.
    style.configure("Data.Treeview", background=CARD, fieldbackground=CARD,
                    foreground=INK, rowheight=30, borderwidth=0, relief="flat",
                    font=(font, 10))
    style.configure("Data.Treeview.Heading", background=CARD, foreground=MUTED,
                    font=(font, 9, "bold"), relief="flat", borderwidth=0,
                    padding=(8, 8))
    style.map("Data.Treeview.Heading", background=[("active", CARD)])
    style.map("Data.Treeview", background=[("selected", "#E3ECF9")],
              foreground=[("selected", INK)])
    style.layout("Data.Treeview", [("Data.Treeview.treearea", {"sticky": "nswe"})])


class App(object):

    COLUMNS = [("system", "SİSTEM", 210), ("journey", "SEFER SÜRESİ", 110),
               ("delta", "FARKI", 90), ("delay", "ORT. GECİKME", 120),
               ("restrained", "KISITLI GEÇEN", 130), ("headway", "EN DAR ARALIK", 130),
               ("authority", "ORT. YETKİ", 110), ("done", "BİTEN", 80),
               ("violations", "İHLAL", 70)]

    def __init__(self, root):
        self.root = root
        self.results = []
        self.messages = queue.Queue()
        self.scenarios = scenario_paths()
        self.font = pick_font()

        root.title("trainsim")
        root.geometry("1280x820")
        root.minsize(1040, 660)
        root.configure(background=PAPER)
        build_theme(ttk.Style(root), self.font)

        self.build_sidebar(root)
        self.build_body(root)
        root.after(120, self.drain)

    def build_sidebar(self, root):
        side = ttk.Frame(root, style="Side.TFrame", width=272)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        def head(text, pad=(0, 6)):
            ttk.Label(box, text=text, style="SideHead.TLabel").pack(
                anchor="w", pady=pad)

        box = ttk.Frame(side, style="Side.TFrame", padding=(24, 26, 24, 24))
        box.pack(fill="both", expand=True)

        ttk.Label(box, text="trainsim", style="SideTitle.TLabel").pack(anchor="w")
        ttk.Label(box, style="SideNote.TLabel", wraplength=220,
                  text="Mikroskopik demiryolu benzetimi").pack(anchor="w",
                                                               pady=(2, 22))

        head("SENARYO")
        self.scenario = ttk.Combobox(box, values=list(self.scenarios),
                                     state="readonly", style="Side.TCombobox",
                                     font=(self.font, 10))
        self.scenario.pack(fill="x", pady=(0, 18))
        if self.scenarios:
            self.scenario.current(0)

        head("KOŞU SÜRESİ (S)")
        self.duration = ttk.Entry(box, style="Side.TEntry", font=(self.font, 10))
        self.duration.pack(fill="x")
        ttk.Label(box, text="boş bırakırsan senaryonunki",
                  style="SideNote.TLabel").pack(anchor="w", pady=(4, 18))

        head("SİNYALİZASYON")
        self.systems = {}
        for name in signalling.LADDER:
            chosen = tk.BooleanVar(value=name in ("fixed_block_3aspect",
                                                  "etcs_moving_block",
                                                  "virtual_coupling"))
            ttk.Checkbutton(box, text=TURKISH.get(name, name), variable=chosen,
                            style="Side.TCheckbutton").pack(anchor="w", pady=1)
            self.systems[name] = chosen

        self.as_fitted = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, variable=self.as_fitted, style="Side.TCheckbutton",
                        text="Senaryonun kendi donanımıyla").pack(anchor="w",
                                                                  pady=(10, 0))

        self.run_button = ttk.Button(box, text="KARŞILAŞTIR", style="Accent.TButton",
                                     command=self.start)
        self.run_button.pack(fill="x", pady=(22, 8))
        ttk.Button(box, text="Şematiği izle", style="Ghost.TButton",
                   command=self.watch).pack(fill="x")

        self.status = ttk.Label(box, text="", style="SideNote.TLabel",
                                wraplength=220)
        self.status.pack(anchor="w", pady=(16, 0))

    def build_body(self, root):
        body = ttk.Frame(root, style="Body.TFrame", padding=(26, 24, 26, 24))
        body.pack(side="right", fill="both", expand=True)

        ttk.Label(body, text="Karşılaştırma", style="Head.TLabel").pack(anchor="w")
        ttk.Label(body, style="Note.TLabel",
                  text="Aynı hat, aynı tarife, aynı tren. Değişen tek şey "
                       "trene ne kadar yol verildiği.").pack(anchor="w",
                                                             pady=(2, 12))

        card = ttk.Frame(body, style="Card.TFrame", padding=10)
        card.pack(fill="x")
        self.table = ttk.Treeview(card, columns=[c[0] for c in self.COLUMNS],
                                  show="headings", height=7, style="Data.Treeview")
        for key, heading, width in self.COLUMNS:
            self.table.heading(key, text=heading, anchor="w")
            self.table.column(key, width=width, anchor="w", stretch=False)
        self.table.tag_configure("odd", background=STRIPE)
        self.table.tag_configure("even", background=CARD)
        self.table.pack(fill="x")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.redraw())

        ttk.Label(body, text="Tren grafiği", style="Head.TLabel").pack(
            anchor="w", pady=(20, 2))
        ttk.Label(body, style="Note.TLabel",
                  text="Yatayda zaman, dikeyde hat boyunca mesafe. Tablodan bir "
                       "satır seç.").pack(anchor="w", pady=(0, 12))

        graph_card = ttk.Frame(body, style="Card.TFrame", padding=2)
        graph_card.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(graph_card, background=CARD, highlightthickness=0,
                                borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

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
        self.canvas.delete("all")
        path = self.scenarios[self.scenario.get()]
        threading.Thread(target=self.work, daemon=True,
                         args=(path, chosen, duration, self.as_fitted.get())).start()

    def work(self, path, chosen, duration, as_fitted):
        """Is parcacigi. Tk'ye dokunmuyor - her sey kuyruktan geciyor."""
        try:
            for name in chosen:
                self.messages.put(("status", "%s koşuyor…"
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
                    self.status.configure(text="%d koşu bitti" % len(self.results)
                                          if self.results else "")
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
            delta = "—"
        else:
            difference = metrics.mean_journey_s - baseline.mean_journey_s
            delta = "aynı" if abs(difference) < 0.5 else format_delay(difference)
        stripe = "odd" if len(self.table.get_children()) % 2 else "even"
        self.table.insert("", "end", tags=(stripe,), values=(
            TURKISH.get(metrics.system, metrics.system),
            mmss(metrics.mean_journey_s),
            delta,
            "%.1f s" % metrics.mean_delay_s,
            "%d s" % round(metrics.total_restrained_s),
            "%d s" % round(metrics.min_headway_s) if metrics.min_headway_s else "—",
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
                             TURKISH.get(result["name"], result["name"]), self.font)

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


def watch_scenario(path):
    """Sematik gorunumu ac. App.watch bunun icin kendini yeniden cagiriyor."""
    from trainsim.viz.schematic_tk import TkSchematicView
    scenario = load_scenario(path)
    TkSchematicView(scenario, build_simulation(scenario),
                    speed=float(scenario.view.get("speed", 30))).run()


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        import uicore
        uicore.selfcheck()
    elif "--watch" in sys.argv:
        watch_scenario(sys.argv[sys.argv.index("--watch") + 1])
    else:
        set_dpi_awareness()
        root = tk.Tk()
        App(root)
        root.mainloop()
