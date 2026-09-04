"""Draw what happens as the booked interval tightens, per signalling system.

    python3 _plot_capacity.py [capacity.svg]

_sweep_headway.py already computes every point in these panels and prints them
as a table: it runs the same flight at fifteen intervals from five minutes down
to well under one, and reports what each cost. It then throws the shape away
and reports a single number, the all-green headway.

The single number is the one worth quoting and it is not the interesting part.
A railway booked tighter than it can work does not fail at once - it degrades,
each train a little later than the one in front - and how sharply it degrades
is what separates a system with margin from one that is merely fast on paper.
That is a curve, and this draws it.

Two panels, the same railway both ways: the circuit's own stopping flight, and
scenarios/ring/scenario-express.yaml's non-stop one. Read them together. The
lineside systems sit in almost the same place on both, because a block section
is longer than a platform occupancy and the platform was never what bound them.
The distance-separated systems move bodily left, by the same 39 s each, because
for them the platform was the constraint and it is gone.

Slow: 160 runs of a twelve-train flight, twenty-odd minutes. It is an offline
picture, not something to put in a loop.

Drawn with matplotlib through trainsim/analysis/chart, the one thing here
outside the standard library. See requirements-optional.txt.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RING = os.path.join(HERE, "scenarios", "ring")
sys.path.insert(0, HERE)
sys.path.insert(0, RING)

import _generate_timetable as ring

#: Captured before _generate_express is imported, because importing it rebinds
#: LAP to the non-stop lap as its first act.
STOPPING_LAP = list(ring.LAP)
STOPPING_SPEC = ring.flight_spec

import _generate_express as express     # noqa: E402 - rebinds ring.LAP
import _sweep_headway as sweep          # noqa: E402

from trainsim.analysis.chart import PALETTE, Chart, document  # noqa: E402

#: The ladder, in the order a comparison reads it.
SYSTEMS = ("fixed_block_3aspect", "etcs_l2", "etcs_hybrid_l3",
           "etcs_moving_block", "virtual_coupling")
NAMES = {"fixed_block_3aspect": "fixed block, 3-aspect",
         "etcs_l2": "ETCS Level 2",
         "etcs_hybrid_l3": "ETCS Hybrid Level 3",
         "etcs_moving_block": "ETCS moving block",
         "virtual_coupling": "virtual coupling"}

#: One flight per panel: what to call it, which lap and spec it is, and the
#: intervals to sweep. The non-stop list runs further down because it gets
#: further down - the stopping flight is over 70 s before the platform stops it.
FLIGHTS = (
    ("the stopping flight", "twenty-two calls a lap, one face at every station",
     STOPPING_LAP, STOPPING_SPEC,
     (300, 240, 195, 165, 135, 120, 105, 90, 75, 60, 50, 45, 40, 35, 30)),
    ("the non-stop flight", "no calls between Akyurt 1 and Akyurt 1",
     express.EXPRESS_LAP, express.express_spec,
     (300, 240, 180, 150, 120, 100, 85, 70, 60, 50, 42, 36, 30, 26, 22, 18, 15)),
)


def sweep_flight(lap, spec, headways):
    """``{system: [(headway_s, worst_delay_s)]}`` for one flight.

    The sweep reads LAP and flight_spec when it is called, so pointing it at a
    flight is two rebinds - the arrangement _sweep_express.py uses, done twice
    here because this draws both flights in one process.
    """
    ring.LAP = lap
    sweep.flight_spec = spec
    times = sweep.probe_all()
    out = {}
    for system in SYSTEMS:
        points = []
        for headway in headways:
            metrics = sweep.run(times, headway, system)
            worst = max(metrics.delays.values()) if metrics.delays else 0.0
            # A flight that did not finish is not a delay, it is a failure, and
            # plotting it as a large number would say the wrong thing.
            if metrics.completed < metrics.services:
                worst = None
            points.append((headway, worst))
            print("  %-22s %4d s  %s" % (system, headway,
                                         "incomplete" if worst is None
                                         else "%6.0f s" % worst))
        out[system] = points
    return out


def panel(title, note, data, x_max):
    chart = Chart("Worst arrival delay, %s" % title,
                  "booked interval  seconds  (tighter to the left)",
                  "worst arrival  seconds", note=note,
                  width=560, height=320, x_max=x_max)
    for index, system in enumerate(SYSTEMS):
        chart.line(NAMES[system], data[system],
                   colour=PALETTE[index % len(PALETTE)])
    return chart


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "capacity.svg")
    charts = []
    for title, note, lap, spec, headways in FLIGHTS:
        print("sweeping %s ..." % title)
        charts.append(panel(title, note,
                            sweep_flight(lap, spec, headways),
                            x_max=max(headways)))
    with open(out, "w") as handle:
        handle.write(document(
            charts,
            heading="What tightening the interval costs",
            subheading="scenarios/ring - the same circuit, twelve services, "
                       "worked with stops and without. Every point is a full "
                       "run of the flight at that interval.",
            columns=1))
    print("wrote %s" % out)
