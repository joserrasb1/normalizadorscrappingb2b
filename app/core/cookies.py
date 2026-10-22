# -*- coding: utf-8 -*-
"""
app/core/cookies.py
-------------------
Política de cookies (sesión y cuota anónima) centralizada.

La landing se sirve desde Cloudflare Pages y la API desde Render: son
dominios distintos, así que la cookie de sesión sólo viaja si se marca
SameSite=None + Secure. En local (http://localhost) eso no funciona, por
eso la política es configurable por entorno:

    SESSION_COOKIE_SAMESITE=lax     # mismo dominio (por defecto)
    SESSION_COOKIE_SAMESITE=none    # landing y API en dominios distintos
    SESSION_COOKIE_SECURE=true      # obligatorio si SAMEITE=none
"""

from __future__ import annotations

from typing import Any, Dict

from app.core.config import settings

VALID_SAMESITE = ("lax", "strict", "none")


def session_cookie_kwargs() -> Dict[str, Any]:
    """Argumentos comunes para set_cookie de sesión y de cuota anónima."""
    samesite = (settings.SESSION_COOKIE_SAMESITE or "").strip().lower()
    if not samesite:
        # Automático: la landing y la API comparten dominio => lax (más seguro).
        # Dominios distintos (pages.dev -> onrender.com) => none es obligatorio.
        samesite = "none" if settings.ENV == "production" else "lax"
    if samesite not in VALID_SAMESITE:
        samesite = "lax"

    secure = bool(settings.SESSION_COOKIE_SECURE) or settings.ENV == "production"
    if samesite == "none":
        # Los navegadores exigen Secure para SameSite=None.
        secure = True

    return {
        "httponly": True,
        "secure": secure,
        "samesite": samesite,
        "path": "/",
    }


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE,
        **session_cookie_kwargs(),
    )


def delete_session_cookie(response) -> None:
    kwargs = session_cookie_kwargs()
    kwargs.pop("httponly", None)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, **kwargs)
