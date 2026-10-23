# -*- coding: utf-8 -*-
"""
test_static_build.py
--------------------
El sitio estático de Cloudflare Pages (landing + modo navegador) se genera con
`tools/build_static.py`. Estos tests comprueban que la build es correcta y
que la API queda accesible desde el otro dominio.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from tools.build_static import build

API = "https://mi-api.onrender.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_build_genera_el_sitio_completo(tmp_path):
    out = tmp_path / "dist"
    files = build(str(out), API)

    for esperado in (
        "index.html",
        "404.html",
        "_headers",
        os.path.join("static", "rules.js"),
        os.path.join("static", "engine.js"),
        os.path.join("static", "csv.js"),
        os.path.join("static", "xlsx.js"),
        os.path.join("static", "app.js"),
        os.path.join("static", "demo.csv"),
    ):
        assert esperado in files, esperado
        assert (out / esperado).exists()


def test_build_inyecta_la_url_de_la_api(tmp_path):
    out = tmp_path / "dist"
    build(str(out), API)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<meta name="api-base" content="%s">' % API in html


def test_build_sin_api_deja_el_mismo_origen(tmp_path):
    out = tmp_path / "dist"
    build(str(out), None)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<meta name="api-base" content="">' in html


def test_build_mismo_origen_no_abre_connect_src(tmp_path):
    """Con el proxy de Pages no hace falta permitir otro origen en la CSP."""
    out = tmp_path / "dist"
    build(str(out), None)
    headers = (out / "_headers").read_text(encoding="utf-8")
    assert "connect-src 'self';" in headers


def test_el_proxy_de_pages_reenvia_las_rutas_de_la_api():
    """
    `functions/_middleware.js` convierte las llamadas a la API en same-origin.

    Sin él la cookie de sesión es de terceros (pages.dev -> onrender.com) y
    Safari/Chrome la descartan: el login responde 200 pero la sesión se
    pierde y el formulario vuelve a aparecer.
    """
    middleware = os.path.join(ROOT, "functions", "_middleware.js")
    assert os.path.exists(middleware), "falta functions/_middleware.js"
    with open(middleware, encoding="utf-8") as fh:
        source = fh.read()

    for prefijo in ("/api/", "/auth/", "/billing/"):
        assert prefijo in source, prefijo
    assert "onrender.com" in source
    assert "set-cookie" in source.lower()
    assert "API_ORIGIN" in source


def test_el_readme_documenta_el_proxy() -> None:  # pragma: no cover - doc
    readme = os.path.join(ROOT, "README.md")
    with open(readme, encoding="utf-8") as fh:
        source = fh.read()
    assert "_middleware.js" in source or "proxy" in source.lower()


def test_build_genera_pagina_404(tmp_path):
    """Cloudflare Pages necesita 404.html si not_found_handling=404-page."""
    out = tmp_path / "dist"
    build(str(out), API)
    html = (out / "404.html").read_text(encoding="utf-8")
    assert "404" in html
    assert 'href="/"' in html
    assert 'name="robots" content="noindex"' in html
    # Sin recursos externos: debe funcionar con la CSP (default-src 'self')
    assert "http://" not in html and "https://" not in html


def test_build_rechaza_urls_invalidas(tmp_path):
    with pytest.raises(ValueError):
        build(str(tmp_path / "dist"), "mi-api.onrender.com")
    with pytest.raises(ValueError):
        build(str(tmp_path / "dist"), "javascript:alert(1)")


def test_headers_permiten_la_api_en_connect_src(tmp_path):
    out = tmp_path / "dist"
    build(str(out), API)
    headers = (out / "_headers").read_text(encoding="utf-8")
    assert "connect-src 'self' %s" % API in headers
    assert "X-Content-Type-Options: nosniff" in headers
    assert "frame-ancestors 'none'" in headers


def test_la_landing_solo_referencia_ficheros_existentes(tmp_path):
    out = tmp_path / "dist"
    build(str(out), API)
    html = (out / "index.html").read_text(encoding="utf-8")
    refs = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', html))
    assert refs, "la landing debería referenciar estáticos"
    for ref in refs:
        assert (out / ref.lstrip("/")).exists(), ref


def test_el_javascript_usa_la_url_de_la_api_configurable():
    """app.js debe leer la API del meta y no hardcodear el mismo origen."""
    app_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "static",
        "app.js",
    )
    with open(app_js, encoding="utf-8") as fh:
        source = fh.read()
    assert "meta[name=\"api-base\"]" in source
    assert "API_BASE + '/api/clean'" in source
    # No debe haber un fetch hardcodeado al mismo origen para la API
    assert "fetch('/api/clean'" not in source


def test_ninguna_ruta_de_la_api_apunta_al_origen_de_la_landing():
    """
    Todas las rutas de la API deben pasar por API_BASE. Si alguna se quedara
    como '/api/...' relativo, en Cloudflare Pages apuntaría al dominio de la
    landing (404) en vez de a la API de Render.
    """
    app_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "static",
        "app.js",
    )
    with open(app_js, encoding="utf-8") as fh:
        source = fh.read()

    # Rutas de la API que aparecen en el código (fetch y enlaces de descarga)
    rutas = re.findall(r"['\"](/api/[^'\"]*)['\"]", source)
    assert rutas, "debería haber rutas de la API en app.js"
    for ruta in rutas:
        # Cada uso debe ir precedido de API_BASE +
        assert "API_BASE + '%s'" % ruta in source, ruta


def test_los_enlaces_del_pie_apuntan_a_la_api():
    """Los enlaces /docs y /health del pie se corrigen en JS con API_BASE."""
    app_js = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "static",
        "app.js",
    )
    with open(app_js, encoding="utf-8") as fh:
        source = fh.read()
    assert "linkDocs.href = API_BASE + '/docs'" in source
    assert "linkHealth.href = API_BASE + '/health'" in source

    html = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "templates",
        "index.html",
    )
    with open(html, encoding="utf-8") as fh:
        template = fh.read()
    assert 'id="link-api-docs"' in template
    assert 'id="link-api-health"' in template


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(
    "meta,esperado",
    [
        ("", ""),
        ("https://api.example.com", "https://api.example.com"),
        ("https://api.example.com/", "https://api.example.com"),
        ("https://api.example.com/", "https://api.example.com"),
        ("  https://api.example.com  ", "https://api.example.com"),
    ],
)
def test_app_js_resuelve_la_url_de_la_api(meta, esperado):
    """app.js lee el <meta name="api-base"> y normaliza la barra final."""
    harness = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "js_app_harness.js"
    )
    proc = subprocess.run(
        [shutil.which("node"), harness, meta],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["apiBase"] == esperado
