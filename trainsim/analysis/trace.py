"""Per-tick trace of what every train was doing, written to a spreadsheet.

The summary tables say how the run came out; this says how it got there. One
row per train per sample, carrying the quantities the driver and the signalling
system actually worked from - speed, the acceleration that was applied, the
distance left in the movement authority, the braking distance needed from the
current speed, and the gap to the train in front - so a headway or a stop short
of a platform can be traced back to the tick where it started.

Nothing here feeds back into the simulation. The recorder is a step hook: it
reads state after the kernel has finished a tick and appends to a list, so a
traced run and an untraced one produce identical results.

Two output formats, chosen from the file extension. CSV is the default and
opens in any spreadsheet. XLSX is written directly - the format is a zip of
XML parts, and writing those five parts by hand is smaller than taking on a
spreadsheet dependency for a debug log.
"""

import csv
import os
import zipfile
from xml.sax.saxutils import escape

from ..core.signalling.common import train_ahead
from ..core.units import braking_distance, format_clock, ms_to_kmh

#: Column headings, in order. Each is paired with a getter in ``_row``.
COLUMNS = [
    "time_s", "clock", "train", "state",
    "km", "chainage_m", "speed_kmh", "accel_ms2",
    "target_kmh", "limit_kmh", "grade_permille",
    "authority_m", "service_brake_m", "emergency_brake_m",
    "ahead", "gap_m", "headway_s",
    "delay_s", "next_stop", "reason",
]


class TraceRecorder:
    """Samples every active train once per ``interval_s`` of simulated time."""

    def __init__(self, interval_s: float = 0.0):
        #: Zero means every tick. Anything larger samples on a grid, so a long
        #: run can be logged without a row per train per second.
        self.interval_s = float(interval_s)
        self.rows = []
        self._next_sample_s = None

    # ------------------------------------------------------------------ capture

    def __call__(self, sim) -> None:
        """Step hook: called by the kernel at the end of each tick."""
        now = sim.time_s
        if self._next_sample_s is None:
            self._next_sample_s = now
        if now + 1e-9 < self._next_sample_s:
            return
        self._next_sample_s = now + max(self.interval_s, sim.dt)
        for train in sim.trains.values():
            if train.is_active:
                self.rows.append(_row(train, sim))

    # ------------------------------------------------------------------- output

    def write(self, path: str) -> str:
        """Write the trace to ``path``; the extension picks the format."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".xlsx":
            _write_xlsx(path, COLUMNS, self.rows)
        else:
            _write_csv(path, COLUMNS, self.rows,
                       delimiter="\t" if ext == ".tsv" else ",")
        return path


def _row(train, sim):
    """One sample of a train, in the order of :data:`COLUMNS`."""
    speed = train.speed_ms
    stock = train.stock

    ahead = train_ahead(train, sim)
    if ahead is None:
        ahead_id, gap_m, headway_s = "", "", ""
    else:
        rear_m, ahead_id = ahead
        gap_m = round(rear_m - train.chainage_m, 1)
        # Time to close the gap at the current speed. Blank at a stand, where
        # it is infinite rather than large.
        headway_s = round(gap_m / speed, 1) if speed > 0.1 else ""

    authority_m = train.last_authority_m
    stop = train.next_stop()

    return [
        round(sim.time_s, 2),
        format_clock(sim.time_s),
        train.id,
        train.state,
        round(train.km, 3),
        round(train.chainage_m, 1),
        round(ms_to_kmh(speed), 2),
        round(train.applied_accel, 3),
        round(ms_to_kmh(train.target_speed_ms), 2),
        round(ms_to_kmh(train.path.speed_limit_at(train.chainage_m)), 1),
        round(train.grade_permille, 2),
        "" if authority_m is None else round(authority_m, 1),
        round(braking_distance(speed, stock.service_brake), 1),
        round(braking_distance(speed, stock.emergency_brake), 1),
        ahead_id,
        gap_m,
        headway_s,
        round(train.delay_s, 1),
        "" if stop is None else stop.station,
        train.authority_reason,
    ]


# ------------------------------------------------------------------- csv output

def _write_csv(path, columns, rows, delimiter=","):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(columns)
        writer.writerows(rows)


# ------------------------------------------------------------------ xlsx output

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="trace" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _column_name(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _cell(ref: str, value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = str(value)
    if isinstance(value, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    # Inline strings rather than a shared-string table: the trace repeats few
    # enough strings that the table would cost more than it saves, and it keeps
    # the writer to one part per sheet.
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(value)))


def _sheet_xml(columns, rows):
    names = [_column_name(i) for i in range(len(columns))]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           # Freeze the heading row: a trace is read by scrolling.
           '<sheetViews><sheetView workbookViewId="0">',
           '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>',
           '</sheetView></sheetViews>',
           '<sheetData>']
    out.append('<row r="1">%s</row>'
               % "".join(_cell(names[i] + "1", c) for i, c in enumerate(columns)))
    for number, row in enumerate(rows, start=2):
        cells = "".join(_cell("%s%d" % (names[i], number), v)
                        for i, v in enumerate(row))
        out.append('<row r="%d">%s</row>' % (number, cells))
    out.append("</sheetData></worksheet>")
    return "".join(out)


def _write_xlsx(path, columns, rows):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", _CONTENT_TYPES)
        book.writestr("_rels/.rels", _ROOT_RELS)
        book.writestr("xl/workbook.xml", _WORKBOOK)
        book.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        book.writestr("xl/worksheets/sheet1.xml", _sheet_xml(columns, rows))
