"""Unit tests for the database and Vault layers, with the network replaced by fakes."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

import pytest  # noqa: E402

import db  # noqa: E402
import vault_client  # noqa: E402


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, table_exists=True):
        self.sql = []
        self.table_exists = table_exists

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if "to_regclass" in sql:
            return FakeCursor(("orders",) if self.table_exists else (None,))
        if sql.startswith("INSERT"):
            return FakeCursor((7,))
        if "count(*)" in sql:
            return FakeCursor((3, 7, 4500))
        if "current_user" in sql:
            return FakeCursor(("v-approle-shoplite-abc",))
        return FakeCursor((1,))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fake_db(monkeypatch):
    conn = FakeConn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/shop")
    monkeypatch.setattr(db, "psycopg", object())
    monkeypatch.setattr(db, "connect", lambda: conn)
    return conn


def test_db_disabled_without_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert not db.enabled()
    assert db.status() == "not configured"
    assert db.current_user() is None


def test_insert_and_stats(fake_db):
    assert db.insert_order("ci", [1, 2], 2298) == 7
    assert db.order_stats() == {"orders": 3, "last_id": 7, "revenue": 4500}
    assert db.status() == "ok"
    assert db.current_user() == "v-approle-shoplite-abc"
    assert not any(s.startswith("CREATE TABLE") for s in fake_db.sql)


def test_schema_created_only_when_missing(fake_db):
    fake_db.table_exists = False
    db.insert_order("ci", [1], 1499)
    assert any("CREATE TABLE IF NOT EXISTS orders" in s for s in fake_db.sql)


def test_database_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/shop")
    monkeypatch.setattr(db, "psycopg", object())

    def down():
        raise db.Error("connection refused")
    monkeypatch.setattr(db, "connect", down)
    assert db.status() == "unavailable"
    assert db.current_user() is None


def test_vault_not_configured(monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    assert vault_client.load() == {}


def test_vault_approle_flow(monkeypatch, tmp_path):
    (tmp_path / "role_id").write_text("role-123\n")
    (tmp_path / "secret_id").write_text("hvs.wrapped\n")
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_ROLE_ID_FILE", str(tmp_path / "role_id"))
    monkeypatch.setenv("VAULT_SECRET_ID_FILE", str(tmp_path / "secret_id"))
    monkeypatch.setenv("VAULT_DB_ROLE", "shoplite-app")
    monkeypatch.setenv("VAULT_KV_PATH", "secret/data/shoplite/config")
    monkeypatch.setenv("DB_HOST", "db")
    calls = []
    answers = {
        "sys/wrapping/unwrap": {"data": {"secret_id": "sid-456"}},
        "auth/approle/login": {"auth": {"client_token": "hvs.app", "policies": ["shoplite-app"], "lease_duration": 900}},
        "database/creds/shoplite-app": {"lease_id": "database/creds/shoplite-app/xyz", "lease_duration": 600,
                                        "data": {"username": "v-app-1", "password": "pw"}},
        "secret/data/shoplite/config": {"data": {"data": {"payment_api_key": "sk_test"}}},
    }

    def fake_urlopen(req, timeout):
        path = req.full_url.split("/v1/", 1)[1]
        calls.append((path, req.get_header("X-vault-token"), req.data))
        return io.BytesIO(json.dumps(answers[path]).encode())
    monkeypatch.setattr(vault_client.urllib.request, "urlopen", fake_urlopen)

    out = vault_client.load()
    assert out["database_url"] == "postgresql://v-app-1:pw@db:5432/shop"
    assert out["payment_api_key"] == "sk_test"
    assert out["lease_duration"] == 600
    # unwrap uses the wrapping token, login sends role_id + unwrapped secret_id, reads use the app token
    assert calls[0][:2] == ("sys/wrapping/unwrap", "hvs.wrapped")
    assert json.loads(calls[1][2]) == {"role_id": "role-123", "secret_id": "sid-456"}
    assert all(c[1] == "hvs.app" for c in calls[2:])
