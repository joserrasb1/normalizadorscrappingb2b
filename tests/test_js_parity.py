# -*- coding: utf-8 -*-
"""
test_js_parity.py
-----------------
Comprueba que el motor de JavaScript (el que corre en el navegador) produce
exactamente los mismos resultados que el motor de Python (el del servidor).

Si el test se salta es porque `node` no está instalado en la máquina; en CI
debe estar disponible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.detection import detect_column
from app.normalizers import Options, normalize_value

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js_harness.js"
CSV_HARNESS = ROOT / "tests" / "js_csv_harness.js"

NODE = shutil.which("node")

# (valor, tipo, opciones python, opciones javascript)
NORMALIZE_CASES = [
    ("ACME Services Europe, S.L.U.", "company", {}, {}),
    ("GOOGLE SPAIN SOCIEDAD LIMITADA", "company", {}, {}),
    ("Banco Santander, S.A.", "company", {}, {}),
    ("Iberdrola, S.A.", "company", {}, {}),
    ("Globex Inc.", "company", {}, {}),
    ("Globex LLC", "company", {}, {}),
    ("The Walt Disney Company", "company", {}, {}),
    ("ACME GROUP", "company", {}, {}),
    ("Grupo Indra", "company", {}, {}),
    ("Nova Se", "company", {}, {}),
    ("Nova SE", "company", {}, {}),
    ("https://www.acme.com", "company", {}, {}),
    (
        "ACME Services Europe, S.L.U.",
        "company",
        {"remove_legal": False, "remove_geo": False},
        {"removeLegal": False, "removeGeo": False},
    ),
    ("GARCÍA, JOSÉ ANTONIO", "person", {}, {}),
    ("Mr. John Smith", "person", {}, {}),
    ("Dña. Ana López", "person", {}, {}),
    ("Doña Ana López", "person", {}, {}),
    ("ana lopez", "person", {}, {}),
    ("JOHN SMITH", "person", {}, {}),
    ("O'Brien, Sean", "person", {}, {}),
    ("McDONALD, ROBERT", "person", {}, {}),
    ("Jean-Pierre Dupont", "person", {}, {}),
    ("  JUAN.PEREZ@ACME.COM ", "email", {}, {}),
    ("<juan@acme.com>", "email", {}, {}),
    ("mailto:juan@acme.com", "email", {}, {}),
    ("juan perez@acme.com", "email", {}, {}),
    ("juan@gmial.com", "email", {}, {}),
    ("no-es-un-email", "email", {}, {}),
    (
        "juan.perez@gmail.com",
        "email",
        {"gmail_dots": True},
        {"gmailDots": True},
    ),
    (
        "juan+ventas@gmail.com",
        "email",
        {"strip_plus_tags": True},
        {"stripPlusTags": True},
    ),
    ("612345678", "phone", {}, {}),
    ("+34 612 34 56 78", "phone", {}, {}),
    ("0034612345678", "phone", {}, {}),
    ("911.234.567", "phone", {}, {}),
    ("612 345 678 ext. 12", "phone", {}, {}),
    ("+44 20 7946 0958", "phone", {}, {}),
    ("+1 415 555 0100", "phone", {}, {}),
    ("+49 89 1234567", "phone", {}, {}),
    ("91.123.45.67", "phone", {}, {}),
    ("612345678", "phone", {"phone_format": "e164"}, {"phoneFormat": "e164"}),
    ("612345678", "phone", {"phone_format": "raw"}, {"phoneFormat": "raw"}),
    (
        "612345678",
        "phone",
        {"phone_format": "national"},
        {"phoneFormat": "national"},
    ),
    ("GERENTE DE VENTAS", "jobtitle", {}, {}),
    ("chief sales officer", "jobtitle", {}, {}),
    ("VP of Sales", "jobtitle", {}, {}),
    ("España (Madrid)", "location", {}, {}),
    ("08020 Barcelona, Spain", "location", {}, {}),
    ("UNITED KINGDOM", "location", {}, {}),
    ("Madrid, Comunidad de Madrid, España", "location", {}, {}),
]

# Casos del parser CSV: (nombre, texto)
# El parser de JavaScript (app/static/csv.js) debe comportarse EXACTAMENTE
# igual que el de Python (app/tabular.py::parse_csv_text).
CSV_CASES = [
    ("simple", "a,b,c\n1,2,3\n"),
    ("crlf", "a,b\r\n1,2\r\n"),
    ("quoted", 'a,b\n"x,y",z\n'),
    ("quotes_escaped", 'a,b\n"he said ""hi""",z\n'),
    ("newline_in_field", 'a,b\n"line1\nline2",z\n'),
    ("empty_header", ",b,c\n1,2,3\n"),
    ("blank_header_row", "\n1,2,3\n"),
    ("trailing_newline", "a,b\n1,2\n"),
    ("ragged", "a,b,c\n1,2\n3,4,5,6\n"),
    ("semicolon", "a;b;c\n1;2;3\n"),
    ("tabs", "a\tb\tc\n1\t2\t3\n"),
    ("pipe", "a|b|c\n1|2|3\n"),
    ("quote_in_middle", 'a,b\nx"y,z\n'),
    ("quoted_then_text", 'a,b\n"x"y,z\n'),
    ("spaces", "a, b\n1, 2\n"),
    ("empty_cells", "a,b,c\n,,\n"),
    ("only_header", "a,b,c\n"),
    ("bom", "\ufeffa,b\n1,2\n"),
    ("utf8_accents", "a,b\nJos\u00e9,\u00c1ngel\n"),
    ("quote_unclosed", 'a,b\n"x,z\n'),
    ("double_delim", "a,b\n1,,3\n"),
    ("trailing_empty_col", "a,b,\n1,2,3\n"),
    ("quoted_delim_nl", 'a,b\n"x;y\nz",w\n'),
    ("empty_rows_middle", "a,b\n\n1,2\n"),
    ("semicolon_in_quotes", 'a;b\n"x;y";z\n'),
    ("only_quotes", '""\n'),
    ("space_before_quote", ' "x,y",z\n'),
    ("quote_only_field", 'a,b\n",",x\n'),
    ("many_cols", ",".join(str(i) for i in range(12)) + "\n" + ",".join("v" for _ in range(12)) + "\n"),
    ("trailing_comma_row", "a,b\n1,2,\n"),
    ("windows_bom_crlf", "\ufeffa,b\r\n1,2\r\n"),
    ("tab_inside_quotes", 'a,b\n"x\ty",z\n'),
]

