"""Timetable for the merge experiment: the ring flight plus a branch flight.

    python scenarios/ring/_generate_merge.py [ring_headway_s] [branch_headway_s]

The circuit already measures what a signalling system is worth where the
constraint is a platform, and the answer there is "not much, because the
platform is not a following distance". This adds the other kind of constraint a
railway has: a flat junction, where two flows want the same piece of rail and
the interlocking has to choose.

A branch service is an ordinary circuit service with a tail at each end. It
leaves Sincan, works in over twelve kilometres of branch, JOINS THE UP LINE at
Akyurt 1 - crossing the down line on the level to get there - runs the full lap
exactly as a circuit service does, and comes off the down line at Akyurt 1 onto
the branch again, crossing nothing. So every branch train costs the down line
one crossing occupancy on its way in and nothing at all on its way out, which
is a property of the branch being on the far side of the railway.

Akyurt 1 rather than the tightest gap on purpose: Macunköy 1 has one face a
line, so merging there would measure the platform again. Akyurt 1 has four a
side, so the platform has room and what binds is the merge.

Both flights are booked at times each achieves with the railway to itself, so
any delay in a run belongs to the two flights meeting rather than to a
timetable that was never possible.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

from _generate_timetable import (BASE, COUNT, DWELL, HEADER, INFRA, LAP,
                                 READY_LEAD, STATIONS, STOCK, flight_spec,
                                 format_clock, probe_all, road, roads,
                                 simulation,
                                 stock_yaml)
from trainsim.scenario.loader import build_timetable

#: How many branch services, and where the branch calls before it reaches the
#: circuit. Sincan is twelve kilometres out, Örnek six.
BRANCH_COUNT = 6
BRANCH_STATIONS = ["SINCAN", "ORNEK"]

#: The branch lap: out over the branch, round the circuit once, back over the
#: branch. It does NOT repeat the circuit's final Akyurt 1 call - that call is
#: on the UP line, and a branch train leaves from the DN line.
BRANCH_LAP = ([(station, "SINCAN_UP", DWELL) for station in BRANCH_STATIONS]
              + [(station, "UP", DWELL) for station in STATIONS]
              + [(station, "DN", DWELL) for station in reversed(STATIONS)]
              + [(station, "SINCAN_DN", DWELL)
                 for station in reversed(BRANCH_STATIONS)])


#: The junction station, where the branch flight and the circuit flight meet.
JUNCTION_STATION = "AKYURT_1"


def branch_road(station, line):
    """The road a branch service takes.

    Its own on the branch; the circuit's everywhere on the circuit except at the
    junction station, where it takes the SECOND face rather than the first.

    That is the whole reason the junction is here and not at the tightest gap on
    the circuit. Akyurt 1 has four faces a side; every other station has one. Put
    both flights on one face and the platform binds before the junction does, and
    the run measures the platform for the third time - under fixed block it does
    not even manage that, because two trains booked into one face at a 180 s
    interval is a block exclusivity violation rather than a delay.
    """
    if line in ("SINCAN_UP", "SINCAN_DN"):
        return "%s_%s_1" % (station, "UP" if line == "SINCAN_UP" else "DN")
    if station == JUNCTION_STATION:
        return roads(station, line)[1]
    return road(station, line)


def branch_calls():
    entries = [{"station": station, "platform": branch_road(station, line),
                "dwell_s": dwell}
               for station, line, dwell in BRANCH_LAP]
    entries[0]["departure"] = format_clock(BASE)
    return entries


def probe_branch():
    """One branch service with the railway to itself, timed call by call."""
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "B", "stock": "EMU",
                       "departure": format_clock(BASE),
                       "ready_lead_s": READY_LEAD, "calls": branch_calls()}]},
        INFRA)
    sim = simulation(timetable, duration_s=14000)
    arrivals, departures = {}, {}
    was_index, was_state = None, None
    while not sim.finished:
        sim.step()
        train = sim.trains.get("B")
        if train is None:
            continue
        if was_index is not None and train.next_stop_index > was_index:
            arrivals[was_index] = sim.time_s
        if was_state == "dwelling" and train.state == "running":
            departures[train.next_stop_index - 1] = sim.time_s
        was_index, was_state = train.next_stop_index, train.state
        if train.state == "finished":
            break
    if len(arrivals) < len(BRANCH_LAP) - 1:
        raise SystemExit(
            "the branch probe did not finish: %d of %d calls made"
            % (len(arrivals) + 1, len(BRANCH_LAP)))
    return [(arrivals.get(i), departures.get(i)) for i in range(len(BRANCH_LAP))]


def branch_spec(times, headway_s, count=BRANCH_COUNT, offset_s=0):
    """``count`` branch services, ``headway_s`` apart, shifted by ``offset_s``."""
    services = []
    for n in range(count):
        shift = offset_s + n * headway_s
        entries = []
        for position, (station, line, dwell) in enumerate(BRANCH_LAP):
            arrival, departure = times[position]
            entry = {"station": station, "platform": branch_road(station, line),
                     "dwell_s": dwell}
            if arrival is not None:
                entry["arrival"] = format_clock(round(arrival) + shift)
            if departure is not None:
                entry["departure"] = format_clock(round(departure) + shift)
            entries.append(entry)
        services.append({
            "id": "S%02d" % (n + 1),
            "name": "%s Sincan - circuit - Sincan"
                    % (format_clock(BASE + shift)[:5],),
            "stock": STOCK["id"], "departure": format_clock(BASE + shift),
            "ready_lead_s": READY_LEAD, "calls": entries})
    return services


MERGE_HEADER = '''# ring merge timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_merge.py %d %d
#
# %d circuit services %d s apart, and %d branch services %d s apart sharing the
# up line with them from Akyurt 1. Every booked time is what that service
# achieves with the railway to itself, so the plan is workable in isolation and
# any delay in a run is the two flights meeting at the junction.
#
'''


def render(ring_times, ring_headway, branch_times, branch_headway, offset_s):
    out = [MERGE_HEADER % (ring_headway, branch_headway, COUNT, ring_headway,
                           BRANCH_COUNT, branch_headway) + stock_yaml(STOCK)]
    services = (flight_spec(ring_times, ring_headway, COUNT)["services"]
                + branch_spec(branch_times, branch_headway, offset_s=offset_s))
    for service in services:
        lines = ["  - id: %s" % service["id"],
                 "    name: %s" % service["name"],
                 "    stock: %s" % service["stock"],
                 '    departure: "%s"' % service["departure"],
                 "    ready_lead_s: %d" % READY_LEAD,
                 "    calls:"]
        for entry in service["calls"]:
            bits = ["station: %s" % entry["station"],
                    "platform: %s" % entry["platform"]]
            if "arrival" in entry:
                bits.append('arrival: "%s"' % entry["arrival"])
            if "departure" in entry:
                bits.append('departure: "%s"' % entry["departure"])
            bits.append("dwell_s: %d" % entry["dwell_s"])
            lines.append("      - {%s}" % ", ".join(bits))
        out.append("\n".join(lines))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    ring_headway = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    branch_headway = int(sys.argv[2]) if len(sys.argv) > 2 else 360
    name = sys.argv[3] if len(sys.argv) > 3 else "timetable-merge"

    ring_times = probe_all()
    branch_times = probe_branch()
    lap = branch_times[-1][0] - branch_times[0][1]
    print("a branch service, with the railway to itself: %d min %02d s "
          "(%d calls)" % (lap // 60, lap % 60, len(BRANCH_LAP)))

    # Half the circuit's interval, so a branch train arrives at the junction
    # between two circuit trains rather than on top of one. The experiment is
    # what happens as the branch interval tightens, not whether one arbitrary
    # offset happens to collide.
    offset = ring_headway // 2
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(ring_times, ring_headway, branch_times,
                            branch_headway, offset))
    print("wrote %s - %d circuit at %d s, %d branch at %d s (offset %d s)"
          % (path, COUNT, ring_headway, BRANCH_COUNT, branch_headway, offset))
