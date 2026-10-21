# -*- coding: utf-8 -*-
"""
tabular.py
----------
Lectura y escritura de tablas (CSV, TSV, XLSX) con garantías:

- Detección automática del delimitador (, ; \\t |).
- Descodificación robusta (UTF-8 con/sin BOM, Latin-1, CP1252).
- Límites de filas y celdas para no agotar memoria.
- Protección contra fórmulas al exportar (CSV injection).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Dict, List, Optional, Sequence, Tuple

MAX_ROWS = 50_000
MAX_COLS = 200
MAX_CELL_LEN = 32_000

DELIMITERS = [",", ";", "\t", "|"]

# Fórmulas peligrosas en Excel / Hojas de cálculo
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Un teléfono o un número con signo NO es una fórmula. Si lo protegemos con
# un apóstrofo, el CRM importará "'+34 911 234 567" en vez del teléfono, así
# que esos valores se dejan intactos.
_SAFE_NUMBER_RE = re.compile(r"^\d[\d\s.,()\-]*(?:ext\.?\s*\d+)?$", re.IGNORECASE)


def sniff_delimiter(sample: str) -> str:
    """Detecta el delimitador más probable de un CSV."""
    counts = {d: 0 for d in DELIMITERS}
    in_quotes = False
    for ch in sample[:20000]:
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes and ch in counts:
            counts[ch] += 1
    # Prioriza ';' y ',' sobre tabulador sólo si hay empate claro
    best = max(counts, key=lambda d: counts[d])
    if counts[best] == 0:
        return ","
    return best


def decode_bytes(data: bytes) -> str:
    """Decodifica bytes trying UTF-8 (BOM), Latin-1 y CP1252."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def parse_csv_text(
    text: str, delimiter: Optional[str] = None
) -> Tuple[List[str], List[List[str]], Dict[str, object]]:
    """
    Parsea un CSV/TSV. Devuelve (cabeceras, filas, metadatos).
    Si no hay fila de cabecera reconocible, se genera una cabecera genérica.
    """
    if text.startswith("\ufeff"):
        text = text[1:]  # BOM UTF-8
    if delimiter is None:
        delimiter = sniff_delimiter(text)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows: List[List[str]] = []
    truncated = False
    for i, row in enumerate(reader):
        if i > MAX_ROWS:
            truncated = True
            break
        rows.append([_clean_cell(c) for c in row])

    if not rows:
        return [], [], {"delimiter": delimiter, "rows": 0, "truncated": truncated}

    header = rows[0]
    data = rows[1:]
    # Descarta la fila final vacía habitual
    while data and not any(str(c).strip() for c in data[-1]):
        data.pop()

    # Normaliza el número de columnas
    width = max([len(header)] + [len(r) for r in data]) if data else len(header)
    width = min(width, MAX_COLS)
    header = (header + [""] * width)[:width]
    data = [(r + [""] * width)[:width] for r in data]

    # Cabecera vacía -> se generan nombres genéricos (una por columna real)
    if not any(str(h).strip() for h in header):
        header = [f"Columna {i + 1}" for i in range(width)]

    meta = {
        "delimiter": delimiter,
        "rows": len(data),
        "columns": width,
        "truncated": truncated,
    }
    return header, data, meta


def _clean_cell(value: str) -> str:
    if value is None:
        return ""
    s = str(value)
    if len(s) > MAX_CELL_LEN:
        s = s[:MAX_CELL_LEN]
    return s


