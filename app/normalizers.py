# -*- coding: utf-8 -*-
"""
normalizers.py
--------------
Normalizadores por tipo de columna. Todos son deterministas (RegEx + reglas)
y devuelven el valor limpio junto con la lista de cambios aplicados, para
poder mostrar un diff "antes → después" y un informe de calidad.

Cada función es pura: `f(valor, opciones) -> Resultado`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .rules import (
    ACRONYMS,
    COUNTRY_ALIASES,
    DEFAULT_COUNTRY_CODE,
    EMAIL_DOMAIN_TYPOS,
    EMAIL_RE,
    GEO_SUFFIX_RE,
    HONORIFICS,
    LEGAL_FORM_RE,
    NAME_PARTICLES,
    POSTAL_PREFIX_RE,
    TITLE_PARTICLES,
    VALID_CALLING_CODES,
    is_removable_legal,
)
from .text_utils import (
    clean_text,
    collapse_spaces,
    is_all_caps,
    is_all_lower,
    is_mostly_caps,
    smart_title,
    strip_edge_punctuation,
)

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


@dataclass
class Change:
    """Un cambio aplicado a un valor."""

    rule: str
    before: str
    after: str

    def as_dict(self) -> Dict[str, str]:
        return {"rule": self.rule, "before": self.before, "after": self.after}


@dataclass
class Result:
    """Resultado de normalizar un valor."""

    original: str
    value: str
    changes: List[Change] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.value != self.original

    def as_dict(self) -> Dict[str, object]:
        return {
            "original": self.original,
            "value": self.value,
            "changed": self.changed,
            "changes": [c.as_dict() for c in self.changes],
        }


@dataclass
class Options:
    """Opciones del proceso de normalización."""

    remove_legal: bool = True
    remove_geo: bool = True
    remove_articles: bool = True
    title_case: bool = True
    fix_email_typos: bool = True
    gmail_dots: bool = False
    strip_plus_tags: bool = False
    phone_format: str = "auto"  # auto | national | e164 | international | raw
    default_country_code: str = DEFAULT_COUNTRY_CODE

    def as_dict(self) -> Dict[str, object]:
        return {
            "remove_legal": self.remove_legal,
            "remove_geo": self.remove_geo,
            "remove_articles": self.remove_articles,
            "title_case": self.title_case,
            "fix_email_typos": self.fix_email_typos,
            "gmail_dots": self.gmail_dots,
            "strip_plus_tags": self.strip_plus_tags,
            "phone_format": self.phone_format,
            "default_country_code": self.default_country_code,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, object]]) -> "Options":
        data = data or {}
        opts = cls()
        for key in (
            "remove_legal", "remove_geo", "remove_articles", "title_case",
            "fix_email_typos", "gmail_dots", "strip_plus_tags",
        ):
            if key in data:
                setattr(opts, key, bool(data[key]))
        if "phone_format" in data:
            val = str(data["phone_format"])
            if val in ("auto", "national", "e164", "international", "raw"):
                opts.phone_format = val
        if "default_country_code" in data:
            cc = re.sub(r"\D", "", str(data["default_country_code"]))
            if cc:
                opts.default_country_code = cc
        return opts


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

_EDGE_SEPARATORS = " \t,;.-_/|·•&"

_HONORIFIC_RE = re.compile(
    r"^(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\.?\s+",
    re.IGNORECASE,
)
_HONORIFIC_TRAIL_RE = re.compile(
    r"\s+(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\.?$",
    re.IGNORECASE,
)
_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)(?:/.*)?$",
    re.IGNORECASE,
)
_PARENS_RE = re.compile(r"^(.+?)\s*\((.+)\)\s*$")
_EXT_RE = re.compile(r"(?:ext|ext\.?|x|#|anexo)\s*(\d{1,6})\s*$", re.IGNORECASE)


def _strip_legal_forms(text: str, changes: List[Change]) -> str:
    """Elimina formas jurídicas situadas al principio o al final."""
    changed = True
    while changed:
        changed = False
        for m in reversed(list(LEGAL_FORM_RE.finditer(text))):
            matched = m.group(0)
            if not is_removable_legal(matched):
                continue
            head = text[: m.start()].strip(_EDGE_SEPARATORS)
            tail = text[m.end():].strip(_EDGE_SEPARATORS)
            if head and not tail:  # al final
                new = text[: m.start()].rstrip(_EDGE_SEPARATORS)
                changes.append(Change("legal_suffix", matched.strip(), ""))
                text = new
                changed = True
                break
            if tail and not head:  # al principio
                new = text[m.end():].lstrip(_EDGE_SEPARATORS)
                changes.append(Change("legal_suffix", matched.strip(), ""))
                text = new
                changed = True
                break
    return text


def _strip_geo_suffix(text: str, changes: List[Change]) -> str:
    """Elimina el sufijo geográfico final ("... Europe", "... Spain")."""
    changed = True
    while changed:
        changed = False
        for m in reversed(list(GEO_SUFFIX_RE.finditer(text))):
            head = text[: m.start()].strip(_EDGE_SEPARATORS)
            tail = text[m.end():].strip(_EDGE_SEPARATORS)
            if head and not tail:  # sólo al final
                new = text[: m.start()].rstrip(_EDGE_SEPARATORS)
                changes.append(Change("geo_suffix", m.group(0).strip(), ""))
                text = new
                changed = True
                break
    return text


def _tidy(text: str) -> str:
    """Limpieza final: comas sueltas, dobles espacios, separadores."""
    s = collapse_spaces(text)
    s = re.sub(r"\s*,\s*,\s*", ", ", s)
    s = re.sub(r"^\s*,\s*", "", s)
    s = re.sub(r"\s*,\s*$", "", s)
    s = re.sub(r"\s*&\s*$", "", s)
    s = re.sub(r"\s*-\s*$", "", s)
    return s.strip()


def _record_if_changed(changes: List[Change], rule: str, before: str, after: str) -> None:
    if before != after:
        changes.append(Change(rule, before, after))


# ---------------------------------------------------------------------------
# 1. Empresa
# ---------------------------------------------------------------------------


def normalize_company(raw: str, opts: Options = Options()) -> Result:
    """Normaliza el nombre de una empresa: formas jurídicas, sufijos, casing."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    # 1) URL -> dominio
    m = _URL_RE.match(value)
    if m and "." in m.group(1):
        domain = m.group(1)
        root = domain.split(".")[0]
        if root and root.lower() != domain.lower():
            _record_if_changed(changes, "prefix_strip", value, root)
            value = root

    # 2) Formas jurídicas
    if opts.remove_legal:
        stripped = _strip_legal_forms(value, changes)
        if stripped:
            value = stripped

    # 3) Sufijo geográfico
    if opts.remove_geo:
        stripped = _strip_geo_suffix(value, changes)
        if stripped:
            value = stripped

    value = _tidy(value)

    # 4) Artículo inicial ("The ...")
    if opts.remove_articles:
        m = re.match(r"^(?:the|The)\s+(.+)$", value)
        if m and len(value.split()) > 1:
            _record_if_changed(changes, "prefix_strip", value, m.group(1))
            value = m.group(1)

    # 5) Mayúsculas -> Title Case (si el texto venía en mayúsculas)
    if opts.title_case and is_mostly_caps(value):
        new = smart_title(value, TITLE_PARTICLES)
        _record_if_changed(changes, "casing", value, new)
        value = new

    # 6) Limpieza final
    value = _tidy(strip_edge_punctuation(value))
    if not value:
        value = _tidy(strip_edge_punctuation(clean_text(original))) or original

    return Result(original=original, value=value, changes=changes)


