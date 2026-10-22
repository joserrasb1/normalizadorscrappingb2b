# -*- coding: utf-8 -*-
"""
app/core/limits.py
------------------
Límites por plan para Data Cleaner B2B
"""

from __future__ import annotations

PLAN_LIMITS = {
    # Free: registro sin tarjeta. deliberately por debajo de Basic para que
    # contratar el plan Basic aporte algo (10x de filas, 2x de tamaño y
    # 4x de histórico).
    "free": {
        "rows_month": 1000,
        "max_mb": 5,
        "max_users": 1,
        "history_days": 7,
        "api_keys": 0,
        "shared_profiles": False,
        "priority_support": False,
    },
    "basic": {
        "rows_month": 10000,
        "max_mb": 10,
        "max_users": 1,
        "history_days": 30,
        "api_keys": 0,
        "shared_profiles": False,
        "priority_support": False,
    },
    "pro": {
        "rows_month": 100000,
        "max_mb": 50,
        "max_users": 5,
        "history_days": 365,
        "api_keys": 10,
        "shared_profiles": True,
        "priority_support": True,
    },
}

# Pruebas anónimas sin registro (UX actual)
ANON_FREE_TRIALS = 10
ANON_MAX_MB = 10
# Filas máximas por uso anónimo: evita que un fichero enorme agote la
# instancia gratuita de Render con una sola llamada.
ANON_MAX_ROWS = 1000

# Conversión
MB_TO_BYTES = 1024 * 1024


def get_plan_limits(plan: str | None):
    if not plan:
        return PLAN_LIMITS["free"]
    plan = plan.lower()
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def max_bytes_for_plan(plan: str | None) -> int:
    limits = get_plan_limits(plan)
    return int(limits["max_mb"] * MB_TO_BYTES)
