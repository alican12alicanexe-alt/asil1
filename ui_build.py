# -*- coding: utf-8 -*-
"""Bir hatti tarif etme sayfasi: yer, tarife, filo, sinyalizasyon.

ui_qt.py'nin ikinci sayfasi. Elle YAML yazmak yerine formu dolduruyorsun,
sonunda scenarios/<ad>/ altina calisir bir senaryo cikiyor ve karsilastirma
sayfasinin listesinde beliriyor.

Iki dugme:

    Senaryoyu uret   hatti yazar, bos hatta bir tren kosturup tarifeyi ondan
                     cikarir - yani plan tek basina her zaman yurur, sonraki
                     kosuda gorunen her gecikme trenlerin birbirine girmesinden
                     gelir.
    Headway tara     ayni filoyu her aralikta kosturup calisan en siki araligi
                     saniyesine kadar bulur, ve bir saniye altinda NEYIN
                     bagladigini soyler. Cevap cogu zaman sinyalizasyon degil
                     bir peron olur; o yuzden istasyon basina peron sayisi bu
                     formda bir sutun.

Agir isler ayri bir is parcaciginda: bir tarama onlarca kosu demek.
"""
import os
import re

from PySide6 import QtCore, QtGui, QtWidgets

from uicore import CARD, GRID, HERE, INK, MUTED, ORANGE, TURKISH
from trainsim.core import signalling
from trainsim.scenario.generate import (LineSpec, HEADWAYS, book, evenly,
                                        gradient_profile, sweep_headway)

#: Uretilen senaryolar buraya, cunku karsilastirma sayfasi scenarios/*/ altina
#: bakiyor - baska bir yere yazmak hatti listede gorunmez yapardi.
OUT_ROOT = os.path.join(HERE, "scenarios")

#: Gercek hatlarda gorulen anma egimleri. Tek bir sayi degil bir karakter
#: seciyorsun: profil bu degeri en dik kesime koyup gerisini yaymaya birakiyor.
TERRAIN = [("Düz (0 ‰)", 0), ("Ova (4 ‰)", 4), ("Ana hat (10 ‰)", 10),
           ("Dağlık (18 ‰)", 18), ("Yüksek hızlı (25 ‰)", 25),
           ("Metro / banliyö (35 ‰)", 35)]

LEADER_BRAKE = [("Acil fren (ihtiyatlı)", "emergency"),
                ("Servis freni (konvoy kuralı)", "service")]


def spin(lo, hi, value, step=1, decimals=0, suffix=""):
    """Sayi kutusu. Ondalik gerekiyorsa QDoubleSpinBox, gerekmiyorsa degil."""
    box = QtWidgets.QDoubleSpinBox() if decimals else QtWidgets.QSpinBox()
    box.setRange(lo, hi)
    box.setSingleStep(step)
    if decimals:
        box.setDecimals(decimals)
    box.setValue(value)
    if suffix:
        box.setSuffix(" " + suffix)
    box.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    box.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    return box


def grid_table(headers, rows=0):
    """Duzenlenebilir kucuk tablo - istasyonlar, egimler, limitler, seferler."""
    table = QtWidgets.QTableWidget(rows, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(28)
    table.horizontalHeader().setSectionResizeMode(
        QtWidgets.QHeaderView.Stretch)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setProperty("class", "card")
    return table


def cells(table, row, values):
    for column, value in enumerate(values):
        table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))


def text_at(table, row, column, fallback=""):
    item = table.item(row, column)
    return item.text().strip() if item is not None else fallback


def number_at(table, row, column, fallback=0.0):
    try:
        return float(text_at(table, row, column).replace(",", "."))
    except ValueError:
        return fallback


