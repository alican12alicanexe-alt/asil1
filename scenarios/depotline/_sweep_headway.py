"""What headway will this line actually hold?

Runs the same homogeneous flight at every interval from four minutes down to
one, and reports what each one costs. The plan is rebuilt at each interval from
the unimpeded run times, so it is always workable in isolation - which means any
delay that appears belongs to trains getting in each other's way and not to a
timetable that was never possible.

    python scenarios/depotline/_sweep_headway.py

Three numbers per row:

  restrained   seconds the flight spent with its speed held down by a signal
               rather than by line speed or a booked stop. The direct cost of
               the signalling, and the first thing to move as trains close up.
  mean delay   how late the average train was at its destination.
  worst        the worst single arrival, which is what a passenger notices.

The minimum workable headway is the shortest interval where all three stay at
zero. Below it the flight does not fall apart at once - it degrades, each train
a little later than the one in front, which is exactly how a real railway
behaves when it is booked tighter than it can work.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import COUNT, flight_spec, probe, simulation, INFRA
from trainsim.analysis.kpi import measure
from trainsim.scenario.loader import build_timetable

HEADWAYS = (240, 225, 210, 195, 180, 165, 150, 135, 120, 105, 90, 75, 60)


def run(times, headway_s):
    timetable = build_timetable(flight_spec(times, headway_s), INFRA)
    sim = simulation(timetable, duration_s=headway_s * COUNT + 3600)
    while not sim.finished:
        sim.step()
        if sim.all_services_done:
            break
    return measure(sim)


def main():
    times = probe()
    print("%d trains, all calling everywhere on the main road\n" % COUNT)
    print("  headway   restrained   mean delay      worst   completed")
    print("  " + "-" * 55)
    workable = None
    for headway in HEADWAYS:
        metrics = run(times, headway)
        worst = max(metrics.delays.values()) if metrics.delays else 0.0
        ok = (metrics.total_restrained_s == 0.0 and worst <= 1.0
              and metrics.completed == metrics.services)
        if ok:
            workable = headway
        print("  %5d s   %7.0f s    %7.1f s   %6.0f s   %d/%d %s"
              % (headway, metrics.total_restrained_s, metrics.mean_delay_s,
                 worst, metrics.completed, metrics.services,
                 "" if ok else "<-- degraded"))
    print()
    if workable is None:
        print("nothing in the range held the plan")
    else:
        print("shortest interval the line holds cleanly: %d s "
              "(%.1f trains an hour)" % (workable, 3600.0 / workable))


if __name__ == "__main__":
    main()
