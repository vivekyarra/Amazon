import os

import pytest

os.environ.setdefault("DONE_IRL_WARM_SCENES", "0")  # keep unit tests fast; warm-up is a runtime accelerator
from fastapi.testclient import TestClient
from done_irl.api import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        tmp_path,
        {"demo-admin": "test-admin-password", "owner": "test-owner-password", "other": "test-other-password"},
    )


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "demo-admin", "password": "test-admin-password"})
        assert r.status_code == 200
        yield c


@pytest.fixture
def post(client):
    import uuid

    def call(path, body=None, key=None, status=200):
        r = client.post("/api" + path, json=body or {}, headers={"Idempotency-Key": key or uuid.uuid4().hex})
        assert r.status_code == status, r.text
        return r.json()

    return call
