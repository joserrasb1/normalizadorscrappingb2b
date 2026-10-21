# -*- coding: utf-8 -*-
"""
detection.py
------------
Detección automática del tipo de cada columna de una tabla de prospectos.

Combina tres señales:

  1. La cabecera ("Email", "Company Name", "Razón social"...). Si la cabecera
     es inequívoca ("Empresa", "Email", "Cargo"...) manda sobre el contenido.
     Si es ambigua ("Nombre", "Contacto") decide el contenido.
  2. El contenido de las celdas (regex, densidad de dígitos, listas de cargos,
     formato "ciudad, país"...).
  3. Las formas jurídicas: un valor con "S.L.U." es el nombre de una empresa,
     nunca el de una persona.

Los pesos de combinación viven en `rules.DETECTION_WEIGHTS` para que el motor
de JavaScript (`app/static/engine.js`) aplique exactamente los mismos.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .rules import (
    COUNTRY_ALIASES,
    DETECTION_WEIGHTS,
    EMAIL_RE,
    HEADER_KEYWORDS,
    HONORIFICS,
    JOB_TITLE_WORDS,
    LEGAL_FORM_RE,
    STRONG_HEADER_KEYWORDS,
    is_removable_legal,
)
from .text_utils import strip_accents_keep

# Palabras clave de cabecera por tipo (definidas en rules.py para que el
# motor de JavaScript aplique exactamente las mismas).
_HEADER_KEYWORDS = HEADER_KEYWORDS
_STRONG_HEADER_KEYWORDS = STRONG_HEADER_KEYWORDS

# Patrones de contenido
_PHONE_CLEAN_RE = re.compile(r"[\s()+\-.]")
_DIGIT_RE = re.compile(r"\d")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")

_HONORIFIC_RE = re.compile(
    r"^(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\.?\s+",
    re.IGNORECASE,
)

# Nombre de persona en Title Case: 2-4 palabras capitalizadas, sin dígitos.
_TITLE_CASE_NAME_RE = re.compile(
    r"^[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü'’\-]+(?:\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü'’\-]+){1,3}$"
)

_COUNTRY_NAMES = set(COUNTRY_ALIASES.keys())

# Orden de preferencia para desempatar de forma determinista.
_TYPE_PRIORITY = ["company", "person", "email", "phone", "jobtitle", "location"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _tokens(text: str) -> List[str]:
    """Divide un texto en tokens normalizados (sin acentos ni puntuación)."""
    s = strip_accents_keep(str(text or "")).lower()
    s = _NON_WORD_RE.sub(" ", s)
    return [t for t in s.split() if t]


def _match_keyword(header_tokens: Sequence[str], kw_tokens: Sequence[str]) -> Optional[float]:
    """
    Fuerza del match entre una cabecera y una palabra clave.

    - 1.0 si la cabecera es exactamente la palabra clave.
    - 0.6-0.9 si la palabra clave aparece como frase dentro de la cabecera.
    - None si no aparece.
    """
    if not kw_tokens or len(kw_tokens) > len(header_tokens):
        return None
    n = len(kw_tokens)
    for i in range(len(header_tokens) - n + 1):
        if list(header_tokens[i:i + n]) == list(kw_tokens):
            if n == len(header_tokens):
                return 1.0
            return min(0.9, 0.6 + 0.1 * n)
    return None


def _header_score(name: str) -> Tuple[Dict[str, float], Set[str]]:
    """
    Puntúa cada tipo según la cabecera.

    Devuelve (puntuaciones, tipos con cabecera inequívoca).
    """
    tokens = _tokens(name)
    scores: Dict[str, float] = {}
    strong: Set[str] = set()
    if not tokens:
        return scores, strong

    for ctype, keywords in _HEADER_KEYWORDS.items():
        best = 0.0
        for kw in keywords:
            kw_tokens = _tokens(kw)
            value = _match_keyword(tokens, kw_tokens)
            if value is not None:
                best = max(best, value)
        if best:
            scores[ctype] = best

    for ctype, keywords in _STRONG_HEADER_KEYWORDS.items():
        for kw in keywords:
            if _match_keyword(tokens, _tokens(kw)) is not None:
                strong.add(ctype)
                break

    return scores, strong


def _sample(values: Sequence[str], limit: int = 40) -> List[str]:
    out: List[str] = []
    for v in values:
        s = str(v or "").strip()
        if s:
            out.append(s)
            if len(out) >= limit:
                break
    return out


def _has_legal_form(value: str) -> bool:
    """True si el valor contiene una forma jurídica eliminable."""
    for m in LEGAL_FORM_RE.finditer(value or ""):
        if is_removable_legal(m.group(0)):
            return True
    return False


def _looks_like_person(value: str) -> bool:
    """
    Heurística de nombre de persona.

    Acepta "Juan Pérez", "GARCÍA, JOSÉ ANTONIO" y "Mr. John Smith", pero
    rechaza "Iberdrola, S.A." (lleva forma jurídica).
    """
    v = str(value or "").strip()
    if not v:
        return False
    if _has_legal_form(v):
        return False
    v = _HONORIFIC_RE.sub("", v).strip()
    if not v:
        return False
    if v.count(",") == 1:
        left, right = v.split(",")
        if left.strip() and right.strip():
            return True
    return bool(_TITLE_CASE_NAME_RE.match(v))


def _content_scores(sample: List[str]) -> Tuple[Dict[str, float], Set[str]]:
    """
    Puntúa cada tipo según el contenido de las celdas.

    Devuelve (puntuaciones, tipos con señal de contenido fuerte). La señal
    fuerte (email, teléfono, forma jurídica...) pesa mucho más que la
    heurística débil de "columna de nombres propios".
    """
    scores: Dict[str, float] = {}
    strong: Set[str] = set()
    if not sample:
        return scores, strong
    n = len(sample)

    emails = sum(1 for v in sample if EMAIL_RE.match(v))
    if emails / n >= 0.6:
        scores["email"] = emails / n
        strong.add("email")

    phones = 0
    for v in sample:
        digits = len(_DIGIT_RE.findall(_PHONE_CLEAN_RE.sub("", v)))
        if digits >= 7 and digits >= 0.5 * len(v.replace(" ", "")):
            phones += 1
    if phones / n >= 0.6:
        scores["phone"] = phones / n
        strong.add("phone")

    # Nombres de persona: 2-4 palabras capitalizadas o formato "Apellido, Nombre"
    persons = sum(1 for v in sample if _looks_like_person(v))
    if persons / n >= 0.6:
        scores["person"] = persons / n
        strong.add("person")

    # Ubicación: contiene un país conocido o un patrón "ciudad, país"
    locs = 0
    for v in sample:
        parts = [p.strip().lower() for p in v.split(",") if p.strip()]
        if any(p in _COUNTRY_NAMES for p in parts):
            locs += 1
        elif len(parts) == 2 and all(p.replace(" ", "").isalpha() for p in parts):
            locs += 0.5
    if locs / n >= 0.6:
        scores["location"] = min(1.0, locs / n)
        strong.add("location")

    # Cargo: contiene términos típicos de puesto
    jobs = 0
    for v in sample:
        words = set(re.findall(r"[a-záéíóúñü]+", v.lower()))
        if words & JOB_TITLE_WORDS:
            jobs += 1
    if jobs / n >= 0.6:
        scores["jobtitle"] = jobs / n
        strong.add("jobtitle")

    # Empresa: forma jurídica (señal fuerte e inequívoca)
    legal = sum(1 for v in sample if _has_legal_form(v))
    if legal / n >= 0.5:
        scores["company"] = legal / n
        strong.add("company")
        return scores, strong

    # Empresa: heurística débil (columna de nombres propios sin forma jurídica)
    others = max(
        [scores.get(k, 0.0) for k in ("email", "phone", "person", "location", "jobtitle")]
        or [0.0]
    )
    if others < 0.5:
        caps = sum(1 for v in sample if v[:1].isupper() and len(v.split()) >= 1)
        if caps / n >= 0.5:
            scores["company"] = 0.5

    return scores, strong


def detect_column(name: str, values: Sequence[str]) -> Dict[str, object]:
    """Detecta el tipo de una columna y su confianza (0-1)."""
    h_scores, strong_header = _header_score(name)
    c_scores, strong_content = _content_scores(_sample(values))

    w = DETECTION_WEIGHTS
    combined: Dict[str, float] = {}
    for ctype in set(h_scores) | set(c_scores):
        h = h_scores.get(ctype, 0.0)
        c = c_scores.get(ctype, 0.0)
        if ctype in strong_header:
            # La cabecera es inequívoca: manda sobre el contenido.
            score = h * w["header_strong"] + c * w["content_with_strong_header"]
        else:
            # Cabecera ambigua: el contenido decide (con más peso).
            c_weight = w["content"] if ctype in strong_content else w["content_weak"]
            score = h * w["header"] + c * c_weight
            if h > 0 and c > 0:
                score += w["bonus_both"]  # ambas señales coinciden
        combined[ctype] = round(score, 3)

    if not combined:
        return {"type": "ignore", "confidence": 0.0, "reason": "sin pistas"}

    def _rank(ctype: str):
        priority = _TYPE_PRIORITY.index(ctype) if ctype in _TYPE_PRIORITY else 99
        return (
            combined[ctype],
            1 if ctype in strong_header else 0,
            -priority,
        )

    best_type = max(sorted(combined), key=_rank)
    best_score = combined[best_type]
    reason = []
    if best_type in h_scores:
        reason.append("cabecera")
    if best_type in c_scores:
        reason.append("contenido")

    if best_score < w["min_score"]:
        return {
            "type": "ignore",
            "confidence": round(1.0 - best_score, 3),
            "reason": "no se reconoce el tipo",
            "scores": combined,
        }

    return {
        "type": best_type,
        "confidence": round(min(1.0, best_score), 3),
        "reason": " + ".join(reason) or "heurística",
        "scores": combined,
    }


def detect_columns(
    headers: Sequence[str], rows: Sequence[Sequence[str]]
) -> List[Dict[str, object]]:
    """Detecta el tipo de todas las columnas de la tabla."""
    out: List[Dict[str, object]] = []
    ncols = len(headers)
    for i in range(ncols):
        name = headers[i] if i < len(headers) else ""
        values = [r[i] for r in rows if i < len(r)]
        det = detect_column(name, values)
        out.append(
            {
                "index": i,
                "name": name,
                "type": det["type"],
                "confidence": det["confidence"],
                "reason": det.get("reason", ""),
            }
        )
    return out
