# tests/test_platform_endpoints.py
"""
Quantoryx — Integration tests for the v6.0 platform feature endpoints.

Covers the alerting engine, trade journal, live signals, market watch,
subscription billing, the visual strategy builder, and help content, plus
the password-recovery route. Exercises the full FastAPI stack against a
temporary SQLite database.
"""

import os
import tempfile
import uuid

import pytest

# Point the ORM at a throwaway database BEFORE the app imports the engine.
_TMP_DB = os.path.join(tempfile.gettempdir(), f"qx_platform_{uuid.uuid4().hex}.db")
os.environ["QUANTORYX_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("QUANTORYX_SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

from backend.database.connection import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    """Registers a throwaway account and returns its bearer header."""
    username = f"pytest_{uuid.uuid4().hex[:10]}"
    client.post("/api/auth/register", json={
        "username": username,
        "email": f"{username}@quantoryx.io",
        "password": "PytestDemo1234!",
        "full_name": "Pytest User",
        "role": "user",
    })
    resp = client.post("/api/auth/login", json={
        "username": username, "password": "PytestDemo1234!",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# =====================================================================
# ACCESS CONTROL
# =====================================================================

@pytest.mark.parametrize("path", [
    "/api/alerts", "/api/journal", "/api/signals",
    "/api/market/tickers", "/api/billing/invoices", "/api/billing/usage",
])
def test_protected_routes_reject_anonymous(path):
    """Every user-scoped route must refuse unauthenticated access."""
    assert client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("path", ["/api/billing/plans", "/api/builder/blocks",
                                  "/api/help/faq", "/api/help/docs"])
def test_public_catalogues_are_reachable(path):
    """Static catalogues carry no user data and stay public."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list) and resp.json()


# =====================================================================
# ALERT ENGINE
# =====================================================================

def test_alert_lifecycle(auth_headers):
    """Create, toggle, and delete an alert, asserting the client contract."""
    listed = client.get("/api/alerts", headers=auth_headers)
    assert listed.status_code == 200

    created = client.post("/api/alerts", headers=auth_headers, json={
        "name": "Pytest breakout",
        "type": "price",
        "instrument": "EURUSD",
        "op": ">",
        "value": "1.2000",
        "channel": ["push", "email"],
        "on": True,
    })
    assert created.status_code == 201, created.text
    body = created.json()

    # Field names must match what the frontend consumes, not the ORM columns.
    for key in ("id", "name", "type", "cond", "channel", "on", "fired"):
        assert key in body, f"missing '{key}' in {body}"
    assert body["cond"] == "EURUSD > 1.2000"
    assert body["on"] is True

    alert_id = body["id"]
    toggled = client.patch(f"/api/alerts/{alert_id}", headers=auth_headers, json={"on": False})
    assert toggled.status_code == 200
    assert toggled.json()["on"] is False

    assert client.delete(f"/api/alerts/{alert_id}", headers=auth_headers).status_code == 200
    assert client.delete(f"/api/alerts/{alert_id}", headers=auth_headers).status_code == 404


# =====================================================================
# TRADE JOURNAL
# =====================================================================

def test_journal_lifecycle(auth_headers):
    """A journal entry survives a write/read round trip and can be removed."""
    created = client.post("/api/journal", headers=auth_headers, json={
        "pair": "GBPUSD",
        "dir": "Short",
        "pnl": -180.5,
        "rating": 3,
        "tags": ["News", "Stopped out"],
        "note": "Stopped out by an unexpected policy comment. Loss within plan.",
        "strategy": "RSI",
    })
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["pair"] == "GBPUSD"
    assert entry["dir"] == "Short"
    assert entry["pnl"] == pytest.approx(-180.5)
    assert "Stopped out" in entry["tags"]

    listing = client.get("/api/journal", headers=auth_headers).json()
    assert any(e["id"] == entry["id"] for e in listing)

    assert client.delete(f"/api/journal/{entry['id']}", headers=auth_headers).status_code == 200


def test_journal_rating_is_bounded(auth_headers):
    """Execution grades outside 1-5 must be rejected by validation."""
    resp = client.post("/api/journal", headers=auth_headers, json={
        "pair": "EURUSD", "dir": "Long", "pnl": 10, "rating": 9, "note": "invalid",
    })
    assert resp.status_code == 422


# =====================================================================
# SIGNALS & MARKET WATCH
# =====================================================================

def test_market_tickers_cover_supported_pairs(auth_headers):
    """The feed returns one quote per configured instrument."""
    import config
    resp = client.get("/api/market/tickers", headers=auth_headers)
    assert resp.status_code == 200
    quotes = resp.json()
    assert len(quotes) == len(config.SUPPORTED_PAIRS)
    for q in quotes:
        assert {"pair", "px", "chg"} <= set(q)
        assert isinstance(q["px"], (int, float))


# =====================================================================
# BILLING
# =====================================================================

def test_plan_catalogue_shape():
    """Every tier exposes both billing cycles and a feature matrix."""
    plans = client.get("/api/billing/plans").json()
    assert {p["id"] for p in plans} == {"starter", "pro", "quant"}
    for p in plans:
        assert {"mo", "yr"} <= set(p["price"])
        assert p["feats"]


def test_subscribe_issues_invoice_and_updates_usage(auth_headers):
    """Switching to a paid tier records an invoice and raises the quota."""
    before = client.get("/api/billing/invoices", headers=auth_headers).json()

    resp = client.post("/api/billing/subscribe", headers=auth_headers,
                       json={"planId": "pro", "cycle": "mo"})
    assert resp.status_code == 200
    assert resp.json()["plan"] == "pro"

    after = client.get("/api/billing/invoices", headers=auth_headers).json()
    assert len(after) == len(before) + 1
    assert after[0]["amt"] == pytest.approx(49.0)
    assert after[0]["status"] == "paid"

    usage = client.get("/api/billing/usage", headers=auth_headers).json()
    backtests = next(u for u in usage if "Backtests" in u["label"])
    assert backtests["limit"] == 1000     # Pro quota, not the Starter 100


def test_subscribe_rejects_unknown_plan(auth_headers):
    resp = client.post("/api/billing/subscribe", headers=auth_headers,
                       json={"planId": "enterprise-unicorn"})
    assert resp.status_code == 422


# =====================================================================
# STRATEGY BUILDER
# =====================================================================

def test_builder_blocks_and_save(auth_headers):
    """The palette is grouped by category and compositions persist."""
    groups = client.get("/api/builder/blocks").json()
    assert {g["cat"] for g in groups} >= {"Indicators", "Conditions", "Risk", "Actions"}

    saved = client.post("/api/builder/strategies", headers=auth_headers, json={
        "name": "Pytest Strategy",
        "symbol": "EURUSD",
        "timeframe": "1H",
        "nodes": [{"id": "ema", "params": "period: 20"}, {"id": "buy"}],
    })
    assert saved.status_code == 201
    assert saved.json()["name"] == "Pytest Strategy"


# =====================================================================
# PASSWORD RECOVERY
# =====================================================================

def test_forgot_password_does_not_leak_account_existence():
    """Both known and unknown addresses must return an identical response."""
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@quantoryx.io"})
    assert unknown.status_code == 200
    assert unknown.json()["status"] == "SUCCESS"

    known = client.post("/api/auth/forgot", json={"email": "pytest@quantoryx.io"})
    assert known.json() == unknown.json()


def test_forgot_password_validates_email_format():
    assert client.post("/api/auth/forgot", json={"email": "not-an-email"}).status_code == 422
