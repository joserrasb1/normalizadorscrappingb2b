# -*- coding: utf-8 -*-
"""
app/billing/router.py
---------------------
Checkout, Customer Portal y Webhooks de Stripe
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import stripe

from app.core.config import settings
from app.db.session import get_db
from app.db import models
from app.auth.session import verify_session_token

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.STRIPE_SECRET_KEY


def _get_org_from_session(request: Request, db: Session):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    member = db.query(models.OrganizationMember).filter(models.OrganizationMember.user_id == user.id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sin organización")
    org = db.query(models.Organization).filter(models.Organization.id == member.organization_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    return org, user


@router.post("/checkout/{plan}")
async def create_checkout(plan: str, request: Request, db: Session = Depends(get_db)):
    org, user = _get_org_from_session(request, db)
    plan = plan.lower()
    if plan not in ("basic", "pro"):
        raise HTTPException(status_code=400, detail="Plan inválido")
    
    price_id = settings.STRIPE_PRICE_BASIC if plan == "basic" else settings.STRIPE_PRICE_PRO
    if not price_id or not stripe.api_key:
        raise HTTPException(status_code=400, detail="Stripe no configurado. Añade STRIPE_SECRET_KEY y STRIPE_PRICE_* en el entorno.")
    
    if not org.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, name=org.name)
        org.stripe_customer_id = customer.id
        db.commit()
    
    session = stripe.checkout.Session.create(
        customer=org.stripe_customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=str(request.base_url) + "billing/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=str(request.base_url) + "#precios",
        metadata={"org_id": org.id, "plan": plan},
    )
    return {"checkout_url": session.url}


@router.get("/portal")
async def customer_portal(request: Request, db: Session = Depends(get_db)):
    org, _ = _get_org_from_session(request, db)
    if not org.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Sin suscripción activa")
    session = stripe.billing_portal.Session.create(
        customer=org.stripe_customer_id,
        return_url=str(request.base_url),
    )
    return {"portal_url": session.url}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if settings.STRIPE_WEBHOOK_SECRET and sig_header:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Webhook inválido: {e}")
    else:
        # En dev sin firma
        import json
        event = json.loads(payload)
    
    event_type = event.get("type")
    
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        org_id = session.get("metadata", {}).get("org_id")
        plan = session.get("metadata", {}).get("plan")
        sub_id = session.get("subscription")
        if org_id and plan:
            org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
            if org:
                org.plan = plan
                org.stripe_subscription_id = sub_id
                db.commit()
    
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        sub_id = sub.get("id")
        status = sub.get("status")
        org = db.query(models.Organization).filter(models.Organization.stripe_subscription_id == sub_id).first()
        if org:
            if status == "canceled" or event_type == "customer.subscription.deleted":
                org.plan = "free"
            else:
                # Mantener plan según metadata o inferir
                pass
            db.commit()
    
    return {"received": True}


@router.get("/success")
async def success():
    return HTMLResponse("""
    <html><head><title>Suscripción activada</title></head>
    <body style="font-family:system-ui;padding:40px;text-align:center">
        <h1>¡Suscripción activada!</h1>
        <p>Tu plan se ha actualizado correctamente.</p>
        <a href="/">Volver al inicio</a>
    </body></html>
    """)
