"""The installable app: /sw.js and /manifest.webmanifest are served with the right types and headers."""
import json

from app import config


def _static(tmp_path, monkeypatch):
    (tmp_path / "sw.js").write_text("self.addEventListener('fetch', () => {})\n", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text(json.dumps({"name": "FinVault", "display": "standalone"}), encoding="utf-8")
    monkeypatch.setattr(config, "STATIC_DIR", tmp_path)


def test_service_worker_served(client, tmp_path, monkeypatch):
    _static(tmp_path, monkeypatch)
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert r.headers["cache-control"] == "no-cache"  # a new deploy's worker is picked up on the next visit
    csp = r.headers["content-security-policy"]
    assert "worker-src 'self'" in csp and "script-src 'self'" in csp and "connect-src 'self'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "fetch" in r.text
    assert client.head("/sw.js").status_code == 200


def test_manifest_served(client, tmp_path, monkeypatch):
    _static(tmp_path, monkeypatch)
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/manifest+json"
    assert r.headers["cache-control"] == "no-cache"
    assert "manifest-src 'self'" in r.headers["content-security-policy"]
    assert r.json()["display"] == "standalone"


def test_missing_pwa_files_are_404_not_index(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATIC_DIR", tmp_path)
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    for path in ("/sw.js", "/manifest.webmanifest"):
        r = client.get(path)
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}


def test_api_stays_no_store(client):
    # The worker keeps its own, purgeable copy for offline viewing; the HTTP cache must never store API data.
    r = client.get("/api/health")
    assert r.headers["cache-control"] == "no-store"
