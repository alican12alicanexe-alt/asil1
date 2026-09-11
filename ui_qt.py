# -*- coding: utf-8 -*-
"""Bir hatti birden fazla sinyalizasyon sistemi altinda kosturup karsilastir.

    python ui_qt.py

ui_tk.py ile ayni isi yapiyor, ayni hesabi kullaniyor (uicore.py); farki
goruntusu. Qt'nin verdikleri: yumusatilmis cizgiler, gercek DPI olcekleme,
QSS - yani stil sayfasi - ve isletim sisteminin kendi metin tarayicisi. Bedeli
bir bagimlilik: PySide6. tkinter surumu hicbir sey kurulamayan makineler icin
duruyor, ikisi de ayni sonucu veriyor.

    pip install PySide6-Essentials

Kosular QThread'de donuyor, sonuclar sinyalle geri geliyor: ayni parcacikta
kossaydi 12000 saniyelik bir tur boyunca pencere donardi.
"""
import os
import subprocess
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from ui_build import BuildPage
from uicore import (CARD, GRID, HERE, INK, INK_SOFT, MUTED, ON_INK, ORANGE,
                    ORANGE_DIM, PAPER, STRIPE, TRACK_COLOURS, TURKISH,
                    mmss, plot_box, run_one, scaler, scenario_paths, series)
from trainsim.core import signalling
from trainsim.core.units import format_delay
from trainsim.scenario.loader import ScenarioError, build_simulation, load_scenario

COLUMNS = ["SİSTEM", "SEFER SÜRESİ", "FARKI", "ORT. GECİKME", "KISITLI GEÇEN",
           "EN DAR ARALIK", "ORT. YETKİ", "BİTEN", "İHLAL"]
ROW_H = 38

