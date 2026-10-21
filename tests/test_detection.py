# -*- coding: utf-8 -*-
"""
test_detection.py
-----------------
Tests de la detección automática del tipo de columna.
"""

from __future__ import annotations

from app.detection import detect_column, detect_columns


def test_detecta_por_cabecera():
    det = detect_column("Email", ["a@b.com", "c@d.com"])
    assert det["type"] == "email"
    assert det["confidence"] > 0.5


def test_detecta_razon_social_como_empresa():
    det = detect_column("Razón Social", ["Acme Services Europe S.L.", "Globex Inc."])
    assert det["type"] == "company"


def test_detecta_telefono():
    det = detect_column("Teléfono", ["612 345 678", "+34 911 234 567"])
    assert det["type"] == "phone"


def test_detecta_cargo():
    det = detect_column("Cargo", ["Sales Manager", "Chief Financial Officer"])
    assert det["type"] == "jobtitle"


def test_detecta_ubicacion():
    det = detect_column("País", ["España", "Germany"])
    assert det["type"] == "location"


def test_detecta_email_solo_por_contenido():
    det = detect_column("col_1", ["juan@acme.com", "pedro@acme.com"])
    assert det["type"] == "email"


def test_detecta_persona_por_contenido():
    det = detect_column("col_2", ["Juan Pérez", "Ana Ruiz"])
    assert det["type"] == "person"


def test_columna_desconocida_ignorar():
    det = detect_column("xyz", ["123", "456"])
    assert det["type"] == "ignore"


def test_detect_columns_devuelve_una_por_columna():
    headers = ["Empresa", "Email", "Telefono", "Cargo", "Pais", "Contacto"]
    rows = [
        ["Acme SL", "a@b.com", "612345678", "CEO", "España", "Juan Perez"],
        ["Globex Inc", "c@d.com", "911234567", "CFO", "Germany", "Ana Ruiz"],
    ]
    cols = detect_columns(headers, rows)
    assert len(cols) == len(headers)
    assert [c["index"] for c in cols] == list(range(len(headers)))
    tipos = {c["name"]: c["type"] for c in cols}
    assert tipos["Empresa"] == "company"
    assert tipos["Email"] == "email"
    assert tipos["Telefono"] == "phone"
    assert tipos["Cargo"] == "jobtitle"
    assert tipos["Pais"] == "location"
    assert tipos["Contacto"] == "person"


def test_detect_columns_sin_filas():
    cols = detect_columns(["Email"], [])
    assert len(cols) == 1


# ============================ CABECERAS vs CONTENIDO ============================


def test_cabecera_ambigua_manda_el_contenido():
    """Una columna "Nombre" que contiene empresas es una columna de empresas."""
    det = detect_column("Nombre", ["ACME Services Europe, S.L.U.", "Globex Inc."])
    assert det["type"] == "company"


def test_cabecera_ambigua_con_nombres_es_persona():
    det = detect_column("Nombre", ["Juan Pérez", "Ana Ruiz"])
    assert det["type"] == "person"


def test_cabecera_fuerte_manda_sobre_el_contenido():
    """Una columna "Empresa" sigue siendo empresa aunque el contenido sea raro."""
    det = detect_column("Empresa", ["Acme Solutions", "Globex Corporation"])
    assert det["type"] == "company"


def test_forma_juridica_delata_a_la_empresa():
    det = detect_column("col_1", ["Acme, S.L.U.", "Globex S.A."])
    assert det["type"] == "company"


def test_razon_social_con_forma_juridica_es_empresa():
    det = detect_column("Razón Social", ["Acme, S.L.U.", "Globex S.A."])
    assert det["type"] == "company"


def test_columna_de_notas_libre_se_ignora():
    det = detect_column("Notas", ["llamar por la mañana", "vuelve en octubre"])
    assert det["type"] == "ignore"


def test_detect_columns_tabla_completa():
    headers = ["Nombre", "Razón Social", "Pais", "Email", "Telefono", "Cargo", "Contacto"]
    rows = [
        [
            "ACME SERVICES EUROPE SL",
            "ACME Services Europe S.L.U.",
            "España",
            "JUAN.PEREZ@ACME.COM",
            "612345678",
            "GERENTE DE VENTAS",
            "GARCÍA, JOSÉ ANTONIO",
        ],
        [
            "GOOGLE SPAIN SOCIEDAD LIMITADA",
            "Google Spain Sociedad Limitada",
            "España",
            "info@google.es",
            "+34 91 123 4567",
            "Chief Executive Officer",
            "Mr. John Smith",
        ],
    ]
    cols = detect_columns(headers, rows)
    tipos = {c["name"]: c["type"] for c in cols}
    assert tipos["Nombre"] == "company"
    assert tipos["Razón Social"] == "company"
    assert tipos["Pais"] == "location"
    assert tipos["Email"] == "email"
    assert tipos["Telefono"] == "phone"
    assert tipos["Cargo"] == "jobtitle"
    assert tipos["Contacto"] == "person"


def test_confianza_alta_para_cabecera_inequivoca():
    det = detect_column("Email corporativo", ["a@b.com", "c@d.com"])
    assert det["confidence"] >= 0.8
    assert "cabecera" in det["reason"]


def test_deteccion_es_determinista():
    """Dos llamadas con los mismos datos dan el mismo resultado."""
    a = detect_column("Nombre", ["ACME Services Europe, S.L.U.", "Globex Inc."])
    b = detect_column("Nombre", ["ACME Services Europe, S.L.U.", "Globex Inc."])
    assert a == b
