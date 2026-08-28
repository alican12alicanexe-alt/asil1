"""Command line entry point: run a scenario with or without the schematic view."""

import argparse
import os
import sys

from .analysis import kpi, propagation
from .core import signalling
from .core.units import format_clock, format_delay
from .scenario import checks
from .scenario.loader import ScenarioError, build_simulation, load_scenario


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="trainsim",
        description="Schematic microscopic railway simulator.",
    )
    parser.add_argument(
        "scenario",
        help="scenario directory, or a scenario.yaml / scenario.json file",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="run without a window and print a summary",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="override the run length, in simulated seconds",
    )
    parser.add_argument(
        "--speed", type=float, default=None,
        help="simulated seconds per real second in the view (default from scenario)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="raise on a block-exclusivity violation instead of logging it",
    )
    parser.add_argument(
        "--events", action="store_true",
        help="print the full event log after a headless run",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="load and validate the scenario, then report on it without running",
    )
    parser.add_argument(
        "--system", metavar="NAME", default=None,
        help="override the signalling system for this run, e.g. "
             "--system etcs_moving_block",
    )
    parser.add_argument(
        "--propagation", action="store_true",
        help="run the scenario with and without its declared disruptions and "
             "report what the incident cost, split into primary and knock-on "
             "delay; combine with --compare to run it under every ETCS level",
    )
    parser.add_argument(
        "--compare", nargs="*", metavar="SYSTEM", default=None,
        help="run the same timetable under several signalling systems and "
             "compare them; with no names, runs the whole ladder from "
             "conventional fixed block to moving block",
    )
    args = parser.parse_args(argv)

    try:
        scenario = load_scenario(args.scenario)
    except ScenarioError as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2

    if args.system is not None:
        if args.system not in signalling.REGISTRY:
            print("error: unknown signalling system %r - available: %s"
                  % (args.system, ", ".join(signalling.LADDER)), file=sys.stderr)
            return 2
        scenario.signalling_spec = {"system": args.system}

    overrides = {}
    if args.duration is not None:
        overrides["duration_s"] = args.duration
    if args.strict:
        overrides["strict"] = True

    try:
        sim = build_simulation(scenario, overrides)
    except ScenarioError as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 2

    if args.check:
        print(_describe(scenario, sim))
        unworkable = [i for i in checks.check_timetable(scenario.infrastructure,
                                                        scenario.timetable)
                      if i.kind != "clash"]
        bad_layout = checks.failures(_spacing(scenario))
        return 1 if (bad_layout or unworkable) else 0

    if args.propagation:
        # Without --compare, measure the scenario's own signalling system; with
        # it, run the named systems, or the whole ladder if none were named.
        systems = None
        if args.compare is not None:
            systems = args.compare or list(signalling.LADDER)
        return _run_propagation(scenario, systems, overrides)

    if args.compare is not None:
        return _run_comparison(scenario, args.compare or list(signalling.LADDER),
                               overrides)

    for warning in (checks.warn_if_unsignalable(scenario),
                    checks.warn_about_timetable(scenario)):
        if warning:
            print(warning, file=sys.stderr)

    if args.headless:
        return _run_headless(sim, show_events=args.events)
    return _run_view(scenario, sim, speed=args.speed)


# ----------------------------------------------------------------------- modes

def _run_headless(sim, show_events: bool) -> int:
    sim.run()
    print(sim.summary())
    print()
    print(_arrivals_table(sim))
    if show_events:
        print()
        print("event log")
        print("-" * 72)
        for event in sim.events:
            print(event)
    if sim.violations:
        print()
        print("BLOCK EXCLUSIVITY VIOLATIONS:")
        for violation in sim.violations:
            print("  " + violation)
        return 1
    return 0


