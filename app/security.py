# -*- coding: utf-8 -*-
"""
security.py
-----------
Límites, saneado de nombres de fichero y cabeceras HTTP seguras.

Adaptado del validador Norma 43, con las extensiones propias de este
servicio (.csv, .tsv, .txt, .xlsx) y sin el filtro de payloads HTML: en un
CSV de prospectos es normal que aparezcan "<", ">" o comillas, y el
resultado siempre se escapa al exportarlo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Tuple

# Límites conservadores para un POC SaaS gratuito
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 50_000
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx"}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}


@dataclass
class SecurityCheckResult:
    safe: bool
    blocked_reasons: List[str]
    warnings: List[str]


def secure_filename(filename: str | None, default: str = "prospectos.csv") -> str:
    """Genera un nombre de fichero seguro para cabeceras HTTP."""
    if not filename:
        return default
    name = os.path.basename(str(filename).replace("\\", "/"))
    name = name.strip().strip(".")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    root = os.path.splitext(name)[0].lower()
    if root in WINDOWS_RESERVED_NAMES:
        name = "safe_" + name
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        root = os.path.splitext(name)[0] or "prospectos"
        name = root + ".csv"
    if len(name) > 150:
        ext = os.path.splitext(name)[1]
        name = name[:140] + ext
    if name.startswith("."):
        name = "upload" + name
    return name


def check_filename_security(filename: str | None) -> SecurityCheckResult:
    res = SecurityCheckResult(safe=True, blocked_reasons=[], warnings=[])
    if not filename:
        res.safe = False
        res.blocked_reasons.append("Nombre de fichero vacío o no válido")
        return res
    name = filename
    if ".." in name or name.count("/") > 3 or name.count("\\") > 3:
        res.safe = False
        res.blocked_reasons.append("Nombre de fichero con ruta sospechosa (path traversal)")
    if "\x00" in name:
        res.safe = False
        res.blocked_reasons.append("Nombre de fichero contiene byte nulo")
    if _CONTROL_RE.search(name):
        res.safe = False
        res.blocked_reasons.append("Nombre de fichero contiene caracteres de control")
    if "\r" in name or "\n" in name:
        res.safe = False
        res.blocked_reasons.append(
            "Nombre de fichero con salto de línea (CRLF injection riesgo en headers)"
        )
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        res.safe = False
        res.blocked_reasons.append(
            "Extensión no permitida. Solo " + ", ".join(sorted(ALLOWED_EXTENSIONS))
        )
    return res


def is_binary_container(data: bytes) -> bool:
    """
    True si el contenido es un contenedor binario (XLSX/ODS = ZIP).

    Los ficheros ZIP contienen bytes de control y nulos por naturaleza, así que
    el análisis de "texto" no aplica: sólo se valida el tamaño y la extensión.
    """
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\xd0\xcf\x11\xe0")


def check_content_security(data: bytes) -> SecurityCheckResult:
    """Validaciones sobre los bytes subidos."""
    res = SecurityCheckResult(safe=True, blocked_reasons=[], warnings=[])
    if len(data) == 0:
        res.safe = False
        res.blocked_reasons.append("Contenido vacío")
        return res
    if len(data) > MAX_UPLOAD_BYTES:
        res.safe = False
        res.blocked_reasons.append("Tamaño excede límite (%d bytes)" % MAX_UPLOAD_BYTES)
    if is_binary_container(data):
        res.warnings.append(
            "Formato binario (hoja de cálculo): no se analizan los caracteres de control"
        )
        return res
    if b"\x00" in data:
        res.safe = False
        res.blocked_reasons.append("Contenido contiene byte nulo")
    # Los caracteres de control (salvo tabulador y saltos de línea) no son
    # legítimos en un CSV de prospectos.
    probe = data[:200_000]
    bad = _CONTROL_RE.findall(probe.decode("latin-1", errors="replace"))
    if len(bad) > 20:
        res.safe = False
        res.blocked_reasons.append("Contenido con demasiados caracteres de control")
    elif bad:
        res.warnings.append(
            "Se han eliminado %d carácter(es) de control del contenido" % len(bad)
        )
    return res


def clean_control_chars(text: str) -> str:
    """Elimina caracteres de control no imprimibles."""
    return _CONTROL_RE.sub("", text)


def secure_http_headers() -> List[Tuple[str, str]]:
    """Cabeceras HTTP seguras recomendadas para las respuestas."""
    return [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
        (
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'",
        ),
        ("Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    ]
