"""What does this line actually hold, and how much of that is the signalling?

``--check`` gives the theoretical all-green headway from signal spacing alone.
This gives the measured one, which is the figure to believe: it runs the same
flight at every interval from five minutes down to one and reports what each
costs. The plan is rebuilt at each interval from the unimpeded run times, so it
is always workable in isolation - any delay that appears therefore belongs to
trains getting in each other's way, and not to a timetable that was never
possible.

Run it once per signalling system and the answers stack up into the comparison
this scenario exists for:

    python scenarios/capacity/_sweep_headway.py                  3-aspect
    python scenarios/capacity/_sweep_headway.py etcs_l2
    python scenarios/capacity/_sweep_headway.py etcs_moving_block
    python scenarios/capacity/_sweep_headway.py virtual_coupling

Three numbers per row:

  restrained   seconds the flight spent with its speed held down by a signal
               rather than by line speed or a booked stop. The direct cost of
               the signalling, and the first thing to move as trains close up.
               Reported over the baseline the flight pays with the railway to
               itself, because a train on an empty railway is still checked on
               every station approach - the platform signal is controlled and
               stands at danger until the interlocking sets a route over it.
               That toll is a property of the layout, not of the traffic.
  mean delay   how late the average train was at its destination.
  worst        the worst single arrival, which is what a passenger notices.

The all-green headway is the shortest interval where no train restrains another
and nothing arrives late. Below it the flight does not fail at once - it
degrades, each train a little later than the one in front, which is how a real
railway behaves when it is booked tighter than it can work.

Both directions run in every sweep. They are independent along the line but they
share the station throats, so the figure this reports is what the railway holds
rather than what one line holds.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import COUNT, flight_spec, probe_all, simulation, INFRA
from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable

#: Wide enough at the top to start clear of anything this line might hold, and
#: fine enough at the bottom to show it degrading rather than simply failing.
HEADWAYS = (300, 270, 240, 210, 195, 180, 165, 150, 135, 120, 105, 90, 75, 60)


def run(times, headway_s, system, count=COUNT, indices=None):
    timetable = build_timetable(
        flight_spec(times, headway_s, count, indices), INFRA)
    sim = simulation(timetable, duration_s=headway_s * count + 4200,
                     system=system)
    # measure() drives the run itself, one tick at a time, because the numbers
    # that matter here only exist while the trains are moving. Stepping the
    # simulation first and measuring afterwards hands it a railway on which
    # everything has already happened, and every per-tick column comes back zero.
    return measure(sim)


def main(system="fixed_block_3aspect"):
    times = probe_all()
    # What the flight pays with the railway to itself. Summed service by service
    # rather than taken once and multiplied: the services take the roads at each
    # station in turn, and a train routed through a loop is checked at a
    # different set of signals from one down the through road.
    alone = sum(run(times, HEADWAYS[0], system, indices=[n]).total_restrained_s
                for n in range(COUNT))
    print("%d trains each way, all calling everywhere, taking the roads at each "
          "station in turn, under %s" % (COUNT, system))
    print("the flight alone is restrained %.0f s at the controlled station "
          "signals; the column below is over that.\n" % alone)
    print("  headway   restrained   mean delay      worst   completed")
    print("  " + "-" * 55)
    all_green = None
    for headway in HEADWAYS:
        metrics = run(times, headway, system)
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        congestion = metrics.total_restrained_s - alone
        ok = (congestion <= 0.0 and worst <= 1.0
              and metrics.completed == metrics.services)
        if ok:
            all_green = headway
        print("  %5d s   %7.0f s    %7.1f s   %6.0f s   %d/%d %s"
              % (headway, congestion, metrics.mean_delay_s,
                 worst, metrics.completed, metrics.services,
                 "" if ok else "<-- degraded"))
    print()
    if all_green is None:
        print("no interval in the range ran all-green; widen HEADWAYS")
    else:
        print("all-green headway: %d s (%.1f trains an hour each way) - the "
              "closest these trains" % (all_green, 3600.0 / all_green))
        print("follow each other without one of them ever being checked by a "
              "signal.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
