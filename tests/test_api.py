# -*- coding: utf-8 -*-
"""
test_api.py
-----------
Tests end-to-end de la API: subida, normalización, descargas y controles
de seguridad.
"""

from __future__ import annotations

import io
import json

CSV_SUCIO = (
    "Nombre,Email,Telefono,Cargo\n"
    '"ACME Services Europe, S.L.U.",JUAN@ACME.COM,612345678,GERENTE DE VENTAS\n'
    "Globex Inc.,pedro@globex.com,911234567,Chief Financial Officer\n"
)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_serve_landing(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Data Cleaner" in r.text


def test_detect(client):
    r = client.post("/api/detect", files={"file": ("prospectos.csv", CSV_SUCIO.encode("utf-8"), "text/csv")})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["headers"][0] == "Nombre"
    assert len(data["columns"]) == 4


def test_clean_normaliza(client):
    r = client.post("/api/clean", files={"file": ("prospectos.csv", CSV_SUCIO.encode("utf-8"), "text/csv")})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["total_rows"] == 2
    filas = data["rows_preview"]
    assert filas[0]["Nombre"] == "ACME Services"
    assert filas[0]["Email"] == "juan@acme.com"
    assert filas[0]["Cargo"] == "Gerente de Ventas"
    assert data["stats"]["cells_changed"] >= 3


def test_clean_respeta_tipos_forzados(client):
    tipos = json.dumps({"0": "ignore"})
    r = client.post(
        "/api/clean",
        files={"file": ("prospectos.csv", CSV_SUCIO.encode("utf-8"), "text/csv")},
        data={"column_types": tipos},
    )
    data = r.json()
    assert data["rows_preview"][0]["Nombre"] == "ACME Services Europe, S.L.U."


def test_clean_opciones_desactivadas(client):
    r = client.post(
        "/api/clean",
        files={"file": ("prospectos.csv", CSV_SUCIO.encode("utf-8"), "text/csv")},
        data={"remove_legal": "false", "remove_geo": "false"},
    )
    data = r.json()
    assert data["rows_preview"][0]["Nombre"] == "ACME Services Europe, S.L.U."


def test_descargas(client):
    r = client.post("/api/clean", files={"file": ("prospectos.csv", CSV_SUCIO.encode("utf-8"), "text/csv")})
    key = r.json()["key"]

    csv_r = client.get(f"/api/download/{key}/csv")
    assert csv_r.status_code == 200
    assert csv_r.content.startswith(b"\xef\xbb\xbf")
    assert "ACME Services" in csv_r.content.decode("utf-8-sig")

    xlsx_r = client.get(f"/api/download/{key}/xlsx")
    assert xlsx_r.status_code == 200
    assert xlsx_r.content[:2] == b"PK"

    json_r = client.get(f"/api/download/{key}/json")
    assert json_r.status_code == 200
    datos = json.loads(json_r.content.decode("utf-8"))
    assert datos[0]["Nombre"] == "ACME Services"


def test_descarga_key_invalida(client):
    r = client.get("/api/download/no-existe/csv")
    assert r.status_code == 404


def test_formato_descarga_invalido(client):
    r = client.post("/api/clean", files={"file": ("p.csv", CSV_SUCIO.encode("utf-8"), "text/csv")})
    key = r.json()["key"]
    r2 = client.get(f"/api/download/{key}/pdf")
    assert r2.status_code == 400


def test_extension_no_permitida(client):
    r = client.post("/api/clean", files={"file": ("malo.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_fichero_vacio(client):
    r = client.post("/api/clean", files={"file": ("vacio.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_nombre_de_fichero_peligroso(client):
    r = client.post(
        "/api/clean",
        files={"file": ("../../etc/passwd.csv", CSV_SUCIO.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 400


def test_xlsx_aceptado(client):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Empresa"])
    ws.append(["ACME Services Europe, S.L.U."])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(
        "/api/clean",
        files={"file": ("lista.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.json()["rows_preview"][0]["Empresa"] == "ACME Services"


def test_cabeceras_de_seguridad(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers


def test_static_servido(client):
    for path in ("/static/rules.js", "/static/engine.js", "/static/csv.js", "/static/app.js"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert len(r.text) > 100
