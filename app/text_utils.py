# -*- coding: utf-8 -*-
"""
text_utils.py
-------------
Utilidades de texto compartidas por todos los normalizadores.

La lógica es deliberadamente simple y determinista (sin IA) para que el
resultado sea reproducible, auditable y testeable. El espejo en JavaScript
(`app/static/engine.js`) replica exactamente estas funciones.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Set

from .rules import ACRONYMS, KNOWN_MIXED_CASE, NAME_PREFIXES

# Caracteres de control y espacios exóticos que se limpian de entrada
_CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_SPACE_LIKE_RE = re.compile(r"[\u00A0\u2007\u202F\u200B\u2060\uFEFF]")
_DASHES_RE = re.compile(r"[\u2010-\u2015\u2212\u2043]")
_QUOTES_RE = re.compile(r"[\u2018\u2019\u201C\u201D\u00AB\u00BB]")
_SEPARATORS_RE = re.compile(r"[\u2013\u2014]")

# Separadores (guiones) dentro de un token compuesto
_HYPHEN_SPLIT_RE = re.compile(r"([-\u2010-\u2015])")
_LETTERS_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def clean_text(value: str) -> str:
    """Limpieza base: normaliza espacios, guiones, comillas y controles."""
    if value is None:
        return ""
    s = str(value)
    s = _CTRL_RE.sub(" ", s)
    s = _SPACE_LIKE_RE.sub(" ", s)
    s = _DASHES_RE.sub("-", s)
    s = _QUOTES_RE.sub("'", s)
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    s = s.replace("\t", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def strip_edge_punctuation(text: str) -> str:
    """
    Quita puntuación sobrante de los extremos (comas, guiones...).

    El punto final NO se toca: "S.L.U." o "Inc." son abreviaturas y quitarlos
    dejaría el valor corrupto.
    """
    s = text.strip()
    s = s.strip(" \t,;_-/|·•")
    s = s.lstrip(".")   # sólo el punto inicial sobra
    return s.strip()


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def is_all_caps(text: str) -> bool:
    """True si el texto tiene letras y todas son mayúsculas."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


def is_all_lower(text: str) -> bool:
    """True si el texto tiene letras y todas son minúsculas."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return all(c.islower() for c in letters)


def is_mostly_caps(text: str, threshold: float = 0.85) -> bool:
    """
    True si el texto está "casi todo" en mayúsculas.

    Cubre el caso "ROBERT McDONALD", donde el prefijo "Mc" impide que el
    texto sea 100% mayúsculas pero sigue siendo un nombre en mayúsculas.
    """
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return (upper / len(letters)) >= threshold


def has_mixed_case(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    return any(c.isupper() for c in letters) and any(c.islower() for c in letters)


_ALPHA_RUN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _cap_word(word: str) -> str:
    """Capitaliza una palabra suelta respetando acrónimos y prefijos."""
    if not word:
        return word
    low = word.lower()
    if low in KNOWN_MIXED_CASE:
        return KNOWN_MIXED_CASE[low]
    if low in ACRONYMS:
        return word.upper()
    if any(ch.isdigit() for ch in word):
        # "3M", "7-Eleven", "B2B": se respetan tal cual
        return word
    # Prefijos de apellido: McDonald, O'Brien, MacGregor
    for p in NAME_PREFIXES:
        if low.startswith(p.lower()) and len(word) > len(p):
            rest = word[len(p):]
            return p + rest[0].upper() + rest[1:].lower()
    return word[0].upper() + word[1:].lower()


def _cap_token(token: str) -> str:
    """
    Aplica el criterio de capitalización a cada fragmento alfabético del
    token, de modo que "(CEO)", "ACME," o "JEAN-PIERRE" se tratan bien.
    """
    out: List[str] = []
    pos = 0
    for m in _ALPHA_RUN_RE.finditer(token):
        out.append(token[pos:m.start()])
        out.append(_cap_word(m.group(0)))
        pos = m.end()
    out.append(token[pos:])
    return "".join(out)


def _title_token(token: str, particles: Set[str], first: bool) -> str:
    """Title Case de un token, respetando partículas, acrónimos y guiones."""
    core = "".join(ch for ch in token if ch.isalpha()).lower()
    if core and not first and core in particles:
        return token.lower()
    return _cap_token(token)


def smart_title(text: str, particles: Set[str]) -> str:
    """
    Title Case "inteligente": conserva acrónimos (IBM, CEO), prefijos de
    apellido (McDonald, O'Brien) y pone en minúscula las partículas
    (de, del, la, of, and...) salvo en la primera palabra.
    """
    tokens = text.split(" ")
    out: List[str] = []
    for i, tok in enumerate(tokens):
        if not tok:
            continue
        out.append(_title_token(tok, particles, first=(i == 0)))
    return " ".join(out)


def title_case_name(text: str, particles: Set[str]) -> str:
    """Title Case para nombres de persona (partículas siempre en minúscula)."""
    return smart_title(text, particles)


def strip_accents_keep(text: str) -> str:
    """Elimina diacríticos manteniendo la ñ como 'n' (opcional, no usado por defecto)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_unicode_dashes(text: str) -> str:
    return _SEPARATORS_RE.sub("-", text)


def slugify_lite(text: str) -> str:
    """Clave de comparación sin acentos, sin puntuación y en minúsculas."""
    s = strip_accents_keep(text.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return collapse_spaces(s)
