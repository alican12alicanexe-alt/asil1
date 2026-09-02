"""Draw what a run actually did: speed, separation and headway, per train.

    python graph.py --system virtual_coupling U03
    python graph.py --system virtual_coupling U03 U08
    python graph.py --system etcs_moving_block --scenario scenarios/capacity
    python graph.py --system virtual_coupling --headway 30 U03 U04 U05

Name the trains you want and they are drawn individually; every panel also
carries the fleet mean over all sixteen services, so a train can be read
against what the rest of the railway was doing at the same place. Name none
and you get the fleet on its own.

Six panels. Speed against distance is the one to read first - it says where a
train was held down and by how much. Speed against time is the same run with
the axis an operator thinks in. The separation panel is the one a signalling
comparison lives in: the solid line is the gap to the rear of the train ahead,
and the dashed line beneath it is the distance that train would need to stop
from its current speed. Under moving block the gap tracks the dashed line,
because that is exactly what the authority is; under virtual coupling it sits
below it, because the follower is allowed to plan on the leader stopping too.
Time headway is that gap divided by speed, which is the quantity a timetable is
written in.

The data is the same per-tick trace that ``run.py --log`` writes, so a picture
and a spreadsheet of the same run agree by construction.

SVG is written directly rather than through a plotting library - see
trainsim/analysis/chart.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.analysis import trace
from trainsim.analysis.chart import PALETTE, Chart, document
from trainsim.core import signalling
from trainsim.scenario.loader import ScenarioError, build_simulation, load_scenario

#: Trace columns this script reads, by name, so a change to COLUMNS is a
#: KeyError here rather than a silently shifted plot.
COL = {name: index for index, name in enumerate(trace.COLUMNS)}


def collect(sim, interval_s):
    """Run ``sim`` with a trace recorder and return its rows grouped by train."""
    recorder = trace.TraceRecorder(interval_s=interval_s)
    sim.step_hooks.append(recorder)
    sim.run()
    by_train = {}
    for row in recorder.rows:
        by_train.setdefault(row[COL["train"]], []).append(row)
    return by_train


def series(rows, x, y):
    """``[(x, y)]`` from trace rows, dropping samples where either is blank."""
    xi, yi = COL[x], COL[y]
    return [(row[xi], row[yi]) for row in rows
            if row[xi] != "" and row[yi] != ""]


def binned_mean(all_rows, x, y, bin_width):
    """Fleet mean of ``y`` against ``x``, averaged into bins of ``bin_width``.

    Trains are at different places at any given moment, so a mean over time
    would average a train leaving a depot against one at line speed and mean
    nothing. Averaging by position instead asks what the railway does *here*,
    which is the question the panels next to it are answering.
    """
    xi, yi = COL[x], COL[y]
    totals = {}
    for row in all_rows:
        if row[xi] == "" or row[yi] == "":
            continue
        key = int(row[xi] / bin_width)
        total, count = totals.get(key, (0.0, 0))
        totals[key] = (total + row[yi], count + 1)
    return [((key + 0.5) * bin_width, total / count)
            for key, (total, count) in sorted(totals.items())]


def stats(train_id, rows):
    """One line of the summary table, in the units the panels use."""
    speeds = [r[COL["speed_kmh"]] for r in rows]
    gaps = [r[COL["gap_m"]] for r in rows if r[COL["gap_m"]] != ""]
    headways = [r[COL["headway_s"]] for r in rows if r[COL["headway_s"]] != ""]
    moving = [s for s in speeds if s > 1.0]
    return {
        "train": train_id,
        "minutes": (rows[-1][COL["time_s"]] - rows[0][COL["time_s"]]) / 60.0,
        "mean_kmh": sum(moving) / len(moving) if moving else 0.0,
        "max_kmh": max(speeds) if speeds else 0.0,
        "min_gap_m": min(gaps) if gaps else None,
        "mean_gap_m": sum(gaps) / len(gaps) if gaps else None,
        "min_headway_s": min(headways) if headways else None,
    }


def table(rows_of_stats):
    out = ["train  minutes  mean km/h  max km/h   min gap  mean gap  min headway",
           "-" * 70]
    for s in rows_of_stats:
        out.append("%-5s  %7.1f  %9.1f  %8.1f  %8s  %8s  %11s"
                   % (s["train"], s["minutes"], s["mean_kmh"], s["max_kmh"],
                      _or_dash(s["min_gap_m"], "%.0f m"),
                      _or_dash(s["mean_gap_m"], "%.0f m"),
                      _or_dash(s["min_headway_s"], "%.1f s")))
    return "\n".join(out)


def _or_dash(value, fmt):
    return "-" if value is None else fmt % (value,)


# ---------------------------------------------------------------------- panels

def build_charts(by_train, wanted, system, bin_width):
    all_rows = [row for rows in by_train.values() for row in rows]
    fleet_colour = "#8a8f98"

    speed_km = Chart("Speed against distance", "km along the line", "speed  km/h",
                     note="where each train was held down, and where it ran")
    speed_t = Chart("Speed against time", "minutes into the run", "speed  km/h",
                    note="the same run on the axis a timetable is written in")
    gap_km = Chart("Gap to the train ahead", "km along the line", "metres",
                   note="solid: gap to its rear. dashed: what it needs to stop "
                        "from there")
    hw_km = Chart("Time headway", "km along the line", "seconds",
                  note="the gap ahead at the speed the follower is doing")
    fleet_speed = Chart("Fleet mean speed", "km along the line", "speed  km/h",
                        note="every service, averaged by where it was")
    fleet_gap = Chart("Fleet mean gap", "km along the line", "metres",
                      note="mean separation from the train ahead, by position")

    for index, train_id in enumerate(wanted):
        rows = by_train[train_id]
        colour = PALETTE[index % len(PALETTE)]
        start = rows[0][COL["time_s"]]
        speed_km.line(train_id, series(rows, "km", "speed_kmh"), colour)
        speed_t.line(train_id, [((r[COL["time_s"]] - start) / 60.0,
                                 r[COL["speed_kmh"]]) for r in rows], colour)
        gap_km.line(train_id, series(rows, "km", "gap_m"), colour)
        # The follower's own service braking distance: what moving block would
        # have made it hold, drawn under what it actually held.
        gap_km.line("", series(rows, "km", "service_brake_m"), colour, dash=True)
        hw_km.line(train_id, series(rows, "km", "headway_s"), colour)

    # The fleet mean goes on every per-train panel too, so a single train is
    # always read against the railway rather than on its own.
    if wanted:
        speed_km.line("fleet", binned_mean(all_rows, "km", "speed_kmh", bin_width),
                      fleet_colour)
        gap_km.line("fleet", binned_mean(all_rows, "km", "gap_m", bin_width),
                    fleet_colour)
        hw_km.line("fleet", binned_mean(all_rows, "km", "headway_s", bin_width),
                   fleet_colour)

    fleet_speed.line("mean", binned_mean(all_rows, "km", "speed_kmh", bin_width),
                     fleet_colour)
    fleet_gap.line("mean gap", binned_mean(all_rows, "km", "gap_m", bin_width),
                   PALETTE[0])
    fleet_gap.line("braking distance",
                   binned_mean(all_rows, "km", "service_brake_m", bin_width),
                   PALETTE[1], dash=True)

    charts = [speed_km, speed_t, gap_km, hw_km, fleet_speed, fleet_gap]
    return [c for c in charts if c.series]


# ------------------------------------------------------------------------- cli

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="graph.py",
        description="Draw speed, separation and headway for a run.")
    parser.add_argument("trains", nargs="*", metavar="TRAIN",
                        help="service ids to draw, e.g. U03 U08. "
                             "With none, only the fleet mean is drawn")
    parser.add_argument("--scenario", default="scenarios/express",
                        help="scenario directory or file (default: %(default)s)")
    parser.add_argument("--system", default=None,
                        help="signalling system to run under; the fleet is "
                             "fitted for it, as run.py does")
    parser.add_argument("--leader-brake", choices=("emergency", "service"),
                        default=None, metavar="RATE",
                        help="virtual coupling only: which brake the follower "
                             "credits the train in front with")
    parser.add_argument("--as-fitted", action="store_true",
                        help="do not re-equip the fleet for --system")
    parser.add_argument("--duration", type=float, default=None,
                        help="override the run length, in simulated seconds")
    parser.add_argument("--every", type=float, default=2.0, metavar="SECONDS",
                        help="trace sampling interval (default: %(default)s)")
    parser.add_argument("--bin", type=float, default=0.5, metavar="KM",
                        help="bin width for the fleet means "
                             "(default: %(default)s km)")
    parser.add_argument("-o", "--out", default="graph.svg",
                        help="output file (default: %(default)s)")
    parser.add_argument("--log", metavar="FILE", default=None,
                        help="also write the underlying trace to a spreadsheet")
    args = parser.parse_args(argv)

    try:
        scenario = load_scenario(args.scenario)
    except ScenarioError as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2

    system = args.system
    if system is not None:
        if system not in signalling.REGISTRY:
            print("error: unknown signalling system %r - available: %s"
                  % (system, ", ".join(signalling.LADDER)), file=sys.stderr)
            return 2
        scenario.signalling_spec = {"system": system}
        if args.leader_brake and system == "virtual_coupling":
            scenario.signalling_spec["leader_brake"] = args.leader_brake
        if not args.as_fitted:
            changed = signalling.fit_timetable(scenario.timetable, system)
            if changed:
                print("fitted %s for %s" % (", ".join(changed), system),
                      file=sys.stderr)
            scenario.driver_config = signalling.fit_driver(
                scenario.driver_config, system)
    else:
        system = scenario.signalling_spec.get("system", "fixed_block_3aspect")

    overrides = {} if args.duration is None else {"duration_s": args.duration}
    try:
        sim = build_simulation(scenario, overrides)
    except ScenarioError as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2

    recorder = trace.TraceRecorder(interval_s=args.every)
    sim.step_hooks.append(recorder)
    sim.run()
    by_train = {}
    for row in recorder.rows:
        by_train.setdefault(row[COL["train"]], []).append(row)

    if not by_train:
        print("error: no train moved - nothing to draw", file=sys.stderr)
        return 1

    unknown = [t for t in args.trains if t not in by_train]
    if unknown:
        print("error: no such train%s: %s (have: %s)"
              % ("" if len(unknown) == 1 else "s", ", ".join(unknown),
                 ", ".join(sorted(by_train))), file=sys.stderr)
        return 2

    wanted = args.trains
    charts = build_charts(by_train, wanted, system, args.bin)
    heading = "%s  -  %s" % (scenario.name, sim.signalling.describe())
    if wanted:
        subheading = ("%s, sampled every %.0f s; fleet mean over %d services "
                      "in grey" % (", ".join(wanted), args.every, len(by_train)))
    else:
        subheading = ("fleet mean over %d services, sampled every %.0f s"
                      % (len(by_train), args.every))
    with open(args.out, "w") as handle:
        handle.write(document(charts, heading, subheading))

    if args.log:
        recorder.write(args.log)

    print(table([stats(t, by_train[t]) for t in
                 (wanted or sorted(by_train))]))
    print()
    print("wrote %s (%d panels, %d trace rows)"
          % (args.out, len(charts), len(recorder.rows)))
    if args.log:
        print("wrote %s" % (args.log,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
