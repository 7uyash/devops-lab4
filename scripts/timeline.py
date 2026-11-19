"""Per-second timeline of a loadgen CSV: requests served by each version and failures.
usage: python scripts/timeline.py results.csv [--from S] [--to S] [--by version|track]"""
import argparse
import collections
import csv

ap = argparse.ArgumentParser()
ap.add_argument("csv")
ap.add_argument("--from", dest="t0", type=float, default=0)
ap.add_argument("--to", dest="t1", type=float, default=1e9)
ap.add_argument("--by", default="version")
a = ap.parse_args()

rows = list(csv.DictReader(open(a.csv)))
keys = sorted({r[a.by] for r in rows if r[a.by] != "-"})
bins = collections.defaultdict(collections.Counter)
for r in rows:
    t = float(r["t"])
    if a.t0 <= t < a.t1:
        ok = 200 <= int(r["status"]) < 400
        bins[int(t)][r[a.by] if ok else "FAILED"] += 1
print("second | " + " | ".join(f"{k:>8}" for k in keys) + " |   FAILED")
for s in sorted(bins):
    print(f"{s:6d} | " + " | ".join(f"{bins[s][k]:8d}" for k in keys) + f" | {bins[s]['FAILED']:8d}")