class Card(QtWidgets.QFrame):
    """Basligi olan bir kutu. Form bunlardan kuruluyor."""

    def __init__(self, title, note=""):
        super(Card, self).__init__()
        self.setProperty("class", "card")
        self.box = QtWidgets.QVBoxLayout(self)
        self.box.setContentsMargins(16, 14, 16, 16)
        self.box.setSpacing(8)
        heading = QtWidgets.QLabel(title)
        heading.setStyleSheet("font-size: 14px; font-weight: 700; color: %s;"
                              % INK)
        self.box.addWidget(heading)
        if note:
            hint = QtWidgets.QLabel(note)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: %s; font-size: 11px;" % MUTED)
            self.box.addWidget(hint)
        self.form = None
        self.next_form()

    def next_form(self):
        """Kartin bundan sonraki satirlari yeni bir formda toplansin.

        Bir bolum basligi arada kaliyorsa satirlar tek bir forma yigilamaz -
        yoksa baslik, kendisinden sonra gelmesi gereken satirlarin altina
        duser."""
        self.form = QtWidgets.QFormLayout()
        self.form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(7)
        self.box.addLayout(self.form)

    def row(self, label, widget):
        tag = QtWidgets.QLabel(label)
        tag.setStyleSheet("color: %s; font-size: 12px;" % MUTED)
        self.form.addRow(tag, widget)
        return widget

    def add(self, widget):
        self.box.addWidget(widget)
        return widget


class Worker(QtCore.QThread):
    """Uretim ve tarama burada. Ikisi de dakikalar surebilir."""

    note = QtCore.Signal(str)
    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, job, spec, directory, system, sweep_args=None):
        super(Worker, self).__init__()
        self.job, self.spec, self.directory = job, spec, directory
        self.system, self.sweep_args = system, sweep_args

    def run(self):
        try:
            if self.job == "build":
                self.note.emit("Hat yazılıyor, boş hatta bir tren koşuyor…")
                booked = book(self.directory, self.spec)
                if booked is None:
                    self.failed.emit(
                        "Tek başına koşan tren bile hattı bitiremedi. Koşu "
                        "süresi kısa, ya da bu plan bu hatta yürümüyor.")
                    return
                self.done.emit(("build", booked))
            else:
                self.note.emit("Tarama başlıyor: her aralık bir koşu…")
                rows, limit, binding = sweep_headway(
                    self.directory, self.spec, self.system,
                    progress=lambda row: self.note.emit(
                        "%d s: %s" % (row["headway_s"],
                                      "temiz" if row["ok"] else "sıkışık")),
                    **self.sweep_args)
                self.done.emit(("sweep", (rows, limit, binding)))
        except Exception as exc:                   # kullanici gorsun, log'a degil
            self.failed.emit("%s: %s" % (type(exc).__name__, exc))


