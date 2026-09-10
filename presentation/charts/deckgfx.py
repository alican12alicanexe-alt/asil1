# -*- coding: utf-8 -*-
"""Sunumun anlatim gorselleri: akis semasi, makale kartlari, sistem matrisi.

Veri tasimayan, yapiyi anlatan uc gorsel. Hepsi ayni palet ve ayni tipografi.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # style.py
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # depo koku
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, FancyArrow
from style import NAVY, SKY, ORANGE, INK, MUTED, GRID, save

PAPER = "#F4F6F9"


def box(ax, x, y, w, h, face, edge=None, r=0.02):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%f" % r,
                                facecolor=face, edgecolor=edge or face,
                                linewidth=1.4, zorder=2))


def blank(w, h):
    fig = Figure(figsize=(w, h))
    ax = fig.subplots()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


# ------------------------------------------------------------ 1) akis semasi
STEPS = [
    (u"TEST AĞI", u"70 km çevrim\n11 istasyon"),
    (u"SİNYALİZASYON", u"sabit blok\nhareketli blok\nsanal kuplaj"),
    (u"SİMÜLASYON", u"1 s adım\nmikroskobik"),
    (u"AYNI KOŞULLAR", u"aynı filo\naynı tarife"),
    (u"KARŞILAŞTIRMA", u"headway\nkapasite\ngecikme"),
]
fig, ax = blank(13.2, 2.5)
n = len(STEPS)
gap, w = 0.030, (1.0 - 0.030 * (n - 1)) / n
for i, (head, sub) in enumerate(STEPS):
    x = i * (w + gap)
    fill = ORANGE if i == n - 1 else (NAVY if i == 0 else PAPER)
    ink = "white" if i in (0, n - 1) else INK
    box(ax, x, 0.10, w, 0.80, fill, GRID if fill is PAPER else fill)
    ax.text(x + w / 2, 0.70, head, ha="center", va="center", fontsize=14.5,
            fontweight="bold", color=ink)
    ax.text(x + w / 2, 0.40, sub, ha="center", va="center", fontsize=11.5,
            color=("white" if ink == "white" else MUTED), linespacing=1.45)
    if i < n - 1:
        ax.add_patch(FancyArrow(x + w + 0.004, 0.50, gap - 0.010, 0,
                                width=0.012, head_width=0.075,
                                head_length=0.010, color=ORANGE,
                                length_includes_head=True, zorder=3))
save(fig, "flow")


# --------------------------------------------------------- 2) makale kartlari
CARDS = [
    (u"Quaglietta vd. (2020)", NAVY, [
        (u"YÖNTEM", u"Çok durumlu tren takip modeli\n20 km hat · 2 tren"),
        (u"BULGU", u"ETCS L3'e göre headway\n%13 – %53 daha kısa"),
        (u"ÖLÇTÜĞÜ", u"iki trenin anlık mesafesi"),
    ]),
    (u"Aoun vd. (2021)", SKY, [
        (u"YÖNTEM", u"Delphi-AHP çok ölçütlü analiz\n15 uzman · 66 senaryo"),
        (u"BULGU", u"Kapasite kazancı %1.8 – %14\nGüvenlik %45 · kapasite %5.6"),
        (u"ÖLÇTÜĞÜ", u"karar ölçütlerinin ağırlığı"),
    ]),
    (u"Bu çalışma", ORANGE, [
        (u"YÖNTEM", u"Mikroskobik simülasyon\n70 km çevrim · 12 tren"),
        (u"BULGU", u"Duraklamalı %9 · duraksız %18\nkonvoy teşvikiyle %32"),
        (u"ÖLÇTÜĞÜ", u"sürdürülebilen en kısa aralık"),
    ]),
]
fig, ax = blank(13.2, 4.5)
gap, w = 0.030, (1.0 - 0.030 * 2) / 3
for i, (head, colour, rows) in enumerate(CARDS):
    x = i * (w + gap)
    box(ax, x, 0.02, w, 0.96, PAPER, GRID)
    box(ax, x, 0.84, w, 0.14, colour, colour)
    ax.text(x + w / 2, 0.905, head, ha="center", va="center", fontsize=15,
            fontweight="bold", color="white")
    y = 0.72
    for label, text in rows:
        ax.text(x + 0.018, y, label, fontsize=10, fontweight="bold",
                color=colour, va="center")
        ax.text(x + 0.018, y - 0.125, text, fontsize=12, color=INK,
                va="center", linespacing=1.5)
        y -= 0.245
save(fig, "papers")


# ------------------------------------------------------- 3) sistem matrisi
COLS = [(u"SABİT BLOK", NAVY), (u"HAREKETLİ BLOK", SKY), (u"SANAL KUPLAJ", ORANGE)]
ROWS = [
    (u"Ayrım ilkesi", [u"blok işgali", u"mutlak fren mesafesi",
                       u"nispi fren mesafesi"]),
    (u"Yetkinin bittiği yer", [u"bir sonraki blok sınırı",
                               u"ön trenin arkası + 100 m",
                               u"ön trenin duracağı yer + 50 m"]),
    (u"Haberleşme", [u"ray devresi / balis", u"tren → yer (ETCS L3)",
                     u"tren → yer + tren → tren"]),
    (u"Ölçülen en kısa aralık", [u"148 s", u"78 s", u"71 s"]),
]
fig, ax = blank(13.2, 3.6)
lab_w, gap = 0.20, 0.016
w = (1.0 - lab_w - gap * 3) / 3
for j, (head, colour) in enumerate(COLS):
    x = lab_w + gap + j * (w + gap)
    box(ax, x, 0.845, w, 0.135, colour, colour)
    ax.text(x + w / 2, 0.9125, head, ha="center", va="center", fontsize=13.5,
            fontweight="bold", color="white")
for i, (label, cells) in enumerate(ROWS):
    y = 0.655 - i * 0.205
    last = i == len(ROWS) - 1
    ax.text(lab_w, y + 0.09, label, ha="right", va="center", fontsize=11.5,
            color=MUTED, fontweight="bold")
    for j, cell in enumerate(cells):
        x = lab_w + gap + j * (w + gap)
        box(ax, x, y, w, 0.18, PAPER if not last else COLS[j][1] + "22", GRID)
        ax.text(x + w / 2, y + 0.09, cell, ha="center", va="center",
                fontsize=(17 if last else 12),
                fontweight=("bold" if last else "normal"),
                color=(COLS[j][1] if last else INK), linespacing=1.4)
save(fig, "systems")
