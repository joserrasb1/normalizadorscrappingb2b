# -*- coding: utf-8 -*-
"""
app/billing/service.py
----------------------
Lógica de negocio del billing con Stripe, separada de la capa HTTP para
poder testearla sin tocar la red.

Responsabilidades:
  * Mapear un price ID de Stripe -> plan interno (free/basic/pro).
  * Resolver la organización a partir de un objeto de Stripe (suscripción,
    sesión de checkout o cliente).
  * Aplicar el estado de la suscripción al plan de la organización.
  * Procesar los eventos de webhook de forma idempotente.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models

# Planes de pago (los que se pueden contratar).
PAID_PLANS = ("basic", "pro")

# Estados de suscripción en los que la organización MANTIENE el plan pagado.
# "past_due" entra aquí: Stripe reintenta el cobro durante unos días y no
# queremos quitar el acceso mientras la suscripción sigue viva.
ACTIVE_SUB_STATUSES = {"active", "trialing", "past_due"}

# Estados en los que el plan vuelve a "free".
FREE_SUB_STATUSES = {
    "canceled",
    "unpaid",
    "incomplete",
    "incomplete_expired",
    "paused",
}


# --------------------------------------------------------------------------
# Mapeo price <-> plan
# --------------------------------------------------------------------------
def plan_for_price(price_id: Optional[str]) -> Optional[str]:
    """Plan interno asociado a un price ID de Stripe (None si no coincide)."""
    if not price_id:
        return None
    if settings.STRIPE_PRICE_BASIC and price_id == settings.STRIPE_PRICE_BASIC:
        return "basic"
    if settings.STRIPE_PRICE_PRO and price_id == settings.STRIPE_PRICE_PRO:
        return "pro"
    return None


def price_for_plan(plan: Optional[str]) -> Optional[str]:
    """Price ID de Stripe asociado a un plan interno."""
    plan = (plan or "").strip().lower()
    if plan == "basic":
        return settings.STRIPE_PRICE_BASIC or None
    if plan == "pro":
        return settings.STRIPE_PRICE_PRO or None
    return None


def subscription_price_id(sub: Dict[str, Any]) -> Optional[str]:
    """Price ID del primer item de una suscripción."""
    items = (sub.get("items") or {}).get("data") or []
    for item in items:
        price = item.get("price") or {}
        if price.get("id"):
            return price["id"]
    return None


def subscription_plan(sub: Dict[str, Any]) -> Optional[str]:
    """Plan que corresponde a una suscripción.

    El price ID manda (es la fuente de verdad de lo que se ha pagado); la
    metadata es sólo el respaldo para suscripciones antiguas.
    """
    price_plan = plan_for_price(subscription_price_id(sub))
    if price_plan:
        return price_plan
    meta_plan = (sub.get("metadata") or {}).get("plan")
    if meta_plan in PAID_PLANS:
        return meta_plan
    return None


# --------------------------------------------------------------------------
# Resolución de la organización
# --------------------------------------------------------------------------
def find_org(
    db: Session,
    org_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
) -> Optional[models.Organization]:
    """Localiza la organización a partir de los identificadores de Stripe."""
    query = db.query(models.Organization)
    if org_id:
        org = query.filter(models.Organization.id == org_id).first()
        if org:
            return org
    if subscription_id:
        org = query.filter(
            models.Organization.stripe_subscription_id == subscription_id
        ).first()
        if org:
            return org
    if customer_id:
        org = query.filter(
            models.Organization.stripe_customer_id == customer_id
        ).first()
        if org:
            return org
    return None


# --------------------------------------------------------------------------
# Aplicación del estado de Stripe sobre la organización
# --------------------------------------------------------------------------
def apply_subscription(db: Session, org: models.Organization, sub: Dict[str, Any]) -> str:
    """Aplica el estado de una suscripción al plan de la organización.

    Devuelve la acción realizada: activated / downgraded / kept / no_org.
    """
    sub_status = (sub.get("status") or "").strip().lower()
    sub_id = sub.get("id")
    customer_id = sub.get("customer")

    if sub_id:
        org.stripe_subscription_id = sub_id
    if customer_id:
        org.stripe_customer_id = customer_id

    if sub_status in ACTIVE_SUB_STATUSES:
        plan = subscription_plan(sub)
        if plan:
            org.plan = plan
            action = "activated"
        else:
            # Suscripción activa pero con un price que no conocemos: no
            # tocamos el plan (podría ser un plan a medida).
            action = "kept"
    elif sub_status in FREE_SUB_STATUSES:
        if org.plan != "free":
            org.plan = "free"
            action = "downgraded"
        else:
            action = "kept"
    else:
        action = "kept"

    db.commit()
    return action


def apply_subscription_event(db: Session, sub: Dict[str, Any]) -> str:
    """Procesa un evento customer.subscription.* (created/updated/deleted)."""
    meta = sub.get("metadata") or {}
    org = find_org(
        db,
        org_id=meta.get("org_id"),
        customer_id=sub.get("customer"),
        subscription_id=sub.get("id"),
    )
    if not org:
        return "no_org"
    return apply_subscription(db, org, sub)


def apply_checkout_session(db: Session, session: Dict[str, Any]) -> str:
    """Procesa checkout.session.completed: activa el plan y guarda IDs."""
    meta = session.get("metadata") or {}
    org = find_org(db, org_id=meta.get("org_id"))
    if not org:
        return "no_org"

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    if customer_id:
        org.stripe_customer_id = customer_id
    if subscription_id:
        org.stripe_subscription_id = subscription_id

    plan = (meta.get("plan") or "").strip().lower()
    if plan in PAID_PLANS:
        org.plan = plan
        action = "activated"
    else:
        action = "kept"

    db.commit()
    return action


# --------------------------------------------------------------------------
# Idempotencia
# --------------------------------------------------------------------------
def event_already_processed(db: Session, event_id: Optional[str]) -> bool:
    if not event_id:
        return False
    exists = (
        db.query(models.StripeEvent)
        .filter(models.StripeEvent.event_id == event_id)
        .first()
    )
    return exists is not None


def mark_event_processed(db: Session, event_id: Optional[str], event_type: Optional[str]) -> None:
    """Registra el evento como procesado (idempotencia ante reenvíos)."""
    if not event_id:
        return
    db.add(models.StripeEvent(event_id=event_id, event_type=event_type or ""))
    try:
        db.commit()
    except IntegrityError:
        # Otro worker lo procesó primero: no es un error.
        db.rollback()


# --------------------------------------------------------------------------
# Dispatcher de eventos
# --------------------------------------------------------------------------
def handle_event(db: Session, event: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica un evento de Stripe. Idempotente."""
    event_id = event.get("id")
    event_type = event.get("type") or ""

    if event_already_processed(db, event_id):
        return {
            "status": "duplicate",
            "event_id": event_id,
            "type": event_type,
        }

    obj = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        action = apply_checkout_session(db, obj)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        action = apply_subscription_event(db, obj)
    elif event_type == "invoice.paid":
        action = "invoice_paid"
    elif event_type == "invoice.payment_failed":
        # No degradamos aquí: la suscripción sigue viva y Stripe reintenta
        # el cobro. El downgrade llega con customer.subscription.updated.
        action = "payment_failed"
    else:
        action = "ignored"

    mark_event_processed(db, event_id, event_type)

    return {
        "status": "ok",
        "action": action,
        "event_id": event_id,
        "type": event_type,
    }
