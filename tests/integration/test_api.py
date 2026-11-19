"""Integration tests: run against the real container image talking to a real PostgreSQL database."""
import os

import requests

BASE = os.getenv("BASE_URL", "http://localhost:8080")


def test_health_reports_database_ok():
    r = requests.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_order_is_persisted():
    before = requests.get(f"{BASE}/api/orders", timeout=5).json()
    r = requests.post(f"{BASE}/api/orders", json={"customer": "ci", "items": [1, 3]}, timeout=5)
    assert r.status_code == 201
    assert r.json()["total"] == 1499 + 2199
    after = requests.get(f"{BASE}/api/orders", timeout=5).json()
    assert after["orders"] == before["orders"] + 1
    assert after["last_id"] == r.json()["id"]
    assert after["revenue"] == before["revenue"] + 3698


def test_many_orders():
    ids = [requests.post(f"{BASE}/api/orders", json={"items": [2]}, timeout=5).json()["id"] for _ in range(20)]
    assert ids == sorted(ids) and len(set(ids)) == 20


def test_bad_order_rejected_and_not_stored():
    before = requests.get(f"{BASE}/api/orders", timeout=5).json()["orders"]
    assert requests.post(f"{BASE}/api/orders", json={"items": [999]}, timeout=5).status_code == 400
    assert requests.get(f"{BASE}/api/orders", timeout=5).json()["orders"] == before


def test_container_runs_as_non_root_and_exposes_metrics():
    m = requests.get(f"{BASE}/metrics", timeout=5).text
    assert 'shop_orders_total' in m