STYLE = """
QWidget           { color: %(INK)s; font-size: 13px; }
#side             { background: %(INK)s; }
#side QLabel      { color: #FFFFFF; background: transparent; }
#brand            { font-size: 22px; font-weight: 700; }
#tagline, #status { color: %(ON_INK)s; font-size: 12px; }
QLabel[class="sectionHead"] { color: %(ON_INK)s; font-size: 11px; font-weight: 700;
                    letter-spacing: 1px; }

#body             { background: %(PAPER)s; }
#body QLabel      { background: transparent; }
#head             { font-size: 17px; font-weight: 700; }
#note             { color: %(MUTED)s; font-size: 12px; }
QWidget[class="card"] { background: %(CARD)s; border: 1px solid %(GRID)s;
                    border-radius: 10px; }

QPushButton#run   { background: %(ORANGE)s; color: #FFFFFF; font-weight: 700;
                    border: 0; border-radius: 8px; padding: 11px; }
QPushButton#run:hover    { background: %(ORANGE_DIM)s; }
QPushButton#run:disabled { background: %(INK_SOFT)s; color: %(ON_INK)s; }
QPushButton#ghost { background: transparent; color: #FFFFFF; border: 1px solid
                    %(INK_SOFT)s; border-radius: 8px; padding: 10px; }
QPushButton#ghost:hover { background: %(INK_SOFT)s; }
QPushButton#nav    { background: transparent; color: %(ON_INK)s; border: 0;
                    border-radius: 8px; padding: 10px 12px; text-align: left;
                    font-size: 13px; }
QPushButton#nav:hover   { background: %(INK_SOFT)s; color: #FFFFFF; }
QPushButton#nav:checked { background: %(INK_SOFT)s; color: #FFFFFF;
                    font-weight: 700; }
QPushButton#small  { background: %(CARD)s; color: %(INK)s; border: 1px solid
                    %(GRID)s; border-radius: 7px; padding: 6px 12px;
                    font-size: 12px; }
QPushButton#small:hover    { background: %(STRIPE)s; border-color: %(ORANGE)s; }
QPushButton#small:disabled { color: %(MUTED)s; }

QRadioButton      { color: %(INK)s; spacing: 8px; background: transparent; }
QRadioButton::indicator { width: 15px; height: 15px; border-radius: 8px;
                    background: %(CARD)s; border: 1px solid %(GRID)s; }
QRadioButton::indicator:checked { background: %(ORANGE)s;
                    border: 4px solid %(CARD)s; }
QSpinBox, QDoubleSpinBox, QTimeEdit, QPlainTextEdit {
                    background: %(CARD)s; color: %(INK)s; border: 1px solid
                    %(GRID)s; border-radius: 7px; padding: 6px 8px; }
QSpinBox:focus, QDoubleSpinBox:focus, QTimeEdit:focus { border-color: %(ORANGE)s; }
QSpinBox:disabled, QDoubleSpinBox:disabled, QTimeEdit:disabled,
QComboBox:disabled { color: %(MUTED)s; background: %(STRIPE)s; }
#body QComboBox, #body QLineEdit { background: %(CARD)s; color: %(INK)s;
                    border: 1px solid %(GRID)s; }
#body QLineEdit:focus { border-color: %(ORANGE)s; }
#body QComboBox::down-arrow { border-top-color: %(MUTED)s; }
#body QComboBox QAbstractItemView { background: %(CARD)s; color: %(INK)s;
                    border: 1px solid %(GRID)s; }
#body QCheckBox   { color: %(INK)s; }
#body QCheckBox::indicator { background: %(CARD)s; border: 1px solid %(GRID)s; }
#body QCheckBox::indicator:checked { background: %(ORANGE)s;
                    border-color: %(ORANGE)s; }
#body QCheckBox:disabled, #body QRadioButton:disabled { color: %(MUTED)s; }

QComboBox, QLineEdit { background: %(INK_SOFT)s; color: #FFFFFF; border: 0;
                    border-radius: 8px; padding: 9px 10px; selection-background-color:
                    %(ORANGE)s; }
QComboBox:focus, QLineEdit:focus { border: 1px solid %(ORANGE)s; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent;
                    border-right: 4px solid transparent; border-top: 5px solid
                    %(ON_INK)s; width: 0; height: 0; margin-right: 10px; }
QComboBox QAbstractItemView { background: %(INK_SOFT)s; color: #FFFFFF; border: 0;
                    outline: 0; selection-background-color: %(ORANGE)s; padding: 4px; }

QCheckBox         { color: #FFFFFF; spacing: 9px; padding: 3px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px;
                    background: %(INK_SOFT)s; border: 1px solid #44548A; }
QCheckBox::indicator:checked { background: %(ORANGE)s; border: 1px solid %(ORANGE)s; }

QTableWidget      { font-size: 12px; background: %(CARD)s; alternate-background-color: %(STRIPE)s;
                    border: 0; gridline-color: transparent; }
QTableWidget::item        { padding: 8px; border: 0; }
QTableWidget::item:selected { background: #E3ECF9; color: %(INK)s; }
QHeaderView::section { background: %(CARD)s; color: %(MUTED)s; font-size: 11px;
                    font-weight: 700; border: 0; border-bottom: 1px solid %(GRID)s;
                    padding: 9px 8px; text-align: left; }
QScrollBar:vertical   { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: %(GRID)s; border-radius: 5px; min-height: 30px;
                    min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
""" % globals()


class Graph(QtWidgets.QWidget):
    """Yatayda zaman, dikeyde hat boyunca mesafe, tren basina bir cizgi -
    demiryolunun en eski resmi. QPainter ciziyor, yani kenarlar yumusak."""

    def __init__(self):
        super(Graph, self).__init__()
        self.rows, self.title = [], ""
        self.setMinimumHeight(240)

    def show_run(self, rows, title):
        self.rows, self.title = rows, title
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(CARD))

        width, height = self.width(), self.height()
        left, top, right, bottom = plot_box(width, height)
        small = QtGui.QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 2))

        paths, (lo_x, hi_x, lo_y, hi_y) = series(self.rows)
        if not paths:
            painter.setPen(QtGui.QColor(MUTED))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "bir koşu seç")
            return

        bold = QtGui.QFont(self.font())
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QtGui.QColor(INK))
        painter.drawText(18, 22, self.title)
        painter.setFont(small)

        to_x = scaler(lo_x, hi_x, left, right)
        to_y = scaler(lo_y, hi_y, bottom, top)              # yukari dogru artiyor
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            value_x, value_y = (lo_x + (hi_x - lo_x) * fraction,
                                lo_y + (hi_y - lo_y) * fraction)
            x, y = to_x(value_x), to_y(value_y)
            painter.setPen(QtGui.QColor(GRID))
            painter.drawLine(QtCore.QPointF(x, top), QtCore.QPointF(x, bottom))
            painter.drawLine(QtCore.QPointF(left, y), QtCore.QPointF(right, y))
            painter.setPen(QtGui.QColor(MUTED))
            painter.drawText(QtCore.QRectF(x - 30, bottom + 4, 60, 16),
                             QtCore.Qt.AlignCenter, "%.0f" % value_x)
            painter.drawText(QtCore.QRectF(0, y - 8, left - 8, 16),
                             QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                             "%.0f" % value_y)

        for index, train_id in enumerate(sorted(paths)):
            line = QtGui.QPainterPath()
            for step, (minute, km) in enumerate(paths[train_id]):
                point = QtCore.QPointF(to_x(minute), to_y(km))
                line.moveTo(point) if step == 0 else line.lineTo(point)
            pen = QtGui.QPen(QtGui.QColor(TRACK_COLOURS[index % len(TRACK_COLOURS)]))
            pen.setWidthF(1.8)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(line)

        painter.setPen(QtGui.QColor(MUTED))
        painter.drawText(QtCore.QRectF(right - 240, bottom + 18, 240, 16),
                         QtCore.Qt.AlignRight, "koşunun kaçıncı dakikası")
        painter.save()                      # dik yazi: baslikla cakismiyor
        painter.translate(16, (top + bottom) / 2.0)
        painter.rotate(-90)
        painter.drawText(QtCore.QRectF(-100, -8, 200, 16),
                         QtCore.Qt.AlignCenter, "hat boyunca km")
        painter.restore()


