# -*- coding: utf-8 -*-
"""
test_auth.py
------------
Tests de cuentas, sesión y cuotas: registro, login, /auth/me y el límite de
filas para usuarios anónimos.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    conn = session()
    try:
        yield conn
    finally:
        conn.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_register_crea_usuario_y_organizacion(client, db):
    r = client.post(
        "/auth/register",
        json={"email": "ana@example.com", "password": "supersecret", "full_name": "Ana"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "ana@example.com"
    assert body["organization"]["plan"] == "free"

    assert db.query(models.User).count() == 1
    assert db.query(models.Organization).count() == 1
    assert db.query(models.OrganizationMember).count() == 1


def test_register_rechaza_email_duplicado(client):
    payload = {"email": "ana@example.com", "password": "supersecret"}
    assert client.post("/auth/register", json=payload).status_code == 200
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 400


def test_register_rechaza_contrasena_corta(client):
    r = client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "corta"}
    )
    assert r.status_code == 400


def test_login_devuelve_cookie_de_sesion(client):
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    assert r.status_code == 200
    assert "dcb_session" in r.cookies
    assert r.cookies["dcb_session"]


def test_login_con_password_incorrecta(client):
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "incorrecta"}
    )
    assert r.status_code == 401


def test_me_sin_sesion_devuelve_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_devuelve_plan_y_limites(client):
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ana@example.com"
    assert body["plan"] == "free"
    assert body["organization"]["slug"].startswith("org-")
    assert body["limits"]["rows_month"] == 1000


def test_logout_invalida_la_sesion(client):
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_la_cookie_de_sesion_es_httponly(client):
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    header = r.headers.get("set-cookie", "")
    assert "HttpOnly" in header
    assert "Path=/" in header


def test_en_local_la_cookie_no_es_secure_ni_none(client, monkeypatch):
    """En http://localhost no puede ser Secure (el navegador la descartaría)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "dev")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "")
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    header = r.headers.get("set-cookie", "").lower()
    assert "samesite=lax" in header
    assert "secure" not in header


def test_en_produccion_la_cookie_es_secure_y_samesite_none(client, monkeypatch):
    """pages.dev -> onrender.com es cross-site: hace falta None + Secure."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SAMESITE", "")
    client.post(
        "/auth/register", json={"email": "ana@example.com", "password": "supersecret"}
    )
    r = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "supersecret"}
    )
    header = r.headers.get("set-cookie", "").lower()
    assert "samesite=none" in header
    assert "secure" in header


def test_bloquea_posts_desde_origenes_no_permitidos(client):
    r = client.post(
        "/auth/login",
        json={"email": "ana@example.com", "password": "supersecret"},
        headers={"Origin": "https://sitio-malicioso.example"},
    )
    assert r.status_code == 403


def test_permite_posts_desde_la_landing(client):
    from app.core.config import settings

    origin = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()][0]
    r = client.post(
        "/auth/login",
        json={"email": "nadie@example.com", "password": "supersecret"},
        headers={"Origin": origin},
    )
    # 401 = llegó al handler (el origen pasó el guard), no 403.
    assert r.status_code == 401


def test_usuarios_anonimos_no_pueden_superar_el_limite_de_filas(client):
    from app.core.limits import ANON_MAX_ROWS

    # Cabecera + 1.001 filas de datos.
    csv = "Nombre\n" + "\n".join("Empresa %d S.L." % i for i in range(ANON_MAX_ROWS + 1))
    r = client.post(
        "/api/clean", files={"file": ("grande.csv", csv.encode("utf-8"), "text/csv")}
    )
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert detail["error"] == "anon_rows_exceeded"
    assert detail["limit"] == ANON_MAX_ROWS
