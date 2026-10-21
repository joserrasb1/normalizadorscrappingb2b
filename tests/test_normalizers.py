# -*- coding: utf-8 -*-
"""
test_normalizers.py
-------------------
Tests unitarios de los normalizadores: empresa, persona, email, teléfono,
cargo y ubicación.
"""

from __future__ import annotations

import pytest

from app.normalizers import (
    Options,
    normalize_company,
    normalize_email,
    normalize_jobtitle,
    normalize_location,
    normalize_person,
    normalize_phone,
    normalize_value,
)


# ============================ EMPRESA ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ACME Services Europe, S.L.U.", "ACME Services"),
        ("GOOGLE SPAIN SOCIEDAD LIMITADA", "Google"),
        ("Acme Services Europe, S.L.U.", "Acme Services"),
        ("Banco Santander, S.A.", "Banco Santander"),
        ("Iberdrola, S.A.", "Iberdrola"),
        ("Telefónica de España, S.A.U.", "Telefónica de España"),
        ("ACME SERVICES EUROPE", "Acme Services"),
        ("Acme, S.L.U. S.A.", "Acme"),
        ("Globex Inc.", "Globex"),
        ("Globex Limited", "Globex"),
        ("Globex LLC", "Globex"),
        ("Globex GmbH", "Globex"),
        ("Globex SARL", "Globex"),
        ("Globex S.p.A.", "Globex"),
        ("Globex B.V.", "Globex"),
        ("Globex Pty Ltd", "Globex"),
        ("Globex S. de R.L. de C.V.", "Globex"),
        ("The Walt Disney Company", "Walt Disney"),
        ("ACME GROUP", "Acme Group"),
        ("Grupo Indra", "Grupo Indra"),
        ("Acme Holdings", "Acme Holdings"),
    ],
)
def test_company_limpieza(raw, expected):
    assert normalize_company(raw).value == expected


def test_company_respeta_marcas_en_mayusculas():
    assert normalize_company("IBM GROUP").value == "IBM Group"
    assert normalize_company("ACME SAP").value == "Acme SAP"


def test_company_no_destruye_formas_debil_en_minusculas():
    # "Se" y "Co" sólo se eliminan en mayúsculas: son ambiguos
    assert normalize_company("Nova Se").value == "Nova Se"
    assert normalize_company("Nova SE").value == "Nova"


def test_company_no_deja_vacio():
    assert normalize_company("S.L.U.").value != ""
    assert normalize_company("S.A.").value != ""


def test_company_detecta_url():
    res = normalize_company("https://www.acme.com")
    assert res.value == "acme"
    assert any(c.rule == "prefix_strip" for c in res.changes)


def test_company_vacia():
    res = normalize_company("")
    assert res.value == ""
    assert res.changed is False


def test_company_opciones_desactivadas():
    o = Options(remove_legal=False, remove_geo=False)
    assert normalize_company("ACME Services Europe, S.L.U.", o).value == "ACME Services Europe, S.L.U."


def test_company_registra_cambios():
    res = normalize_company("ACME Services Europe, S.L.U.")
    rules = [c.rule for c in res.changes]
    assert "legal_suffix" in rules
    assert "geo_suffix" in rules
    assert res.changed is True


# ============================ PERSONA ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("GARCÍA, JOSÉ ANTONIO", "José Antonio García"),
        ("Mr. John Smith", "John Smith"),
        ("Dr. José García", "José García"),
        ("Dña. Ana López", "Ana López"),
        ("Doña Ana López", "Ana López"),
        ("ana lopez", "Ana Lopez"),
        ("JOHN SMITH", "John Smith"),
        ("José García", "José García"),
        ("O'Brien, Sean", "Sean O'Brien"),
        ("McDONALD, ROBERT", "Robert McDonald"),
        ("Jean-Pierre Dupont", "Jean-Pierre Dupont"),
    ],
)
def test_persona(raw, expected):
    assert normalize_person(raw).value == expected


def test_persona_registra_orden_y_titulo():
    res = normalize_person("GARCÍA, JOSÉ ANTONIO")
    rules = [c.rule for c in res.changes]
    assert "name_order" in rules
    assert "casing" in rules

    res2 = normalize_person("Mr. John Smith")
    assert "honorific" in [c.rule for c in res2.changes]


def test_persona_no_trocea_con_comas_multiples():
    res = normalize_person("Smith, John, Jr.")
    assert res.value == "Smith, John, Jr."


