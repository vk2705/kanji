"""
Shared pytest fixtures for the isolated API test suite (test_api_*.py).

Architecture review finding #3 (2026-08-31, docs/2026-08-31-architecture-review.md):
test_regression_fixes.py and the audit_*.py scripts are valuable but all read the
live, mutable kanji.db — none of them exercise auth, visibility rules end-to-end,
migrations, or contribution-endpoint ownership checks in isolation. This gives every
test its own throwaway temp-file SQLite DB and a FastAPI TestClient wired to it via
dependency_overrides, so tests can freely create/mutate data without ever touching
backend/kanji.db and without tests affecting each other.

Run with: cd backend && ./venv/bin/pytest
(needs requirements-dev.txt: pip install -r requirements.txt -r requirements-dev.txt)
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

import database  # noqa: E402
from database import db_conn, init_db, migrate_schema  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    """A fresh, migrated, empty (no kanji rows) temp-file DB per test. A real file
    rather than :memory: because get_db() always opens by path (sqlite3.connect(
    DB_PATH)) and different connections to :memory: don't share data — the app's
    db_conn() dependency opens a new connection per request, so a temp file is the
    simplest way to get the same on-disk-DB semantics as production."""
    path = tmp_path / "test.db"
    saved_path = database.DB_PATH
    database.DB_PATH = path
    try:
        init_db()
        conn = database.get_db()
        migrate_schema(conn)
        conn.close()
        yield path
    finally:
        database.DB_PATH = saved_path


@pytest.fixture
def app(db_path):
    """The real FastAPI app, with db_conn overridden to open connections against
    this test's temp DB instead of the real backend/kanji.db. Imported lazily
    (after db_path has already pointed database.DB_PATH at the temp file) so
    main.py's module-level UPLOAD_DIR.mkdir() etc. run safely, and so each test
    gets a fresh app.dependency_overrides state."""
    import main as main_module

    def override_db_conn():
        conn = database.get_db()
        try:
            yield conn
        finally:
            conn.close()

    main_module.app.dependency_overrides[db_conn] = override_db_conn
    yield main_module.app
    main_module.app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """TestClient with an https:// base URL — required for the app's session/
    visitor cookies to round-trip at all: they're set with secure=True (auth.py,
    analytics.py), and httpx's cookie jar silently drops Secure cookies over a
    plain http:// base URL, which would otherwise make every login-dependent test
    fail with a confusing 401 instead of a clear cookie-handling explanation."""
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def conn(db_path):
    """A direct sqlite3 connection to the same temp DB, for tests that want to
    seed fixture rows or assert on raw DB state without going through the API."""
    c = database.get_db()
    yield c
    c.close()


def register_user(client: TestClient, username: str, password: str = "testpass123") -> dict:
    """Helper: register a user and return the parsed response body. The session
    cookie is captured automatically by the TestClient's cookie jar for subsequent
    requests on the same client instance."""
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()
