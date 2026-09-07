"""Timetable for the flat-crossing experiment: the circuit, and a railway over it.

    python scenarios/ring/_generate_cross.py [ring_headway_s] [cross_headway_s]

WHAT THIS MEASURES AND WHY IT IS NOT THE MERGE

The circuit already says what a signalling system is worth where the constraint
is a platform: not much, because a platform is not a following distance.
_generate_merge.py was meant to put the other kind of constraint on it and does
not quite - it joins the circuit at Akyurt 1, which is a station, so what binds
there is a platform road again, and only the joining half of the junction
conflicts at all.

This is the constraint on its own. Two railways cross at km 26.60 and share
nothing else - no connection, no platform, no merged flow - so the diamond is
the only interaction there is, and every movement on both railways conflicts
with the other railway.

NOTHING STOPS ON THE CIRCUIT

The circuit flight is the non-stop lap, for the reason infrastructure-cross.yaml
gives: stations sit every three kilometres or so, and there is nowhere to put a
crossing that is clear of one. With no train calling anywhere, it does not have
to be - the diamond is the only thing in the way wherever it sits.

THE CROSSING FLIGHT

Sanayi to Batikent on the up road and back the other way on the down, eleven
kilometres, one call at each end. Not a lap and not a circuit: this railway is
the traffic over the diamond, not a second thing being measured. Both flights
are booked at times each achieves with the other railway absent, so a delay in a
run belongs to the two railways meeting rather than to a plan that never worked.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_express as express          # rebinds ring.LAP (must come first)
import _generate_timetable as ring
from _generate_timetable import (BASE, COUNT, DWELL, READY_LEAD, STOCK,
                                 format_clock, probe_all, simulation,
                                 stock_yaml)
from trainsim.scenario.loader import build_timetable

INFRA_FILE = "infrastructure-cross.yaml"
ring.use_infrastructure(INFRA_FILE)

#: How many services on the crossing railway, each way. Enough to put a train
#: over the diamond often enough to be in the circuit's way, few enough that
#: the crossing railway is never queueing on its own account.
CROSS_COUNT = 8

#: The crossing railway's two runs, as ``(station, line)`` in the order they
#: are called at. One call at each end and nothing between them: this railway
#: has no intermediate stations and wants none.
CROSS_UP_RUN = [("SANAYI", "CROSS_UP"), ("BATIKENT", "CROSS_UP")]
CROSS_DN_RUN = [("BATIKENT", "CROSS_DN"), ("SANAYI", "CROSS_DN")]


def cross_road(station, line):
    return "%s_%s_1" % (station, "UP" if line == "CROSS_UP" else "DN")


def probe_cross(run):
    """One crossing service with both railways to itself, timed at each end."""
    calls = [{"station": station, "platform": cross_road(station, line),
              "dwell_s": DWELL} for station, line in run]
    calls[0]["departure"] = format_clock(BASE)
    timetable = build_timetable(
        {"stock": [STOCK],
         "services": [{"id": "X", "stock": STOCK["id"],
                       "departure": format_clock(BASE),
                       "ready_lead_s": READY_LEAD, "calls": calls}]},
        ring.INFRA)
    sim = simulation(timetable, duration_s=4000)
    arrivals, departures = {}, {}
    was_index, was_state = None, None
    while not sim.finished:
        sim.step()
        train = sim.trains.get("X")
        if train is None:
            continue
        if was_index is not None and train.next_stop_index > was_index:
            arrivals[was_index] = sim.time_s
        if was_state == "dwelling" and train.state == "running":
            departures[train.next_stop_index - 1] = sim.time_s
        was_index, was_state = train.next_stop_index, train.state
        if train.state == "finished":
            break
    if len(arrivals) < len(run) - 1:
        raise SystemExit("the crossing probe did not finish: %d of %d calls"
                         % (len(arrivals) + 1, len(run)))
    return [(arrivals.get(i), departures.get(i)) for i in range(len(run))]


def cross_spec(times_up, times_dn, headway_s, count=CROSS_COUNT, offset_s=0,
               stock=None):
    """``count`` services each way over the crossing railway.

    The two directions are booked together rather than interleaved: a diamond
    does not care which way a train is going over it, and a flight each way at
    the same interval is the arrangement that puts the most movements over the
    crossing for the fewest trains.
    """
    unit = dict(stock or STOCK)
    services = []
    for label, run, times in (("XU", CROSS_UP_RUN, times_up),
                              ("XD", CROSS_DN_RUN, times_dn)):
        for n in range(count):
            shift = offset_s + n * headway_s
            entries = []
            for position, (station, line) in enumerate(run):
                arrival, departure = times[position]
                entry = {"station": station, "platform": cross_road(station, line),
                         "dwell_s": DWELL}
                if arrival is not None:
                    entry["arrival"] = format_clock(round(arrival) + shift)
                if departure is not None:
                    entry["departure"] = format_clock(round(departure) + shift)
                entries.append(entry)
            services.append({
                "id": "%s%02d" % (label, n + 1),
                "name": "%s %s - %s" % (format_clock(BASE + shift)[:5],
                                        run[0][0].title(), run[-1][0].title()),
                "stock": unit["id"], "departure": format_clock(BASE + shift),
                "ready_lead_s": READY_LEAD, "calls": entries})
    return services


def combined_spec(ring_times, ring_headway, times_up, times_dn, cross_headway,
                  count=COUNT, cross_count=CROSS_COUNT, offset_s=0, stock=None):
    """Both flights as one timetable spec, which is what the sweep runs."""
    spec = express.express_spec(ring_times, ring_headway, count, stock=stock)
    spec["services"] = spec["services"] + cross_spec(
        times_up, times_dn, cross_headway, cross_count, offset_s, stock=stock)
    return spec


HEADER = '''# ring flat-crossing timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_cross.py %d %d
#
# %d non-stop circuit services %d s apart, and %d crossing services each way
# %d s apart over the diamond at km 26.60. Every booked time is what that
# service achieves with the other railway absent, so any delay in a run is the
# two railways meeting on the crossing.
#
'''


def render(ring_times, ring_headway, times_up, times_dn, cross_headway, offset_s):
    out = [HEADER % (ring_headway, cross_headway, COUNT, ring_headway,
                     CROSS_COUNT, cross_headway) + stock_yaml(STOCK)]
    spec = combined_spec(ring_times, ring_headway, times_up, times_dn,
                         cross_headway, offset_s=offset_s)
    for service in spec["services"]:
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
    ring_headway = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    cross_headway = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    name = sys.argv[3] if len(sys.argv) > 3 else "timetable-cross"

    ring_times = probe_all()
    times_up, times_dn = probe_cross(CROSS_UP_RUN), probe_cross(CROSS_DN_RUN)
    leg = times_up[-1][0] - times_up[0][1]
    print("a crossing service, with the railway to itself: %d min %02d s"
          % (leg // 60, leg % 60))

    # Half the circuit's interval, so a crossing train reaches the diamond
    # between two circuit trains rather than on top of one. Landing them all on
    # top of each other would measure the offset rather than the crossing.
    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render(ring_times, ring_headway, times_up, times_dn,
                            cross_headway, offset_s=ring_headway // 2))
    print("wrote %s" % path)
