# -*- coding: utf-8 -*-
"""
test_xlsx_writer.py
-------------------
El exportador XLSX del navegador (app/static/xlsx.js) no usa ninguna librería
externa: genera el ZIP con XML a mano. Estos tests comprueban que el fichero
que produce es un XLSX válido (se abre con openpyxl, como haría el usuario).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js_xlsx_harness.js"

NODE = shutil.which("node")


def _write_xlsx(tmp_path, headers, rows, sheet_name="Datos limpios"):
    payload = {"headers": headers, "rows": rows, "sheet_name": sheet_name}
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    out_file = tmp_path / "out.xlsx"
    proc = subprocess.run(
        [NODE, str(HARNESS), str(payload_file), str(out_file)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return out_file


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_xlsx_generado_es_valido(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    headers = ["Empresa", "Email", "Teléfono"]
    rows = [
        ["ACME Services", "a@b.com", "+34 911 234 567"],
        ["Globex Inc.", "c@d.es", "612 345 678"],
    ]
    path = _write_xlsx(tmp_path, headers, rows)

    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Datos limpios"]
    ws = wb.active
    assert ws.max_row == 3
    assert ws.max_column == 3
    data = list(ws.iter_rows(values_only=True))
    assert data[0] == ("Empresa", "Email", "Teléfono")
    assert data[1] == ("ACME Services", "a@b.com", "+34 911 234 567")
    assert data[2] == ("Globex Inc.", "c@d.es", "612 345 678")


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_xlsx_protege_formulas_y_conserva_telefonos(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    headers = ["Empresa", "Teléfono"]
    rows = [
        ["=CMD|calc", "+34 911 234 567"],
        ["ACME", "612 345 678"],
    ]
    path = _write_xlsx(tmp_path, headers, rows)
    wb = openpyxl.load_workbook(path)
    data = list(wb.active.iter_rows(values_only=True))
    # La fórmula queda neutralizada con el apóstrofo...
    assert data[1][0] == "'=CMD|calc"
    # ...pero el teléfono se mantiene intacto
    assert data[1][1] == "+34 911 234 567"
    assert data[2][1] == "612 345 678"


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_xlsx_acepta_acentos_y_saltos_de_linea(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")

    headers = ["Empresa", "Notas"]
    rows = [["Müller & Cía.", "Línea 1\nLínea 2"], ["Ñandú, S.L.", ""]]
    path = _write_xlsx(tmp_path, headers, rows)
    wb = openpyxl.load_workbook(path)
    data = list(wb.active.iter_rows(values_only=True))
    assert data[1][0] == "Müller & Cía."
    assert data[1][1] == "Línea 1\nLínea 2"
    assert data[2][0] == "Ñandú, S.L."
    assert data[2][1] in ("", None)
