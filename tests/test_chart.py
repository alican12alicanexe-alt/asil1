"""The SVG chart renderer, and the run graphs built on it."""

import unittest
import xml.etree.ElementTree as ET

import support  # noqa: F401  - puts the package on the path

import graph
from trainsim.analysis import trace
from trainsim.analysis.chart import Chart, document, nice_step

SVG = "{http://www.w3.org/2000/svg}"


class TestNiceStep(unittest.TestCase):

    def test_a_step_is_one_two_or_five_times_a_power_of_ten(self):
        """What keeps an axis reading 0/20/40 rather than 0/17/34."""
        for span in (0.4, 3.0, 7.0, 60.0, 130.0, 4200.0):
            step = nice_step(span)
            scaled = step
            while scaled < 1.0:
                scaled *= 10.0
            while scaled >= 10.0:
                scaled /= 10.0
            self.assertIn(round(scaled, 6), (1.0, 2.0, 5.0), span)

    def test_a_step_divides_the_span_into_a_readable_number_of_ticks(self):
        for span in (3.0, 60.0, 130.0, 4200.0):
            self.assertTrue(2 <= span / nice_step(span) <= 12, span)

    def test_an_empty_span_does_not_divide_by_zero(self):
        self.assertGreater(nice_step(0.0), 0.0)


class TestChart(unittest.TestCase):

    def test_a_chart_renders_as_well_formed_svg(self):
        chart = Chart("t", "x", "y").line("a", [(0, 0), (1, 5), (2, 3)])
        root = ET.fromstring("<svg xmlns='http://www.w3.org/2000/svg'>%s</svg>"
                             % chart.render(0, 0))
        self.assertTrue(root.findall(".//" + SVG + "path"))

    def test_an_empty_series_is_dropped_rather_than_drawn(self):
        chart = Chart("t", "x", "y")
        chart.line("nothing", [])
        chart.line("blanks", [(0, None), (1, None)])
        self.assertEqual(chart.series, [])

    def test_series_take_distinct_colours_in_turn(self):
        chart = Chart("t", "x", "y")
        for n in range(4):
            chart.line(str(n), [(0, n), (1, n)])
        colours = [s[2] for s in chart.series]
        self.assertEqual(len(set(colours)), 4)

    def test_a_document_is_sized_from_the_panels_it_holds(self):
        one = document([Chart("a", "x", "y").line("s", [(0, 0), (1, 1)])])
        four = document([Chart(str(n), "x", "y").line("s", [(0, 0), (1, 1)])
                         for n in range(4)])
        self.assertLess(_height(one), _height(four))
        for body in (one, four):
            ET.fromstring(body)

    def test_a_document_with_nothing_to_draw_is_an_error(self):
        with self.assertRaises(ValueError):
            document([])


def _height(body):
    return int(ET.fromstring(body).get("height"))


class TestRunGraph(unittest.TestCase):
    """graph.py reads the trace by column name, so the two must stay in step."""

    def _rows(self):
        sim, _, _ = support.build_test_sim(duration_s=900.0)
        recorder = trace.TraceRecorder(interval_s=10.0)
        sim.step_hooks.append(recorder)
        sim.run()
        return recorder.rows

    def test_every_column_it_reads_still_exists(self):
        for name in ("train", "time_s", "km", "speed_kmh", "gap_m",
                     "headway_s", "service_brake_m"):
            self.assertIn(name, graph.COL)

    def test_series_drops_samples_with_a_blank_on_either_axis(self):
        rows = self._rows()
        # Nothing is ahead of a single train, so every gap is blank.
        self.assertEqual(graph.series(rows, "km", "gap_m"), [])
        self.assertTrue(graph.series(rows, "km", "speed_kmh"))

    def test_the_fleet_mean_is_binned_by_position_not_by_time(self):
        rows = self._rows()
        means = graph.binned_mean(rows, "km", "speed_kmh", 0.5)
        self.assertTrue(means)
        # One point per occupied half-kilometre, in order, and each is a speed.
        self.assertEqual(means, sorted(means))
        for _, value in means:
            self.assertGreaterEqual(value, 0.0)

    def test_a_leading_path_is_the_scenario_and_the_rest_are_trains(self):
        """Positionals split around an option, which is what people type."""
        # A real path, because that is the test: a first argument is the
        # scenario when it exists on disk and a train when it does not.
        args = graph.parse_arguments([support.CAPACITY, "--system",
                                      "virtual_coupling", "U03", "U08"])
        self.assertEqual(args.scenario, support.CAPACITY)
        self.assertEqual(args.trains, ["U03", "U08"])

    def test_the_scenario_may_be_named_instead_of_led_with(self):
        args = graph.parse_arguments(["--scenario", support.CAPACITY, "U03"])
        self.assertEqual(args.scenario, support.CAPACITY)
        self.assertEqual(args.trains, ["U03"])

    def test_giving_it_both_ways_is_refused_rather_than_guessed(self):
        with self.assertRaises(SystemExit):
            graph.parse_arguments([support.CAPACITY, "--scenario",
                                   support.CAPACITY, "U03"])

    def test_with_no_scenario_at_all_there_is_a_default(self):
        args = graph.parse_arguments(["U03"])
        self.assertEqual(args.scenario, graph.DEFAULT_SCENARIO)
        self.assertEqual(args.trains, ["U03"])

    def test_a_mistyped_option_is_still_refused(self):
        """Gathering the leftovers must not swallow a typo silently."""
        with self.assertRaises(SystemExit):
            graph.parse_arguments(["--systemm", "virtual_coupling", "U03"])

    def test_stats_report_a_journey_rather_than_a_sample(self):
        rows = self._rows()
        summary = graph.stats("P", rows)
        self.assertGreater(summary["minutes"], 0.0)
        self.assertGreater(summary["max_kmh"], summary["mean_kmh"] * 0.5)
        # No train ahead: the separation columns say so rather than reading 0.
        self.assertIsNone(summary["min_gap_m"])
        self.assertIn("-", graph.table([summary]))


if __name__ == "__main__":
    unittest.main()
