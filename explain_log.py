"""Explain the reason column of a --log trace: what governed each train, and where.

    python run.py scenarios/ring --headless --log ring.csv --log-every 2
    python explain_log.py ring.csv

The trace records, for every train on every sample, the constraint that was
actually governing it - the one the driver was braking against. Read down that
column and you have the answer to "what is the bottleneck", but the raw strings
carry signal and block ids, so twelve trains held at the same place look like
two hundred different reasons. This groups them by kind, says what each kind
means, and then locates the ones that are the signalling holding a train back.

What counts as "held back" is not decided here: it is RESTRAINT_MARKERS in
trainsim.analysis.kpi, the same list the comparison table's restrained column
uses, so a reason cannot be a bottleneck in one report and not the other.

Stdlib only, and it reads a file rather than running anything, so it works on a
trace somebody else sent you.

    python explain_log.py --selfcheck     the classifier, against known strings
"""

import collections
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.analysis.kpi import RESTRAINT_MARKERS  # noqa: E402

#: ``(pattern, kind, what it means)``, tried in order: the first match names the
#: sample. Ids are stripped by the patterns themselves, which is what collapses
#: "no route set at S_UP_014" and its two hundred siblings into one row.
KINDS = (
    (r"^line speed$", "line speed",
     "nothing held it: running to the limit under the train"),
    (r"^station stop ", "station stop",
     "braking for a booked call - the timetable, not the signalling"),
    (r"^speed restriction$", "speed restriction",
     "a slower stretch ahead: a loop road, a curve, or a TSR laid on"),
    (r"passed signal at danger", "SPAD",
     "the train is past a red: authority zero, brakes in. Should never appear"),
    (r"signal at danger$", "signal at danger",
     "red ahead - the block beyond is occupied or has no route set"),
    (r"caution", "caution",
     "yellow: the next signal is red, so this one is approached at a rate "
     "that can stop at it"),
    (r"no route set at ", "no route set",
     "the interlocking has not given the movement - see --check for what "
     "each route conflicts with"),
    (r"block \S+ occupied", "block occupied",
     "the first block ahead holds another train"),
    (r"block \S+ shared", "block shared",
     "two trains in one block. A fault, not a constraint"),
    (r"rear of ", "rear of the train ahead",
     "moving block: running up to the leader's rear less the margin"),
    (r"^VC: coupled to ", "coupled",
     "virtual coupling: authority ends where the leader will stop"),
    (r"absolute distance to ", "V2V link lost",
     "virtual coupling degraded to moving block - no link, or no integrity "
     "report from the leader"),
    (r"no integrity report", "no integrity report",
     "the leader cannot vouch for its own rear, so it is followed by block "
     "rather than by distance"),
    (r"clear", "clear",
     "green, or an authority running to the end of the line"),
    (r"end of line", "end of line",
     "nothing ahead but the buffer stop"),
)


def kind_of(reason):
    """``(kind, meaning)`` for one reason string."""
    for pattern, kind, meaning in KINDS:
        if re.search(pattern, reason):
            return kind, meaning
    return reason, "(no explanation written for this one yet)"


