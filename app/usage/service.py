# -*- coding: utf-8 -*-
"""
app/usage/service.py
-------------------
Control de cuotas server-side para usuarios autenticados y anónimos.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.limits import get_plan_limits, ANON_FREE_TRIALS, ANON_MAX_ROWS
from app.core.cookies import session_cookie_kwargs
from app.db import models


ANON_COOKIE = "dcb_anon_usage"


def _period_bounds(now: datetime | None = None) -> Tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _usage_limit_for_plan(plan: str | None, limits: dict) -> int:
    """El plan Free se mide en documentos (usos); los de pago, en filas."""
    if (plan or "free").lower() == "free":
        return int(limits.get("uses_month") or ANON_FREE_TRIALS)
    return int(limits["rows_month"])


def get_or_create_usage(db: Session, org: models.Organization) -> models.Usage:
    start, end = _period_bounds()
    usage = (
        db.query(models.Usage)
        .filter(
            models.Usage.organization_id == org.id,
            models.Usage.period_start == start,
        )
        .first()
    )
    if usage:
        return usage

    limits = get_plan_limits(org.plan)
    usage = models.Usage(
        organization_id=org.id,
        period_start=start,
        period_end=end,
        rows_used=0,
        rows_limit=_usage_limit_for_plan(org.plan, limits),
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def sync_usage_limit(db: Session, org: models.Organization) -> models.Usage:
    """Devuelve el usage del periodo y lo sincroniza con el plan actual.

    Si el tipo de cuota cambia (filas -> documentos en el plan Free), se
    reinicia el consumo del periodo para que la prueba gratuita sea real.
    """
    usage = get_or_create_usage(db, org)
    limits = get_plan_limits(org.plan)
    target_limit = _usage_limit_for_plan(org.plan, limits)
    if usage.rows_limit != target_limit:
        usage.rows_limit = target_limit
        if (org.plan or "free").lower() == "free":
            usage.rows_used = 0
        db.commit()
        db.refresh(usage)
    return usage


def check_quota(db: Session, org: models.Organization, rows_to_add: int) -> models.Usage:
    usage = sync_usage_limit(db, org)

    if usage.rows_used + rows_to_add > usage.rows_limit:
        if (org.plan or "free").lower() == "free":
            message = (
                f"Has agotado tus {usage.rows_limit} pruebas gratis. "
                "Elige un plan para seguir limpiando listas."
            )
        else:
            message = f"Has alcanzado el límite de {usage.rows_limit:,} filas este mes."
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "quota_exceeded",
                "message": message,
                "plan": org.plan,
                "used": usage.rows_used,
                "limit": usage.rows_limit,
                "upgrade_to": "basic" if org.plan == "free" else "pro",
            },
        )
    return usage


def consume_quota(db: Session, org: models.Organization, rows_to_add: int) -> models.Usage:
    usage = check_quota(db, org, rows_to_add)
    # Incremento atómico por transacción
    usage.rows_used += rows_to_add
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


# --- Anónimos ---
def get_anon_usage_count(request) -> int:
    raw = request.cookies.get(ANON_COOKIE)
    if not raw:
        return 0
    try:
        data = json.loads(raw)
        return int(data.get("count", 0))
    except Exception:
        return 0


def check_anon_quota(request, rows_to_add: int):
    count = get_anon_usage_count(request)
    if count >= ANON_FREE_TRIALS:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "anon_quota_exceeded",
                "message": f"Has agotado tus {ANON_FREE_TRIALS} pruebas gratis. Regístrate o elige un plan.",
                "limit": ANON_FREE_TRIALS,
                "used": count,
            },
        )
    if rows_to_add > ANON_MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "anon_rows_exceeded",
                "message": (
                    f"Un uso anónimo admite hasta {ANON_MAX_ROWS:,} filas. "
                    "Crea una cuenta para procesar listas más grandes."
                ),
                "limit": ANON_MAX_ROWS,
                "used": rows_to_add,
            },
        )


def set_anon_usage_cookie(response, request):
    count = get_anon_usage_count(request) + 1
    response.set_cookie(
        key=ANON_COOKIE,
        value=json.dumps({"count": count}),
        max_age=60 * 60 * 24 * 365,
        **session_cookie_kwargs(),
    )
    return response
