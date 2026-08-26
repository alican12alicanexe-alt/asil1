"""What does the diamond cost? Swept across every branch-train phase.

Comparing one flat run against one grade-separated run answers the question only
for the phasing that timetable happens to have. Move the branch trains ninety
seconds and the conflict can miss entirely - which makes a single number an
anecdote rather than a result, and would be an easy way to quote whatever figure
suited the argument.

So this sweeps the branch services across a whole service interval and reports
the distribution: what a flat junction costs at its best, at its worst, and on
average over the phasings a real timetable might land on. That is how junction
capacity is actually assessed - over the timetable, not over one path through it.

    python scenarios/junction/_sweep_phase.py
"""
import os
import sys
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from trainsim.analysis import kpi
from trainsim.scenario.loader import build_simulation, load_scenario

FLAT = os.path.join(HERE, "scenario-flat.yaml")
FLYOVER = os.path.join(HERE, "scenario-flyover.yaml")
#: The branch runs every six minutes, so shifting by more than that repeats.
INTERVAL_S = 360
STEP_S = 30
SHIFTED = "BU"          # the services whose phase is being swept


def shift(scenario, prefix, seconds):
    """Move every service whose id starts with ``prefix`` later by ``seconds``."""
    services = []
    for service in scenario.timetable.services:
        if not service.id.startswith(prefix) or not seconds:
            services.append(service)
            continue
        stops = [
            replace(
                stop,
                arrival_s=None if stop.arrival_s is None else stop.arrival_s + seconds,
                departure_s=(None if stop.departure_s is None
                             else stop.departure_s + seconds),
            )
            for stop in service.stops
        ]
        services.append(replace(service, stops=stops,
                                departure_s=service.departure_s + seconds))
    scenario.timetable = replace(scenario.timetable, services=services)
    return scenario


def measure(path, seconds):
    return kpi.measure(build_simulation(shift(load_scenario(path), SHIFTED, seconds)))


print("branch phase   flyover      flat     cost   restrained flat/flyover")
print("-" * 68)
costs = []
for offset in range(0, INTERVAL_S, STEP_S):
    flyover = measure(FLYOVER, offset)
    flat = measure(FLAT, offset)
    cost = flat.mean_journey_s - flyover.mean_journey_s
    costs.append((cost, offset))
    print("%9d s %9.0fs %9.0fs %+7.0fs %10.0fs / %.0fs"
          % (offset, flyover.mean_journey_s, flat.mean_journey_s, cost,
             flat.total_restrained_s, flyover.total_restrained_s))

values = [cost for cost, _ in costs]
best, worst = min(costs), max(costs)
print()
print("over %d phasings of the branch service:" % (len(costs),))
print("  best     %+6.0f s per train  (branch %d s later)" % (best[0], best[1]))
print("  mean     %+6.0f s per train" % (sum(values) / len(values),))
print("  worst    %+6.0f s per train  (branch %d s later)" % (worst[0], worst[1]))
print()
print("A flat junction does not cost the same every day. It costs nothing when")
print("the conflicting moves happen to miss each other and a great deal when")
print("they do not - which is why the case for grade separation is made against")
print("a whole timetable, and why a single figure from a single run is worth")
print("very little on its own.")