def _run_comparison(scenario, systems, overrides) -> int:
    """Run one timetable under several signalling systems and tabulate the result.

    The infrastructure, the timetable, the rolling stock, the driver model and the
    interlocking are all held constant; only the train control system changes. Any
    difference in the table is therefore attributable to what the train is told
    and when, which is the only way the comparison means anything.
    """
    results = []
    for name in systems:
        if name not in signalling.REGISTRY:
            print("error: unknown signalling system %r - available: %s"
                  % (name, ", ".join(signalling.LADDER)), file=sys.stderr)
            return 2
        # A fresh scenario each time: signalling systems may hold state, and a
        # timetable must not carry anything over from the previous run.
        fresh = load_scenario(scenario.source or scenario.directory)
        fresh.signalling_spec = {"system": name}
        sim = build_simulation(fresh, overrides)
        print("running %-22s %s" % (name, sim.signalling.describe()), file=sys.stderr)
        results.append(kpi.measure(sim))

    print()
    print("same infrastructure, same timetable, same trains - only the train")
    print("control system differs")
    print()
    print(kpi.compare_table(results))

    fastest = min(results, key=lambda r: r.mean_journey_s)
    baseline = results[0]
    if fastest is not baseline and baseline.mean_journey_s:
        saved = baseline.mean_journey_s - fastest.mean_journey_s
        print()
        print("%s saves %.0f s per journey against %s (%.1f%%)"
              % (fastest.system, saved, baseline.system,
                 100.0 * saved / baseline.mean_journey_s))
    return 1 if any(r.violations for r in results) else 0


def _run_propagation(scenario, systems, overrides) -> int:
    """Account for what a declared incident cost, optionally under every level.

    Always two runs per system - the same railway with the incident and without
    it - because a disturbed run on its own says nothing. The difference is what
    the incident cost, and splitting it into primary and knock-on says how much
    of that the railway did to itself.
    """
    if not scenario.disruptions:
        print("error: %s declares no disruptions, so there is nothing to measure.\n"
              "       Add a disruptions: block, or see "
              "scenarios/corridor3/scenario-disrupted.yaml."
              % (scenario.name,), file=sys.stderr)
        return 2

    if systems is None:
        result = propagation.measure_propagation(
            scenario, build_simulation, overrides=overrides)
        print(propagation.report(result))
        return 0

    results = []
    for name in systems:
        if name not in signalling.REGISTRY:
            print("error: unknown signalling system %r - available: %s"
                  % (name, ", ".join(signalling.LADDER)), file=sys.stderr)
            return 2
        fresh = load_scenario(scenario.source or scenario.directory)
        print("running %-22s clean and disrupted" % (name,), file=sys.stderr)
        results.append(propagation.measure_propagation(
            fresh, build_simulation, system=name, overrides=overrides))

    print()
    print("the same incident, run through every train control system")
    print()
    print(propagation.compare_systems(results))
    print()
    print("primary    time lost by the train the incident happened to")
    print("knock-on   time lost by trains it merely got in the way of")
    print()
    print(propagation.report(results[0]))
    return 0


def _run_view(scenario, sim, speed=None) -> int:
    try:
        from .viz.schematic_tk import TkSchematicView
    except ImportError as exc:
        print(
            "error: the schematic view needs tkinter, which is missing from this "
            "Python (%s).\nRun with --headless instead." % (exc,),
            file=sys.stderr,
        )
        return 2
    view_speed = speed if speed is not None else scenario.view.get("speed", 30)
    view = TkSchematicView(scenario, sim, speed=float(view_speed))
    view.run()
    return 1 if sim.violations else 0


# --------------------------------------------------------------------- reports

def _describe(scenario, sim) -> str:
    infra = scenario.infrastructure
    network = infra.network
    lines = [
        "scenario       : %s" % scenario.name,
        "description    : %s" % (scenario.description or "-"),
        "directory      : %s" % os.path.abspath(scenario.directory),
        "",
        "stations       : %d (%s)" % (
            len(network.stations),
            ", ".join("%s/%d plat" % (s.name, len(s.platforms))
                      for s in network.stations.values()),
        ),
        "tracks         : %s" % ", ".join(sorted(infra.tracks)),
        "segments       : %d" % len(network.segments),
        "block sections : %d" % len(infra.blocks),
        "signals        : %d" % len(infra.signals),
        "",
        "signalling     : %s" % sim.signalling.describe(),
        "interlocking   : %s" % (sim.interlocking.describe()
                                 if sim.interlocking else "none (automatic block)"),
        "dispatch       : %s" % sim.dispatcher.describe(),
        "window         : %s for %.0f min" % (
            format_clock(sim.config.start_time_s), sim.config.duration_s / 60.0,
        ),
        "",
        checks.summarise(_spacing(
            scenario, getattr(sim.signalling, "sighting_distance_m", 0.0))),
        "",
        checks.summarise_timetable(
            checks.check_timetable(scenario.infrastructure, scenario.timetable),
            len(scenario.timetable.services)),
        "",
        _interlocking_report(scenario, sim),
    ]
    return "\n".join(lines)


