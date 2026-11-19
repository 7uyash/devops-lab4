"""RPO check after a database failover: is every order the client got an HTTP 201 for still present?
usage: python3 rpo_check.py loadgen.csv present_ids.txt   (prints JSON: acked, missing, present)"""
import csv
import json
import sys

acked = {r["id"] for r in csv.DictReader(open(sys.argv[1])) if r["status"] == "201"}
present = {line.strip() for line in open(sys.argv[2]) if line.strip()}
missing = sorted(acked - present, key=int)
print(json.dumps({"acked": len(acked), "missing": len(missing), "missing_ids": missing[:20],
                  "rows_on_new_primary": len(present)}))