def cost_kmh(row):
    """How much speed the governing constraint was actually taking, km/h.

    The reason column names whichever constraint bound *first*, and says
    nothing about by how much: a train accelerating hard towards 80 that is
    permitted 79.4 is "coupled to R03" in exactly the same way as one held to
    40. Counting rows alone therefore reports a bottleneck where there is none,
    which is why every total here is also weighted by this.
    """
    if row.get("reason") == "line speed":
        # Nothing is taking anything: the line itself is the constraint. The
        # subtraction below would still show a few km/h, because limit_kmh is
        # read at the nose while the driver obeys the limit under the whole
        # train - so a train whose tail is still in a slower section reads as
        # held when it is simply not clear of the restriction yet.
        return 0.0
    try:
        return max(0.0, float(row["limit_kmh"]) - float(row["target_kmh"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def held_back(reason):
    """Whether this reason is the signalling holding a train down."""
    low = reason.lower()
    return any(marker in low for marker in RESTRAINT_MARKERS)


def read(path):
    """Running samples from a --log trace. CSV or TSV, by extension."""
    delimiter = "\t" if path.lower().endswith(".tsv") else ","
    if path.lower().endswith(".xlsx"):
        raise SystemExit("explain_log.py reads .csv or .tsv - re-run --log "
                         "with one of those extensions")
    with open(path, newline="") as handle:
        rows = [r for r in csv.DictReader(handle, delimiter=delimiter)
                if r.get("state") == "running"]
    if not rows:
        raise SystemExit("no running samples in %s - is it a --log trace?" % path)
    return rows


def bar(count, most, width=28):
    return "#" * max(1, int(round(width * count / float(most))))


def report(rows):
    lines = []
    trains = {r["train"] for r in rows}
    lines.append("%d running samples, %d trains, from the reason column of the trace."
                 % (len(rows), len(trains)))
    lines.append("")

    kinds = collections.Counter()
    cost = collections.Counter()
    meanings = {}
    for row in rows:
        kind, meaning = kind_of(row["reason"])
        kinds[kind] += 1
        cost[kind] += cost_kmh(row)
        meanings[kind] = meaning
    lines.append("what governed each train")
    lines.append("  %-24s %7s %8s   %s"
                 % ("kind", "share", "costing", "what it means"))
    for kind, n in kinds.most_common():
        lines.append("  %-24s %6.1f%% %6.1f km/h   %s"
                     % (kind, 100.0 * n / len(rows),
                        cost[kind] / n, meanings[kind]))
    lines.append("  \"costing\" is the mean speed the constraint was taking while it")
    lines.append("  governed. A fraction of a km/h means it bound first and cost")
    lines.append("  nothing - the train was not being held.")

    restrained = [r for r in rows if held_back(r["reason"])]
    lines.append("")
    if not restrained:
        lines.append("Nothing was held back by the signalling: every sample was "
                     "line speed, a booked stop or a speed restriction.")
        return "\n".join(lines)

    lost = sum(cost_kmh(r) for r in restrained)
    lines.append("the signalling governed %.1f%% of running time, and over those "
                 "samples" % (100.0 * len(restrained) / len(rows),))
    lines.append("took a mean %.1f km/h off the line speed. Where it cost most:"
                 % (lost / len(restrained),))
    where = collections.Counter()
    for r in restrained:
        where[round(float(r["km"]))] += cost_kmh(r)
    if not where or max(where.values()) <= 0.0:
        lines.append("  nowhere: every sample it governed, it was costing nothing.")
        return "\n".join(lines)
    most = max(where.values())
    for km, n in where.most_common(8):
        lines.append("  km %-4d %8.0f km/h-samples  %s" % (km, n, bar(n, most)))

    stops = collections.Counter()
    for r in restrained:
        if r["next_stop"]:
            stops[r["next_stop"]] += cost_kmh(r)
    if stops:
        lines.append("")
        lines.append("and what those trains were next booked to call at:")
        for stop, n in stops.most_common(5):
            lines.append("  %-18s %8.0f km/h-samples" % (stop, n))

    worst = collections.Counter()
    for r in restrained:
        worst[r["train"]] += cost_kmh(r)
    lines.append("")
    lines.append("worst affected: %s"
                 % ", ".join("%s (%.0f)" % (t, n) for t, n in worst.most_common(4)))
    return "\n".join(lines)


def selfcheck():
    """The classifier, against one real string of every kind the kernel emits."""
    cases = {
        "line speed": "line speed",
        "station stop MACUNKOY_1": "station stop",
        "speed restriction": "speed restriction",
        "signal at danger": "signal at danger",
        "passed signal at danger": "SPAD",
        "obeying caution": "caution",
        "approaching caution": "caution",
        "L2: no route set at S_UP_014": "no route set",
        "L1: block B_UP_007 occupied": "block occupied",
        "MB: rear of R03": "rear of the train ahead",
        "VC: coupled to R03": "coupled",
        "VC: R03 not V2V fitted, absolute distance to R03": "V2V link lost",
        "running on clear": "clear",
        "end of line": "end of line",
    }
    for reason, expected in cases.items():
        got = kind_of(reason)[0]
        assert got == expected, "%r read as %r, not %r" % (reason, got, expected)

    # A booked stop and line speed are the timetable, not the signalling; a red
    # and a yellow are. Getting this backwards would put the bottleneck in the
    # wrong half of the report.
    assert not held_back("line speed")
    assert not held_back("station stop MACUNKOY_1")
    assert held_back("signal at danger")
    assert held_back("obeying caution")
    assert held_back("VC: coupled to R03")
    print("selfcheck: %d reason strings classified as expected" % len(cases))


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().split("\n\n")[1])
    else:
        print(report(read(sys.argv[1])))
