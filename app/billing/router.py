# -*- coding: utf-8 -*-
"""
app/billing/router.py
---------------------
Checkout, Customer Portal y Webhooks de Stripe.

La lógica de negocio vive en app/billing/service.py; aquí sólo se traduce
HTTP <-> Stripe.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.session import verify_session_token
from app.billing import service
from app.core.config import settings
from app.core.limits import get_plan_limits
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/billing", tags=["billing"])

logger = logging.getLogger(__name__)


class ConfirmRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=255)


def _get_org_from_session(request: Request, db: Session):
    """Devuelve (organización, usuario) de la sesión actual."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado"
        )
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        )
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado"
        )
    member = (
        db.query(models.OrganizationMember)
        .filter(models.OrganizationMember.user_id == user.id)
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Sin organización"
        )
    org = (
        db.query(models.Organization)
        .filter(models.Organization.id == member.organization_id)
        .first()
    )
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada"
        )
    return org, user


def _require_stripe() -> None:
    """Comprueba que Stripe está configurado y fija la clave de la API."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Stripe no configurado. Añade STRIPE_SECRET_KEY, "
                "STRIPE_PRICE_BASIC y STRIPE_PRICE_PRO en el entorno."
            ),
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _app_base(request: Request) -> str:
    """URL pública de la landing (a la que debe volver el usuario)."""
    base = (settings.APP_URL or "").strip().rstrip("/")
    if base:
        return base
    return str(request.base_url).rstrip("/")


def _key_mode(key: str) -> str:
    """Modo de la clave de Stripe, sin revelarla."""
    key = (key or "").strip()
    if not key:
        return "sin configurar"
    if key.startswith("sk_test_"):
        return "test"
    if key.startswith("sk_live_"):
        return "live"
    if key.startswith("rk_test_"):
        return "test (restringida)"
    if key.startswith("rk_live_"):
        return "live (restringida)"
    return "formato desconocido"


def _stripe_detail(exc: Exception) -> str:
    """Mensaje corto y legible de un error de Stripe."""
    detail = getattr(exc, "user_message", None) or str(exc)
    detail = " ".join(str(detail).split())
    return (detail[:300] or exc.__class__.__name__)


def _stripe_fail(exc: Exception) -> None:
    """Convierte un error de Stripe en un 400 con el motivo real.

    Sin esto, cualquier fallo de Stripe (precio inexistente, precio de pago
    único usado en una suscripción, clave restringida, etc.) acababa en un
    500 genérico y el usuario no sabía qué corregir.
    """
    logger.exception("Stripe rechazó la operación")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Stripe ha rechazado la operación: " + _stripe_detail(exc),
    )


@router.post("/checkout/{plan}")
async def create_checkout(plan: str, request: Request, db: Session = Depends(get_db)):
    """Crea una sesión de checkout de Stripe para el plan pedido."""
    org, user = _get_org_from_session(request, db)

    plan = (plan or "").strip().lower()
    if plan not in service.PAID_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan inválido. Usa 'basic' o 'pro'.",
        )

    price_id = service.price_for_plan(plan)
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Stripe no configurado: falta STRIPE_PRICE_BASIC "
                "o STRIPE_PRICE_PRO en el entorno."
            ),
        )
    if price_id.startswith("prod_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"STRIPE_PRICE_{plan.upper()} contiene un ID de producto "
                f"({price_id}). Abre el producto en Stripe → Pricing y copia "
                "el ID del precio, que empieza por 'price_'."
            ),
        )

    _require_stripe()

    if not org.stripe_customer_id:
        try:
            customer = stripe.Customer.create(
                email=user.email,
                name=org.name,
                metadata={"org_id": org.id},
            )
        except Exception as exc:  # noqa: BLE001 - se traduce a un 400 legible
            _stripe_fail(exc)
        org.stripe_customer_id = customer.id
        db.commit()

    base = _app_base(request)
    try:
        session = stripe.checkout.Session.create(
            customer=org.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=base + "/?checkout=success&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=base + "/#precios",
            client_reference_id=org.id,
            metadata={"org_id": org.id, "plan": plan},
            # La metadata de la suscripción es la que permite resolver la
            # organización en customer.subscription.* (Stripe puede enviar ese
            # evento ANTES que checkout.session.completed).
            subscription_data={"metadata": {"org_id": org.id, "plan": plan}},
            allow_promotion_codes=True,
        )
    except Exception as exc:  # noqa: BLE001
        _stripe_fail(exc)
    return {"checkout_url": session.url, "plan": plan}


@router.get("/portal")
async def customer_portal(request: Request, db: Session = Depends(get_db)):
    """Abre el Customer Portal de Stripe para gestionar la suscripción."""
    org, _ = _get_org_from_session(request, db)
    if not org.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta organización todavía no tiene cliente en Stripe.",
        )
    _require_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=_app_base(request),
        )
    except Exception as exc:  # noqa: BLE001
        _stripe_fail(exc)
    return {"portal_url": session.url}


@router.get("/status")
async def billing_status(request: Request, db: Session = Depends(get_db)):
    """Plan actual, límites y estado de la suscripción."""
    org, user = _get_org_from_session(request, db)
    return {
        "plan": org.plan,
        "limits": get_plan_limits(org.plan),
        "email": user.email,
        "organization": {"id": org.id, "name": org.name},
        "subscription_id": org.stripe_subscription_id,
        "has_customer": bool(org.stripe_customer_id),
        "stripe_configured": bool(
            settings.STRIPE_SECRET_KEY
            and settings.STRIPE_PRICE_BASIC
            and settings.STRIPE_PRICE_PRO
        ),
    }


@router.get("/diagnose")
async def diagnose(request: Request, db: Session = Depends(get_db)):
    """Comprueba la configuración de Stripe (sin exponer claves).

    Devuelve el modo de la clave y el estado de cada precio en Stripe: si
    existe, si es recurrente y si está activo. Sirve para detectar los fallos
    típicos (price de Live pegado en Test, precio de pago único, etc.).
    """
    _get_org_from_session(request, db)

    key = (settings.STRIPE_SECRET_KEY or "").strip()
    out: Dict[str, Any] = {
        "key_mode": _key_mode(key),
        "webhook_secret": bool((settings.STRIPE_WEBHOOK_SECRET or "").strip()),
        "app_url": _app_base(request),
        "account": None,
        "prices": {},
    }
    if not key:
        return out

    stripe.api_key = key
    try:
        account = stripe.Account.retrieve()
        out["account"] = {
            "id": account.get("id"),
            "country": account.get("country"),
            "charges_enabled": account.get("charges_enabled"),
        }
    except Exception as exc:  # noqa: BLE001
        out["account_error"] = _stripe_detail(exc)

    for name, price_id in (
        ("basic", settings.STRIPE_PRICE_BASIC),
        ("pro", settings.STRIPE_PRICE_PRO),
    ):
        price_id = (price_id or "").strip()
        if not price_id:
            out["prices"][name] = {"configured": False, "ok": False}
            continue
        if price_id.startswith("prod_"):
            out["prices"][name] = {
                "configured": True,
                "id": price_id,
                "ok": False,
                "error": (
                    "Es un ID de producto (prod_...), no de precio. Abre el "
                    "producto en Stripe → Pricing y copia el price_..."
                ),
            }
            continue
        try:
            price = stripe.Price.retrieve(price_id)
            recurring = price.get("recurring") or {}
            out["prices"][name] = {
                "configured": True,
                "id": price.get("id"),
                "type": price.get("type"),
                "active": price.get("active"),
                "unit_amount": price.get("unit_amount"),
                "currency": price.get("currency"),
                "interval": recurring.get("interval"),
                "ok": price.get("type") == "recurring" and bool(price.get("active")),
            }
        except Exception as exc:  # noqa: BLE001
            out["prices"][name] = {
                "configured": True,
                "id": price_id,
                "ok": False,
                "error": _stripe_detail(exc),
            }

    return out


@router.post("/confirm")
async def confirm_checkout(
    payload: ConfirmRequest, request: Request, db: Session = Depends(get_db)
):
    """Confirma el pago consultando Stripe.

    Complementa al webhook: si el webhook tarda o no está configurado, el
    usuario ve su plan activado de inmediato al volver de Stripe.
    """
    org, _ = _get_org_from_session(request, db)
    _require_stripe()

    try:
        checkout_session = stripe.checkout.Session.retrieve(payload.session_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo recuperar la sesión de checkout")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No se pudo verificar la sesión de pago en Stripe: "
                + _stripe_detail(exc)
            ),
        )

    meta = (checkout_session.get("metadata") or {})
    if meta.get("org_id") != org.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta sesión de pago no pertenece a tu organización.",
        )

    payment_status = checkout_session.get("payment_status")
    if payment_status not in ("paid", "no_payment_required"):
        return {"status": payment_status, "plan": org.plan, "action": "pending"}

    action = service.apply_checkout_session(db, checkout_session)
    db.refresh(org)
    return {"status": "paid", "action": action, "plan": org.plan}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Endpoint del webhook de Stripe.

    - Con STRIPE_WEBHOOK_SECRET la firma es obligatoria (si no, 400).
    - Sin secreto sólo se acepta en dev; en producción se rechaza (503).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    secret = settings.STRIPE_WEBHOOK_SECRET

    if secret:
        if not sig_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falta la firma del webhook (cabecera stripe-signature).",
            )
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Firma del webhook inválida.",
            )
    else:
        # Sin secreto configurado: sólo se acepta para desarrollo local.
        # En producción (o desde cualquier IP externa) se rechaza, para que
        # nadie pueda activar planes enviando JSON sin firmar.
        client_host = request.client.host if request.client else ""
        if settings.ENV == "production" or client_host not in (
            "127.0.0.1",
            "::1",
            "localhost",
            "testclient",
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook no configurado: define STRIPE_WEBHOOK_SECRET.",
            )
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Payload JSON inválido."
            )

    result = service.handle_event(db, event)
    return {"received": True, **result}


@router.get("/success", response_class=HTMLResponse)
async def success():
    """Página de retorno tras el pago (redirige a la landing)."""
    base = (settings.APP_URL or "/").rstrip("/")
    return HTMLResponse(
        """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Suscripción activada</title>
<meta name="robots" content="noindex">
</head>
<body style="font-family:system-ui,-apple-system,sans-serif;padding:48px;text-align:center;color:#0f172a">
<h1 style="font-size:24px">Suscripción activada</h1>
<p>Tu plan se ha actualizado correctamente.</p>
<p><a href="__BASE__/" style="color:#047857;font-weight:600">Volver al inicio</a></p>
<script>window.location.replace("__BASE__/?checkout=success");</script>
</body></html>""".replace(
            "__BASE__", base
        )
    )
