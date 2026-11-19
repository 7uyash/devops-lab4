"""Fetch secrets from HashiCorp Vault at start-up (AppRole auth, standard library only).

Configuration (all optional - without VAULT_ADDR the app falls back to plain environment variables):
  VAULT_ADDR              e.g. http://vault:8200
  VAULT_ROLE_ID_FILE      file containing the AppRole role_id
  VAULT_SECRET_ID_FILE    file containing a *response-wrapped* secret_id token (single use, short TTL)
  VAULT_DB_ROLE           database secrets engine role, e.g. shoplite-app
  VAULT_KV_PATH           KV v2 path, e.g. secret/data/shoplite/config
  DB_HOST / DB_NAME       where the dynamic credentials are used
The secret values are kept in memory only; they are never written to disk, logs or environment of the image.
"""
import hashlib
import json
import logging
import os
import urllib.request

log = logging.getLogger("shoplite.vault")


def _call(method, path, token=None, body=None):
    req = urllib.request.Request(os.environ["VAULT_ADDR"].rstrip("/") + "/v1/" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Vault-Token", token)
    with urllib.request.urlopen(req, timeout=5) as r:  # nosec B310 - URL comes from trusted config
        return json.loads(r.read() or b"{}")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def load():
    if not os.getenv("VAULT_ADDR"):
        return {}
    role_id = _read(os.environ["VAULT_ROLE_ID_FILE"])
    wrapped = _read(os.environ["VAULT_SECRET_ID_FILE"])
    # unwrap the single-use wrapping token to obtain the real secret_id
    secret_id = _call("POST", "sys/wrapping/unwrap", token=wrapped)["data"]["secret_id"]
    token = _call("POST", "auth/approle/login", body={"role_id": role_id, "secret_id": secret_id})["auth"]
    log.info("logged in to Vault with AppRole, policies=%s ttl=%ss", token["policies"], token["lease_duration"])
    out = {}
    if os.getenv("VAULT_DB_ROLE"):
        cred = _call("GET", "database/creds/" + os.environ["VAULT_DB_ROLE"], token=token["client_token"])
        d = cred["data"]
        out["database_url"] = (f"postgresql://{d['username']}:{d['password']}@{os.getenv('DB_HOST', 'db')}:5432/"
                               f"{os.getenv('DB_NAME', 'shop')}")
        out["lease_id"] = cred["lease_id"]
        out["lease_duration"] = cred["lease_duration"]
        log.info("received dynamic database user %s (lease %ss)", d["username"], cred["lease_duration"])
    if os.getenv("VAULT_KV_PATH"):
        kv = _call("GET", os.environ["VAULT_KV_PATH"], token=token["client_token"])["data"]["data"]
        out["payment_api_key"] = kv.get("payment_api_key")
    return out


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12] if value else None
