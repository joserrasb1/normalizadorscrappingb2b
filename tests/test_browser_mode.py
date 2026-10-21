# -*- coding: utf-8 -*-
"""
test_browser_mode.py
--------------------
El modo "100 % en el navegador" (app/static/*.js) y el modo "servidor"
(app/*.py) deben producir exactamente el mismo resultado para el mismo
fichero. Este test ejecuta el flujo real del navegador (parseo -> deteccion
-> normalizacion -> exportacion) con Node y lo compara con el pipeline de
Python.

Si Node no está instalado, el test se salta (en CI debe estar disponible).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.engine import normalize_table
from app.normalizers import Options
from app.tabular import read_table

ROOT = Path(__file__).resolve().parent.parent
BROWSER_HARNESS = ROOT / "tests" / "js_browser_harness.js"
DEMO_CSV = ROOT / "app" / "static" / "demo.csv"

NODE = shutil.which("node")

# Mismas opciones que usa la UI por defecto (app/static/app.js)
BROWSER_OPTIONS = {
    "removeLegal": True,
    "removeGeo": True,
    "removeArticles": True,
    "titleCase": True,
    "fixEmailTypos": True,
    "gmailDots": False,
    "stripPlusTags": False,
    "phoneFormat": "auto",
    "defaultCountryCode": "34",
}


def _run_browser_harness(path: Path, options: dict | None = None, tmp_path: Path | None = None):
    cmd = [NODE, str(BROWSER_HARNESS), str(path)]
    if options:
        assert tmp_path is not None, "hace falta tmp_path para escribir las opciones"
        opts_file = tmp_path / "options.json"
        opts_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
        cmd.append(str(opts_file))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_modo_navegador_y_servidor_coinciden(tmp_path):
    """El demo debe limpiarse igual en el navegador y en el servidor."""
    js = _run_browser_harness(DEMO_CSV)

    data = DEMO_CSV.read_bytes()
    headers, rows, meta = read_table(data, "demo.csv")
    py = normalize_table(headers, rows, Options())

    # --- Cabeceras y filas leidas ---
    assert js["headers"] == headers, (js["headers"], headers)
    assert js["rows"] == rows, (js["rows"], rows)
    assert js["delimiter"] == meta["delimiter"]

    # --- Deteccion de columnas ---
    assert len(js["columns"]) == len(py.columns)
    for js_col, py_col in zip(js["columns"], py.columns):
        assert js_col["name"] == py_col["name"]
        assert js_col["type"] == py_col["applied_type"], (js_col, py_col)
        assert js_col["confidence"] == py_col["confidence"], (js_col, py_col)

    # --- Resultado de la normalizacion ---
    assert js["out_rows"] == py.rows, (js["out_rows"], py.rows)

    # --- Estadisticas ---
    for key in (
        "total_rows",
        "total_columns",
        "cells_processed",
        "cells_changed",
        "cells_empty",
        "by_rule",
        "by_column",
        "percent_changed",
    ):
        assert js["stats"][key] == py.stats[key], (key, js["stats"][key], py.stats[key])


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_modo_navegador_respeta_las_opciones(tmp_path):
    """Las opciones de la UI deben tener el mismo efecto en ambos motores."""
    options = dict(BROWSER_OPTIONS)
    options["removeLegal"] = False
    options["titleCase"] = False
    options["gmailDots"] = True

    js = _run_browser_harness(DEMO_CSV, options, tmp_path)

    headers, rows, _ = read_table(DEMO_CSV.read_bytes(), "demo.csv")
    py = normalize_table(headers, rows, Options.from_dict(
        {
            "remove_legal": False,
            "remove_geo": True,
            "remove_articles": True,
            "title_case": False,
            "fix_email_typos": True,
            "gmail_dots": True,
            "strip_plus_tags": False,
            "phone_format": "auto",
            "default_country_code": "34",
        }
    ))

    assert js["out_rows"] == py.rows
    assert js["stats"]["percent_changed"] == py.stats["percent_changed"]
    # Sin quitar la forma jurídica, "ACME SERVICES EUROPE SL" no se toca
    assert js["out_rows"][0][0] == "ACME SERVICES EUROPE SL"


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_exportacion_csv_del_navegador_es_valida(tmp_path):
    """El CSV que genera el navegador se puede releer con el parser de Python."""
    from app.tabular import parse_csv_text

    js = _run_browser_harness(DEMO_CSV)
    py_headers, py_rows, _ = parse_csv_text(js["csv"])

    assert py_headers == js["headers"]
    assert py_rows == js["out_rows"]
