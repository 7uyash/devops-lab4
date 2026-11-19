"""Compare measured recovery times / data loss with the recovery objectives. Reads dr/results/*.json.

RTO (Recovery Time Objective)  = longest acceptable outage
RPO (Recovery Point Objective) = longest acceptable window of lost data
"""
import csv
import json
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def J(name):
    return json.load(open(os.path.join(HERE, name)))


def outage(csv_file, t_event):
    """Outage = from the event until the first successful request after the LAST failed one.
    Returns (rto_seconds, failed_requests, requests_after_event)."""
    rows = [(float(r["epoch"]), int(r["status"])) for r in csv.DictReader(open(csv_file))]
    after = [r for r in rows if r[0] >= t_event]
    fails = [r for r in after if not 200 <= r[1] < 300]
    if not fails:
        return 0.0, 0, len(after)
    last_fail = max(r[0] for r in fails)
    recovered = next((r for r in after if r[0] > last_fail and 200 <= r[1] < 300), None)
    return (recovered[0] - t_event if recovered else None), len(fails), len(after)


def fmt(x, n):
    return "n/a" if x is None else f"{x:.{n}f}"


ev = J("events.json")
rows = []

# 1) logical data loss -> restore from backup
a = ev["data_loss"]
rows.append(["Accidental DROP TABLE (human error)", "restore last pg_dump backup", "RTO <= 5 min",
             f"{a['outage_s']:.1f} s (restore {a['restore_s']:.1f} s)", "RPO <= 15 min (backup interval)",
             f"{a['lost_orders']} orders = {a['seconds_since_backup']:.0f} s of writes",
             a["outage_s"] <= 300 and a["seconds_since_backup"] <= 900])

# 2) primary database crash -> promote standby
b = ev["db_crash"]
rto, failed, _ = outage(os.path.join(HERE, "db_failover.csv"), b["t_kill"])
lost = b["acked_missing"]
rows.append(["Primary database node lost", "promote replica, move \"db\"", "RTO <= 60 s",
             f"{fmt(rto, 1)} s ({failed} failed writes)", "RPO = 0 (no acknowledged order lost)",
             f"{lost} of {b['acked']} acknowledged orders lost", rto is not None and rto <= 60 and lost == 0])

# 3) application node crash -> nginx backup server
c = ev["app_crash"]
rto, failed, _ = outage(os.path.join(HERE, "app_failover.csv"), c["t_kill"])
rows.append(["Primary-site app server lost", "nginx fails over to DR-site app", "RTO <= 10 s",
             f"{fmt(rto, 2)} s ({failed} failed requests)", "RPO = 0 (stateless tier)", "0 (no state on app servers)",
             rto is not None and rto <= 10])

print(f"{'scenario':38} {'recovery':34} {'RTO objective':14} {'RTO measured':28} {'RPO measured':36} result")
for r in rows:
    print(f"{r[0]:38} {r[1]:34} {r[2]:14} {r[3]:28} {r[5]:36} {'MET' if r[6] else 'MISSED'}")
json.dump({"scenarios": [dict(zip(["scenario", "recovery", "rto_objective", "rto_measured", "rpo_objective",
                                   "rpo_measured", "met"], r)) for r in rows]},
          open(os.path.join(HERE, "objectives.json"), "w"), indent=1)
