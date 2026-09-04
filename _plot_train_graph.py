"""Draw the ring express as a train graph, moving block against virtual coupling.

    python3 _plot_train_graph.py [train-graph.svg] [booked_headway_s]

A train graph is the oldest picture in railway operations and the one this
repository did not have: time across, distance up, one line per train. Its
slope is speed, so a train held down by the one in front bends, and a flight
that is fighting itself fans out - which is the thing every headway number in
here is a summary of.

Both panels are the same flight of twelve non-stop laps at the same booked
interval, differing only in what the follower is allowed to know. The interval
is deliberately between the two systems' all-green headways - moving block
holds 39 s on this railway and virtual coupling 32 s - so one of them is being
asked for something it cannot do and the other is not. That is the whole seven
seconds, drawn.

The train graphs are drawn over the first twenty minutes and the first
twenty-five kilometres rather than the whole lap. All twelve services are away
inside six minutes, so the fan they make is six minutes wide against an
hour-long lap: at full extent it is one thick diagonal band and the only thing
readable off it is that one band is thicker than the other.

The third panel is the quantity a timetable is actually written in. For every
kilometre of the lap it takes the time between each train passing it and the
train behind passing it, and plots the mean and the widest of those eleven
intervals. Both flights are booked at the same figure, so a flat line at that
figure is a railway doing what it was asked; a line that climbs is one where
the interval is being stretched to whatever the signalling can hold. The two
answers are the seven seconds seen a third way.

Drawn with matplotlib through trainsim/analysis/chart, the one thing here
outside the standard library. See requirements-optional.txt.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RING = os.path.join(HERE, "scenarios", "ring")
sys.path.insert(0, HERE)
sys.path.insert(0, RING)

import _generate_timetable as ring     # noqa: E402
import _generate_express as express    # noqa: E402 - rebinds ring.LAP

from trainsim.analysis import trace      # noqa: E402
from trainsim.analysis.chart import PALETTE, Chart, document  # noqa: E402
from trainsim.core import signalling as reg  # noqa: E402
from trainsim.scenario.loader import build_timetable  # noqa: E402

COL = {name: index for index, name in enumerate(trace.COLUMNS)}

#: The two systems the seven seconds lives between. The lineside ones are a
#: different picture - they queue at signals rather than close up - and they
#: have their own panels in _plot_capacity.py.
SYSTEMS = (("etcs_moving_block", "ETCS moving block", 39),
           ("virtual_coupling", "virtual coupling", 32))

#: Below both all-green headways, so both systems are being asked for more than
#: they hold - but moving block by 13 s and virtual coupling by 6. At 36 s,
#: between the two limits, moving block is checked without ever losing time and
#: the two graphs look identical; the difference has to be pushed into the
#: delay before it can be seen.
DEFAULT_HEADWAY_S = 26

#: The window the train graphs are drawn over: minutes, and km along the lap.
WINDOW_MIN = 20.0
WINDOW_KM = 25.0

#: Distance bins for the delay panel, km. One per kilometre of the lap.
BIN_KM = 1.0


def stock_for(system):
    unit = dict(ring.STOCK)
    unit["etcs_level"], unit["tims"], unit["v2v"] = reg.fitment_for(system)
    return unit


def run_traced(system, headway_s, times):
    """Run the express flight under ``system``; return its rows and its stock.

    The stock comes back off the built timetable rather than being rebuilt from
    the dict, so the permitted curve below is drawn for the unit that actually
    ran - fitment and all - which is how separation.py gets hold of one too.
    """
    timetable = build_timetable(
        express.express_spec(times, headway_s, ring.COUNT,
                             stock=stock_for(system)), ring.INFRA)
    sim = ring.simulation(timetable,
                          duration_s=headway_s * ring.COUNT + 7200,
                          system=system)
    recorder = trace.TraceRecorder(interval_s=0.0)
    sim.step_hooks.append(recorder)
    while not sim.finished:
        sim.step()
    return recorder.rows, timetable.services[0].stock


def train_graph(rows, title, note):
    """Time across, distance up, one line per train."""
    by_train = {}
    for row in rows:
        by_train.setdefault(row[COL["train"]], []).append(
            (row[COL["time_s"]], row[COL["chainage_m"]]))
    chart = Chart(title, "minutes into the run", "km along the lap", note=note,
                  width=560, height=300,
                  x_max=WINDOW_MIN, y_max=WINDOW_KM)
    base = min(point[0] for points in by_train.values() for point in points)
    for name in sorted(by_train):
        # No label: twelve identical services need no legend, and the shape of
        # the sheaf is the whole of what there is to read.
        chart.line("", [((t - base) / 60.0, x / 1000.0)
                        for t, x in by_train[name]], colour=PALETTE[0])
    return chart


def passing_times(rows):
    """``{train: {km_bin: time_s}}`` - when each train first reached each km.

    The rows come out of the recorder in time order, so the first sample in a
    bin is the passing time and everything after it is the same train still in
    the same kilometre.
    """
    out = {}
    for row in rows:
        if row[COL["state"]] == "not started":
            continue
        seen = out.setdefault(row[COL["train"]], {})
        seen.setdefault(int(row[COL["chainage_m"]] / 1000.0 / BIN_KM),
                        row[COL["time_s"]])
    return out


def headway_profile(rows):
    """``(mean, widest)`` interval between consecutive trains, per km.

    Eleven intervals per kilometre for a flight of twelve, measured where the
    trains were rather than where they were booked to be. This is the number a
    timetable is written in, and unlike a delay it does not need a booked time
    to compare against - it is what the railway did.
    """
    times = passing_times(rows)
    names = sorted(times)
    bins = {}
    for leader, follower in zip(names, names[1:]):
        for index, when in times[leader].items():
            if index in times[follower]:
                bins.setdefault(index, []).append(times[follower][index] - when)
    mean = [((i + 0.5) * BIN_KM, sum(v) / len(v)) for i, v in sorted(bins.items())]
    widest = [((i + 0.5) * BIN_KM, max(v)) for i, v in sorted(bins.items())]
    return mean, widest


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "train-graph.svg")
    headway = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_HEADWAY_S

    times = ring.probe_all()
    charts, profiles = [], []
    for index, (system, label, all_green) in enumerate(SYSTEMS):
        rows, _stock = run_traced(system, headway, times)
        late = max((row[COL["delay_s"]] for row in rows), default=0.0)
        charts.append(train_graph(
            rows, "%s at %d s" % (label, headway),
            "all-green at %d s - worst delay over the whole lap %.0f s"
            % (all_green, late)))
        profiles.append((label, headway_profile(rows),
                         PALETTE[index % len(PALETTE)]))
        print("%-20s booked %d s   worst delay %5.0f s   %d trace rows"
              % (system, headway, late, len(rows)))

    gaps = Chart(
        "The interval twelve trains actually ran",
        "km along the lap",
        "seconds between one train and the next",
        note="Booked %d s apart. Solid: the widest of the eleven intervals at "
             "that point. Dashed: their mean." % headway,
        width=980, height=420, y_min=20.0, y_max=44.0)
    for label, (mean, widest), colour in profiles:
        gaps.line(label, widest, colour=colour)
        gaps.line("", mean, colour=colour, dash=True)
    # The reference the two are being read against, drawn rather than left to
    # the reader to hold in their head: a system that ran what it was booked is
    # a flat line on top of this one.
    span = [point[0] for point in profiles[0][1][1]]
    gaps.line("booked %d s" % headway,
              [(span[0], float(headway)), (span[-1], float(headway))],
              colour="#999999", dash=True)
    charts.append(gaps)

    with open(out, "w") as handle:
        handle.write(document(
            charts,
            heading="Twelve non-stop laps of the ring, booked %d s apart" % headway,
            subheading="scenarios/ring/scenario-express.yaml - the same flight "
                       "and the same railway under both systems, differing only "
                       "in what the follower is allowed to know about the train "
                       "in front.",
            columns=1))
    print("wrote %s" % out)

    # The interval panel again on its own page. It is the one that carries the
    # finding, and at a third of a shared page it is being asked to do that in
    # 300 pixels.
    alone = os.path.splitext(out)[0] + "-interval" + os.path.splitext(out)[1]
    with open(alone, "w") as handle:
        handle.write(document(
            [gaps],
            heading="What the railway ran, against what it was booked",
            subheading="scenarios/ring/scenario-express.yaml - twelve non-stop "
                       "laps booked %d s apart, run twice. Virtual coupling "
                       "holds the booked interval the whole way round; moving "
                       "block cannot, and opens it to whatever it can hold."
                       % headway,
            columns=1))
    print("wrote %s" % alone)