def _interlocking_report(scenario, sim) -> str:
    """Points and controlled routes - the movements a signaller has to request."""
    infra = scenario.infrastructure
    if not infra.points and not infra.crossings:
        return "points         : none; every signal is plain automatic block"

    lines = []
    if infra.crossings:
        lines.append("level crossings of one line by another (diamonds)")
        seen = set()
        for block_id, others in sorted(infra.crossings.items()):
            for other in others:
                pair = tuple(sorted((block_id, other)))
                if pair in seen:
                    continue
                seen.add(pair)
                lines.append("  %-12s x %-12s  no connection, but only one train "
                             "at a time" % pair)
        lines.append("")
    lines.append("points and routes")
    for point in sorted(infra.points.values(), key=lambda p: (p.km, p.id)):
        lines.append("  %-18s %-8s km %6.3f  legs %-16s normal %s"
                     % (point.id, point.kind, point.km,
                        "/".join(point.legs), point.normal))

    controlled = sorted((r for r in infra.routes.values() if r.controlled),
                        key=lambda r: r.id)
    lines.append("  %d routes, %d of them controlled (a route must be requested "
                 "before the signal may clear):" % (len(infra.routes), len(controlled)))
    for route in controlled:
        lines.append("    %s" % route.describe())
        conflicts = sim.interlocking.conflicts_for(route.id) if sim.interlocking else ()
        if conflicts:
            lines.append("      cannot be set with: %s" % ", ".join(conflicts))

    lines.append("")
    lines.extend(_signal_control_report(infra, sim))
    return "\n".join(lines)


def _signal_control_report(infra, sim) -> list:
    """Which signals need a route, and what they read with nothing running.

    Worth stating explicitly, because it is the one place the interlocking is
    visible without watching a train: a controlled signal is dark-red on an empty
    railway and stays that way until somebody asks for the movement, while an
    automatic signal on the same railway is already green.
    """
    controlled = sorted(s.id for s in infra.signals.values() if s.controlled)
    automatic = [s.id for s in infra.signals.values() if not s.controlled]
    lines = [
        "  %d of %d signals are controlled: they read over points and stand at"
        % (len(controlled), len(infra.signals)),
        "  danger until a route is set from them. The other %d are plain"
        % (len(automatic),),
        "  automatic block and follow occupancy alone - there is no route to ask",
        "  for, which is what makes them automatic.",
    ]
    if not controlled:
        return lines

    standing = sorted(set(sim.aspects.get(s, "?") for s in controlled))
    lines.append("  on an empty railway, with no route locked anywhere, the")
    lines.append("  controlled signals read: %s" % ", ".join(standing))
    if automatic:
        lines.append("  and the automatic ones read: %s"
                     % ", ".join(sorted(set(sim.aspects.get(s, "?")
                                            for s in automatic))))
    return lines


def _spacing(scenario, sighting_distance_m: float = 0.0):
    """Signal-spacing check results for this scenario."""
    return checks.check_block_lengths(
        scenario.infrastructure, scenario.timetable, scenario.driver_config,
        sighting_distance_m=sighting_distance_m,
    )


def _arrivals_table(sim) -> str:
    header = "%-5s %-28s %-9s %-8s %s" % (
        "id", "service", "state", "delay", "calls made")
    rows = [header, "-" * len(header)]
    for train in sorted(sim.trains.values(), key=lambda t: t.id):
        calls = ", ".join(
            "%s %s" % (station, format_clock(when))
            for station, when in sorted(train.actual_arrivals.items(),
                                        key=lambda kv: kv[1])
        )
        rows.append("%-5s %-28s %-9s %-8s %s" % (
            train.id, train.name[:28], train.state,
            format_delay(train.delay_s), calls or "-",
        ))
    return "\n".join(rows)


if __name__ == "__main__":
    sys.exit(main())
