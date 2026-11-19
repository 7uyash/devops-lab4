import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))
os.environ.pop("DATABASE_URL", None)
os.environ.pop("VAULT_ADDR", None)

import pytest  # noqa: E402

import app as shop  # noqa: E402
import vault_client  # noqa: E402


@pytest.fixture
def client():
    return shop.create_app().test_client()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json["status"] == "ok"
    assert r.json["database"] == "not configured"


def test_version_headers(client):
    r = client.get("/version")
    assert r.json["version"] == shop.APP_VERSION
    assert r.headers["X-App-Version"] == shop.APP_VERSION
    assert r.headers["X-App-Track"] == "stable"


def test_products(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    assert len(r.json["products"]) == 4


def test_product_found_and_missing(client):
    assert client.get("/api/products/2").json["name"] == "Wireless Mouse"
    assert client.get("/api/products/99").status_code == 404


def test_order_total():
    assert shop.order_total([1, 2]) == 1499 + 799
    assert shop.order_total([]) == 0
    with pytest.raises(KeyError):
        shop.order_total([42])


def test_order_rejects_unknown_product(client):
    r = client.post("/api/orders", json={"items": [42]})
    assert r.status_code == 400


def test_order_without_database(client):
    assert client.post("/api/orders", json={"items": [1]}).status_code == 503
    assert client.get("/api/orders").status_code == 503


def test_config_hides_secrets(client):
    r = client.get("/api/config")
    assert r.json["source"] == "environment"
    assert r.json["payment_api_key_sha256"] is None


def test_fingerprint_is_not_the_secret():
    fp = vault_client.fingerprint("sk_live_example")
    assert len(fp) == 12 and "sk_live" not in fp
    assert vault_client.fingerprint(None) is None


def test_index_shows_version(client):
    r = client.get("/")
    assert r.status_code == 200
    assert shop.APP_VERSION.encode() in r.data


def test_metrics(client):
    client.get("/api/products")
    body = client.get("/metrics").data.decode()
    assert "http_requests_total" in body
    assert "app_info" in body


def test_fault_injection(monkeypatch, client):
    monkeypatch.setattr(shop, "ERROR_RATE", 1.0)
    assert shop.create_app().test_client().get("/api/products").status_code == 500
