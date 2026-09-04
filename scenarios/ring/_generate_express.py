"""Regenerate scenarios/ring/timetable-express.yaml - the circuit, run non-stop.

    python scenarios/ring/_generate_express.py [headway_s] [name]

The circuit's own timetable calls at every station twice a lap, and every
measurement made on it came back saying the same thing: what the interval has
to fit through is a platform road, not the distance between two trains. Moving
block holds 78 s there and virtual coupling 71 s - a 7 s spread, on a railway
where the signalling is not what is binding. A comparison of signalling systems
made on that is measuring the platform.

So this is the circuit with the platforms taken out of the way, which is what
scenarios/express does to scenarios/capacity and for the same reason. Two
changes, and nothing else:

  - NOTHING STOPS. A service is booked at Akyurt 1 on the up line and again at
    Akyurt 1 on the down line, and the twenty-one calls between them are run
    through. That is the circuit less the final horseshoe: out on the up line,
    round HS_EAST, back down the down line, and stand. It cannot be the full
    lap, because a service needs an origin and a destination and a path from
    one to the other - and a path from Akyurt 1 up to Akyurt 1 up is no path
    at all.

  - THE FOUR FACES AT AKYURT 1 ARE USED IN TURN. Everywhere else on this
    railway a flight puts every service on the same face on purpose, because
    that is the harder case and it is the one worth measuring. Here it would be
    the only case: with one face and thirty seconds standing, the terminus alone
    floors the interval somewhere around a minute, which is exactly the range
    the answer lives in, and the scenario would measure its own terminus rather
    than the line. Akyurt 1 has four roads a side, so the flight uses them in
    turn - the arrangement scenarios/express already uses at its depots.

Same drawing, same unit, same speed profile. The comparison against the ring's
own timetable is therefore a comparison of what trains are asked to do.

Stdlib only, like everything else here.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)

import _generate_timetable as ring
from _generate_timetable import (BASE, COUNT, DWELL, READY_LEAD, STOCK,
                                 format_clock, probe_all, roads, stock_yaml)

#: Origin and destination, and nothing between them. The stations in between
#: are passed rather than called at: a call in this timetable format is a stop,
#: so a non-stop service is one that books none.
EXPRESS_LAP = [("AKYURT_1", "UP", DWELL), ("AKYURT_1", "DN", DWELL)]

#: probe(), calls() and flight_spec() all read LAP when they are called, so
#: rebinding it here is what makes the probe time a non-stop lap rather than a
#: twenty-two call one. Same arrangement _generate_merge.py uses for INFRA.
ring.LAP = EXPRESS_LAP


def express_road(station, line, index):
    """The road service ``index`` takes at the terminus - taken in turn."""
    available = roads(station, line)
    return available[index % len(available)]


def express_spec(times, headway_s, count=COUNT, indices=None, stock=None):
    """The flight as a timetable spec, one non-stop lap per service.

    Its own spec rather than ring.flight_spec, which puts every service on the
    first face by design. Same signature, so the sweep can be pointed at this
    instead: ``indices`` restricts the spec to particular services while leaving
    them booked where the full flight would put them, and ``stock`` replaces the
    unit the flight is fitted with.

    Booked times are the same for every service. The faces at Akyurt 1 are
    parallel roads of equal length at equal offsets, so which one a service
    stands on changes nothing it does on the way round - one probe answers for
    the flight, as it does on the ring's own timetable.
    """
    unit = dict(stock or STOCK)
    services = []
    for n in range(count) if indices is None else indices:
        shift = n * headway_s
        entries = []
        for position, (station, line, dwell) in enumerate(EXPRESS_LAP):
            arrival, departure = times[n][position]
            entry = {"station": station,
                     "platform": express_road(station, line, n),
                     "dwell_s": dwell}
            if arrival is not None:
                entry["arrival"] = format_clock(round(arrival) + shift)
            if departure is not None:
                entry["departure"] = format_clock(round(departure) + shift)
            entries.append(entry)
        services.append({
            "id": "X%02d" % (n + 1),
            "name": "%s Akyurt 1 circuit non-stop"
                    % (format_clock(BASE + shift)[:5],),
            "stock": unit["id"], "departure": format_clock(BASE + shift),
            "ready_lead_s": READY_LEAD, "calls": entries})
    return {"stock": [unit], "services": services}


EXPRESS_HEADER = '''# ring express timetable - generated, do not edit by hand.
#
#   python scenarios/ring/_generate_express.py %d
#
# %d non-stop laps of the circuit, booked %d seconds apart, all of them the same
# unit. A lap is two calls: away from Akyurt 1 on the up line, round HS_EAST,
# back down the down line and into Akyurt 1 again, running through the twenty-one
# stations in between. The four faces at Akyurt 1 are used in turn, so what the
# interval has to fit through is the line rather than the terminus. Every booked
# time is what that service achieves with the railway to itself.

'''


def render(times, headway_s, count=COUNT):
    out = [EXPRESS_HEADER % (headway_s, count, headway_s) + stock_yaml(STOCK)]
    for service in express_spec(times, headway_s, count)["services"]:
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
    headway = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    name = sys.argv[2] if len(sys.argv) > 2 else "timetable-express"

    times = probe_all()
    lap = times[0][-1][0] - times[0][0][1]
    print("a non-stop lap, with the railway to itself: %d min %02d s"
          % (lap // 60, lap % 60))

    path = os.path.join(HERE, "%s.yaml" % name)
    with open(path, "w") as handle:
        handle.write(render(times, headway))
    print("wrote %s - %d services at %d s" % (path, COUNT, headway))