# ---------------------------------------------------------------------------
# 2. Persona
# ---------------------------------------------------------------------------


def normalize_person(raw: str, opts: Options = Options()) -> Result:
    """Normaliza el nombre de una persona: títulos, orden apellido-nombre."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    # 1) Títulos al principio ("Mr. ", "Dra. ")
    new = _HONORIFIC_RE.sub("", value)
    if new != value:
        changes.append(Change("honorific", value[: len(value) - len(new)].strip(), ""))
        value = new.strip()

    # 2) Títulos al final
    new = _HONORIFIC_TRAIL_RE.sub("", value)
    if new != value:
        changes.append(Change("honorific", value[len(new):].strip(), ""))
        value = new.strip()

    # 3) Orden "Apellido, Nombre" -> "Nombre Apellido"
    if value.count(",") == 1:
        left, right = value.split(",")
        left, right = left.strip(), right.strip()
        if left and right:
            candidate = f"{right} {left}"
            _record_if_changed(changes, "name_order", value, candidate)
            value = candidate

    value = _tidy(value)

    # 4) Mayúsculas (si venía todo en mayúsculas o todo en minúsculas)
    if opts.title_case and (is_mostly_caps(value) or is_all_lower(value)):
        new = smart_title(value, NAME_PARTICLES)
        _record_if_changed(changes, "casing", value, new)
        value = new

    value = _tidy(strip_edge_punctuation(value))
    if not value:
        value = clean_text(original)

    return Result(original=original, value=value, changes=changes)


# ---------------------------------------------------------------------------
# 3. Email
# ---------------------------------------------------------------------------


def normalize_email(raw: str, opts: Options = Options()) -> Result:
    """Normaliza una dirección de correo."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    value = value.strip("<>").strip().strip("'\"")
    if value.lower().startswith("mailto:"):
        value = value[7:].strip()
    value = value.replace(" ", "")

    lowered = value.lower()
    if lowered != value:
        changes.append(Change("email_case", value, lowered))
        value = lowered

    local, sep, domain = value.partition("@")
    if sep and domain:
        # Puntos sobrantes al inicio/final de la parte local
        fixed_local = local.strip(".")
        if fixed_local != local:
            _record_if_changed(changes, "email_case", local, fixed_local)
            local = fixed_local
        value = f"{local}@{domain}"

        if not EMAIL_RE.match(value):
            changes.append(Change("email_invalid", original, value))
            return Result(original=original, value=value, changes=changes)

        # Typo de dominio conocido
        if opts.fix_email_typos and domain in EMAIL_DOMAIN_TYPOS:
            fixed_domain = EMAIL_DOMAIN_TYPOS[domain]
            fixed = f"{local}@{fixed_domain}"
            changes.append(Change("email_typo", value, fixed))
            value = fixed
            local, domain = local, fixed_domain

        # Etiqueta "+tag" y puntos de Gmail
        if opts.strip_plus_tags and "+" in local:
            new_local = local.split("+", 1)[0]
            if new_local:
                fixed = f"{new_local}@{domain}"
                changes.append(Change("email_case", value, fixed))
                value = fixed
                local = new_local
        if opts.gmail_dots and domain == "gmail.com" and "." in local:
            new_local = local.replace(".", "")
            fixed = f"{new_local}@{domain}"
            changes.append(Change("email_case", value, fixed))
            value = fixed

    else:
        changes.append(Change("email_invalid", original, value))

    return Result(original=original, value=value, changes=changes)