# ============================ EMAIL ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  JUAN.PEREZ@ACME.COM ", "juan.perez@acme.com"),
        ("<juan@acme.com>", "juan@acme.com"),
        ("mailto:juan@acme.com", "juan@acme.com"),
        ("juan perez@acme.com", "juanperez@acme.com"),
        ("Juan.Perez+ventas@Acme.es", "juan.perez+ventas@acme.es"),
    ],
)
def test_email(raw, expected):
    assert normalize_email(raw).value == expected


def test_email_typo_gmail():
    res = normalize_email("juan@gmial.com")
    assert res.value == "juan@gmail.com"
    assert "email_typo" in [c.rule for c in res.changes]


def test_email_typo_desactivado():
    o = Options(fix_email_typos=False)
    assert normalize_email("juan@gmial.com", o).value == "juan@gmial.com"


def test_email_invalido_marca():
    res = normalize_email("no-es-un-email")
    assert "email_invalid" in [c.rule for c in res.changes]


def test_email_gmail_dots_opcional():
    o = Options(gmail_dots=True)
    assert normalize_email("juan.perez@gmail.com", o).value == "juanperez@gmail.com"


def test_email_plus_tags_opcional():
    o = Options(strip_plus_tags=True)
    assert normalize_email("juan+ventas@gmail.com", o).value == "juan@gmail.com"


# ============================ TELÉFONO ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("612345678", "612 345 678"),
        ("+34 612 34 56 78", "+34 612 345 678"),
        ("0034612345678", "+34 612 345 678"),
        ("911.234.567", "911 234 567"),
        ("612 345 678 ext. 12", "612 345 678 ext. 12"),
    ],
)
def test_telefono(raw, expected):
    assert normalize_phone(raw).value == expected


def test_telefono_formatos():
    assert normalize_phone("612345678", Options(phone_format="e164")).value == "+34612345678"
    assert normalize_phone("612345678", Options(phone_format="raw")).value == "612345678"
    assert normalize_phone("612345678", Options(phone_format="national")).value == "612 345 678"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+44 20 7946 0958", "+44 207 946 0958"),
        ("+1 415 555 0100", "+1 415 555 0100"),
        ("+49 89 1234567", "+49 891 234 567"),
        ("+34 91 123 4567", "+34 911 234 567"),
        ("91.123.45.67", "911 234 567"),
    ],
)
def test_telefono_internacional(raw, expected):
    assert normalize_phone(raw).value == expected


def test_telefono_invalido():
    res = normalize_phone("sin numero")
    assert "phone_invalid" in [c.rule for c in res.changes]


def test_telefono_vacio():
    assert normalize_phone("").value == ""


# ============================ CARGO ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("GERENTE DE VENTAS", "Gerente de Ventas"),
        ("chief sales officer", "Chief Sales Officer"),
        ("DIRECTOR DE OPERACIONES", "Director de Operaciones"),
        ("VP of Sales", "VP of Sales"),
        ("IT Manager", "IT Manager"),
        ("Chief Executive Officer", "Chief Executive Officer"),
        ("SALES DEVELOPMENT REPRESENTATIVE", "Sales Development Representative"),
    ],
)
def test_cargo(raw, expected):
    assert normalize_jobtitle(raw).value == expected


def test_cargo_conserva_acentos():
    assert normalize_jobtitle("GESTIÓN DE PROYECTOS").value == "Gestión de Proyectos"


# ============================ UBICACIÓN ============================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("España (Madrid)", "Madrid, España"),
        ("08020 Barcelona, Spain", "Barcelona, Spain"),
        ("UNITED KINGDOM", "United Kingdom"),
        ("Madrid, Comunidad de Madrid, España", "Madrid, España"),
        ("Madrid", "Madrid"),
    ],
)
def test_ubicacion(raw, expected):
    assert normalize_location(raw).value == expected


def test_ubicacion_registra_cambio():
    res = normalize_location("España (Madrid)")
    assert "location_format" in [c.rule for c in res.changes]


# ============================ DESPACHO ============================

def test_normalize_value_tipo_desconocido():
    res = normalize_value("texto", "noexiste")
    assert res.value == "texto"
    assert res.changes == []


def test_normalize_value_none():
    res = normalize_value(None, "company")
    assert res.value == ""


def test_resultado_no_muta_si_no_hay_cambios():
    res = normalize_company("Acme Services")
    assert res.changed is False
    assert res.changes == []
