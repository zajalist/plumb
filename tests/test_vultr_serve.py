"""Smoke test for the Vultr box's FastAPI app (vultr/serve.py).

The inference functions are monkeypatched so no real model weights load in CI. Covers: bearer
auth (401 without/with bad token), /health shape, and one inference route returning the mocked
JSON shape that the cortex band-projection consumes.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_VULTR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vultr")
sys.path.insert(0, _VULTR_DIR)

import serve  # noqa: E402

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("VULTR_TOKEN", TOKEN)
    yield


@pytest.fixture
def client():
    return TestClient(serve.app)


def test_health_requires_token(client):
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_ok_with_token(client):
    r = client.get("/health", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "segment" in body["models"] and "depth" in body["models"]


def test_segment_route_returns_label_score(client, monkeypatch):
    monkeypatch.setattr(serve, "infer_segment",
                        lambda png: [{"label": "base", "score": 0.9}])
    r = client.post("/segment", headers=AUTH, content=b"fake-png")
    assert r.status_code == 200
    assert r.json() == [{"label": "base", "score": 0.9}]


def test_inference_route_requires_token(client, monkeypatch):
    monkeypatch.setattr(serve, "infer_segment", lambda png: [])
    assert client.post("/segment", content=b"x").status_code == 401


def test_clipseg_passes_prompt(client, monkeypatch):
    seen = {}

    def fake(png, prompt):
        seen["prompt"] = prompt
        return [{"label": prompt, "score": 0.5}]

    monkeypatch.setattr(serve, "infer_clipseg", fake)
    r = client.post("/clipseg", headers=AUTH, params={"prompt": "handle"}, content=b"x")
    assert r.status_code == 200
    assert seen["prompt"] == "handle"
    assert r.json()[0]["label"] == "handle"


def test_token_unset_fails_closed(client, monkeypatch):
    monkeypatch.delenv("VULTR_TOKEN", raising=False)
    # No token configured on the box ⇒ every route 401s (fail-closed), even with a bearer.
    assert client.get("/health", headers=AUTH).status_code == 401
