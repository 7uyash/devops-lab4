"""Constant-rate HTTP load generator that records every response.

usage: python scripts/loadgen.py URL --rps 50 --seconds 60 --out results.csv [--users 1000] [--stop-file F]

Each request carries a random X-User header (from a pool of --users users), so user-based traffic
splitting (canary) can be observed. Every response is written to the CSV as:
    t_offset_s, user, status, version, track, latency_ms, epoch, id (order id returned by a POST)
status 0 means the connection itself failed (refused / reset / timeout).
On exit a JSON summary is printed: totals, failures, and requests per version.
"""
import argparse
import collections
import csv
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("--rps", type=float, default=50)
ap.add_argument("--seconds", type=float, default=60)
ap.add_argument("--users", type=int, default=1000)
ap.add_argument("--out", default="loadgen.csv")
ap.add_argument("--stop-file", default=None, help="stop early when this file appears")
ap.add_argument("--method", default="GET")
a = ap.parse_args()

rows, lock = [], threading.Lock()
t_start = time.time()


def one():
    user = f"user{random.randint(1, a.users):04d}"
    t0 = time.time()
    status, version, track, oid = 0, "-", "-", ""
    data = b'{"items": [1, 2]}' if a.method == "POST" else None
    req = urllib.request.Request(a.url, method=a.method, data=data, headers={"X-User": user,
                                                                             "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:  # nosec B310 - local test target
            body = r.read()
            if a.method == "POST":
                try:
                    oid = json.loads(body).get("id", "")
                except ValueError:
                    pass
            status, version, track = r.status, r.headers.get("X-App-Version", "-"), r.headers.get("X-App-Track", "-")
    except urllib.error.HTTPError as e:
        status, version, track = e.code, e.headers.get("X-App-Version", "-"), e.headers.get("X-App-Track", "-")
    except Exception:  # noqa: BLE001 - connection errors are what we want to count
        status = 0
    with lock:
        rows.append((round(t0 - t_start, 3), user, status, version, track, round((time.time() - t0) * 1000, 1),
                     round(t0, 3), oid))


threads = []
interval = 1.0 / a.rps
n = 0
while time.time() - t_start < a.seconds:
    if a.stop_file and os.path.exists(a.stop_file):
        break
    th = threading.Thread(target=one, daemon=True)
    th.start()
    threads.append(th)
    n += 1
    sleep = t_start + n * interval - time.time()
    if sleep > 0:
        time.sleep(sleep)
for th in threads:
    th.join(timeout=5)

rows.sort()
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t", "user", "status", "version", "track", "latency_ms", "epoch", "id"])
    w.writerows(rows)

ok = [r for r in rows if 200 <= r[2] < 400]
fail = [r for r in rows if not 200 <= r[2] < 400]
per_version = collections.Counter(r[3] for r in rows)
users_per_track = {k: len({r[1] for r in rows if r[4] == k}) for k in {r[4] for r in rows}}
lat = sorted(r[5] for r in ok) or [0]
print(json.dumps({"requests": len(rows), "ok": len(ok), "failed": len(fail),
                  "failed_by_status": dict(collections.Counter(str(r[2]) for r in fail)),
                  "duration_s": round(rows[-1][0] if rows else 0, 1), "per_version": dict(per_version),
                  "users_per_track": users_per_track,
                  "p50_ms": lat[len(lat) // 2], "p95_ms": lat[int(len(lat) * 0.95) - 1 if len(lat) > 1 else 0]}))
