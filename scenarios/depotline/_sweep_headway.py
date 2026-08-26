"""What headway will this line actually hold?

Runs the same homogeneous flight at every interval from six minutes down to
one, and reports what each one costs. The plan is rebuilt at each interval from
the unimpeded run times, so it is always workable in isolation - which means any
delay that appears belongs to trains getting in each other's way and not to a
timetable that was never possible.

    python scenarios/depotline/_sweep_headway.py
    python scenarios/depotline/_sweep_headway.py fixed_block_2block

Three numbers per row:

  restrained   seconds the flight spent with its speed held down by a signal
               rather than by line speed or a booked stop. The direct cost of
               the signalling, and the first thing to move as trains close up.
               Reported over the baseline a single train pays alone, because a
               train on an empty railway is still checked on every station
               approach - the platform signal is controlled, and stands at
               danger until the interlocking sets a route over it. That toll is
               a property of the layout, not of the traffic, and counting it as
               congestion would put a floor under every row and hide the thing
               being looked for.
  mean delay   how late the average train was at its destination.
  worst        the worst single arrival, which is what a passenger notices.

The minimum workable headway is the shortest interval where no train restrains
another and nothing arrives late. Below it the flight does not fall apart at
once - it degrades, each train a little later than the one in front, which is
exactly how a real railway behaves when it is booked tighter than it can work.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import COUNT, flight_spec, probe, simulation, INFRA
from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable

#: Wide enough at the top for two-block working, which needs the best part of
#: five minutes on this line, and fine enough at the bottom to show conventional
#: working degrading rather than simply failing.
HEADWAYS = (360, 330, 300, 285, 270, 240, 210, 180, 165, 150,
            135, 120, 105, 90, 75, 60)


def run(times, headway_s, system, count=COUNT):
    timetable = build_timetable(flight_spec(times, headway_s, count), INFRA)
    sim = simulation(timetable, duration_s=headway_s * count + 3600,
                     system=system)
    # measure() drives the run itself, one tick at a time, because the numbers
    # that matter here - seconds restrained, authority lengths, the closest two
    # trains ever came - only exist while the trains are moving. Stepping the
    # simulation first and measuring afterwards hands it a railway on which
    # everything has already happened, and every per-tick column comes back zero.
    return measure(sim)


def main(system="fixed_block_3aspect"):
    times = probe()
    # What one train pays with the railway to itself. Every row below is
    # reported over this, so the column shows trains obstructing each other and
    # nothing else.
    alone = run(times, HEADWAYS[0], system, count=1).total_restrained_s
    print("%d trains, all calling everywhere on the main road, under %s"
          % (COUNT, system))
    print("one train alone is restrained %.0f s at the controlled station "
          "signals; the column below is over that.\n" % alone)
    print("  headway   restrained   mean delay      worst   completed")
    print("  " + "-" * 55)
    workable = None
    for headway in HEADWAYS:
        metrics = run(times, headway, system)
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        congestion = metrics.total_restrained_s - alone * COUNT
        ok = (congestion <= 0.0 and worst <= 1.0
              and metrics.completed == metrics.services)
        if ok:
            workable = headway
        print("  %5d s   %7.0f s    %7.1f s   %6.0f s   %d/%d %s"
              % (headway, congestion, metrics.mean_delay_s,
                 worst, metrics.completed, metrics.services,
                 "" if ok else "<-- degraded"))
    print()
    if workable is None:
        print("nothing in the range held the plan")
    else:
        print("shortest interval the line holds cleanly: %d s "
              "(%.1f trains an hour)" % (workable, 3600.0 / workable))


if __name__ == "__main__":
    main(*sys.argv[1:2])
