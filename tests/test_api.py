"""Tests d'intégration — routes FastAPI via TestClient."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch qb_request avant d'importer app pour éviter les appels réseau
with patch("core.qb_client.qb_request", return_value=MagicMock()):
    from app import app
    from core.extensions import auth_required

# ── Helpers ──────────────────────────────────────────────────────────────────

FAKE_SESSION = {
    "qb_url": "http://localhost:8080",
    "qb_sid": "test_sid_12345",
    "qb_sid_cookie": "SID",
}


def override_auth():
    """Dependency override — bypasse la vérification d'auth."""
    return None


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_client():
    """Client avec auth bypassée via dependency_overrides."""
    app.dependency_overrides[auth_required] = override_auth
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


# ── Pages HTML ───────────────────────────────────────────────────────────────

class TestHtmlPages:
    def test_login_page_renders(self, client):
        resp = client.get("/login", follow_redirects=False)
        assert resp.status_code == 200
        assert b"qBit Manager" in resp.content

    def test_root_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_dashboard_redirects_to_login_unauthenticated(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_torrents_redirects_unauthenticated(self, client):
        resp = client.get("/torrents", follow_redirects=False)
        assert resp.status_code == 302

    def test_trackers_redirects_unauthenticated(self, client):
        resp = client.get("/trackers", follow_redirects=False)
        assert resp.status_code == 302

    def test_categories_redirects_unauthenticated(self, client):
        resp = client.get("/categories", follow_redirects=False)
        assert resp.status_code == 302

    def test_logs_redirects_unauthenticated(self, client):
        resp = client.get("/logs", follow_redirects=False)
        assert resp.status_code == 302


# ── Auth API ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_api_returns_401_when_not_authenticated(self, client):
        resp = client.get("/api/torrents/status")
        assert resp.status_code == 401

    def test_api_dashboard_401(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    def test_api_trackers_401(self, client):
        resp = client.get("/api/trackers")
        assert resp.status_code == 401

    def test_api_categories_401(self, client):
        resp = client.get("/api/categories")
        assert resp.status_code == 401

    def test_debug_toggle_401(self, client):
        resp = client.post("/api/debug/toggle")
        assert resp.status_code == 401


# ── Endpoints publics ─────────────────────────────────────────────────────────

class TestPublicEndpoints:
    def test_debug_status_no_auth(self, client):
        resp = client.get("/api/debug/status")
        assert resp.status_code == 200
        assert "debug" in resp.json()


# ── Torrents (auth bypassée) ─────────────────────────────────────────────────

class TestTorrentsApi:
    def test_status_empty_cache(self, auth_client):
        resp = auth_client.get("/api/torrents/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "total" in data
        assert isinstance(data["total"], int)

    def test_torrents_loading_when_cache_empty(self, auth_client):
        with patch("api.torrents._cache.is_ready", return_value=False), \
             patch("api.torrents._start_bg_fetch"), \
             patch("api.torrents.session_snapshot", return_value={}):
            resp = auth_client.get("/api/torrents")
            assert resp.status_code == 200
            data = resp.json()
            assert data["loading"] is True
            assert data["data"] == []

    def test_torrents_returns_paginated(self, auth_client):
        fake_data = [
            {"hash": "a" * 40, "name": f"Torrent {i}", "category": "", "state": "downloading",
             "size": i * 100, "dlspeed": 0, "upspeed": 0, "num_seeds": 0, "num_leechs": 0,
             "ratio": 0.0, "progress": 0.0, "added_on": i, "save_path": "", "eta": 0}
            for i in range(5)
        ]
        with patch("api.torrents._cache.is_ready", return_value=True), \
             patch("api.torrents._cache.age", return_value=0), \
             patch("api.torrents._cache.get", return_value=fake_data), \
             patch("api.torrents.session_snapshot", return_value={}):
            resp = auth_client.get("/api/torrents?draw=1&start=0&length=3")
            assert resp.status_code == 200
            data = resp.json()
            assert data["recordsTotal"] == 5
            assert len(data["data"]) == 3

    def test_torrent_action_invalid_hashes(self, auth_client):
        resp = auth_client.post(
            "/api/torrent/action",
            json={"action": "pause", "hashes": ["invalid"]},
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_torrent_action_unknown_action(self, auth_client):
        resp = auth_client.post(
            "/api/torrent/action",
            json={"action": "explode", "hashes": ["a" * 40]},
        )
        assert resp.status_code == 400

    def test_torrent_set_category_invalid_hash(self, auth_client):
        resp = auth_client.post(
            "/api/torrent/set-category",
            json={"hash": "bad", "category": "movies"},
        )
        assert resp.status_code == 400

    def test_torrent_set_location_traversal(self, auth_client):
        resp = auth_client.post(
            "/api/torrent/set-location",
            json={"hash": "a" * 40, "location": "/home/../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_states_returns_list(self, auth_client):
        with patch("api.torrents._cache.get", return_value=[
            {"state": "downloading"}, {"state": "pausedDL"}, {"state": "downloading"}
        ]):
            resp = auth_client.get("/api/torrents/states")
            assert resp.status_code == 200
            states = resp.json()
            assert "downloading" in states
            assert "pausedDL" in states
            assert states == sorted(set(states))  # trié, sans doublons


# ── Trackers (auth bypassée) ─────────────────────────────────────────────────

class TestTrackersApi:
    def test_bulk_invalid_operation(self, auth_client):
        resp = auth_client.post(
            "/api/tracker/bulk",
            json={"operation": "nope", "old_url": "x", "new_url": "y"},
        )
        assert resp.status_code == 400

    def test_bulk_missing_old_url(self, auth_client):
        resp = auth_client.post(
            "/api/tracker/bulk",
            json={"operation": "replace", "new_url": "http://new.tracker"},
        )
        assert resp.status_code == 400

    def test_delete_many_empty_urls(self, auth_client):
        resp = auth_client.post("/api/tracker/delete-many", json={"urls": []})
        assert resp.status_code == 400


# ── Catégories (auth bypassée) ───────────────────────────────────────────────

class TestCategoriesApi:
    def test_create_missing_name(self, auth_client):
        resp = auth_client.post("/api/category/create", json={"name": ""})
        assert resp.status_code == 400

    def test_edit_missing_name(self, auth_client):
        resp = auth_client.post("/api/category/edit", json={"name": ""})
        assert resp.status_code == 400

    def test_delete_missing_name(self, auth_client):
        resp = auth_client.post("/api/category/delete", json={"name": ""})
        assert resp.status_code == 400

    def test_move_missing_src(self, auth_client):
        resp = auth_client.post("/api/category/move-torrents", json={"src": "", "dst": "movies"})
        assert resp.status_code == 400


# ── Système ──────────────────────────────────────────────────────────────────

class TestSystemApi:
    def test_debug_status_shape(self, client):
        resp = client.get("/api/debug/status")
        assert resp.status_code == 200
        assert isinstance(resp.json()["debug"], bool)