# ---------------------------------------------------------------------------
# 4. Teléfono
# ---------------------------------------------------------------------------

_VALID_CALLING_CODES = VALID_CALLING_CODES


def _split_country_code(
    digits: str, default_cc: str, explicit_intl: bool = False
) -> tuple[Optional[str], str]:
    """Separa prefijo internacional y número nacional."""
    if not digits:
        return None, ""
    # 00 34 ...  -> equivalente a +34
    if digits.startswith("00"):
        rest = digits[2:]
        cc, nat = _split_country_code(rest, default_cc, True)
        return cc, nat
    if explicit_intl:
        # El usuario ya escribió el prefijo internacional: se busca el código
        # más largo que encaje ("+44 20 7946 0958" -> 44 / 2079460958).
        for size in (3, 2, 1):
            cc = digits[:size]
            if cc in _VALID_CALLING_CODES:
                nat = digits[size:]
                if 7 <= len(nat) <= 12:
                    return cc, nat
        return None, digits
    # Formato internacional [+34] 612345678
    if len(digits) == 11 and digits.startswith("34") and digits[2] in "6789":
        return "34", digits[2:]
    if len(digits) == 11 and digits.startswith("1"):
        return "1", digits[1:]
    for size in (3, 2, 1):
        cc = digits[:size]
        nat = digits[size:]
        if len(nat) == 9 and nat[0] in "6789" and cc in _VALID_CALLING_CODES:
            return cc, nat
    if default_cc and digits.startswith(default_cc):
        nat = digits[len(default_cc):]
        if len(nat) == 9:
            return default_cc, nat
    return None, digits


def _group_national(number: str) -> str:
    """Agrupa el número nacional: 9 dígitos -> 3-3-3 (ES), 10 -> 3-3-4 (US)."""
    if len(number) == 9:
        return f"{number[0:3]} {number[3:6]} {number[6:9]}"
    if len(number) == 10:
        return f"{number[0:3]} {number[3:6]} {number[6:10]}"
    return number


