# -*- coding: utf-8 -*-
"""Admin access and first-party traffic tracking."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session()

    def override_get_db():
        yield db

    monkeypatch.setattr(settings, "ADMIN_USER", "adm")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "4dm1n$")
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_admin_requiere_autenticacion_basica(client):
    response = client.get("/admin")
    assert response.status_code == 401
    assert "basic" in response.headers.get("www-authenticate", "").lower()
    assert client.get("/admin", auth=("adm", "incorrecta")).status_code == 401


def test_admin_muestra_registros_y_exporta_csv(client):
    created = client.post(
        "/auth/register",
        json={"email": "admin-view@example.com", "password": "supersecret"},
    )
    assert created.status_code == 200

    response = client.get("/admin", auth=("adm", "4dm1n$"))
    assert response.status_code == 200
    assert "admin-view@example.com" in response.text
    assert "10 usos" in response.text
    assert response.headers["cache-control"] == "no-store"

    export = client.get("/admin/export/users.csv", auth=("adm", "4dm1n$"))
    assert export.status_code == 200
    assert "admin-view@example.com" in export.text


def test_tracking_guarda_visitas_y_reutiliza_id_aleatorio(client):
    first = client.post(
        "/api/track",
        json={"path": "/", "referrer": "https://example.org/"},
        headers={"user-agent": "Mozilla/5.0 test browser"},
    )
    assert first.status_code == 204
    visitor_cookie = client.cookies.get("dcb_visitor")
    assert visitor_cookie

    second = client.post(
        "/api/track",
        json={"path": "/", "referrer": ""},
        headers={"user-agent": "Mozilla/5.0 test browser"},
    )
    assert second.status_code == 204
    assert client.cookies.get("dcb_visitor") == visitor_cookie

    dashboard = client.get("/admin", auth=("adm", "4dm1n$"))
    assert dashboard.status_code == 200
    assert "Visitas últimos 30 días" in dashboard.text
    assert "/" in dashboard.text


def test_tracking_ignora_bots(client):
    response = client.post(
        "/api/track",
        json={"path": "/", "referrer": ""},
        headers={"user-agent": "ExampleBot/1.0"},
    )
    assert response.status_code == 204
    assert client.cookies.get("dcb_visitor") is None

    export = client.get("/admin/export/visits.csv", auth=("adm", "4dm1n$"))
    assert export.status_code == 200
    assert export.text.count("\n") == 1  # sólo cabecera