class Runner(QtCore.QThread):
    """Kosular burada donuyor. Arayuze tek dokunus sinyaller uzerinden."""

    progress = QtCore.Signal(str)
    produced = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, path, chosen, duration, as_fitted):
        super(Runner, self).__init__()
        self.path, self.chosen = path, chosen
        self.duration, self.as_fitted = duration, as_fitted

    def run(self):
        try:
            for name in self.chosen:
                self.progress.emit("%s koşuyor…" % TURKISH.get(name, name))
                self.produced.emit(run_one(self.path, name, self.duration,
                                           self.as_fitted))
        except ScenarioError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:                   # kullanici gorsun, log'a degil
            self.failed.emit("%s: %s" % (type(exc).__name__, exc))


class Window(QtWidgets.QMainWindow):

    def __init__(self):
        super(Window, self).__init__()
        self.results, self.runner = [], None
        self.scenarios = scenario_paths()

        self.setWindowTitle("trainsim")
        self.resize(1320, 840)
        self.setMinimumSize(1060, 680)
        self.setStyleSheet(STYLE)

        centre = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(centre)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.builder = BuildPage()
        self.builder.built.connect(self.adopt)
        self.pages = QtWidgets.QStackedWidget()

        layout.addWidget(self.build_sidebar())
        self.pages.addWidget(self.build_body())
        self.pages.addWidget(self.builder)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(centre)
        self.show_page(0)

    # --------------------------------------------------------------- chrome

    def build_sidebar(self):
        """Marka, gezinme, sayfanin kendi denetimleri, durum satiri."""
        side = QtWidgets.QFrame()
        side.setObjectName("side")
        side.setFixedWidth(280)
        outer = QtWidgets.QVBoxLayout(side)
        outer.setContentsMargins(24, 26, 24, 24)
        outer.setSpacing(0)

        brand = QtWidgets.QLabel("trainsim")
        brand.setObjectName("brand")
        outer.addWidget(brand)
        tagline = QtWidgets.QLabel("Mikroskopik demiryolu benzetimi")
        tagline.setObjectName("tagline")
        outer.addWidget(tagline)

        outer.addSpacing(20)
        self.nav = []
        for index, label in enumerate(("Karşılaştır", "Hat kur")):
            button = QtWidgets.QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked, page=index:
                                   self.show_page(page))
            outer.addWidget(button)
            self.nav.append(button)

        # Her sayfanin kendi denetimleri; gezinme ikisinin de ustunde kaliyor.
        self.controls = QtWidgets.QStackedWidget()
        self.controls.addWidget(self.compare_controls())
        self.controls.addWidget(self.build_controls())
        outer.addSpacing(4)
        outer.addWidget(self.controls)

        outer.addSpacing(16)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        outer.addStretch(1)
        return side

    def compare_controls(self):
        panel = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        def head(text, space=18):
            box.addSpacing(space)
            label = QtWidgets.QLabel(text)
            label.setProperty("class", "sectionHead")
            box.addWidget(label)
            box.addSpacing(6)

        head("SENARYO", 14)
        self.scenario = QtWidgets.QComboBox()
        self.scenario.addItems(list(self.scenarios))
        box.addWidget(self.scenario)

        head("KOŞU SÜRESİ (S)")
        self.duration = QtWidgets.QLineEdit()
        self.duration.setPlaceholderText("boş bırakırsan senaryonunki")
        self.duration.setValidator(QtGui.QDoubleValidator(0.0, 1e7, 1))
        box.addWidget(self.duration)

        head("SİNYALİZASYON")
        self.systems = {}
        for name in signalling.LADDER:
            tick = QtWidgets.QCheckBox(TURKISH.get(name, name))
            tick.setChecked(name in ("fixed_block_3aspect", "etcs_moving_block",
                                     "virtual_coupling"))
            box.addWidget(tick)
            self.systems[name] = tick

        box.addSpacing(10)
        self.as_fitted = QtWidgets.QCheckBox("Senaryonun kendi donanımıyla")
        box.addWidget(self.as_fitted)

        box.addSpacing(22)
        self.run_button = QtWidgets.QPushButton("KARŞILAŞTIR")
        self.run_button.setObjectName("run")
        self.run_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.run_button.clicked.connect(self.start)
        box.addWidget(self.run_button)

        box.addSpacing(8)
        watch = QtWidgets.QPushButton("Şematiği izle")
        watch.setObjectName("ghost")
        watch.setCursor(QtCore.Qt.PointingHandCursor)
        watch.clicked.connect(self.watch)
        box.addWidget(watch)
        return panel

    def build_controls(self):
        panel = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        box.addSpacing(14)
        generate = QtWidgets.QPushButton("SENARYOYU ÜRET")
        generate.setObjectName("run")
        generate.setCursor(QtCore.Qt.PointingHandCursor)
        generate.clicked.connect(lambda: self.builder.start("build"))
        box.addWidget(generate)

        sweep = QtWidgets.QPushButton("Headway tara")
        sweep.setObjectName("ghost")
        sweep.setCursor(QtCore.Qt.PointingHandCursor)
        sweep.clicked.connect(lambda: self.builder.start("sweep"))
        box.addWidget(sweep)

        hint = QtWidgets.QLabel(
            "Üretmek boş hatta bir tren koşturur ve tarifeyi ondan yazar. "
            "Taramak aynı filoyu her aralıkta koşturur - dakikalar sürebilir.")
        hint.setObjectName("tagline")
        hint.setWordWrap(True)
        box.addWidget(hint)
        return panel

    def build_body(self):
        body = QtWidgets.QFrame()
        body.setObjectName("body")
        box = QtWidgets.QVBoxLayout(body)
        box.setContentsMargins(28, 26, 28, 26)
        box.setSpacing(0)

        def heading(title, note, space):
            box.addSpacing(space)
            label = QtWidgets.QLabel(title)
            label.setObjectName("head")
            box.addWidget(label)
            hint = QtWidgets.QLabel(note)
            hint.setObjectName("note")
            box.addWidget(hint)
            box.addSpacing(12)

        heading("Karşılaştırma",
                "Aynı hat, aynı tarife, aynı tren. Değişen tek şey trene ne "
                "kadar yol verildiği.", 0)

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setObjectName("table")
        self.table.setProperty("class", "card")
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        self.table.verticalHeader().setDefaultSectionSize(ROW_H)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # Sutunlar icerige gore, artan yeri sistem adi yutuyor - boylece sabit
        # genislik verip tasmak ya da yatay kaydirma cubugu gostermek gerekmiyor.
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        for index in range(len(COLUMNS)):        # baslik da veri gibi sola dayali
            self.table.horizontalHeaderItem(index).setTextAlignment(
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.table.itemSelectionChanged.connect(self.redraw)
        self.fit_table()
        box.addWidget(self.table)

        heading("Tren grafiği",
                "Yatayda zaman, dikeyde hat boyunca mesafe. Tablodan bir satır "
                "seç.", 22)

        card = QtWidgets.QFrame()
        card.setProperty("class", "card")
        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(2, 2, 2, 2)
        self.graph = Graph()
        inner.addWidget(self.graph)
        box.addWidget(card, 1)
        return body

    def fit_table(self):
        """Tablo bos yer birakmasin: yuksekligi satir sayisiyla buyusun."""
        rows = max(self.table.rowCount(), 1)
        self.table.setFixedHeight(self.table.horizontalHeader().height()
                                  + rows * ROW_H + 16)

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.controls.setCurrentIndex(index)
        for position, button in enumerate(self.nav):
            button.setChecked(position == index)

    def adopt(self, directory):
        """Yeni uretilen hatti listeye al ve sec - kurup karsilastirmaya
        gecerken ayrica aramak gerekmesin."""
        self.scenarios = scenario_paths()
        self.scenario.blockSignals(True)
        self.scenario.clear()
        self.scenario.addItems(list(self.scenarios))
        self.scenario.blockSignals(False)
        wanted = os.path.basename(directory)
        for index, label in enumerate(self.scenarios):
            if label.startswith(wanted + " /"):
                self.scenario.setCurrentIndex(index)
                break
        self.status.setText("%s listeye eklendi" % wanted)

    # -------------------------------------------------------------- actions

    def start(self):
        chosen = [name for name, tick in self.systems.items() if tick.isChecked()]
        if not self.scenario.currentText() or not chosen:
            QtWidgets.QMessageBox.information(
                self, "trainsim", "Bir senaryo ve en az bir sistem seç.")
            return
        self.results = []
        self.table.setRowCount(0)
        self.fit_table()
        self.graph.show_run([], "")
        self.run_button.setEnabled(False)

        self.runner = Runner(self.scenarios[self.scenario.currentText()], chosen,
                             float(self.duration.text() or 0),
                             self.as_fitted.isChecked())
        self.runner.progress.connect(self.status.setText)
        self.runner.produced.connect(self.add_row)
        self.runner.failed.connect(self.complain)
        self.runner.finished.connect(self.settle)
        self.runner.start()

    def complain(self, message):
        self.status.setText("")
        QtWidgets.QMessageBox.critical(self, "trainsim", message)

    def settle(self):
        self.run_button.setEnabled(True)
        if self.results:
            self.status.setText("%d koşu bitti" % len(self.results))
            if not self.table.selectedItems():
                self.table.selectRow(0)

    def add_row(self, result):
        self.results.append(result)
        metrics = result["metrics"]
        baseline = self.results[0]["metrics"]
        if metrics is baseline:
            delta = "—"
        else:
            difference = metrics.mean_journey_s - baseline.mean_journey_s
            delta = "aynı" if abs(difference) < 0.5 else format_delay(difference)
        cells = [TURKISH.get(metrics.system, metrics.system),
                 mmss(metrics.mean_journey_s),
                 delta,
                 "%.1f s" % metrics.mean_delay_s,
                 "%d s" % round(metrics.total_restrained_s),
                 "%d s" % round(metrics.min_headway_s) if metrics.min_headway_s else "—",
                 "%d m" % round(metrics.mean_authority_m),
                 "%d/%d" % (metrics.completed, metrics.services),
                 str(metrics.violations)]
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(cells):
            item = QtWidgets.QTableWidgetItem(text)
            if column == 0:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.table.setItem(row, column, item)
        self.fit_table()

    def redraw(self):
        rows = self.table.selectionModel().selectedRows()
        index = rows[0].row() if rows else -1
        if 0 <= index < len(self.results):
            result = self.results[index]
            self.graph.show_run(result["rows"],
                                TURKISH.get(result["name"], result["name"]))

    def watch(self):
        """Sematik gorunum kendi tk.Tk() kokunu aciyor (schematic_tk.py:66), o
        yuzden bu pencerenin icinde degil ayri bir surecte kosuyor.

        Kendimizi --watch ile yeniden cagiriyoruz: exe olarak paketlendiginde
        sys.executable exe'nin kendisi olur ve yaninda run.py bulunmaz."""
        if not self.scenario.currentText():
            return
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(os.path.abspath(__file__))
        command += ["--watch", self.scenarios[self.scenario.currentText()]]
        subprocess.Popen(command, cwd=HERE)


def watch_scenario(path):
    """Sematik gorunumu ac. Window.watch bunun icin kendini yeniden cagiriyor."""
    from trainsim.viz.schematic_tk import TkSchematicView
    scenario = load_scenario(path)
    TkSchematicView(scenario, build_simulation(scenario),
                    speed=float(scenario.view.get("speed", 30))).run()


def main():
    app = QtWidgets.QApplication(sys.argv)
    for family in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans"):
        if family in QtGui.QFontDatabase.families():
            app.setFont(QtGui.QFont(family, 10))
            break
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_scenario(sys.argv[sys.argv.index("--watch") + 1])
    else:
        main()
