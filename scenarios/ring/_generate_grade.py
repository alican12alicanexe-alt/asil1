"""Book the graded circuit: the ring flight, timed on infrastructure-grade.yaml.

    python scenarios/ring/_generate_grade.py [headway_s] [name]

The flight is the circuit's own - twelve laps, twenty-two calls apiece, the
same unit - and the only reason it needs its own timetable is that the times
are different. A train climbing at 15 per thousand accelerates away from a
platform more slowly than one on the level, and a train falling at 14 has to
start braking sooner, so a lap on the graded railway is not the lap that
timetable.yaml books.

Booking it on the railway it runs on is the whole point. Every time here is
what one service achieves with the graded circuit to itself, so a delay in a
full run belongs to trains getting in each other's way rather than to a plan
that was never possible on this ground - which is exactly the property
scenarios/ring has, and the only way the two can be compared.

Stdlib only, like everything else here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_timetable as ring
from _generate_timetable import COUNT, HEADWAY_S, format_clock, probe_all, render

#: The drawing this flight is timed on. Swapped here rather than in
#: _generate_timetable.py so the circuit's own scenarios stay level.
ring.use_infrastructure("infrastructure-grade.yaml")

HEADER = '''# ring-grade timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_grade.py
#
# %d laps of the graded circuit, booked %d seconds apart, all of them the same
# unit. Identical in shape to timetable.yaml and different in every time:
# these are what a lap achieves on infrastructure-grade.yaml with the railway
# to itself, gradients included.

'''


if __name__ == "__main__":
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else HEADWAY_S
    name = sys.argv[2] if len(sys.argv) > 2 else "timetable-grade"
    times = probe_all()
    lap = times[0][-1][0] - times[0][0][1]
    print("a lap of the graded circuit, with the railway to itself: "
          "%s to %s, %d min %02d s"
          % (format_clock(times[0][0][1]), format_clock(times[0][-1][0]),
             lap // 60, lap % 60))
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway, header=HEADER % (COUNT, headway)))
    print("wrote %s - %d laps at %d s" % (path, COUNT, headway))
