"""Sweep 2: what does the line hold when the trains are not all the same?

Same script as scenarios/capacity/_sweep_headway.py - same KPI definitions, the
same two questions, the same bisection - run against a flight of two alternating
types instead of one. The point is not the absolute numbers, which cannot be
compared with the base's directly because the line limit and the crossovers
moved with the fleet. The point is the *ranking*: does fixed block, moving block
and virtual coupling stand in the same order, and by the same margins, when a
quicker train is following a slower one every other path.

    python scenarios/capacity2/_sweep_headway.py fixed_block_3aspect
    python scenarios/capacity2/_sweep_headway.py etcs_moving_block
    python scenarios/capacity2/_sweep_headway.py virtual_coupling

Three numbers per row:

  restrained   seconds the flight spent with its speed held down by a signal
               rather than by line speed or a booked stop. Reported over the
               baseline the flight pays with the railway to itself.
  mean delay   how late the average train was at its destination.
  worst        the worst single arrival, which is what a passenger notices.

WHY THE INTERVAL LIST STARTS SO MUCH WIDER THAN THE BASE'S

On the homogeneous base every train covers the ground at the same rate, so a
gap booked at the depot is still there at the terminus and five minutes is
already loose. Here it is not: a fast unit makes up around a minute on every
fifteen-kilometre leg, so over four legs it eats about four minutes of the gap
in front of it whatever the signalling does. Book the flight at five minutes
and the fast trains arrive late on an empty railway - not because they were
obstructed but because they were booked behind something slower and the
timetable had nowhere for them to go.

That is a real property of a mixed flight at a uniform interval, and it is why
the list runs up to fifteen minutes: the sweep has to start somewhere the
railway is genuinely clean, or the first row is already the answer and nothing
has been measured.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import (COUNT, FLEET, flight_spec, fleet_for,
                                 probe_all, simulation, INFRA)
from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable

#: What the train is fitted with, per system: (etcs_level, tims, v2v).
#:
#: Identical to the base's, and applied to both types. What the trains can do
#: differs in this experiment; what they are fitted with must not, or the fleet
#: and the fitment move together and neither can be blamed for the result.
FITMENT = {
    "fixed_block_3aspect": ("none", False, False),
    "etcs_moving_block":   ("l3",   True,  False),
    "virtual_coupling":    ("l3",   True,  True),
}


def fleet_fitted(system):
    """A copy of :data:`FLEET` fitted for ``system`` - both types alike."""
    try:
        level, tims, v2v = FITMENT[system]
    except KeyError:
        raise SystemExit(
            "no fitment declared for %r - add it to FITMENT" % (system,))
    fitted = []
    for unit in FLEET:
        copy = dict(unit)
        copy["etcs_level"], copy["tims"], copy["v2v"] = level, tims, v2v
        fitted.append(copy)
    return tuple(fitted)


#: The base's list, with the top extended. Everything from 300 s down is exactly
#: what the base sweeps, so the two can be read side by side row for row; above
#: it are the intervals a mixed flight needs before it stops fighting its own
#: timetable.
HEADWAYS = (900, 780, 660, 600, 540, 480, 420, 360,
            300, 270, 240, 210, 195, 180, 165, 150, 135, 120, 105, 90, 75, 60)


def run(times, headway_s, system, count=COUNT, indices=None):
    timetable = build_timetable(
        flight_spec(times, headway_s, count, indices,
                    fleet=fleet_fitted(system)), INFRA)
    sim = simulation(timetable, duration_s=headway_s * count + 4200,
                     system=system)
    # measure() drives the run itself, one tick at a time, because the numbers
    # that matter here only exist while the trains are moving.
    return measure(sim)


def is_clean(metrics, alone):
    """Whether this interval ran all-green: nothing checked, nobody late."""
    worst = max(metrics.delays.values()) if metrics.delays else 0.0
    return (metrics.total_restrained_s - alone <= 0.0 and worst <= 1.0
            and metrics.completed == metrics.services)


def keeps_time(metrics):
    """Whether the flight still ran to time at this interval.

    The threshold is 30 s because that is where the simulator itself stops
    printing "on time".
    """
    worst = max(metrics.delays.values()) if metrics.delays else 0.0
    return worst < 30.0 and metrics.completed == metrics.services


def refine(times, system, test, clean_s, degraded_s):
    """Narrow the boundary between a clean interval and a degraded one to 1 s.

    Assumes the railway does not un-degrade as the interval tightens. Where the
    restraint column is not monotonic this finds *a* boundary in the bracket
    rather than the only one.
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
    alone = sum(run(times, HEADWAYS[0], system, indices=[n]).total_restrained_s
                for n in range(COUNT))
    fast = sum(1 for n in range(COUNT) if fleet_for(n) is FLEET[1])
    print("%d trains each way under %s: %d normal, %d fast, alternating, all "
          "calling everywhere" % (COUNT, system, COUNT - fast, fast))
    print("the flight alone is restrained %.0f s at the controlled station "
          "signals; the column below is over that.\n" % alone)
    print("  headway   restrained   mean delay      worst   completed")
    print("  " + "-" * 55)
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
    elif green_bad is None:
        print("every interval in the range ran all-green down to %d s; the "
              "railway has not" % (green_ok,))
        print("bent yet, so this is the end of HEADWAYS rather than a limit. "
              "Tighten the list.")
    else:
        print("all-green between %d s and %d s. Closing in on the boundary:"
              % (green_ok, green_bad))
        exact, tried = refine(times, system,
                              lambda m: is_clean(m, alone), green_ok, green_bad)
        for headway, ok in tried:
            print("  %5d s   %s" % (headway, "clean" if ok else "checked"))
        print()
        print("all-green headway: %d s (%.1f trains an hour each way) - the "
              "closest these trains" % (exact, 3600.0 / exact))
        print("follow each other without one of them ever being checked by a "
              "signal. One second")
        print("closer, at %d s, one of them is." % (exact - 1,))

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
    print("arrival.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
