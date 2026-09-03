"""Reorder a --log trace by train: all of R01, then all of R02, and so on.

    python run.py scenarios/ring --headless --log ring.csv --log-every 2
    python sort_log.py ring.csv                 writes ring-by-train.csv
    python sort_log.py ring.csv one-train.csv   or name the output yourself

The recorder samples every train once per tick, so a trace comes out in time
order with the fleet interleaved: to follow one train down its journey you are
reading every twelfth row. This rewrites it grouped by train and still in time
order within each train, which is what a spreadsheet wants for a per-train
chart and what the eye wants for reading a single run.

Nothing is dropped, changed or recomputed - same rows, same columns, same
header, different order - so anything that reads a trace reads this too.

    python sort_log.py --selfcheck    the ordering, on a hand-made trace
"""

import csv
import os
import re
import sys


def train_key(train_id):
    """Sort key that puts R2 before R10 rather than after it.

    Trace ids are usually zero-padded and would sort right as plain strings,
    but not always - the express scenarios number services U1..U16 - and a
    fleet listed R1, R10, R11, R2 is exactly the thing this script exists to
    stop somebody having to do by hand.
    """
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", train_id)]


def row_key(row):
    """By train, then by time within that train."""
    try:
        when = float(row.get("time_s") or 0.0)
    except ValueError:
        when = 0.0
    return train_key(row.get("train") or ""), when


def sort_rows(rows):
    return sorted(rows, key=row_key)


def default_output(path):
    stem, ext = os.path.splitext(path)
    return "%s-by-train%s" % (stem, ext)


def reorder(path, out_path=None):
    """Rewrite ``path`` grouped by train. Returns the file written."""
    if path.lower().endswith(".xlsx"):
        raise SystemExit("sort_log.py reads .csv or .tsv - re-run --log with "
                         "one of those extensions")
    delimiter = "\t" if path.lower().endswith(".tsv") else ","
    out_path = out_path or default_output(path)
    if os.path.abspath(out_path) == os.path.abspath(path):
        raise SystemExit("refusing to overwrite the trace in place: name a "
                         "different output file")

    with open(path, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames or "train" not in reader.fieldnames:
            raise SystemExit("%s has no train column - is it a --log trace?" % path)
        columns = reader.fieldnames
        rows = sort_rows(list(reader))
    if not rows:
        raise SystemExit("no rows in %s" % path)

    with open(out_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, columns, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)

    order = []
    for row in rows:
        if not order or order[-1] != row["train"]:
            order.append(row["train"])
    return out_path, len(rows), order


def selfcheck():
    """Ordering, on a trace made to break the obvious string sort."""
    rows = [{"train": "U10", "time_s": "5"},
            {"train": "U2", "time_s": "9"},
            {"train": "U2", "time_s": "1"},
            {"train": "U10", "time_s": "2"}]
    got = [(r["train"], r["time_s"]) for r in sort_rows(rows)]
    assert got == [("U2", "1"), ("U2", "9"), ("U10", "2"), ("U10", "5")], got

    # Zero-padded ids were already fine; check the change did not break them.
    padded = [{"train": t, "time_s": "0"} for t in ("R03", "R01", "R12", "R02")]
    assert [r["train"] for r in sort_rows(padded)] == ["R01", "R02", "R03", "R12"]

    assert default_output("ring.csv") == "ring-by-train.csv"
    assert default_output("a/b/ring.tsv") == "a/b/ring-by-train.tsv"
    print("selfcheck: trains group in order, and time still rises inside each")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif not 2 <= len(sys.argv) <= 3:
        raise SystemExit(__doc__.strip().split("\n\n")[1])
    else:
        written, count, order = reorder(*sys.argv[1:])
        print("wrote %s - %d rows, %d trains in order: %s"
              % (written, count, len(order), ", ".join(order)))
