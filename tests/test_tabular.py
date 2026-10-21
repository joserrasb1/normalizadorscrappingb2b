# -*- coding: utf-8 -*-
"""
test_tabular.py
---------------
Tests de lectura/escritura de CSV, TSV y XLSX, y de la protección frente a
fórmulas maliciosas en las exportaciones.
"""

from __future__ import annotations

import io

from app.tabular import (
    decode_bytes,
    parse_csv_text,
    protect_formula,
    read_table,
    sniff_delimiter,
    to_json_rows,
    write_csv,
    write_xlsx,
)


def test_sniff_delimiters():
    assert sniff_delimiter("a,b,c\n1,2,3") == ","
    assert sniff_delimiter("a;b;c\n1;2;3") == ";"
    assert sniff_delimiter("a\tb\tc\n1\t2\t3") == "\t"
    assert sniff_delimiter("a|b|c\n1|2|3") == "|"


def test_parse_csv_basico():
    headers, rows, meta = parse_csv_text("Nombre;Email\na;a@b.com\nb;c@d.com")
    assert headers == ["Nombre", "Email"]
    assert len(rows) == 2
    assert rows[0] == ["a", "a@b.com"]
    assert meta["delimiter"] == ";"


def test_parse_csv_comillas():
    text = 'Nombre,Razon\n"Iberdrola, S.A.","Empresa, S.L."'
    headers, rows, _ = parse_csv_text(text)
    assert headers == ["Nombre", "Razon"]
    assert rows[0] == ["Iberdrola, S.A.", "Empresa, S.L."]


def test_parse_csv_con_comas_dentro():
    text = 'Contacto\n"GARCÍA, JOSÉ ANTONIO"\n'
    headers, rows, _ = parse_csv_text(text)
    assert rows[0][0] == "GARCÍA, JOSÉ ANTONIO"


def test_parse_csv_cabecera_vacia_genera_nombres():
    headers, rows, _ = parse_csv_text(";;\n1;2;3")
    assert headers == ["Columna 1", "Columna 2", "Columna 3"]
    assert rows[0] == ["1", "2", "3"]


def test_parse_csv_filas_vacias_al_final():
    headers, rows, _ = parse_csv_text("a,b\n1,2\n\n\n")
    assert len(rows) == 1


def test_decode_bytes_bom():
    assert decode_bytes(b"\xef\xbb\xbfhola") == "hola"


def test_decode_bytes_latin1():
    data = "café".encode("latin-1")
    assert "caf" in decode_bytes(data)


def test_read_table_csv():
    headers, rows, meta = read_table(b"a;b\n1;2", "x.csv")
    assert headers == ["a", "b"]
    assert meta["rows"] == 1


def test_read_table_txt():
    headers, rows, _ = read_table(b"a\tb\n1\t2", "x.txt")
    assert headers == ["a", "b"]


def test_read_table_xlsx():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Empresa", "Email"])
    ws.append(["Acme SL", "a@b.com"])
    buf = io.BytesIO()
    wb.save(buf)
    headers, rows, meta = read_table(buf.getvalue(), "x.xlsx")
    assert headers == ["Empresa", "Email"]
    assert rows[0] == ["Acme SL", "a@b.com"]
    assert meta["rows"] == 1


def test_write_csv_bom_y_delimitador():
    data = write_csv(["a", "b"], [["1", "2"]], delimiter=";", bom=True)
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"a;b" in data


def test_write_csv_sin_bom():
    data = write_csv(["a"], [["1"]], bom=False)
    assert not data.startswith(b"\xef\xbb\xbf")


def test_protect_formula():
    assert protect_formula("=1+1") == "'=1+1"
    assert protect_formula("@SUM(A1)") == "'@SUM(A1)"
    assert protect_formula("normal") == "normal"
    # Un teléfono no es una fórmula: no debe "'+34 600" en el CSV exportado
    assert protect_formula("+34 600") == "+34 600"
    assert protect_formula("+34 600 12 34") == "+34 600 12 34"
    assert protect_formula("-100") == "-100"
    # ...pero un intento de inyección sí se protege
    assert protect_formula("+CMD|calc") == "'+CMD|calc"
    assert protect_formula("-2+3") == "'-2+3"


def test_write_csv_protege_formulas():
    data = write_csv(["a"], [["=CMD|calc"]], protect=True)
    assert b"'=CMD|calc" in data


def test_write_csv_sin_proteccion():
    data = write_csv(["a"], [["=CMD|calc"]], protect=False)
    assert b"=CMD|calc" in data
    assert b"'=CMD|calc" not in data


def test_write_xlsx_dos_hojas():
    data = write_xlsx(
        ["Empresa"], [["Acme"]], report_rows=[["Empresa", "Forma jurídica", "Acme SL", "Acme"]]
    )
    assert data[:2] == b"PK"  # zip


def test_to_json_rows():
    rows = to_json_rows(["Empresa", "Email"], [["Acme", "a@b.com"]])
    assert rows == [{"Empresa": "Acme", "Email": "a@b.com"}]


def test_to_json_rows_cabecera_vacia():
    rows = to_json_rows(["", "Email"], [["Acme", "a@b.com"]])
    assert "columna_1" in rows[0]
