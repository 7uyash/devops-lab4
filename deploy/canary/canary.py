"""Progressive canary rollout with automated analysis and rollback.

usage: python canary.py [--steps 10,25,50,100] [--window 40]

At every step the router sends that percentage of users to the canary, waits one analysis window and
then compares the canary with the stable version in Prometheus. Rollback triggers (any one is enough):
  * canary error rate        > MAX_ERROR_RATE (2 %)
  * canary p95 latency       > MAX_P95_RATIO x stable p95 (1.5x) and > 100 ms
  * canary receives no traffic (it is not reachable / not scraped)
If every step passes, the canary is promoted to 100 % and becomes the new stable version.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROM = os.getenv("PROM_URL", "http://localhost:9090")
MAX_ERROR_RATE = 0.02
MAX_P95_RATIO = 1.5
MIN_P95_MS = 100

ap = argparse.ArgumentParser()
ap.add_argument("--steps", default="10,25,50,100")
ap.add_argument("--window", type=int, default=40, help="seconds of traffic analysed per step")
a = ap.parse_args()


def set_weight(pct):
    rule = "* stable;" if pct == 0 else ("* canary;" if pct >= 100 else f"{pct}% canary; * stable;")
    with open(os.path.join(HERE, "split", "weight.conf"), "w") as f:
        f.write('split_clients "${http_x_user}" $track { ' + rule + " }\n")
    subprocess.run(["docker", "compose", "exec", "-T", "router", "nginx", "-s", "reload"], cwd=HERE, check=True,
                   capture_output=True)


def q(expr):
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    res = json.load(urllib.request.urlopen(url, timeout=5))["data"]["result"]  # nosec B310 - local Prometheus
    return {r["metric"].get("track", ""): float(r["value"][1]) for r in res}


def metrics(window):
    w = f"{window}s"
    rps = q(f'sum by (track) (rate(http_requests_total{{endpoint!="/health"}}[{w}]))')
    err = q(f'sum by (track) (rate(http_requests_total{{status=~"5.."}}[{w}])) / '
            f'sum by (track) (rate(http_requests_total{{endpoint!="/health"}}[{w}]))')
    p95 = q(f'histogram_quantile(0.95, sum by (track, le) (rate(http_request_duration_seconds_bucket[{w}])))')
    return {t: {"rps": rps.get(t, 0.0), "error_rate": err.get(t, 0.0), "p95_ms": p95.get(t, 0.0) * 1000}
            for t in ("stable", "canary")}


def verdict(m):
    c, s = m["canary"], m["stable"]
    if c["rps"] <= 0:
        return "canary receives no traffic"
    if c["error_rate"] > MAX_ERROR_RATE:
        return f"error rate {c['error_rate']:.1%} > {MAX_ERROR_RATE:.0%}"
    if c["p95_ms"] > MIN_P95_MS and s["p95_ms"] > 0 and c["p95_ms"] > MAX_P95_RATIO * s["p95_ms"]:
        return f"p95 {c['p95_ms']:.0f} ms > {MAX_P95_RATIO}x stable ({s['p95_ms']:.0f} ms)"
    return None


steps = [int(x) for x in a.steps.split(",")]
print(f"canary rollout: steps {steps} %, analysis window {a.window}s, rollback if error rate > "
      f"{MAX_ERROR_RATE:.0%} or p95 > {MAX_P95_RATIO}x stable")
print(f"{'time':8} {'weight':>6} | {'stable rps':>10} {'err':>6} {'p95 ms':>7} | {'canary rps':>10} {'err':>6} "
      f"{'p95 ms':>7} | decision")
history = []
for pct in steps:
    set_weight(pct)
    time.sleep(a.window + 5)        # +5 s so the window holds only traffic of this step
    m = metrics(a.window)
    why = verdict(m)
    s, c = m["stable"], m["canary"]
    decision = f"ROLLBACK: {why}" if why else ("PROMOTE" if pct >= 100 else "pass -> next step")
    print(f"{time.strftime('%H:%M:%S'):8} {pct:5d}% | {s['rps']:10.1f} {s['error_rate']:6.1%} {s['p95_ms']:7.0f} | "
          f"{c['rps']:10.1f} {c['error_rate']:6.1%} {c['p95_ms']:7.0f} | {decision}", flush=True)
    history.append({"weight": pct, "metrics": m, "decision": decision})
    if why:
        set_weight(0)
        print(f"ROLLED BACK at {pct}% - all users are on stable again ({why})")
        json.dump({"result": "rolled_back", "at_weight": pct, "reason": why, "steps": history},
                  open(os.path.join(HERE, "result.json"), "w"), indent=1)
        sys.exit(2)
print("CANARY PROMOTED - 100% of users on the new version")
json.dump({"result": "promoted", "steps": history}, open(os.path.join(HERE, "result.json"), "w"), indent=1)
