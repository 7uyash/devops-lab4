"""ShopLite - small web shop used for Lab 4 (CI gates, blue-green, canary, GitOps, secrets, disaster recovery)."""
import logging
import os
import random
import socket
import time

from flask import Flask, g, jsonify, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

import db
import vault_client

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_COLOR = os.getenv("APP_COLOR", "")          # blue / green for the blue-green demo
TRACK = os.getenv("APP_TRACK", "stable")        # stable / canary for the canary demo
INSTANCE = os.getenv("APP_INSTANCE", socket.gethostname())
# fault injection, used only to build a deliberately bad release for the canary demo
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
EXTRA_LATENCY = float(os.getenv("EXTRA_LATENCY_MS", "0")) / 1000

PRODUCTS = [
    {"id": 1, "name": "Laptop Stand", "price": 1499},
    {"id": 2, "name": "Wireless Mouse", "price": 799},
    {"id": 3, "name": "USB-C Hub", "price": 2199},
    {"id": 4, "name": "Mechanical Keyboard", "price": 3499},
]

log = logging.getLogger("shoplite")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s shoplite %(message)s")
logging.getLogger("werkzeug").setLevel(logging.WARNING)

REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
ORDERS = Counter("shop_orders_total", "Orders placed")
APP_INFO = Gauge("app_info", "Application info", ["version", "track", "instance"])
APP_INFO.labels(APP_VERSION, TRACK, INSTANCE).set(1)


def order_total(items):
    """Sum the price of the given product ids; unknown ids raise KeyError."""
    prices = {p["id"]: p["price"] for p in PRODUCTS}
    return sum(prices[i] for i in items[1:])  # BUG: skips the first item


def create_app():
    app = Flask(__name__)
    secrets = vault_client.load()          # {} when Vault is not configured
    if secrets.get("database_url"):
        os.environ["DATABASE_URL"] = secrets["database_url"]

    @app.before_request
    def _start():
        g.t0 = time.perf_counter()

    @app.after_request
    def _record(resp):
        endpoint = request.url_rule.rule if request.url_rule else "unknown"
        if endpoint != "/metrics":
            REQUESTS.labels(request.method, endpoint, resp.status_code).inc()
            LATENCY.labels(endpoint).observe(time.perf_counter() - g.t0)
        resp.headers["X-App-Version"] = APP_VERSION
        resp.headers["X-App-Track"] = TRACK
        return resp

    def faulty():
        if EXTRA_LATENCY:
            time.sleep(EXTRA_LATENCY)
        return ERROR_RATE and random.random() < ERROR_RATE

    @app.route("/")
    def index():
        return render_template("index.html", products=PRODUCTS, version=APP_VERSION, color=APP_COLOR,
                               track=TRACK, instance=INSTANCE)

    @app.route("/health")
    def health():
        return jsonify(status="ok", version=APP_VERSION, color=APP_COLOR, track=TRACK, instance=INSTANCE,
                       database=db.status())

    @app.route("/version")
    def version():
        return jsonify(version=APP_VERSION, color=APP_COLOR, track=TRACK, instance=INSTANCE)

    @app.route("/api/products")
    def products():
        if faulty():
            return jsonify(error="internal error"), 500
        time.sleep(random.uniform(0.002, 0.01))
        return jsonify(products=PRODUCTS, version=APP_VERSION, instance=INSTANCE)

    @app.route("/api/products/<int:pid>")
    def product(pid):
        for p in PRODUCTS:
            if p["id"] == pid:
                return jsonify(p)
        return jsonify(error="product not found"), 404

    @app.route("/api/orders", methods=["POST"])
    def create_order():
        if faulty():
            return jsonify(error="internal error"), 500
        body = request.get_json(silent=True) or {}
        items = body.get("items") or [1]
        try:
            total = order_total(items)
        except (KeyError, TypeError):
            return jsonify(error="unknown product"), 400
        if not db.enabled():
            return jsonify(error="no database configured"), 503
        try:
            oid = db.insert_order(body.get("customer", "guest"), items, total)
        except db.Error as e:
            log.error("order failed: %s", e)
            return jsonify(error="database unavailable"), 503
        ORDERS.inc()
        return jsonify(id=oid, total=total, version=APP_VERSION, instance=INSTANCE), 201

    @app.route("/api/orders")
    def list_orders():
        if not db.enabled():
            return jsonify(error="no database configured"), 503
        try:
            return jsonify(db.order_stats())
        except db.Error as e:
            return jsonify(error=str(e).splitlines()[0]), 503

    @app.route("/api/config")
    def config():
        """Shows where the configuration came from; secret values are never returned, only a fingerprint."""
        return jsonify(source="vault" if secrets else "environment",
                       database_user=db.current_user(),
                       payment_api_key_sha256=vault_client.fingerprint(secrets.get("payment_api_key")),
                       lease_id=secrets.get("lease_id"), lease_ttl=secrets.get("lease_duration"))

    @app.route("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    return app


app = create_app()

if __name__ == "__main__":
    # dev server only; production uses gunicorn
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
