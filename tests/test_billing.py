# -*- coding: utf-8 -*-
"""
test_billing.py
---------------
Tests del billing con Stripe: checkout, portal, webhook firmado,
idempotencia de eventos y sincronización del plan.

Stripe queda completamente simulado: los tests no tocan la red.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import models
from app.db.base import Base
from app.db.session import get_db


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def db():
    """Base de datos SQLite en memoria, aislada por test."""
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
    """TestClient con la base de datos de test."""
    from fastapi.testclient import TestClient
    from main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class _Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeStripe:
    """Doble de prueba del módulo stripe."""

    def __init__(self, checkout_session=None, session_error=None,
                 price_type="recurring", price_error=None):
        self.api_key = ""
        self.customers_created = []
        self.sessions_created = []
        self.portals_created = []
        self.webhook_calls = []
        self.checkout_session = checkout_session
        self.session_error = session_error
        self.price_type = price_type
        self.price_error = price_error

        self.Customer = _Namespace(create=self._create_customer)
        self.checkout = _Namespace(
            Session=_Namespace(
                create=self._create_session, retrieve=self._retrieve_session
            )
        )
        self.billing_portal = _Namespace(
            Session=_Namespace(create=self._create_portal)
        )
        self.Webhook = _Namespace(construct_event=self._construct_event)
        self.Price = _Namespace(
            retrieve=self._retrieve_price, list=self._list_prices
        )
        self.Account = _Namespace(retrieve=self._retrieve_account)

    def _create_customer(self, **kwargs):
        self.customers_created.append(kwargs)
        return _Namespace(id="cus_test_123")

    def _create_session(self, **kwargs):
        if self.session_error is not None:
            raise self.session_error
        self.sessions_created.append(kwargs)
        return _Namespace(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")

    def _create_portal(self, **kwargs):
        self.portals_created.append(kwargs)
        return _Namespace(url="https://billing.stripe.com/p/session/test")

    def _retrieve_price(self, price_id, **kwargs):
        if self.price_error is not None:
            raise self.price_error
        return {
            "id": price_id,
            "type": self.price_type,
            "active": True,
            "unit_amount": 2900,
            "currency": "eur",
            "recurring": {"interval": "month"} if self.price_type == "recurring" else None,
            "product": "prod_test",
        }

    def _retrieve_account(self, **kwargs):
        return {"id": "acct_test", "country": "ES", "charges_enabled": True}

    def _list_prices(self, **kwargs):
        return {
            "data": [
                {
                    "id": "price_basic_test",
                    "type": self.price_type,
                    "active": True,
                    "unit_amount": 2900,
                    "currency": "eur",
                    "recurring": {"interval": "month"},
                    "nickname": None,
                }
            ]
        }

    def _retrieve_session(self, session_id, **kwargs):
        if self.checkout_session is not None:
            return self.checkout_session
        return {
            "id": session_id,
            "metadata": {},
            "payment_status": "paid",
        }

    def _construct_event(self, payload, sig_header, secret):
        self.webhook_calls.append((payload, sig_header, secret))
        return json.loads(payload)


@pytest.fixture
def fake_stripe(monkeypatch):
    """Sustituye el módulo stripe en el router de billing."""
    from app.billing import router as billing_router

    fake = FakeStripe()
    monkeypatch.setattr(billing_router, "stripe", fake)
    return fake


@pytest.fixture
def stripe_config(monkeypatch):
    """Configura las variables de Stripe como en producción."""
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(settings, "STRIPE_PRICE_BASIC", "price_basic_test")
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro_test")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "APP_URL", "https://landing.example")
    return settings


@pytest.fixture
def logged_in(client):
    """Registra un usuario (con su organización) e inicia sesión."""
    r = client.post(
        "/auth/register",
        json={"email": "demo@example.com", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/auth/login",
        json={"email": "demo@example.com", "password": "supersecret"},
    )
    assert r.status_code == 200, r.text
    return client


def _org(client, db):
    return db.query(models.Organization).first()


def _subscription(status="active", price_id="price_basic_test", sub_id="sub_123", customer="cus_test_123"):
    return {
        "id": sub_id,
        "status": status,
        "customer": customer,
        "metadata": {},
        "items": {"data": [{"price": {"id": price_id}}]},
    }


def _event(event_id, event_type, obj):
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------
def test_checkout_requiere_sesion(client, stripe_config, fake_stripe):
    r = client.post("/billing/checkout/basic")
    assert r.status_code == 401


def test_checkout_rechaza_plan_invalido(logged_in, stripe_config, fake_stripe):
    r = logged_in.post("/billing/checkout/platinum")
    assert r.status_code == 400
    assert "inválido" in r.json()["detail"].lower()


def test_checkout_crea_sesion_con_el_precio_correcto(logged_in, stripe_config, fake_stripe):
    r = logged_in.post("/billing/checkout/basic")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")
    assert body["plan"] == "basic"

    assert len(fake_stripe.sessions_created) == 1
    kwargs = fake_stripe.sessions_created[0]
    assert kwargs["mode"] == "subscription"
    assert kwargs["line_items"] == [{"price": "price_basic_test", "quantity": 1}]
    # La metadata debe permitir resolver la org en los eventos de suscripción.
    assert kwargs["metadata"]["plan"] == "basic"
    assert kwargs["subscription_data"]["metadata"]["plan"] == "basic"
    assert kwargs["subscription_data"]["metadata"]["org_id"] == kwargs["metadata"]["org_id"]
    # La redirección va a la landing, no a la API.
    assert kwargs["success_url"].startswith("https://landing.example/")
    assert kwargs["cancel_url"].startswith("https://landing.example/")


def test_checkout_de_pro_usa_el_price_de_pro(logged_in, stripe_config, fake_stripe):
    r = logged_in.post("/billing/checkout/PRO")
    assert r.status_code == 200
    assert fake_stripe.sessions_created[0]["line_items"][0]["price"] == "price_pro_test"


def test_checkout_sin_stripe_configurado_da_400(logged_in, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    r = logged_in.post("/billing/checkout/basic")
    assert r.status_code == 400
    assert "stripe" in r.json()["detail"].lower()


def test_checkout_sin_price_configurado_da_400(logged_in, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_BASIC", "")
    r = logged_in.post("/billing/checkout/basic")
    assert r.status_code == 400


def test_checkout_con_id_de_producto_explica_que_falta_el_price(logged_in, stripe_config, fake_stripe, monkeypatch):
    """Pegar un prod_... en STRIPE_PRICE_* es el fallo más común."""
    monkeypatch.setattr(settings, "STRIPE_PRICE_BASIC", "prod_ABC123")
    r = logged_in.post("/billing/checkout/basic")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "STRIPE_PRICE_BASIC" in detail
    assert "price_" in detail
    assert fake_stripe.sessions_created == []


def test_checkout_crea_el_cliente_de_stripe_una_sola_vez(logged_in, stripe_config, fake_stripe, db):
    logged_in.post("/billing/checkout/basic")
    logged_in.post("/billing/checkout/pro")
    assert len(fake_stripe.customers_created) == 1
    org = _org(logged_in, db)
    assert org.stripe_customer_id == "cus_test_123"


def test_checkout_error_de_stripe_da_400_con_el_motivo(logged_in, stripe_config, fake_stripe):
    """Un fallo de Stripe no debe acabar en un 500 genérico."""
    fake_stripe.session_error = RuntimeError(
        "You can only use a recurring price in subscription mode"
    )
    r = logged_in.post("/billing/checkout/basic")
    assert r.status_code == 400
    assert "recurring" in r.json()["detail"]


# --------------------------------------------------------------------------
# Diagnóstico de la configuración de Stripe
# --------------------------------------------------------------------------
def test_diagnose_requiere_sesion(client, stripe_config, fake_stripe):
    assert client.get("/billing/diagnose").status_code == 401


def test_diagnose_precio_recurrente_correcto(logged_in, stripe_config, fake_stripe):
    r = logged_in.get("/billing/diagnose")
    assert r.status_code == 200
    body = r.json()
    assert body["key_mode"] == "test"
    assert body["webhook_secret"] is False
    assert body["account"]["country"] == "ES"
    assert body["prices"]["basic"]["ok"] is True
    assert body["prices"]["basic"]["interval"] == "month"
    assert body["prices"]["pro"]["ok"] is True


def test_diagnose_detecta_precio_de_pago_unico(logged_in, stripe_config, fake_stripe):
    fake_stripe.price_type = "one_time"
    r = logged_in.get("/billing/diagnose")
    assert r.status_code == 200
    basic = r.json()["prices"]["basic"]
    assert basic["type"] == "one_time"
    assert basic["ok"] is False


def test_diagnose_muestra_error_si_el_precio_no_existe(logged_in, stripe_config, fake_stripe):
    fake_stripe.price_error = RuntimeError("No such price: 'price_basic_test'")
    r = logged_in.get("/billing/diagnose")
    assert r.status_code == 200
    basic = r.json()["prices"]["basic"]
    assert basic["ok"] is False
    assert "No such price" in basic["error"]


def test_diagnose_detecta_id_de_producto(logged_in, stripe_config, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_PRICE_BASIC", "prod_ABC123")
    r = logged_in.get("/billing/diagnose")
    assert r.status_code == 200
    basic = r.json()["prices"]["basic"]
    assert basic["ok"] is False
    assert "prod_" in basic["error"]
    assert basic["available_prices"][0]["id"] == "price_basic_test"


# --------------------------------------------------------------------------
# Portal y estado
# --------------------------------------------------------------------------
def test_portal_devuelve_la_url(logged_in, stripe_config, fake_stripe):
    logged_in.post("/billing/checkout/basic")
    r = logged_in.get("/billing/portal")
    assert r.status_code == 200
    assert r.json()["portal_url"].startswith("https://billing.stripe.com/")


def test_status_devuelve_el_plan(logged_in, stripe_config, fake_stripe):
    r = logged_in.get("/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    assert body["limits"]["rows_month"] == 1000
    assert body["stripe_configured"] is True


def test_el_plan_free_es_inferior_a_basic():
    """Si no, pagar Basic no aporta nada: el tier Free debe ser menor."""
    from app.core.limits import PLAN_LIMITS

    free = PLAN_LIMITS["free"]
    basic = PLAN_LIMITS["basic"]
    assert free["rows_month"] < basic["rows_month"]
    assert free["max_mb"] <= basic["max_mb"]
    assert free["history_days"] <= basic["history_days"]
    assert basic["rows_month"] < PLAN_LIMITS["pro"]["rows_month"]


def test_status_requiere_sesion(client, stripe_config, fake_stripe):
    assert client.get("/billing/status").status_code == 401


# --------------------------------------------------------------------------
# Webhook: firma
# --------------------------------------------------------------------------
def test_webhook_rechaza_payload_sin_firma_cuando_hay_secreto(
    logged_in, fake_stripe, monkeypatch
):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    r = logged_in.post(
        "/billing/webhook",
        json=_event("evt_1", "checkout.session.completed", {"metadata": {}}),
    )
    assert r.status_code == 400
    assert "firma" in r.json()["detail"].lower()


def test_webhook_rechaza_firma_invalida(logged_in, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")

    def boom(payload, sig, secret):
        raise ValueError("firma inválida")

    fake_stripe.Webhook.construct_event = boom
    r = logged_in.post(
        "/billing/webhook",
        content=b'{"id":"evt_1","type":"checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=abc"},
    )
    assert r.status_code == 400


def test_webhook_verifica_la_firma(logged_in, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    payload = json.dumps(_event("evt_1", "invoice.paid", {})).encode("utf-8")
    r = logged_in.post(
        "/billing/webhook", content=payload, headers={"stripe-signature": "t=1,v1=abc"}
    )
    assert r.status_code == 200
    assert fake_stripe.webhook_calls[0][1] == "t=1,v1=abc"
    assert fake_stripe.webhook_calls[0][2] == "whsec_test"


def test_webhook_sin_secreto_falla_en_produccion(logged_in, fake_stripe, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "ENV", "production")
    r = logged_in.post(
        "/billing/webhook", json=_event("evt_1", "invoice.paid", {})
    )
    assert r.status_code == 503


def test_webhook_sin_secreto_rechaza_origenes_externos(db, fake_stripe, monkeypatch):
    """Aunque ENV no sea 'production', un POST externo sin firma se rechaza."""
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "ENV", "dev")

    from fastapi.testclient import TestClient
    from main import app

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, client=("8.8.8.8", 1234)) as external:
            r = external.post(
                "/billing/webhook", json=_event("evt_ext", "invoice.paid", {})
            )
            assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Webhook: sincronización del plan
# --------------------------------------------------------------------------
def test_checkout_completed_activa_el_plan(logged_in, fake_stripe, db):
    org = _org(logged_in, db)
    event = _event(
        "evt_checkout_1",
        "checkout.session.completed",
        {
            "metadata": {"org_id": org.id, "plan": "pro"},
            "customer": "cus_test_123",
            "subscription": "sub_123",
        },
    )
    r = logged_in.post("/billing/webhook", json=event)
    assert r.status_code == 200
    assert r.json()["action"] == "activated"
    db.expire_all()
    org = db.query(models.Organization).first()
    assert org.plan == "pro"
    assert org.stripe_subscription_id == "sub_123"
    assert org.stripe_customer_id == "cus_test_123"


def test_subscription_created_activa_el_plan_por_metadata(logged_in, fake_stripe, db):
    org = _org(logged_in, db)
    sub = _subscription(status="active", price_id="price_pro_test")
    sub["metadata"] = {"org_id": org.id, "plan": "pro"}
    r = logged_in.post(
        "/billing/webhook", json=_event("evt_sub_1", "customer.subscription.created", sub)
    )
    assert r.status_code == 200
    assert r.json()["action"] == "activated"
    db.expire_all()
    assert db.query(models.Organization).first().plan == "pro"


def test_subscription_updated_hace_downgrade_a_basic(logged_in, fake_stripe, db, stripe_config):
    org = _org(logged_in, db)
    org.plan = "pro"
    db.commit()

    sub = _subscription(status="active", price_id="price_basic_test")
    sub["metadata"] = {"org_id": org.id}
    r = logged_in.post(
        "/billing/webhook", json=_event("evt_sub_2", "customer.subscription.updated", sub)
    )
    assert r.status_code == 200
    assert r.json()["action"] == "activated"
    db.expire_all()
    assert db.query(models.Organization).first().plan == "basic"


def test_subscription_deleted_degrada_a_free(logged_in, fake_stripe, db):
    org = _org(logged_in, db)
    org.plan = "pro"
    db.commit()

    sub = _subscription(status="canceled", price_id="price_pro_test")
    sub["metadata"] = {"org_id": org.id}
    r = logged_in.post(
        "/billing/webhook", json=_event("evt_sub_3", "customer.subscription.deleted", sub)
    )
    assert r.status_code == 200
    assert r.json()["action"] == "downgraded"
    db.expire_all()
    assert db.query(models.Organization).first().plan == "free"


def test_suscripcion_cancelada_mantiene_el_plan_mientras_se_reintenta(
    logged_in, fake_stripe, db
):
    """past_due = Stripe reintenta el cobro: no se quita el acceso."""
    org = _org(logged_in, db)
    org.plan = "pro"
    db.commit()

    sub = _subscription(status="past_due", price_id="price_pro_test")
    sub["metadata"] = {"org_id": org.id}
    logged_in.post(
        "/billing/webhook", json=_event("evt_sub_4", "customer.subscription.updated", sub)
    )
    db.expire_all()
    assert db.query(models.Organization).first().plan == "pro"


def test_evento_desconocido_se_ignora(logged_in, fake_stripe, db):
    r = logged_in.post(
        "/billing/webhook", json=_event("evt_x", "customer.created", {"id": "cus_1"})
    )
    assert r.status_code == 200
    assert r.json()["action"] == "ignored"


def test_evento_sin_organizacion_no_rompe(logged_in, fake_stripe, db):
    r = logged_in.post(
        "/billing/webhook",
        json=_event("evt_y", "customer.subscription.updated", _subscription()),
    )
    assert r.status_code == 200
    assert r.json()["action"] == "no_org"


# --------------------------------------------------------------------------
# Idempotencia
# --------------------------------------------------------------------------
def test_el_webhook_es_idempotente(logged_in, fake_stripe, db):
    org = _org(logged_in, db)
    event = _event(
        "evt_dup",
        "checkout.session.completed",
        {"metadata": {"org_id": org.id, "plan": "pro"}, "subscription": "sub_999"},
    )
    first = logged_in.post("/billing/webhook", json=event)
    second = logged_in.post("/billing/webhook", json=event)
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    # Sólo se ha procesado una vez.
    assert db.query(models.StripeEvent).filter_by(event_id="evt_dup").count() == 1


def test_no_se_crean_tablas_de_stripe_events_dos_veces(logged_in, fake_stripe, db):
    org = _org(logged_in, db)
    for i in range(3):
        event = _event(
            "evt_multi_%d" % i,
            "checkout.session.completed",
            {"metadata": {"org_id": org.id, "plan": "basic"}},
        )
        assert logged_in.post("/billing/webhook", json=event).status_code == 200
    assert db.query(models.StripeEvent).count() == 3


# --------------------------------------------------------------------------
# Confirm (respaldo del webhook)
# --------------------------------------------------------------------------
def test_confirm_activa_el_plan_sin_webhook(logged_in, fake_stripe, db, stripe_config):
    org = _org(logged_in, db)
    fake_stripe.checkout_session = {
        "id": "cs_1",
        "metadata": {"org_id": org.id, "plan": "pro"},
        "payment_status": "paid",
        "subscription": "sub_777",
    }
    r = logged_in.post("/billing/confirm", json={"session_id": "cs_1"})
    assert r.status_code == 200
    assert r.json()["plan"] == "pro"
    db.expire_all()
    assert db.query(models.Organization).first().plan == "pro"


def test_confirm_rechaza_una_sesion_de_otra_organizacion(logged_in, fake_stripe, db, stripe_config):
    fake_stripe.checkout_session = {
        "id": "cs_2",
        "metadata": {"org_id": "org_de_otro", "plan": "pro"},
        "payment_status": "paid",
    }
    r = logged_in.post("/billing/confirm", json={"session_id": "cs_2"})
    assert r.status_code == 403


def test_confirm_con_pago_pendiente_no_cambia_el_plan(logged_in, fake_stripe, db, stripe_config):
    org = _org(logged_in, db)
    fake_stripe.checkout_session = {
        "id": "cs_3",
        "metadata": {"org_id": org.id, "plan": "pro"},
        "payment_status": "unpaid",
    }
    r = logged_in.post("/billing/confirm", json={"session_id": "cs_3"})
    assert r.status_code == 200
    assert r.json()["action"] == "pending"
    db.expire_all()
    assert db.query(models.Organization).first().plan == "free"


# --------------------------------------------------------------------------
# Servicio (sin HTTP)
# --------------------------------------------------------------------------
def test_plan_for_price_usa_la_configuracion(stripe_config):
    from app.billing import service

    assert service.plan_for_price("price_basic_test") == "basic"
    assert service.plan_for_price("price_pro_test") == "pro"
    assert service.plan_for_price("price_desconocido") is None
    assert service.plan_for_price(None) is None


def test_price_for_plan_usa_la_configuracion(stripe_config):
    from app.billing import service

    assert service.price_for_plan("basic") == "price_basic_test"
    assert service.price_for_plan("PRO") == "price_pro_test"
    assert service.price_for_plan("free") is None
    assert service.price_for_plan(None) is None


def test_subscription_plan_prefiere_el_price_sobre_la_metadata(stripe_config):
    from app.billing import service

    sub = _subscription(status="active", price_id="price_pro_test")
    sub["metadata"] = {"plan": "basic"}
    assert service.subscription_plan(sub) == "pro"
