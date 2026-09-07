"""The chart renderer, and the run graphs built on it."""

import unittest
import xml.etree.ElementTree as ET

import support  # noqa: F401  - puts the package on the path

import graph
from trainsim.analysis import trace
from trainsim.analysis.chart import Chart, document, figure

SVG = "{http://www.w3.org/2000/svg}"


class TestChart(unittest.TestCase):

    def test_a_chart_draws_one_line_per_series(self):
        chart = (Chart("t", "x", "y")
                 .line("a", [(0, 0), (1, 5), (2, 3)])
                 .line("b", [(0, 2), (1, 1), (2, 4)]))
        axes = figure([chart]).axes[0]
        self.assertEqual([line.get_label() for line in axes.get_lines()],
                         ["a", "b"])

    def test_the_axis_reads_in_ones_twos_or_fives(self):
        """What keeps an axis reading 0/20/40 rather than 0/17/34."""
        chart = Chart("t", "x", "y").line("a", [(0, 0), (130, 4200)])
        axes = figure([chart]).axes[0]
        for ticks in (axes.get_xticks(), axes.get_yticks()):
            steps = {round(b - a, 6) for a, b in zip(ticks, ticks[1:])}
            self.assertEqual(len(steps), 1, list(ticks))
            scaled = steps.pop()
            while scaled < 1.0:
                scaled *= 10.0
            while scaled >= 10.0:
                scaled /= 10.0
            self.assertIn(round(scaled, 6), (1.0, 2.0, 5.0), list(ticks))

    def test_a_document_is_well_formed_svg(self):
        body = document([Chart("t", "x", "y").line("a", [(0, 0), (1, 5)])])
        root = ET.fromstring(body)
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

    def test_a_part_full_last_row_leaves_no_empty_panel_behind(self):
        drawn = figure([Chart(str(n), "x", "y").line("s", [(0, 0), (1, 1)])
                        for n in range(3)]).axes
        self.assertEqual([ax.get_visible() for ax in drawn],
                         [True, True, True, False])

    def test_a_document_with_nothing_to_draw_is_an_error(self):
        with self.assertRaises(ValueError):
            document([])


def _height(body):
    """The page height, without whatever unit matplotlib wrote it in."""
    return float(ET.fromstring(body).get("height").rstrip("pt"))


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
