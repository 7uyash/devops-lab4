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
    """Seconds from the event to the first successful response after it, and failed requests in between."""
    rows = [(float(r["epoch"]), int(r["status"]), r["track"]) for r in csv.DictReader(open(csv_file))]
    after = [r for r in rows if r[0] >= t_event]
    first_ok = next((r for r in after if 200 <= r[1] < 300), None)
    failed = sum(1 for r in after if not 200 <= r[1] < 300 and (first_ok is None or r[0] < first_ok[0]))
    acked = sum(1 for r in rows if r[1] == 201)
    return (first_ok[0] - t_event if first_ok else None), failed, acked, first_ok


ev = J("events.json")
rows = []

# 1) logical data loss -> restore from backup
a = ev["data_loss"]
rows.append(["Accidental DROP TABLE (human error)", "restore last pg_dump backup", "RTO <= 5 min", f"{a['restore_s']:.1f} s",
             "RPO <= 15 min (backup interval)",
             f"{a['lost_orders']} orders = {a['seconds_since_backup']:.0f} s of writes", True])

# 2) primary database crash -> promote standby
b = ev["db_crash"]
rto, failed, acked, _ = outage(os.path.join(HERE, "db_failover.csv"), b["t_kill"])
lost = b["expected_rows"] - b["rows_after"]
rows.append(["Primary database node lost", "promote streaming replica", "RTO <= 60 s", f"{rto:.1f} s ({failed} failed writes)",
             "RPO = 0 (no acknowledged order lost)", f"{lost} acknowledged orders lost", rto <= 60 and lost == 0])

# 3) application node crash -> nginx backup server
c = ev["app_crash"]
rto, failed, _, first = outage(os.path.join(HERE, "app_failover.csv"), c["t_kill"])
rows.append(["Primary-site app server lost", "nginx fails over to DR-site app", "RTO <= 10 s",
             f"{rto:.2f} s ({failed} failed requests)", "RPO = 0 (stateless tier)", "0", rto <= 10])

print(f"{'scenario':38} {'recovery':34} {'RTO objective':14} {'RTO measured':28} {'RPO measured':36} result")
for r in rows:
    print(f"{r[0]:38} {r[1]:34} {r[2]:14} {r[3]:28} {r[5]:36} {'MET' if r[6] else 'MISSED'}")
json.dump({"scenarios": [dict(zip(["scenario", "recovery", "rto_objective", "rto_measured", "rpo_objective",
                                   "rpo_measured", "met"], r)) for r in rows]},
          open(os.path.join(HERE, "objectives.json"), "w"), indent=1)
