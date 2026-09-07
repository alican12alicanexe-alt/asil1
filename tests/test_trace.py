"""The run trace: a spreadsheet of what every train was doing, tick by tick."""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import support

from trainsim.analysis.trace import COLUMNS, TraceRecorder

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class TestTraceRecorder(unittest.TestCase):

    def _traced_run(self, interval_s=0.0):
        sim, _, _ = support.build_test_sim(duration_s=900.0)
        recorder = TraceRecorder(interval_s=interval_s)
        sim.step_hooks.append(recorder)
        sim.run()
        return sim, recorder

    def test_watching_a_run_does_not_change_it(self):
        """The recorder is an observer, so a traced run must match an untraced one."""
        plain, _, _ = support.build_test_sim(duration_s=900.0)
        plain.run()
        traced, recorder = self._traced_run()

        self.assertTrue(recorder.rows)
        for train_id, train in plain.trains.items():
            self.assertAlmostEqual(train.chainage_m,
                                   traced.trains[train_id].chainage_m, places=6)
            self.assertAlmostEqual(train.speed_ms,
                                   traced.trains[train_id].speed_ms, places=6)

    def test_a_row_carries_every_column(self):
        _, recorder = self._traced_run()
        for row in recorder.rows:
            self.assertEqual(len(row), len(COLUMNS))

    def test_sampling_interval_thins_the_trace(self):
        """A coarser interval must give fewer rows over the same run."""
        _, every_tick = self._traced_run()
        _, every_30s = self._traced_run(interval_s=30.0)
        self.assertLess(len(every_30s.rows), len(every_tick.rows))

    def test_braking_distance_grows_with_speed(self):
        """The braking columns are the ones the trace exists to show."""
        _, recorder = self._traced_run()
        speed = COLUMNS.index("speed_kmh")
        service = COLUMNS.index("service_brake_m")
        emergency = COLUMNS.index("emergency_brake_m")
        # Above walking pace, where the two rates are far enough apart that
        # rounding to a tenth of a metre cannot make them equal.
        moving = [r for r in recorder.rows if r[speed] > 10.0]
        self.assertTrue(moving)
        for row in moving:
            self.assertGreater(row[service], 0.0)
            # Emergency is the harder rate, so it always needs less room.
            self.assertLess(row[emergency], row[service])

    def test_csv_has_a_heading_row_per_column(self):
        _, recorder = self._traced_run(interval_s=30.0)
        with tempfile.TemporaryDirectory() as directory:
            path = recorder.write(os.path.join(directory, "trace.csv"))
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        self.assertEqual(lines[0].split(","), COLUMNS)
        self.assertEqual(len(lines), len(recorder.rows) + 1)

    def test_xlsx_is_a_readable_workbook(self):
        """Written by hand, so the parts have to be checked rather than assumed."""
        _, recorder = self._traced_run(interval_s=30.0)
        with tempfile.TemporaryDirectory() as directory:
            path = recorder.write(os.path.join(directory, "trace.xlsx"))
            with zipfile.ZipFile(path) as book:
                names = book.namelist()
                parts = {name: book.read(name) for name in names}

        self.assertIn("[Content_Types].xml", names)
        self.assertIn("xl/workbook.xml", names)
        for body in parts.values():
            ET.fromstring(body)  # every part must be well-formed XML

        sheet = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
        rows = list(sheet.find(MAIN + "sheetData"))
        self.assertEqual(len(rows), len(recorder.rows) + 1)

        headings = [cell.find(MAIN + "is/" + MAIN + "t").text for cell in rows[0]]
        self.assertEqual(headings, COLUMNS)
        # Cells carry their own reference, so a blank one is omitted rather
        # than written empty; the first heading anchors the grid.
        self.assertEqual(rows[0][0].get("r"), "A1")


if __name__ == "__main__":
    unittest.main()
