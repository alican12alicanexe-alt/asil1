"""What does this circuit actually hold, and how much of that is the signalling?

``--check`` gives the theoretical all-green headway from signal spacing alone.
This gives the measured one, which is the figure to believe: it runs the same
flight of laps at every interval from five minutes down to well under one, and
reports what each costs. The plan is rebuilt at each interval from the
unimpeded lap times, so it is always workable in isolation - any delay that
appears therefore belongs to trains getting in each other's way, and not to a
timetable that was never possible.

Run it once per signalling system and the answers stack up into the comparison
this scenario exists for:

    python scenarios/ring/_sweep_headway.py                  3-aspect
    python scenarios/ring/_sweep_headway.py etcs_l2
    python scenarios/ring/_sweep_headway.py etcs_moving_block
    python scenarios/ring/_sweep_headway.py virtual_coupling

The fleet is fitted to the system by trainsim.core.signalling.fit_timetable, so
each run is measured on a train that has the equipment its signalling needs -
moving block wants the integrity report, virtual coupling the radio on top of
it - rather than on one unfitted unit reported under three names.

Three numbers per row:

  restrained   seconds the flight spent with its speed held down by a signal
               rather than by line speed or a booked stop. The direct cost of
               the signalling, and the first thing to move as trains close up.
               Reported over the baseline the flight pays with the railway to
               itself, which on a stopping service is not small: every lap is
               twenty-two approaches to a platform.
  mean delay   how late the average train was at the end of its lap.
  worst        the worst single arrival, which is what a passenger notices.

The all-green headway is the shortest interval where no train restrains another
and nothing arrives late. Below it the flight does not fail at once - it
degrades, each train a little later than the one in front, which is how a real
railway behaves when it is booked tighter than it can work.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import (COUNT, OPTIONS, flight_spec, probe_all,
                                 simulation, INFRA, STOCK)
from trainsim.analysis.kpi import measure
from trainsim.core import signalling as reg
from trainsim.scenario.loader import build_timetable

#: Enough time after the last train is away for it to finish its lap - a lap is
#: about 79 minutes with the railway to itself, and rather longer when the
#: circuit is full.
TAIL_S = 7200

#: Wide enough at the top to start clear of anything this circuit might hold,
#: and fine enough at the bottom to show it degrading rather than simply
#: failing. A stopping service every three kilometres will bind well above the
#: intervals scenarios/express reaches - the platform is in the way long before
#: the following distance is.
HEADWAYS = (300, 240, 195, 165, 135, 120, 105, 90, 75, 60, 50, 45, 40, 35, 30)

#: What the flight is, for the line main() prints above the table. A constant
#: because _sweep_express.py runs this same sweep over a non-stop flight, and a
#: sweep that says it is measuring twenty-two calls a lap when it is measuring
#: none is a sweep nobody can read.
FLIGHT_DESCRIPTION = "every one calling at all eleven stations twice"


def stock_for(system):
    """A copy of :data:`STOCK` fitted for ``system``."""
    level, tims, v2v = reg.fitment_for(system)
    unit = dict(STOCK)
    unit["etcs_level"], unit["tims"], unit["v2v"] = level, tims, v2v
    return unit


def run(times, headway_s, system, count=COUNT, indices=None):
    timetable = build_timetable(
        flight_spec(times, headway_s, count, indices,
                    stock=stock_for(system)), INFRA)
    sim = simulation(timetable, duration_s=headway_s * count + TAIL_S,
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
    booked arrival. The threshold is 30 s because that is where the simulator
    itself stops printing "on time".
    """
    worst = max(metrics.delays.values()) if metrics.delays else 0.0
    return worst < 30.0 and metrics.completed == metrics.services


def refine(times, system, test, clean_s, degraded_s):
    """Narrow the boundary between a clean interval and a degraded one to 1 s.

    The coarse sweep only says the answer is somewhere between two of its rows.
    This halves that bracket until one second separates the two ends, which
    costs four or five runs rather than the fifteen a second-by-second sweep
    would. It assumes the railway does not un-degrade as the interval tightens.
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
    # What the flight pays with the railway to itself. Every lap now takes the
    # same face at every station, so the services do pay the same; it is still
    # summed service by service rather than multiplied, because that stays true
    # if the roads are ever spread across the faces again.
    alone = sum(run(times, HEADWAYS[0], system, indices=[n]).total_restrained_s
                for n in range(COUNT))
    print("%d laps of the circuit, %s, under %s"
          % (COUNT, FLIGHT_DESCRIPTION, system))
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
    print("all-green headway: %d s (%.1f trains an hour) - the closest these "
          "trains follow" % (exact, 3600.0 / exact))
    print("each other without one of them ever being checked by a signal. One "
          "second closer,")
    print("at %d s, one of them is." % (exact - 1,))

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
    print("keeps-time headway: %d s (%.1f trains an hour) - trains are checked "
          "here and the" % (punctual, 3600.0 / punctual))
    print("run is no longer all-green, but every one of them still makes its "
          "booked arrival.")


if __name__ == "__main__":
    # A second argument, for virtual coupling, picks which brake the follower
    # credits the train in front with:
    #
    #   python scenarios/ring/_sweep_headway.py virtual_coupling service
    #
    # "service" is the convoy braking rule of the literature and is worth a
    # great deal of separation - see VirtualCoupling._run_on_m for what it
    # assumes and what this model does not enforce.
    if len(sys.argv) > 2:
        if sys.argv[1] != "virtual_coupling":
            raise SystemExit("only virtual_coupling has a leader brake setting")
        OPTIONS["virtual_coupling"] = {"leader_brake": sys.argv[2]}
    main(*sys.argv[1:2])
