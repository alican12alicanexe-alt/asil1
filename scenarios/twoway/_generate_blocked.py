"""Regenerate scenarios/twoway/timetable-blocked.yaml - the diversion.

Same flight as _generate_timetable.py, with one change: every up service calls at
MARLOWE_DN_1_R rather than a Marlowe up road. That is the down main road taken in
the up direction, so the path finder takes each up train off its own line at
km 13.5, up the down line through Marlowe, and back at km 32.0.

The booked times are still each service's own unimpeded run - over the diversion,
since that is now its road - so the plan is workable by construction and the
delays the run reports are trains getting in each other's way.

    python scenarios/twoway/_generate_blocked.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_timetable as gen

# The up services are worked round the back of Marlowe: instead of calling at a
# Marlowe up road they call at the down main road, taken in the up direction.
def calls(line, pattern, shift=0, index=0):
    entries = []
    for station, dwell in pattern:
        road = gen.road(station, line, index)
        if line == "UP" and station == "MARLOWE":
            road = "MARLOWE_DN_1_R"
        entries.append({"station": station, "platform": road, "dwell_s": dwell})
    entries[0]["departure"] = gen.format_clock(gen.BASE + shift)
    return entries

gen.calls = calls
_road = gen.road
def road(station, line, index):
    if line == "UP" and station == "MARLOWE":
        return "MARLOWE_DN_1_R"
    return _road(station, line, index)
gen.road = road

times = gen.probe_all()
open(os.path.join(HERE, "timetable-blocked.yaml"), "w").write(
    gen.render(times, gen.HEADWAY_S).replace(
        "# twoway timetable - generated, do not edit by hand.",
        "# twoway timetable, Marlowe up main closed - generated, do not edit by hand."
    ).replace(
        "#   python scenarios/twoway/_generate_timetable.py",
        "#   python scenarios/twoway/_generate_blocked.py"))
print("wrote timetable-blocked.yaml")