def normalize_phone(raw: str, opts: Options = Options()) -> Result:
    """Normaliza un teléfono a un formato consistente (E.164 o nacional)."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    ext = ""
    m = _EXT_RE.search(value)
    if m:
        ext = m.group(1)
        value = value[: m.start()].strip()

    has_plus = "+" in value
    digits = re.sub(r"\D", "", value)
    explicit_intl = has_plus

    if not digits:
        changes.append(Change("phone_invalid", original, value))
        return Result(original=original, value=value, changes=changes)

    # Prefijo 00 internacional
    if digits.startswith("00") and len(digits) > 10:
        digits = digits[2:]
        explicit_intl = True

    cc, national = _split_country_code(digits, opts.default_country_code, explicit_intl)

    # Número nacional español sin prefijo
    if cc is None:
        if len(national) == 10 and national[0] == "0":
            national = national[1:]
        if len(national) == 10 and national[0] == "8":
            national = national[1:]

    fmt = opts.phone_format
    if fmt == "auto":
        if explicit_intl:
            # El usuario ya había indicado el prefijo internacional: se respeta
            fmt = "international"
        elif cc is None or cc == opts.default_country_code:
            fmt = "national"
        else:
            fmt = "e164"

    if fmt == "raw":
        out = digits
    elif fmt == "e164":
        out = ("+" + (cc or opts.default_country_code) + national) if national else digits
    elif fmt == "international":
        out = ("+" + (cc or opts.default_country_code) + " " + _group_national(national)) if national else digits
    else:  # national
        if cc is None or cc == opts.default_country_code:
            out = _group_national(national)
        else:
            out = ("+" + cc + " " + _group_national(national)) if national else digits

    out = out.strip()
    if ext:
        out = f"{out} ext. {ext}"

    _record_if_changed(changes, "phone_format", original, out)
    return Result(original=original, value=out, changes=changes)


# ---------------------------------------------------------------------------
# 5. Cargo / puesto
# ---------------------------------------------------------------------------

_JOB_NOISE_RE = re.compile(r"\s*[-–—|/]\s*$")


def normalize_jobtitle(raw: str, opts: Options = Options()) -> Result:
    """Normaliza el cargo: Title Case respetando partículas y acrónimos."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    value = _JOB_NOISE_RE.sub("", value)

    if opts.title_case and (is_all_caps(value) or is_all_lower(value)):
        new = smart_title(value, TITLE_PARTICLES)
        _record_if_changed(changes, "title_case", value, new)
        value = new

    value = _tidy(strip_edge_punctuation(value))
    if not value:
        value = clean_text(original)

    return Result(original=original, value=value, changes=changes)


# ---------------------------------------------------------------------------
# 6. Ubicación
# ---------------------------------------------------------------------------


def _is_country(text: str) -> bool:
    return text.strip().lower() in COUNTRY_ALIASES


def normalize_location(raw: str, opts: Options = Options()) -> Result:
    """Normaliza la ubicación: código postal, orden ciudad/país, mayúsculas."""
    original = "" if raw is None else str(raw)
    value = clean_text(original)
    changes: List[Change] = []

    if not value:
        return Result(original=original, value=value, changes=changes)

    # 1) Código postal inicial
    m = POSTAL_PREFIX_RE.match(value)
    if m:
        new = value[m.end():].strip()
        if new:
            _record_if_changed(changes, "prefix_strip", value, new)
            value = new

    # 2) "España (Madrid)" -> "Madrid, España"
    m = _PARENS_RE.match(value)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        if left and right:
            if _is_country(left) and not _is_country(right):
                new = f"{right}, {left}"
                _record_if_changed(changes, "location_format", value, new)
                value = new
            elif _is_country(right) and not _is_country(left):
                new = f"{left}, {right}"
                _record_if_changed(changes, "location_format", value, new)
                value = new

    # 3) Separado por comas: conservar ciudad y país
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) >= 2:
        if _is_country(parts[-1]):
            new = f"{parts[0]}, {parts[-1]}"
            if new != value:
                _record_if_changed(changes, "location_format", value, new)
                value = new
        elif _is_country(parts[0]):
            new = f"{parts[-1]}, {parts[0]}"
            if new != value:
                _record_if_changed(changes, "location_format", value, new)
                value = new

    value = _tidy(value)

    # 4) Mayúsculas
    if opts.title_case and is_all_caps(value):
        new = smart_title(value, TITLE_PARTICLES)
        _record_if_changed(changes, "country_case", value, new)
        value = new

    value = _tidy(strip_edge_punctuation(value))
    if not value:
        value = clean_text(original)

    return Result(original=original, value=value, changes=changes)


# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------

NORMALIZERS = {
    "company": normalize_company,
    "person": normalize_person,
    "email": normalize_email,
    "phone": normalize_phone,
    "jobtitle": normalize_jobtitle,
    "location": normalize_location,
}


def normalize_value(value: str, kind: str, opts: Optional[Options] = None) -> Result:
    """Normaliza un valor según el tipo de columna indicado."""
    opts = opts or Options()
    fn = NORMALIZERS.get(kind)
    if fn is None:
        return Result(original="" if value is None else str(value), value="" if value is None else str(value))
    return fn("" if value is None else str(value), opts)
