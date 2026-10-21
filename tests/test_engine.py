# -*- coding: utf-8 -*-
"""
test_engine.py
--------------
Tests del orquestador: normalización de una tabla completa, estadísticas
y respecto de los tipos de columna forzados por el usuario.
"""

from __future__ import annotations

from app.engine import normalize_table
from app.normalizers import Options


def test_normaliza_tabla_completa():
    headers = ["Empresa", "Email"]
    rows = [
        ["ACME Services Europe, S.L.U.", "JUAN@ACME.COM"],
        ["Globex Inc.", "pedro@globex.com"],
    ]
    res = normalize_table(headers, rows, Options())
    assert res.rows[0][0] == "ACME Services"
    assert res.rows[0][1] == "juan@acme.com"
    assert res.stats["total_rows"] == 2
    assert res.stats["cells_changed"] == 3
    assert res.stats["cells_processed"] == 4


def test_tipo_forzado_manda():
    headers = ["col"]
    rows = [["ACME Services Europe, S.L.U."]]
    res = normalize_table(headers, rows, Options(), column_types={0: "company"})
    assert res.rows[0][0] == "ACME Services"
    assert res.columns[0]["forced"] is True


def test_columna_ignore_no_se_toca():
    headers = ["Empresa", "Notas"]
    rows = [["ACME Services Europe, S.L.U.", "ACME Services Europe, S.L.U."]]
    res = normalize_table(headers, rows, Options(), column_types={1: "ignore"})
    assert res.rows[0][1] == "ACME Services Europe, S.L.U."
    assert res.stats["cells_changed"] == 1


def test_celdas_vacias_no_cuentan():
    headers = ["Empresa"]
    rows = [["Acme"], [""], ["   "]]
    res = normalize_table(headers, rows, Options())
    assert res.stats["cells_processed"] == 1
    assert res.stats["cells_empty"] == 2


def test_estadisticas_por_regla():
    headers = ["Empresa"]
    rows = [["ACME Services Europe, S.L.U."], ["ACME Services Europe, S.L.U."]]
    res = normalize_table(headers, rows, Options())
    assert res.stats["by_rule"]["legal_suffix"] == 2
    assert res.stats["by_rule"]["geo_suffix"] == 2
    assert res.stats["by_column"]["Empresa"] == 2


def test_porcentaje_cambiado():
    headers = ["Empresa", "Email"]
    rows = [["Acme SL", "a@b.com"]]
    res = normalize_table(headers, rows, Options())
    assert res.stats["percent_changed"] == 50.0


def test_cambios_registran_fila():
    headers = ["Empresa"]
    rows = [["Acme SL"], ["Globex Inc."]]
    res = normalize_table(headers, rows, Options())
    filas = sorted({c["row"] for c in res.changes})
    assert filas == [2, 3]


def test_preview_rows_limita_el_calculo():
    headers = ["Empresa"]
    rows = [["Acme SL"]] * 10
    res = normalize_table(headers, rows, Options(), preview_rows=2)
    assert res.stats["cells_processed"] == 2
    assert len(res.rows) == 10


def test_max_changes():
    headers = ["Empresa"]
    rows = [["Acme SL"]] * 50
    res = normalize_table(headers, rows, Options(), max_changes=5)
    assert len(res.changes) == 5


def test_columnas_detectadas_incluidas():
    headers = ["Email"]
    rows = [["a@b.com"]]
    res = normalize_table(headers, rows, Options())
    assert res.columns[0]["applied_type"] == "email"
    assert res.columns[0]["label"] == "Email"
