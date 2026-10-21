# -*- coding: utf-8 -*-
"""
test_rules_sync.py
------------------
Verifica que `app/static/rules.js` está sincronizado con `app/rules.py`.

`rules.py` es la fuente única de verdad: si se cambia una regla hay que
regenerar el fichero con:

    python -m tools.gen_rules_js
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.rules import rules_payload
from tools.gen_rules_js import TARGET, render


def test_rules_js_existe():
    assert TARGET.exists(), "Falta app/static/rules.js"


def test_rules_js_sincronizado():
    esperado = render()
    actual = TARGET.read_text(encoding="utf-8")
    assert actual == esperado, (
        "rules.js desactualizado. Ejecuta: python -m tools.gen_rules_js"
    )


def test_rules_js_contiene_las_reglas_principales():
    contenido = TARGET.read_text(encoding="utf-8")
    m = re.search(r"window\.RULES\s*=\s*(\{.*\});", contenido, re.S)
    assert m, "No se encuentra el objeto RULES en rules.js"
    data = json.loads(m.group(1))
    payload = rules_payload()
    assert set(payload.keys()) == set(data.keys())
    for key in payload:
        assert data[key] == payload[key], key


def test_el_payload_incluye_las_claves_que_usa_el_motor_js():
    payload = rules_payload()
    for key in (
        "dotted",
        "word_forms",
        "weak_forms",
        "always_legal_forms",
        "geo_suffixes",
        "honorifics",
        "header_keywords",
        "strong_header_keywords",
        "detection_weights",
        "job_title_words",
        "legal_form_src",
        "geo_suffix_src",
        "honorific_src",
        "honorific_trail_src",
        "valid_calling_codes",
    ):
        assert key in payload, key
        assert payload[key], key
