# -*- coding: utf-8 -*-
"""Iz dosyalarindan kuplaj metriklerini sayar. convoy2.py'nin sayilari buradan.

    python run.py scenarios/ring/scenario-convoy.yaml --headless \
           --log express.csv --log-every 5
    python run.py scenarios/ring/scenario-convoy-stopping.yaml --headless \
           --log stopping.csv --log-every 5
    python convoy_stats.py express.csv stopping.csv

Bir tik kuplajli sayiliyor: authority reason "coupled to X" iceriyor ve
", uncoupled" icermiyor - yani sanal kuplaj nispi fren mesafesi veriyor VE
tren kuplaj esigi icinde. (virtual_coupling.py: _is_coupled / uncoupled_speed)
"""
import collections
import csv
import re
import sys

LOG_EVERY = 5.0


def stats(path):
    rows = [r for r in csv.DictReader(open(path)) if r["state"] == "running"]
    seen = collections.defaultdict(dict)          # t -> {tren: lider|None}
    run = collections.Counter()
    for r in rows:
        t, tr = float(r["time_s"]), r["train"]
        run[tr] += 1
        m = re.search(r"coupled to (\S+?)(?:,|$)", r["reason"])
        seen[t][tr] = m.group(1) if (m and ", uncoupled" not in r["reason"]) else None
    coupled = sum(1 for mp in seen.values() for v in mp.values() if v)
    spells = []
    for tr in run:
        n = 0
        for t in sorted(seen):
            if tr not in seen[t]:
                continue
            if seen[t][tr]:
                n += 1
            elif n:
                spells.append(n * LOG_EVERY); n = 0
        if n:
            spells.append(n * LOG_EVERY)
    total = sum(run.values())
    return {"kuplajli_yuzde": 100.0 * coupled / total,
            "olay": len(spells),
            "ortalama_s": sum(spells) / len(spells) if spells else 0.0,
            "en_uzun_s": max(spells) if spells else 0.0}


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(path, stats(path))
