# -*- coding: utf-8 -*-
"""
build_static.py
---------------
Genera el **sitio estático** para Cloudflare Pages: la landing + el modo
navegador, que no necesitan servidor (todo el procesado ocurre en el
cliente). La API Python se despliega aparte (Render) y su URL se inyecta
en la página.

    python -m tools.build_static --api-base https://mi-api.onrender.com --out dist

Salida:

    dist/index.html      landing con la URL de la API inyectada
    dist/static/...      rules.js, engine.js, csv.js, xlsx.js, app.js, demo.csv
    dist/_headers        cabeceras de seguridad (CSP que permite la API)

Notas:
- Cloudflare Pages usa "None" como framework preset y este comando como
  build command; el directorio de salida es `dist`.
- Si no se pasa `--api-base`, la landing se sirve en el mismo origen que la
  API (despliegue monolítico en Render, sin Cloudflare).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from typing import List, Optional

from app.security import content_security_policy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "app", "templates", "index.html")
STATIC_SRC = os.path.join(ROOT, "app", "static")

# Cabeceras de seguridad para Cloudflare Pages (formato del fichero _headers)
_HEADERS_TEMPLATE = """\
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  Content-Security-Policy: {csp}
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Cross-Origin-Resource-Policy: same-origin
"""


def _normalize_api_base(api_base: Optional[str]) -> str:
    """Quita la barra final y valida que sea http(s)."""
    base = (api_base or "").strip()
    if not base:
        return ""
    base = base.rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError(
            "La URL de la API debe empezar por http:// o https:// (recibido: %r)" % base
        )
    return base


def build(out_dir: str, api_base: Optional[str] = None) -> List[str]:
    """
    Construye el sitio estático y devuelve la lista de ficheros generados.
    """
    base = _normalize_api_base(api_base)
    out = os.path.abspath(out_dir)

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "static"), exist_ok=True)

    # 1. Estáticos del cliente
    for name in sorted(os.listdir(STATIC_SRC)):
        src = os.path.join(STATIC_SRC, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out, "static", name))

    # 2. Landing con la URL de la API inyectada
    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()

    def _replace_meta(match):
        return '%scontent="%s"' % (match.group(1), base)

    html, n = re.subn(
        r'(<meta\s+name="api-base"\s+)content="[^"]*"',
        _replace_meta,
        html,
        count=1,
    )
    if n != 1:
        raise RuntimeError(
            "No se encontró la etiqueta <meta name=\"api-base\"> en index.html"
        )

    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)

    # 3. Cabeceras de seguridad (con la API permitida en connect-src)
    connect = base if base else ""
    with open(os.path.join(out, "_headers"), "w", encoding="utf-8") as fh:
        fh.write(_HEADERS_TEMPLATE.format(csp=content_security_policy(connect)))

    generated = []
    for dirpath, _dirnames, filenames in os.walk(out):
        for name in filenames:
            generated.append(
                os.path.relpath(os.path.join(dirpath, name), out)
            )
    return sorted(generated)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el sitio estático para Cloudflare Pages")
    parser.add_argument(
        "--api-base",
        default=os.environ.get("API_BASE", ""),
        help="URL base de la API (ej. https://mi-api.onrender.com). Vacío = mismo origen.",
    )
    parser.add_argument("--out", default="dist", help="Directorio de salida (por defecto: dist)")
    args = parser.parse_args(argv)

    files = build(args.out, args.api_base)
    print("Sitio estático generado en %s (%d ficheros)" % (os.path.abspath(args.out), len(files)))
    for name in files:
        print("  -", name)
    if args.api_base:
        print("API base: %s" % args.api_base)
    else:
        print("API base: (mismo origen)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