# (cabecera, valores)
DETECT_CASES = [
    ("Email", ["a@b.com", "c@d.com"]),
    ("Razón Social", ["Acme Services Europe S.L.", "Globex Inc."]),
    ("Nombre", ["ACME Services Europe, S.L.U.", "Globex Inc."]),
    ("Empresa", ["Acme SL", "Globex Inc"]),
    ("Teléfono", ["612 345 678", "+34 911 234 567"]),
    ("Cargo", ["Sales Manager", "Chief Financial Officer"]),
    ("País", ["España", "Germany"]),
    ("Contacto", ["Juan Pérez", "Ana Ruiz"]),
    ("col_1", ["juan@acme.com", "pedro@acme.com"]),
    ("col_2", ["Juan Pérez", "Ana Ruiz"]),
    ("xyz", ["123", "456"]),
    ("Company Name", ["Acme SL", "Globex Inc"]),
]


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_paridad_motor_js_y_python(tmp_path):
    payload = {
        "normalize": [
            {"value": v, "kind": k, "options": js_opts}
            for v, k, py_opts, js_opts in NORMALIZE_CASES
        ],
        "detect": [{"name": n, "values": vals} for n, vals in DETECT_CASES],
    }
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [NODE, str(HARNESS), str(payload_file)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    js = json.loads(proc.stdout)

    for case, js_res in zip(NORMALIZE_CASES, js["normalize"]):
        value, kind, py_opts, _ = case
        py = normalize_value(value, kind, Options(**py_opts))
        assert py.value == js_res["value"], (value, kind, py.value, js_res["value"])
        assert [c.rule for c in py.changes] == js_res["changes"], (value, kind)

    for case, js_det in zip(DETECT_CASES, js["detect"]):
        name, values = case
        py = detect_column(name, values)
        assert py["type"] == js_det["type"], (name, py, js_det)
        assert py["confidence"] == js_det["confidence"], (name, py, js_det)


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_paridad_deteccion_columnas(tmp_path):
    """La detección por columnas completas también debe coincidir."""
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
    payload = {"normalize": [], "detect": [{"name": h, "values": [r[i] for r in rows]} for i, h in enumerate(headers)]}
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(HARNESS), str(payload_file)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    js = json.loads(proc.stdout)

    from app.detection import detect_columns

    py_cols = detect_columns(headers, rows)
    for py_col, js_det in zip(py_cols, js["detect"]):
        assert py_col["type"] == js_det["type"], (py_col, js_det)
        assert py_col["confidence"] == js_det["confidence"], (py_col, js_det)


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_paridad_parser_csv_js_y_python(tmp_path):
    """El parser CSV del navegador debe dar exactamente los mismos datos."""
    from app.tabular import parse_csv_text

    payload = {"texts": [text for _, text in CSV_CASES]}
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [NODE, str(CSV_HARNESS), str(payload_file)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout)

    for (name, text), js_res in zip(CSV_CASES, results):
        py_headers, py_rows, py_meta = parse_csv_text(text)
        assert py_headers == js_res["headers"], (name, py_headers, js_res["headers"])
        assert py_rows == js_res["rows"], (name, py_rows, js_res["rows"])
        assert py_meta["delimiter"] == js_res["delimiter"], name


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_paridad_proteccion_formulas_js_y_python():
    """La protección contra fórmulas debe ser idéntica en ambos motores."""
    from app.tabular import protect_formula

    values = [
        "",
        "Empresa normal",
        "=1+1",
        "=HYPERLINK(\"http://evil\",\"clic\")",
        "+34 911 234 567",
        "+34600123456",
        "+1 (415) 555-0100",
        "-100",
        "-2+3",
        "612 345 678 ext. 12",
        "@SUM(A1)",
        "@acme",
        "\tcon tabulador",
        "línea\ncon salto",
    ]
    js = subprocess.run(
        [
            NODE,
            "-e",
            (
                "global.window=global;"
                f"require({str(ROOT / 'app' / 'static' / 'csv.js')!r});"
                "const vals=" + json.dumps(values, ensure_ascii=False) + ";"
                "process.stdout.write(JSON.stringify(vals.map(v=>window.CSV_UTILS.protectFormula(v))));"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert js.returncode == 0, js.stderr
    js_values = json.loads(js.stdout)
    for value, js_value in zip(values, js_values):
        assert protect_formula(value) == js_value, (value, protect_formula(value), js_value)


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_paridad_serializador_csv_js_y_python(tmp_path):
    """El CSV exportado en el navegador debe ser idéntico al del servidor."""
    from app.tabular import write_csv

    headers = ["Empresa", "Email", "Importe"]
    rows = [
        ["ACME, S.L.", "a@b.com", "=1+1"],
        ['Frase "con" comillas', "c@d.es", "3,50"],
        ["Línea\ncon salto", "", "0"],
    ]
    js = subprocess.run(
        [
            NODE,
            "-e",
            (
                "global.window=global;"
                f"require({str(ROOT / 'app' / 'static' / 'csv.js')!r});"
                "const csv=window.CSV_UTILS.serialize("
                + json.dumps(headers, ensure_ascii=False) + ","
                + json.dumps(rows, ensure_ascii=False) + ",';',true,true);"
                "process.stdout.write(Buffer.from(csv,'utf8').toString('base64'));"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert js.returncode == 0, js.stderr
    import base64

    js_csv = base64.b64decode(js.stdout).decode("utf-8")
    py_csv = write_csv(headers, rows, delimiter=";", bom=True, protect=True).decode("utf-8")
    assert js_csv == py_csv