def read_xlsx(data: bytes) -> Tuple[List[str], List[List[str]], Dict[str, object]]:
    """Lee la primera hoja de un XLSX."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows: List[List[str]] = []
    truncated = False
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i > MAX_ROWS:
            truncated = True
            break
        rows.append(["" if c is None else _clean_cell(str(c)) for c in row])
    wb.close()

    if not rows:
        return [], [], {"delimiter": None, "rows": 0, "truncated": truncated}

    header = rows[0]
    data_rows = rows[1:]
    while data_rows and not any(str(c).strip() for c in data_rows[-1]):
        data_rows.pop()

    width = max([len(header)] + [len(r) for r in data_rows]) if data_rows else len(header)
    width = min(width, MAX_COLS)
    header = (header + [""] * width)[:width]
    data_rows = [(r + [""] * width)[:width] for r in data_rows]

    return header, data_rows, {
        "delimiter": None,
        "rows": len(data_rows),
        "columns": width,
        "truncated": truncated,
    }


def read_table(
    data: bytes, filename: str
) -> Tuple[List[str], List[List[str]], Dict[str, object]]:
    """Lee un fichero subido (CSV/TSV/TXT/XLSX) y devuelve la tabla."""
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return read_xlsx(data)
    text = decode_bytes(data)
    return parse_csv_text(text)


def _looks_like_number(value: str) -> bool:
    """¿El valor es un teléfono o un número (y por tanto no una fórmula)?"""
    rest = value[1:].strip() if value[:1] in ("+", "-") else value.strip()
    return bool(_SAFE_NUMBER_RE.match(rest))


def protect_formula(value: str) -> str:
    """Neutraliza celdas que Excel interpretaría como fórmula."""
    if not value:
        return value
    if value[0] not in _FORMULA_PREFIXES:
        return value
    if _looks_like_number(value):
        return value
    return "'" + value


def write_csv(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    delimiter: str = ";",
    bom: bool = True,
    protect: bool = True,
) -> bytes:
    """Genera un CSV (UTF-8) listo para Excel o para importar en un CRM."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL,
                        lineterminator="\r\n")
    writer.writerow([protect_formula(str(h)) if protect else str(h) for h in headers])
    for row in rows:
        cells = []
        for c in row:
            s = "" if c is None else str(c)
            if len(s) > MAX_CELL_LEN:
                s = s[:MAX_CELL_LEN]
            cells.append(protect_formula(s) if protect else s)
        writer.writerow(cells)
    data = buf.getvalue().encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    return data


def write_xlsx(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    report_rows: Optional[Sequence[Sequence[str]]] = None,
    report_title: str = "Informe",
    protect: bool = True,
) -> bytes:
    """
    Genera un XLSX con dos hojas: los datos limpios y un informe de cambios.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Datos limpios"

    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(color="FFFFFF", bold=True)

    ws.append([str(h) for h in headers])
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    for row in rows:
        cells = []
        for c in row:
            s = "" if c is None else str(c)
            if len(s) > MAX_CELL_LEN:
                s = s[:MAX_CELL_LEN]
            cells.append(protect_formula(s) if protect else s)
        ws.append(cells)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Ancho de columnas automático (aproximado)
    for i, h in enumerate(headers, start=1):
        width = len(str(h))
        for j, row in enumerate(rows[:200]):
            if i - 1 < len(row):
                width = max(width, len(str(row[i - 1]) or ""))
            if j > 200:
                break
        ws.column_dimensions[get_column_letter(i)].width = min(48, max(10, width + 2))

    if report_rows:
        rs = wb.create_sheet(report_title[:31])
        rs.append(["Columna", "Regla", "Antes", "Después"])
        for cell in rs[1]:
            cell.fill = header_fill
            cell.font = header_font
        for r in report_rows:
            rs.append([str(x) for x in r])
        rs.freeze_panes = "A2"
        for i, w in enumerate([26, 30, 42, 42], start=1):
            rs.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def to_json_rows(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> List[Dict[str, str]]:
    """Convierte la tabla en una lista de diccionarios (para JSON/CRM)."""
    out = []
    for row in rows:
        obj: Dict[str, str] = {}
        for i, h in enumerate(headers):
            key = str(h).strip() or f"columna_{i + 1}"
            obj[key] = "" if i >= len(row) else str(row[i])
        out.append(obj)
    return out