class BuildPage(QtWidgets.QWidget):

    built = QtCore.Signal(str)          # yazilan senaryo yolu

    def __init__(self):
        super(BuildPage, self).__init__()
        self.setObjectName("body")
        self.worker = None
        body = QtWidgets.QVBoxLayout(self)
        body.setContentsMargins(28, 26, 28, 26)
        body.setSpacing(0)

        head = QtWidgets.QLabel("Hat kur")
        head.setObjectName("head")
        body.addWidget(head)
        note = QtWidgets.QLabel(
            "İstasyonları, yeri, filoyu ve tarifeyi buradan tarif et; senaryo "
            "yazıldıktan sonra karşılaştırma listesinde belirir.")
        note.setObjectName("note")
        body.addWidget(note)
        body.addSpacing(12)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        inner = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        scroll.setWidget(inner)
        body.addWidget(scroll, 1)

        self.build_line_card()
        self.build_terrain_card()
        self.build_fleet_card()
        self.build_service_card()
        self.build_signalling_card()
        self.build_log_card()
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.refresh_stations()
        self.fill_gradients()
        self.system_changed()

    # ----------------------------------------------------------------- cards

    def build_line_card(self):
        card = Card("Hat", "İstasyon sayısını ve aralığını gir, Uygula'ya bas; "
                           "tablodaki adları, kilometreleri ve peron sayılarını "
                           "sonra tek tek değiştirebilirsin.")
        self.name = card.row("Adı", QtWidgets.QLineEdit("yenihat"))
        self.count = card.row("İstasyon sayısı", spin(2, 60, 6))
        self.spacing = card.row("İstasyon arası", spin(0.5, 200, 9.0, 0.5, 1, "km"))
        self.line_speed = card.row("Hat hızı", spin(20, 350, 100, 5, 0, "km/h"))
        self.block = card.row("Blok uzunluğu", spin(100, 5000, 1200, 50, 0, "m"))
        self.zone = card.row("Peron bölgesi", spin(100, 2000, 700, 50, 0, "m"))
        self.default_roads = card.row("Varsayılan peron", spin(1, 6, 1))

        apply_button = QtWidgets.QPushButton("Uygula")
        apply_button.setObjectName("small")
        apply_button.clicked.connect(self.refresh_stations)
        card.row("", apply_button)

        self.stations = card.add(grid_table(["İSTASYON", "AD", "KM", "PERON",
                                             "DEPO"]))
        self.stations.setMinimumHeight(190)
        self.grid.addWidget(card, 0, 0)

    def build_terrain_card(self):
        card = Card("Yer", "Eğim kesim kesim, binde olarak ve gidiş yönünde: "
                           "artı tırmanış. Profil en dik kesimi anma eğimine "
                           "koyar, gerisini gerçek bir güzergâh gibi yayar ve "
                           "toplamı sıfırlar. Hız limitleri kilometreyle "
                           "verilir - bir kurp tarifeye değil yere aittir.")
        self.terrain = QtWidgets.QComboBox()
        for label, _ in TERRAIN:
            self.terrain.addItem(label)
        self.terrain.setCurrentIndex(2)
        card.row("Arazi", self.terrain)
        fill = QtWidgets.QPushButton("Profili doldur")
        fill.setObjectName("small")
        fill.clicked.connect(self.fill_gradients)
        card.row("", fill)

        self.gradients = card.add(grid_table(["KESİM", "EĞİM ‰"]))
        self.gradients.setMinimumHeight(130)
        self.gradients.setMaximumHeight(230)

        self.section(card, "Hız limitleri")
        self.limits = card.add(grid_table(["KM BAŞI", "KM SONU", "KM/H"]))
        self.limits.setMinimumHeight(90)
        self.limits.setMaximumHeight(150)
        card.add(self.row_buttons(self.limits, lambda table, row: cells(
            table, row, ["0.0", "1.0", "%d" % self.line_speed.value()])))
        self.grid.addWidget(card, 0, 1)

    def build_fleet_card(self):
        card = Card("Filo", "Bir satır bir tren tipi: uzunluk m, azami km/h, "
                            "ivme ve frenler m/s². İlk satır hattın varsayılan "
                            "treni; ikinci bir satır eklersen tarifede sefer "
                            "sefer hangisinin koşacağını seçebilirsin.")
        self.fleet = card.add(grid_table(
            ["ID", "AD", "UZUNLUK", "AZAMİ", "İVME", "SERVİS", "ACİL"]))
        self.fleet.setMinimumHeight(110)
        self.fleet.setMaximumHeight(200)
        cells(self.fleet, self.add_row(self.fleet),
              ["EMU", "Banliyö", 120, 90, 1.0, 1.0, 1.5])
        card.add(self.row_buttons(self.fleet, lambda table, row: cells(
            table, row, ["EXP", "Ekspres", 160, 140, 0.8, 0.9, 1.4])))
        self.grid.addWidget(card, 1, 0)

    def build_service_card(self):
        card = Card("Tarife", "Varsayılan otomatik: aynı tren, seçtiğin "
                              "aralıkta birbiri ardına. Elle geçersen her "
                              "seferin kalkışını, trenini ve duraklarını tek "
                              "tek yazarsın - duraklar boşsa hepsinde durur.")
        self.auto = QtWidgets.QRadioButton("Otomatik")
        self.auto.setChecked(True)
        self.manual = QtWidgets.QRadioButton("Elle")
        mode = QtWidgets.QHBoxLayout()
        mode.addWidget(self.auto)
        mode.addWidget(self.manual)
        mode.addStretch(1)
        holder = QtWidgets.QWidget()
        holder.setLayout(mode)
        card.row("Yazım", holder)

        self.trains = card.row("Tren sayısı", spin(1, 60, 10))
        self.headway = card.row("Aralık", spin(20, 1800, 180, 5, 0, "s"))
        self.dwell = card.row("Bekleme", spin(0, 600, 30, 5, 0, "s"))
        self.first = card.row("İlk kalkış", QtWidgets.QTimeEdit(
            QtCore.QTime(7, 0)))
        self.first.setDisplayFormat("HH:mm")

        self.services = card.add(grid_table(
            ["SEFER", "TREN", "KALKIŞ", "DURAKLAR", "BEKLEME S"]))
        self.services.setMinimumHeight(110)
        self.services.setMaximumHeight(220)
        fill = QtWidgets.QPushButton("Otomatikten doldur")
        fill.setObjectName("small")
        fill.clicked.connect(self.fill_services)
        card.add(fill)
        card.add(self.row_buttons(self.services, lambda table, row: cells(
            table, row, ["S%02d" % (row + 1), "EMU", "07:30", "", 30])))
        self.manual.toggled.connect(self.mode_changed)
        self.mode_changed()
        self.grid.addWidget(card, 1, 1)

    def build_signalling_card(self):
        card = Card("Sinyalizasyon ve arama",
                    "Aralığı elle verirsen senaryo o aralıkla yazılır. "
                    "Taratırsan aynı filo her aralıkta koşulur, çalışan en "
                    "sıkı aralık saniyesine kadar bulunur ve bir saniye "
                    "altında neyin bağladığı söylenir.")
        self.system = QtWidgets.QComboBox()
        for name in signalling.LADDER:
            self.system.addItem(TURKISH.get(name, name), name)
        self.system.currentIndexChanged.connect(self.system_changed)
        card.row("Sistem", self.system)

        self.capped = QtWidgets.QCheckBox("Kuplajsız hız limiti uygula")
        card.row("", self.capped)
        self.cap_kmh = card.row("Kuplajsız hız", spin(10, 300, 70, 5, 0, "km/h"))
        self.coupling_margin = card.row("Kuplaj marjı",
                                        spin(0, 5000, 800, 50, 0, "m"))
        self.latency = card.row("V2V gecikmesi", spin(0, 5, 0.5, 0.1, 2, "s"))
        self.leader_brake = QtWidgets.QComboBox()
        for label, value in LEADER_BRAKE:
            self.leader_brake.addItem(label, value)
        card.row("Lider freni", self.leader_brake)
        self.capped.toggled.connect(self.system_changed)

        self.section(card, "Arama")
        self.do_sweep = QtWidgets.QCheckBox("Aralığı tarayarak bul")
        card.row("", self.do_sweep)
        self.sweep_hi = card.row("Aramanın üstü", spin(30, 1800, 300, 10, 0, "s"))
        self.sweep_lo = card.row("Aramanın altı", spin(10, 900, 30, 5, 0, "s"))
        self.sweep_steps = card.row("Basamak", spin(3, 40, len(HEADWAYS)))
        self.rule = QtWidgets.QComboBox()
        self.rule.addItem("Hiç sinyalle tutulmadan (all-green)", "clean")
        self.rule.addItem("Tutulsa da tarifeye uyarak", "ontime")
        card.row("Ölçüt", self.rule)
        self.do_sweep.toggled.connect(self.system_changed)
        self.grid.addWidget(card, 2, 0)

    def build_log_card(self):
        card = Card("Sonuç")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(260)
        self.log.setStyleSheet(
            "QPlainTextEdit { background: %s; border: 1px solid %s; "
            "border-radius: 8px; padding: 10px; font-family: Consolas, "
            "'DejaVu Sans Mono', monospace; font-size: 11px; color: %s; }"
            % (CARD, GRID, INK))
        card.add(self.log)
        self.grid.addWidget(card, 2, 1)

    # ---------------------------------------------------------------- pieces

    def section(self, card, title):
        """Kart icinde bir ara baslik, ve ardindan temiz bir form."""
        label = QtWidgets.QLabel(title.upper())
        label.setStyleSheet("color: %s; font-size: 11px; font-weight: 700; "
                            "letter-spacing: 1px; padding-top: 10px;" % MUTED)
        card.add(label)
        card.next_form()
        return label

    def add_row(self, table):
        row = table.rowCount()
        table.insertRow(row)
        return row

    def row_buttons(self, table, make):
        """Bir tabloya satir ekleyip cikaran ikili."""
        holder = QtWidgets.QWidget()
        box = QtWidgets.QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        add = QtWidgets.QPushButton("Satır ekle")
        add.setObjectName("small")
        add.clicked.connect(lambda: make(table, self.add_row(table)))
        drop = QtWidgets.QPushButton("Seçileni sil")
        drop.setObjectName("small")
        drop.clicked.connect(lambda: self.drop_row(table))
        box.addWidget(add)
        box.addWidget(drop)
        box.addStretch(1)
        return holder

    def drop_row(self, table):
        rows = sorted((index.row() for index in
                       table.selectionModel().selectedRows()), reverse=True)
        for row in rows or ([table.rowCount() - 1] if table.rowCount() else []):
            table.removeRow(row)

    # --------------------------------------------------------------- filling

    def refresh_stations(self):
        """İstasyon tablosunu sayidan ve araliktan yeniden kur."""
        laid = evenly(self.count.value(), self.spacing.value())
        self.stations.setRowCount(0)
        for index, (sid, name, km) in enumerate(laid):
            row = self.add_row(self.stations)
            depot = index in (0, len(laid) - 1)
            cells(self.stations, row, [sid, name, "%.1f" % km,
                                       self.default_roads.value(),
                                       "evet" if depot else "hayır"])
        self.fill_gradients()

    def station_rows(self):
        found = []
        for row in range(self.stations.rowCount()):
            sid = text_at(self.stations, row, 0)
            if sid:
                found.append((sid, text_at(self.stations, row, 1) or sid,
                              number_at(self.stations, row, 2, row * 10.0)))
        return found

    def fill_gradients(self):
        laid = self.station_rows()
        ruling = TERRAIN[self.terrain.currentIndex()][1]
        profile = gradient_profile(laid, ruling)
        self.gradients.setRowCount(0)
        for start, end, permille in profile:
            row = self.add_row(self.gradients)
            cells(self.gradients, row, ["%s → %s" % (start, end),
                                        "%.1f" % permille])
        if not profile:                 # duz hat: kesimleri yine de goster
            for index in range(len(laid) - 1):
                row = self.add_row(self.gradients)
                cells(self.gradients, row, ["%s → %s" % (laid[index][0],
                                                         laid[index + 1][0]),
                                            "0.0"])

    def fill_services(self):
        """Elle tarifeyi otomatik olanin kopyasiyla baslat - sifirdan yazmak
        yerine duzenlemek icin."""
        away = self.first.time()
        start = away.hour() * 3600 + away.minute() * 60
        self.services.setRowCount(0)
        for index in range(self.trains.value()):
            row = self.add_row(self.services)
            when = start + int(round(index * self.headway.value()))
            cells(self.services, row,
                  ["S%02d" % (index + 1), self.fleet_ids()[0],
                   "%02d:%02d" % (when // 3600 % 24, when // 60 % 60), "",
                   self.dwell.value()])
        self.manual.setChecked(True)

    def fleet_ids(self):
        found = [text_at(self.fleet, row, 0)
                 for row in range(self.fleet.rowCount())]
        return [name for name in found if name] or ["EMU"]

    def mode_changed(self):
        manual = self.manual.isChecked()
        self.services.setEnabled(manual)
        for widget in (self.trains, self.headway):
            widget.setEnabled(not manual)
        if manual and self.do_sweep.isChecked():
            self.do_sweep.setChecked(False)

    def system_changed(self):
        coupling = self.system.currentData() == "virtual_coupling"
        for widget in (self.capped, self.cap_kmh, self.coupling_margin,
                       self.latency, self.leader_brake):
            widget.setEnabled(coupling)
        self.cap_kmh.setEnabled(coupling and self.capped.isChecked())
        sweeping = self.do_sweep.isChecked()
        for widget in (self.sweep_hi, self.sweep_lo, self.sweep_steps,
                       self.rule):
            widget.setEnabled(sweeping)
        self.headway.setEnabled(not sweeping and not self.manual.isChecked())

    # ------------------------------------------------------------ the answer

    def spec(self):
        """Formdaki her seyi tek bir LineSpec'e topla."""
        laid = self.station_rows()
        if len(laid) < 2:
            raise ValueError("Bir hat en az iki istasyon ister.")
        ids = [sid for sid, _, _ in laid]
        if len(set(ids)) != len(ids):
            raise ValueError("İki istasyon aynı id'yi taşıyamaz: %s"
                             % ", ".join(sorted(ids)))
        if sorted(km for _, _, km in laid) != [km for _, _, km in laid]:
            raise ValueError("İstasyonlar kilometre sırasında olmalı.")

        platforms, depots = {}, []
        for row in range(self.stations.rowCount()):
            sid = text_at(self.stations, row, 0)
            if not sid:
                continue
            platforms[sid] = max(1, int(number_at(self.stations, row, 3, 1)))
            if text_at(self.stations, row, 4).lower().startswith(("e", "y", "1")):
                depots.append(sid)

        gradients = []
        for row in range(self.gradients.rowCount()):
            stretch = re.split(r"[^\w]+", text_at(self.gradients, row, 0))
            permille = number_at(self.gradients, row, 1, 0.0)
            if len(stretch) >= 2 and permille:
                gradients.append((stretch[0], stretch[1], permille))

        limits = []
        for row in range(self.limits.rowCount()):
            from_km = number_at(self.limits, row, 0, -1.0)
            to_km = number_at(self.limits, row, 1, -1.0)
            kmh = number_at(self.limits, row, 2, 0.0)
            if from_km >= 0 and to_km > from_km and kmh > 0:
                limits.append((from_km, to_km, kmh))

        units = []
        for row in range(self.fleet.rowCount()):
            unit_id = text_at(self.fleet, row, 0)
            if not unit_id:
                continue
            units.append({
                "id": unit_id, "name": text_at(self.fleet, row, 1) or unit_id,
                "length_m": number_at(self.fleet, row, 2, 120.0),
                "max_speed_kmh": number_at(self.fleet, row, 3, 90.0),
                "max_accel": number_at(self.fleet, row, 4, 1.0),
                "service_brake": number_at(self.fleet, row, 5, 1.0),
                "emergency_brake": number_at(self.fleet, row, 6, 1.5)})
        if not units:
            raise ValueError("Filoda en az bir tren tipi olmalı.")

        away = self.first.time()
        first_s = away.hour() * 3600 + away.minute() * 60
        head = units[0]
        options = {}
        if self.system.currentData() == "virtual_coupling":
            options = {"coupling_margin_m": self.coupling_margin.value(),
                       "v2v_latency_s": self.latency.value(),
                       "leader_brake": self.leader_brake.currentData()}
            if self.capped.isChecked():
                options["uncoupled_speed_kmh"] = self.cap_kmh.value()

        spec = LineSpec(
            stations=laid, name=self.name.text().strip() or "yenihat",
            line_speed_kmh=self.line_speed.value(),
            block_length_m=self.block.value(),
            platform_zone_m=self.zone.value(),
            platforms_per_station=self.default_roads.value(),
            stock_length_m=head["length_m"], max_speed_kmh=head["max_speed_kmh"],
            max_accel=head["max_accel"], service_brake=head["service_brake"],
            emergency_brake=head["emergency_brake"],
            stock_id=units[0]["id"], extra_stock=units[1:],
            trains=self.trains.value(), headway_s=self.headway.value(),
            dwell_s=self.dwell.value(), first_departure_s=first_s,
            gradients=gradients, speed_limits=limits, depots=depots,
            platforms=platforms, system=self.system.currentData(),
            signalling_options=options)
        if self.manual.isChecked():
            spec.services_spec = self.manual_services(ids)
        spec.duration_s = max(3600.0, spec.headway_s * spec.trains + 5400.0)
        return spec

    def manual_services(self, ids):
        found = []
        for row in range(self.services.rowCount()):
            service_id = text_at(self.services, row, 0)
            if not service_id:
                continue
            clock = text_at(self.services, row, 2, "07:00")
            parts = re.split(r"[^\d]+", clock) or ["7", "0"]
            hours = int(parts[0] or 0)
            minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            stops = [name for name in re.split(r"[^\w]+",
                                               text_at(self.services, row, 3))
                     if name]
            unknown = [name for name in stops if name not in ids]
            if unknown:
                raise ValueError("%s seferi olmayan istasyonda duruyor: %s"
                                 % (service_id, ", ".join(unknown)))
            found.append({"id": service_id,
                          "stock": text_at(self.services, row, 1)
                                   or self.fleet_ids()[0],
                          "departure_s": hours * 3600 + minutes * 60,
                          "calls": stops or None,
                          "dwell_s": number_at(self.services, row, 4, 30.0)})
        if not found:
            raise ValueError("Elle tarife seçili ama tabloda sefer yok - "
                             "\"Otomatikten doldur\" iyi bir başlangıç.")
        return found

    # --------------------------------------------------------------- running

    def start(self, job):
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            spec = self.spec()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Hat kur", str(exc))
            return
        directory = os.path.join(OUT_ROOT, re.sub(r"[^\w.-]+", "-", spec.name))
        self.log.clear()
        self.say("%s  ·  %d istasyon  ·  %.1f km  ·  %s"
                 % (spec.name, len(spec.stations), spec.last_km,
                    TURKISH.get(spec.system, spec.system)))
        arguments = None
        if job == "sweep":
            hi, lo = self.sweep_hi.value(), self.sweep_lo.value()
            if lo >= hi:
                QtWidgets.QMessageBox.warning(
                    self, "Hat kur", "Aramanın altı üstünden küçük olmalı.")
                return
            steps = self.sweep_steps.value()
            span = [int(round(hi - (hi - lo) * index / float(steps - 1)))
                    for index in range(steps)]
            arguments = {"headways": tuple(sorted(set(span), reverse=True)),
                         "rule": self.rule.currentData()}
        self.worker = Worker(job, spec, directory, spec.system, arguments)
        self.worker.note.connect(self.say)
        self.worker.failed.connect(self.complain)
        self.worker.done.connect(lambda payload: self.settle(payload, directory))
        self.worker.start()

    def say(self, line):
        self.log.appendPlainText(line)

    def complain(self, message):
        self.say("")
        self.say("HATA: " + message)
        QtWidgets.QMessageBox.critical(self, "Hat kur", message)

    def settle(self, payload, directory):
        job, result = payload
        if job == "build":
            self.report_build(result)
        else:
            self.report_sweep(result)
        self.say("")
        self.say("Yazıldı: %s" % directory)
        self.built.emit(directory)

    def report_build(self, bookings):
        self.say("")
        for key, times in sorted(bookings.items()):
            unit, stops = key[0], key[1:]
            start = times[0][1] or times[0][0]
            end = times[-1][0]
            self.say("%-6s %2d durak   boş hatta %s"
                     % (unit, len(stops), _mmss((end or 0) - (start or 0))))

    def report_sweep(self, result):
        rows, limit, binding = result
        self.say("")
        self.say("  aralık    sinyalle tutulan   ort. gecikme    en kötü   biten")
        self.say("  " + "-" * 60)
        for row in rows:
            if row.get("refined"):
                continue
            self.say("  %5d s   %12.0f s   %10.1f s   %7.0f s   %d/%d %s"
                     % (row["headway_s"], row["restrained_s"],
                        row["mean_delay_s"], row["worst_s"], row["completed"],
                        row["services"], "" if row["ok"] else "<-- sıkışık"))
        self.say("")
        if limit is None:
            self.say("Aralığın hiçbir yerinde sınır geçilmedi. Arama sınırlarını "
                     "genişlet: ya üstü zaten sıkışıksa yukarı, ya altı hâlâ "
                     "temizse aşağı.")
        else:
            self.say("Çalışan en sıkı aralık: %d s  (saatte %.1f tren)"
                     % (limit, 3600.0 / limit))
            self.say("Senaryo bu aralıkla yazıldı.")
        why, where = binding
        if why:
            self.say("")
            self.say("Bir saniye altında bağlayan:")
            for reason, seconds in why:
                self.say("    %-28s %6.0f s" % (reason, seconds))
            self.say("Nerede (trenin gitmekte olduğu istasyona göre):")
            for station, seconds in where:
                self.say("    %-28s %6.0f s" % (station, seconds))
            self.say("Bir istasyon tek başına öne çıkıyorsa oraya bir peron "
                     "eklemek sinyalizasyonu değiştirmekten ucuzdur.")


def _mmss(seconds):
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def selfcheck():
    """Formdan LineSpec cikarmanin cetrefilli yerleri: tablo ayristirma.

    Benzetim kosturmuyor - onu trainsim.scenario.generate'in kendi demo'su
    yapiyor. Buradaki soru "kullanicinin yazdigi sey dogru okunuyor mu".
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    page = BuildPage()
    page.name.setText("deneme")
    page.count.setValue(4)
    page.spacing.setValue(9.0)
    page.refresh_stations()
    cells(page.stations, 1, ["B", "Bala", "10.0", "2", "hayır"])

    spec = page.spec()
    assert [sid for sid, _, _ in spec.stations] == list("ABCD"), spec.stations
    assert spec.stations[1][1] == "Bala", "istasyon adi elle degistirilebilmeli"
    assert spec.platforms["B"] == 2 and spec.platforms["A"] == 1, spec.platforms
    assert spec.depots == ["A", "D"], "uclar depo olarak isaretli gelmeli"
    assert len(spec.gradients) == 3, spec.gradients
    assert abs(sum(permille for _, _, permille in spec.gradients)) < 0.2, \
        "profil hatti gokyuzune tirmandirmamali"

    cells(page.limits, page.add_row(page.limits), ["12.0", "14.0", "60"])
    cells(page.limits, page.add_row(page.limits), ["9.0", "9.0", "60"])
    assert page.spec().speed_limits == [(12.0, 14.0, 60.0)], \
        "sifir uzunluktaki limit atilmali"

    page.system.setCurrentIndex(len(signalling.LADDER) - 1)
    page.capped.setChecked(True)
    page.cap_kmh.setValue(70)
    options = page.spec().signalling_options
    assert options["uncoupled_speed_kmh"] == 70, options
    assert options["leader_brake"] == "emergency", options
    page.capped.setChecked(False)
    assert "uncoupled_speed_kmh" not in page.spec().signalling_options
    page.system.setCurrentIndex(0)
    assert page.spec().signalling_options == {}, "sistemin almadigi ayar yazilmaz"

    cells(page.fleet, page.add_row(page.fleet),
          ["EXP", "Ekspres", 160, 140, 0.8, 0.9, 1.4])
    page.trains.setValue(3)
    page.headway.setValue(200)
    page.fill_services()
    cells(page.services, 1, ["S02", "EXP", "07:05", "A D", 30])
    spec = page.spec()
    assert spec.stock_id == "EMU" and spec.extra_stock[0]["id"] == "EXP"
    assert len(spec.services_spec) == 3, spec.services_spec
    assert spec.services_spec[0]["departure_s"] == 7 * 3600
    assert spec.services_spec[1]["departure_s"] == 7 * 3600 + 300, "saat okunmali"
    assert spec.services_spec[1]["calls"] == ["A", "D"], "duraklar okunmali"
    assert spec.services_spec[0]["calls"] is None, "bos durak = hepsi"

    cells(page.services, 2, ["S03", "EMU", "07:10", "A Z", 30])
    try:
        page.spec()
        raise AssertionError("olmayan istasyon sessizce gecmemeli")
    except ValueError as exc:
        assert "Z" in str(exc), exc

    page.auto.setChecked(True)
    assert page.spec().services_spec is None, "otomatige donunce elle plan biter"
    print("ui_build selfcheck tamam")


if __name__ == "__main__":
    selfcheck()
