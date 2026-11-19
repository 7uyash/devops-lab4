"""Run a GitHub Actions workflow locally, step by step, the same way the hosted runner does.

usage: python3 scripts/run_local.py .github/workflows/<file>.yml [--out DIR]

- every `run:` step is executed with `bash --noprofile --norc -eo pipefail`, with the workflow/job/step env,
  `defaults.run.working-directory`, `$GITHUB_ENV` support, `continue-on-error` and `if: failure()`/`always()`
- `uses:` steps are handled locally (checkout = current clone, setup-* = tools pre-installed,
  upload-artifact = copied to <out>/artifacts/<name>, upload-sarif = file kept)
- the output of every step is saved to <out>/<job>/<nn>_<step>.log and a summary.json is written
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

ap = argparse.ArgumentParser()
ap.add_argument("workflow")
ap.add_argument("--out", default=None)
a = ap.parse_args()

repo = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
REPO_NAME = "7uyash/" + os.path.basename(repo)
BRANCH = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
wf = yaml.safe_load(open(a.workflow, encoding="utf-8"))
name = os.path.splitext(os.path.basename(a.workflow))[0]
out = os.path.abspath(a.out or os.path.join(repo, "local-runs", name))
shutil.rmtree(out, ignore_errors=True)
os.makedirs(out)

CTX = {"github.sha": sha, "github.ref": "refs/heads/" + BRANCH, "github.ref_name": BRANCH, "github.actor": "7uyash",
       "github.repository": REPO_NAME, "github.workspace": repo, "runner.os": "Linux"}


def expr(text, env):
    def sub(m):
        key = m.group(1).strip()
        if key.startswith("env."):
            return env.get(key[4:], "")
        if key.startswith("secrets."):
            return ""
        return CTX.get(key, "")
    return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", sub, str(text))


def as_env(d, env):
    return {k: expr(v, env) for k, v in (d or {}).items()}


base_env = dict(os.environ)
base_env.update({"CI": "true", "GITHUB_ACTIONS": "true", "GITHUB_SHA": sha, "GITHUB_WORKSPACE": repo,
                 "GITHUB_REF": "refs/heads/" + BRANCH, "GITHUB_REF_NAME": BRANCH, "GITHUB_REPOSITORY": REPO_NAME,
                 "GITHUB_ACTOR": "7uyash", "RUNNER_TEMP": tempfile.gettempdir()})
base_env.update(as_env(wf.get("env"), base_env))
wf_defaults = (wf.get("defaults") or {}).get("run", {})
summary = {"workflow": wf.get("name"), "file": a.workflow, "commit": sha, "branch": BRANCH,
           "started": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "jobs": []}
print(f"=== {wf.get('name')}  (commit {sha[:7]})")

for jname, job in wf["jobs"].items():
    jenv = dict(base_env)
    jenv.update(as_env(job.get("env"), jenv))
    jdefaults = {**wf_defaults, **((job.get("defaults") or {}).get("run", {}))}
    jdir = os.path.join(out, jname)
    os.makedirs(jdir)
    ghenv = os.path.join(jdir, ".github_env")
    open(ghenv, "w").close()
    jres = {"id": jname, "name": job.get("name", jname), "steps": [], "status": "success"}
    t_job = time.time()
    failed = False
    print(f"--- job {jres['name']}")
    for i, st in enumerate(job.get("steps", []), 1):
        cond = str(st.get("if", "")).strip()
        if failed and "failure()" not in cond and "always()" not in cond:
            continue
        if not failed and cond.startswith("failure()"):
            continue
        sname = st.get("name") or st.get("uses") or f"step {i}"
        t0 = time.time()
        log = os.path.join(jdir, f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '_', sname)[:60]}.log")
        status = "success"
        if "uses" in st:
            uses = st["uses"]
            w = st.get("with") or {}
            msg = f"[local] {uses}"
            if "upload-artifact" in uses:
                dest = os.path.join(out, "artifacts", expr(w.get("name", "artifact"), jenv))
                os.makedirs(dest, exist_ok=True)
                cwd = repo
                for p in str(w.get("path", "")).split():
                    for f in glob.glob(os.path.join(cwd, p)):
                        (shutil.copytree if os.path.isdir(f) else shutil.copy)(
                            f, os.path.join(dest, os.path.basename(f.rstrip("/"))), **(
                                {"dirs_exist_ok": True} if os.path.isdir(f) else {}))
                msg += f" -> {dest}"
            open(log, "w").write(msg + "\n")
        else:
            env = dict(jenv)
            for ln in open(ghenv):
                if "=" in ln:
                    k, v = ln.rstrip("\n").split("=", 1)
                    env[k] = v
            env.update(as_env(st.get("env"), env))
            env["GITHUB_ENV"] = ghenv
            wd = st.get("working-directory") or jdefaults.get("working-directory") or "."
            script = expr(st["run"], env)
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
                f.write(script)
            with open(log, "w") as lf:
                p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", f.name],
                                   cwd=os.path.join(repo, wd), env=env, stdout=lf, stderr=subprocess.STDOUT)
            os.unlink(f.name)
            if p.returncode != 0:
                status = "failure"
                with open(log, "a") as lf:
                    lf.write(f"Error: Process completed with exit code {p.returncode}.\n")
        if status == "failure":
            if st.get("continue-on-error"):
                status = "failure (continue-on-error)"
            else:
                failed = True
        dur = round(time.time() - t0, 1)
        jres["steps"].append({"n": i, "name": sname, "status": status, "seconds": dur,
                              "log": os.path.relpath(log, out)})
        print(f"  {'OK ' if status == 'success' else 'ERR'} {dur:7.1f}s  {sname}")
    jres["status"] = "failure" if failed else "success"
    jres["seconds"] = round(time.time() - t_job, 1)
    summary["jobs"].append(jres)
    if failed:
        break

summary["finished"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
summary["status"] = "failure" if any(j["status"] == "failure" for j in summary["jobs"]) else "success"
json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=2)
print(f"=== {summary['status'].upper()}  logs: {out}")
sys.exit(0 if summary["status"] == "success" else 1)
