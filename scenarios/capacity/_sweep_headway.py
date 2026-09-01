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

from _generate_timetable import (COUNT, flight_spec, probe_all, simulation,
                                 INFRA, STOCK)
from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable

#: What the train is fitted with, per system: (etcs_level, tims, v2v).
#:
#: The physical train never changes - same length, same power, same brake. What
#: changes is the equipment, and it has to change with the system or every
#: system is measured on the same unfitted unit and reports the same fallback
#: under three different names.
#:
#: Moving block needs the integrity report and nothing else: it follows the rear
#: of the train in front, and a rear that cannot be confirmed cannot be
#: followed. Virtual coupling needs the radio link on top of that, because it
#: plans to stop where the leader will stop rather than where it stands.
FITMENT = {
    "fixed_block_3aspect": ("none", False, False),
    "etcs_moving_block":   ("l3",   True,  False),
    "virtual_coupling":    ("l3",   True,  True),
}


def stock_for(system):
    """A copy of :data:`STOCK` fitted for ``system``."""
    try:
        level, tims, v2v = FITMENT[system]
    except KeyError:
        raise SystemExit(
            "no fitment declared for %r - add it to FITMENT" % (system,))
    unit = dict(STOCK)
    unit["etcs_level"], unit["tims"], unit["v2v"] = level, tims, v2v
    return unit

#: Wide enough at the top to start clear of anything this line might hold, and
#: fine enough at the bottom to show it degrading rather than simply failing.
HEADWAYS = (300, 270, 240, 210, 195, 180, 165, 150, 135, 120, 105, 90, 75, 60)


def run(times, headway_s, system, count=COUNT, indices=None):
    timetable = build_timetable(
        flight_spec(times, headway_s, count, indices,
                    stock=stock_for(system)), INFRA)
    sim = simulation(timetable, duration_s=headway_s * count + 4200,
                     system=system)
    # measure() drives the run itself, one tick at a time, because the numbers
    # that matter here only exist while the trains are moving. Stepping the
    # simulation first and measuring afterwards hands it a railway on which
    # everything has already happened, and every per-tick column comes back zero.
    return measure(sim)


def is_clean(metrics, alone):
    """Whether this interval ran all-green: nothing checked, nobody late.

    ``alone`` is what the flight pays with the railway to itself, so what is
    tested is the congestion on top of that rather than the total.
    """
    worst = max(metrics.delays.values()) if metrics.delays else 0.0
    return (metrics.total_restrained_s - alone <= 0.0 and worst <= 1.0
            and metrics.completed == metrics.services)


def keeps_time(metrics):
    """Whether the flight still ran to time at this interval.

    A weaker test than :func:`is_clean` and the one an operator would ask. A
    train can be checked by a signal, brake for a few seconds and still make its
    booked arrival, because a station-to-station run time is not the same thing
    as an unimpeded one. The threshold is 30 s because that is where the
    simulator itself stops printing "on time".
    """
    worst = max(metrics.delays.values()) if metrics.delays else 0.0
    return worst < 30.0 and metrics.completed == metrics.services


def refine(times, system, test, clean_s, degraded_s):
    """Narrow the boundary between a clean interval and a degraded one to 1 s.

    The coarse sweep only says the answer is somewhere between two of its rows -
    clean at 135 s, degraded at 120 s says nothing about 128 s. This halves that
    bracket until one second separates the two ends, which costs four or five
    runs rather than the fifteen a second-by-second sweep would.

    It assumes the railway does not un-degrade as the interval tightens. That is
    true of every case seen here, but it is an assumption: when the restraint
    column is not monotonic, this finds *a* boundary in the bracket rather than
    the only one.

    ``test`` is the question being asked of each run - all-green, or merely
    keeping time. Returns the tightest interval that still passed it, and every
    interval tried.
    """
    lo, hi = int(degraded_s), int(clean_s)   # lo is degraded, hi is clean
    tried = []
    while hi - lo > 1:
        mid = (lo + hi) // 2
        ok = test(run(times, mid, system))
        tried.append((mid, ok))
        if ok:
            hi = mid
        else:
            lo = mid
    return hi, tried


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
    # Two questions, asked of every row. "All-green" is the strict one: was any
    # train ever checked by a signal at all. "Keeps time" is the one an operator
    # would ask: did every train still make its booked arrival. They are not the
    # same interval and the gap is not small - a train can be throttled back for
    # twenty seconds on a forty-minute run and still arrive on the minute, which
    # is why a railway swept well past its all-green headway still looks, and
    # is, perfectly punctual to watch.
    green_ok, green_bad = None, None
    time_ok, time_bad = None, None
    for headway in HEADWAYS:
        metrics = run(times, headway, system)
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        congestion = metrics.total_restrained_s - alone
        ok = is_clean(metrics, alone)
        punctual = keeps_time(metrics)
        if ok:
            green_ok, green_bad = headway, None
        elif green_ok is not None and green_bad is None:
            green_bad = headway
        if punctual:
            time_ok, time_bad = headway, None
        elif time_ok is not None and time_bad is None:
            time_bad = headway
        note = "" if ok else ("<-- checked, still on time" if punctual
                              else "<-- late")
        print("  %5d s   %7.0f s    %7.1f s   %6.0f s   %d/%d %s"
              % (headway, congestion, metrics.mean_delay_s,
                 worst, metrics.completed, metrics.services, note))
    print()
    if green_ok is None:
        print("no interval in the range ran all-green; widen HEADWAYS")
        return
    if green_bad is None:
        print("every interval in the range ran all-green down to %d s; the "
              "railway has not" % (green_ok,))
        print("bent yet, so this is the end of HEADWAYS rather than a limit. "
              "Tighten the list.")
        return

    print("all-green between %d s and %d s. Closing in on the boundary:"
          % (green_ok, green_bad))
    exact, tried = refine(times, system,
                          lambda m: is_clean(m, alone), green_ok, green_bad)
    for headway, ok in tried:
        print("  %5d s   %s" % (headway, "clean" if ok else "checked"))
    print()
    print("all-green headway: %d s (%.1f trains an hour each way) - the closest "
          "these trains" % (exact, 3600.0 / exact))
    print("follow each other without one of them ever being checked by a "
          "signal. One second")
    print("closer, at %d s, one of them is." % (exact - 1,))

    # And the interval the railway actually keeps time at, which is the figure
    # to quote at anyone who has watched a run and seen nothing wrong with it.
    if time_ok is None:
        print()
        print("no interval in the range kept time; widen HEADWAYS")
        return
    if time_bad is None:
        print()
        print("every interval in the range kept time, down to %d s; where it "
              "stops doing" % (time_ok,))
        print("so is below the bottom of HEADWAYS.")
        return

    print()
    print("keeps time between %d s and %d s. Closing in:" % (time_ok, time_bad))
    punctual, tried = refine(times, system, keeps_time, time_ok, time_bad)
    for headway, ok in tried:
        print("  %5d s   %s" % (headway, "on time" if ok else "late"))
    print()
    print("keeps-time headway: %d s (%.1f trains an hour each way) - trains are "
          "checked here" % (punctual, 3600.0 / punctual))
    print("and the run is no longer all-green, but every one of them still "
          "makes its booked")
    print("arrival. A run at this interval looks entirely normal to watch.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
