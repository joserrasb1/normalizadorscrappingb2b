# -*- coding: utf-8 -*-
"""
rules.py
--------
Diccionarios y patrones de normalización.

Este módulo es la **fuente única de verdad** de las reglas. El motor en
JavaScript que corre en el navegador (`app/static/rules.js`) se genera a
partir de este fichero con `tools/gen_rules_js.py`, y un test verifica que
ambos están sincronizados (así el modo "servidor" y el modo "navegador"
devuelven exactamente el mismo resultado).
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# 1. Formas jurídicas (se eliminan del nombre de empresa)
# ---------------------------------------------------------------------------

# 1.1 Abreviaturas con puntos: "S.L.", "S.L.U.", "B.V.", "S.p.A." ...
#     Se permiten puntos opcionales para tolerar "SLU", "S L U", "S.L.U".
_DOTTED: Dict[str, str] = {
    "SLU": r"s\.?\s?l\.?\s?u\.?",
    "SLSC": r"s\.?\s?l\.?\s?s\.?\s?c\.?",
    "SASU": r"s\.?\s?a\.?\s?s\.?\s?u\.?",
    "SAU": r"s\.?\s?a\.?\s?u\.?",
    "SAPIdeCV": r"s\.?\s?a\.?\s?p\.?\s?i\.?\s?d\.?\s?e\.?\s?c\.?\s?v\.?",
    "SdeRLdeCV": r"s\.?\s?d\.?\s?e\.?\s?r\.?\s?l\.?\s?d\.?\s?e\.?\s?c\.?\s?v\.?",
    "SAdeRL": r"s\.?\s?a\.?\s?d\.?\s?e\.?\s?r\.?\s?l\.?",
    "SAdeCV": r"s\.?\s?a\.?\s?d\.?\s?e\.?\s?c\.?\s?v\.?",
    "SAcoop": r"s\.?\s?a\.?\s?c\.?\s?o\.?\s?o\.?\s?p\.?",
    "SAS": r"s\.?\s?a\.?\s?s\.?",
    "SL": r"s\.?\s?l\.?",
    "SA": r"s\.?\s?a\.?",
    "SCL": r"s\.?\s?c\.?\s?l\.?",
    "SLL": r"s\.?\s?l\.?\s?l\.?",
    "SC": r"s\.?\s?c\.?",
    "EL": r"e\.?\s?l\.?",
    "CV": r"c\.?\s?v\.?",
    "SpA": r"s\.?\s?p\.?\s?a\.?",
    "SrL": r"s\.?\s?r\.?\s?l\.?",
    "BV": r"b\.?\s?v\.?",
    "NV": r"n\.?\s?v\.?",
    "BVBA": r"b\.?\s?v\.?\s?b\.?\s?a\.?",
    "SARL": r"s\.?\s?a\.?\s?r\.?\s?l\.?",
    "EURL": r"e\.?\s?u\.?\s?r\.?\s?l\.?",
    "KG": r"k\.?\s?g\.?",
    "OHG": r"o\.?\s?h\.?\s?g\.?",
    "SpZoo": r"s\.?\s?p\.?\s?z\.?\s?o\.?\s?o\.?",
    "Sapa": r"s\.?\s?a\.?\s?p\.?\s?a\.?",
}

# 1.2 Formas jurídicas escritas con palabras.
#     OJO: NO se incluyen "group", "holdings", "registered" ni "partners":
#     son parte del nombre comercial real ("Grupo Indra", "Acme Holdings").
_WORD_FORMS: List[str] = [
    # España
    "sociedad limitada unipersonal",
    "sociedad de responsabilidad limitada",
    "sociedad limitada",
    "sociedad anonima",
    "sociedad cooperativa",
    "sociedad civil",
    "sociedad profesional",
    "sociedad patrimonial",
    "fundacion", "fundacio", "fundacao", "fundación",
    # Reino Unido / USA
    "incorporated", "limited", "corporation", "company",
    "inc", "llc", "ltd", "corp", "plc", "llp",
    # Alemania / Austria
    "gmbh", "mbh", "aktiengesellschaft", "ag", "kg", "ohg", "gbr", "se",
    # Francia
    "sarl", "sasl", "sas", "sasu", "eurl", "enterprise unipersonnelle",
    # Italia
    "s p a", "s r l", "spa", "srl",
    # Países Bajos / Bélgica
    "b v", "n v", "bv", "nv", "cv", "cvba", "comm v",
    # Nordicos / bálticos
    "aps", "asa", "oy", "oyj", "ehf", "hf", "a s", "k s",
    # Portugal
    "unipessoal lda", "lda",
    # Rusia / emerging
    "ooo", "oao", "zao", "pao", "jsc", "pjsc", "cjsc",
    # Otros
    "pty ltd", "pvt ltd", "pty", "ulc",
]

# 1.3 Formas "débiles": sólo se eliminan si aparecen en MAYÚSCULAS en el
#     original (evita destrozar nombres como "Alfa Co" o "Nova Se").
_WEAK_FORMS: Set[str] = {
    "sa", "sl", "ag", "kg", "se", "ab", "as", "cv", "bv", "nv", "co", "lp",
    "pc", "spa", "srl", "lda", "oy", "hf", "asa", "aps", "ehf", "gbr",
    "jsc", "pjsc", "cjsc", "ooo", "oao", "zao", "pao", "ulc", "sarl", "sas",
    "sasl", "eurl", "mbh", "ltd", "inc", "corp", "llc", "plc", "llp", "pty",
    "pvt", "oyj",
}

# ---------------------------------------------------------------------------
# 2. Sufijos geográficos (se eliminan del final del nombre de empresa)
# ---------------------------------------------------------------------------

GEO_SUFFIXES: List[str] = [
    "united kingdom", "united states", "new zealand", "south africa",
    "north america", "south america", "latin america", "middle east",
    "european union", "european", "europe", "asia pacific", "asia",
    "germany", "deutschland", "france", "italy", "italia", "spain", "espana",
    "portugal", "netherlands", "holland", "belgium", "belgie", "switzerland",
    "schweiz", "austria", "osterreich", "poland", "polska", "sweden", "sverige",
    "norway", "norge", "denmark", "danmark", "finland", "suomi", "ireland",
    "iceland", "greece", "turkey", "turkiye", "russia", "ukraine", "romania",
    "hungary", "czech republic", "czechia", "slovakia", "slovenia", "croatia",
    "serbia", "bulgaria", "estonia", "latvia", "lithuania", "luxembourg",
    "canada", "mexico", "brazil", "brasil", "argentina", "chile", "colombia",
    "peru", "uruguay", "paraguay", "bolivia", "ecuador", "venezuela",
    "costa rica", "panama", "guatemala", "dominican republic", "puerto rico",
    "australia", "india", "china", "japan", "korea", "singapore", "indonesia",
    "thailand", "vietnam", "philippines", "malaysia", "pakistan",
    "emirates", "israel", "egypt", "nigeria", "kenya", "morocco",
    "saudi arabia", "qatar", "kuwait", "global", "international",
    "worldwide", "world wide", "emea", "latam", "apac", "usa", "u s a",
    "u s", "uk", "uae", "mena",
]

# 1.4 Formas jurídicas inequívocas: se eliminan siempre, aunque sean cortas
#     y estén en minúsculas ("Globex ltd", "Acme plc").
_ALWAYS_LEGAL_FORMS: Set[str] = {"inc", "ltd", "co", "corp", "llc", "plc"}


def _build_always_forms() -> Set[str]:
    """
    Construye el conjunto de formas jurídicas que se eliminan siempre.

    Criterio:
    - Formas escritas con palabras de 4+ letras ("company", "gmbh", "sarl").
    - Abreviaturas con punto inequívocas ("S.L.U." -> "slu", "S.p.A." -> "spa").
    - Formas cortas listadas explícitamente en `_ALWAYS_LEGAL_FORMS`.
    """
    forms: Set[str] = set()
    for w in _WORD_FORMS:
        if len(w.replace(" ", "")) >= 4:
            forms.add(w)
    forms.update(_ALWAYS_LEGAL_FORMS)
    for key in _DOTTED:
        letters = re.sub(r"[^a-z]", "", key.lower())
        if len(letters) >= 3:
            forms.add(letters)
    return forms


ALWAYS_LEGAL_FORMS: Set[str] = _build_always_forms()


def is_removable_legal(matched: str) -> bool:
    """
    Decide si una forma jurídica detectada debe eliminarse del nombre.

    - Si lleva puntos ("S.L.", "B.V.") es inequívoca: siempre.
    - Si es larga (>= 4 letras) siempre ("Company", "GmbH", "S.L.U").
    - Si es corta ("SA", "AG", "plc") sólo si aparece en MAYÚSCULAS, para no
      destrozar nombres como "Alfa Co" o "Nova Se".
    """
    text = (matched or "").strip().strip(".")
    if not text:
        return False
    if "." in matched:
        return True
    key = re.sub(r"[^a-z]", "", text.lower())
    if not key:
        return False
    if key in ALWAYS_LEGAL_FORMS:
        return True
    if key in _WEAK_FORMS:
        return text.isupper()
    return len(key) >= 4


# ---------------------------------------------------------------------------
# 3. Títulos y tratamientos (nombre de persona / cargo)
# ---------------------------------------------------------------------------

HONORIFICS: List[str] = [
    "mr", "mrs", "ms", "miss", "mx", "msr", "dr", "dra", "dmd", "phd", "prof",
    "ing", "sr", "sra", "srta", "don", "dona", "doña", "dño", "dña", "lady",
    "lord", "sir", "madam", "maestro", "lic", "master",
]

# Partículas en minúscula en nombres de persona
NAME_PARTICLES: Set[str] = {
    "de", "del", "la", "las", "los", "das", "do", "dos", "da", "di", "van",
    "von", "der", "den", "du", "y", "of", "le", "el", "bin", "ibn", "al",
}

# Partículas en minúscula en cargos (salvo la primera palabra)
TITLE_PARTICLES: Set[str] = {
    "de", "del", "la", "las", "los", "of", "and", "for", "en", "para", "con",
    "y", "e", "a", "the", "in", "on", "at", "to", "por", "sin", "desde",
    "under", "over", "between",
}

# Acrónimos que se conservan en mayúsculas al aplicar Title Case
ACRONYMS: Set[str] = {
    # corporativas / tech
    "ibm", "sap", "hp", "hpe", "dhl", "ups", "fedex", "hsbc", "bbva", "bt",
    "basf", "abb", "sncf", "aig", "axa", "ikea", "lego", "ncr", "nec", "rwe",
    "edf", "cnh", "gsk", "pwc", "deloitte", "kpmg", "mckinsey", "bcg", "bain",
    "boeing", "caterpillar", "siemens", "bosch", "toyota", "honda", "nissan",
    "renault", "peugeot", "citroen", "volvo", "scania", "michelin", "danone",
    "nestle", "unilever", "loreal", "lvmh", "pfizer", "novartis", "roche",
    "astrazeneca", "cisco", "oracle", "adobe", "at&t", "t-mobile", "comcast",
    "shell", "total", "totalenergies", "iberdrola", "repsol", "endesa",
    "naturgy", "accenture", "capgemini", "inditex", "santander", "telefonica",
    "vodafone", "orange", "caixabank", "kpn", "aena", "adif", "renfe",
    "3m", "7-eleven", "gm", "vw", "bmw", "fiat",
    # cargos
    "ceo", "cto", "cfo", "cmo", "coo", "cio", "ciso", "vp", "svp", "evp",
    "md", "hr", "it", "pr", "seo", "sem", "b2b", "b2c", "crm", "erp", "api",
    "ux", "ui", "pm", "qa", "qc", "dev", "ops", "kpi", "kpis", "saas", "gdpr",
    "iso", "mba", "msc", "bsc", "emea", "apac", "latam",
}

# Marcas con casing canónico no derivable de mayúsculas/minúsculas
KNOWN_MIXED_CASE: Dict[str, str] = {
    "ebay": "eBay", "linkedin": "LinkedIn", "youtube": "YouTube",
    "iphone": "iPhone", "ipad": "iPad", "macbook": "MacBook",
    "powerpoint": "PowerPoint", "excel": "Excel", "salesforce": "Salesforce",
    "hubspot": "HubSpot", "shopify": "Shopify", "docusign": "DocuSign",
}

# Prefijos de apellido que conservan la mayúscula interior ("McDonald")
NAME_PREFIXES = ("Mc", "Mac", "O'", "D'", "Van", "Von")

# ---------------------------------------------------------------------------
# 4. Países (para normalizar ubicación)
# ---------------------------------------------------------------------------

COUNTRIES: Dict[str, str] = {
    "espana": "España", "españa": "España", "spain": "España",
    "esp": "España", "es": "España",
    "estados unidos": "Estados Unidos", "united states": "Estados Unidos",
    "usa": "Estados Unidos", "eeuu": "Estados Unidos", "us": "Estados Unidos",
    "reino unido": "Reino Unido", "united kingdom": "Reino Unido",
    "uk": "Reino Unido", "gb": "Reino Unido",
    "alemania": "Alemania", "germany": "Alemania", "de": "Alemania",
    "francia": "Francia", "france": "Francia", "fr": "Francia",
    "italia": "Italia", "italy": "Italia", "it": "Italia",
    "portugal": "Portugal", "pt": "Portugal",
    "paises bajos": "Países Bajos", "netherlands": "Países Bajos",
    "holanda": "Países Bajos", "holland": "Países Bajos",
    "belgica": "Bélgica", "belgium": "Bélgica", "be": "Bélgica",
    "suiza": "Suiza", "switzerland": "Suiza", "ch": "Suiza",
    "austria": "Austria", "at": "Austria",
    "polonia": "Polonia", "poland": "Polonia", "pl": "Polonia",
    "suecia": "Suecia", "sweden": "Suecia", "se": "Suecia",
    "noruega": "Noruega", "norway": "Noruega", "no": "Noruega",
    "dinamarca": "Dinamarca", "denmark": "Dinamarca", "dk": "Dinamarca",
    "finlandia": "Finlandia", "finland": "Finlandia", "fi": "Finlandia",
    "irlanda": "Irlanda", "ireland": "Irlanda", "ie": "Irlanda",
    "canada": "Canadá", "ca": "Canadá",
    "mexico": "México", "méxico": "México", "mx": "México",
    "brasil": "Brasil", "brazil": "Brasil", "br": "Brasil",
    "argentina": "Argentina", "ar": "Argentina",
    "chile": "Chile", "cl": "Chile",
    "colombia": "Colombia", "co": "Colombia",
    "peru": "Perú", "pe": "Perú",
    "australia": "Australia", "au": "Australia",
    "nueva zelanda": "Nueva Zelanda", "new zealand": "Nueva Zelanda",
    "india": "India", "in": "India",
    "china": "China", "cn": "China",
    "japon": "Japón", "japón": "Japón", "jp": "Japón",
    "egipto": "Egipto", "marruecos": "Marruecos", "nigeria": "Nigeria",
    "sudafrica": "Sudáfrica", "south africa": "Sudáfrica",
    "israel": "Israel", "emirates arabes unidos": "Emiratos Árabes Unidos",
    "turquia": "Turquía", "turkey": "Turquía", "tr": "Turquía",
    "rusia": "Rusia", "russia": "Russia", "ucrania": "Ucrania",
}

# Códigos telefónicos por defecto (para formateo E.164)
DEFAULT_COUNTRY_CODE = "34"  # España
COUNTRY_CALLING_CODES: Dict[str, str] = {
    "España": "34", "Estados Unidos": "1", "Reino Unido": "44", "Alemania": "49",
    "Francia": "33", "Italia": "39", "Portugal": "351", "Países Bajos": "31",
    "Bélgica": "32", "Suiza": "41", "Austria": "43", "Polonia": "48",
    "Suecia": "46", "Noruega": "47", "Dinamarca": "45", "Finlandia": "358",
    "Irlanda": "353", "Canadá": "1", "México": "52", "Brasil": "55",
    "Argentina": "54", "Chile": "56", "Colombia": "57", "Perú": "51",
    "Australia": "61", "India": "91", "China": "86", "Japón": "81",
}

# Códigos telefónicos válidos para detectar el prefijo internacional
VALID_CALLING_CODES: Set[str] = set(COUNTRY_CALLING_CODES.values()) | {
    "1", "7", "20", "27", "30", "31", "32", "33", "34", "36", "39", "40", "41",
    "43", "44", "45", "46", "47", "48", "49", "51", "52", "53", "54", "55",
    "56", "57", "58", "60", "61", "62", "63", "64", "66", "81", "82", "84",
    "86", "90", "91", "92", "93", "94", "95", "98",
}

# Dominios de correo con typos frecuentes (para sugerir correcciones)
EMAIL_DOMAIN_TYPOS: Dict[str, str] = {
    "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gmail.co": "gmail.com",
    "gmail.con": "gmail.com", "gmail.cm": "gmail.com", "gnail.com": "gmail.com",
    "gmail.es": "gmail.com", "hotmial.com": "hotmail.com",
    "hotmai.com": "hotmail.com", "hotmail.es": "hotmail.com",
    "outlok.com": "outlook.com", "outlook.es": "outlook.com",
    "yahooo.com": "yahoo.com", "yaho.com": "yahoo.com", "yahoo.es": "yahoo.com",
    "icloud.co": "icloud.com", "icloud.es": "icloud.com",
}

# ---------------------------------------------------------------------------
# 5. Expresiones regulares compuestas
# ---------------------------------------------------------------------------


def _build_legal_pattern() -> str:
    """Alternancia de formas jurídicas, de la más larga a la más corta."""
    alts: List[str] = list(_DOTTED.values())
    alts.extend(re.escape(w) for w in _WORD_FORMS)
    alts.sort(key=len, reverse=True)
    return "(?:" + "|".join(alts) + ")"


def _build_geo_pattern() -> str:
    alts = [re.escape(g) for g in sorted(GEO_SUFFIXES, key=len, reverse=True)]
    return "(?:" + "|".join(alts) + ")"


# Fuentes de los patrones: se exportan a JavaScript para que el motor del
# navegador aplique exactamente las mismas reglas que el servidor.
LEGAL_FORM_SRC = r"(?<![\w&])(?:" + _build_legal_pattern() + r")\.?(?![\w&])"
GEO_SUFFIX_SRC = r"(?<![\w])(?:" + _build_geo_pattern() + r")\.?(?![\w])"
HONORIFIC_SRC = r"^(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\.?\s+"
HONORIFIC_TRAIL_SRC = (
    r"\s+(?:" + "|".join(sorted(HONORIFICS, key=len, reverse=True)) + r")\.?$"
)

LEGAL_FORM_RE = re.compile(LEGAL_FORM_SRC, re.IGNORECASE)
GEO_SUFFIX_RE = re.compile(GEO_SUFFIX_SRC, re.IGNORECASE)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}$")

POSTAL_PREFIX_RE = re.compile(r"^\s*\d{4,6}\s*[-/]?\s*(?=[A-Za-zÀ-ÿ])")

COUNTRY_ALIASES: Dict[str, str] = {k.lower(): v for k, v in COUNTRIES.items()}

# ---------------------------------------------------------------------------
# 6. Metadatos (tipos de columna y etiquetas de las reglas)
# ---------------------------------------------------------------------------

# Palabras clave de cabecera por tipo de columna (se comparan en minúsculas
# y sin acentos). Compartidas con el motor de JavaScript.
HEADER_KEYWORDS: Dict[str, List[str]] = {
    "company": [
        "company name", "company", "empresa", "razon social", "compania",
        "organizacion", "account name", "account", "organization", "org name",
        "dominio", "domain", "website", "sitio web", "nombre comercial",
        "employer", "cliente", "brand", "marca", "institution",
        "nombre de empresa", "legal name",
    ],
    "person": [
        "full name", "contact name", "nombre completo", "nombre", "name",
        "apellidos", "last name", "lastname", "surname", "first name",
        "firstname", "contacto", "contact", "persona", "person", "lead",
        "decision maker", "titular", "representante", "candidato", "candidate",
        "nombre y apellidos",
    ],
    "email": [
        "email", "e mail", "mail", "correo", "correo electronico",
        "correo electronico principal", "work email", "email corporativo",
        "email de contacto", "buzon",
    ],
    "phone": [
        "phone", "telephone", "tel", "telefono", "movil", "celular",
        "whatsapp", "contact number", "numero de telefono", "fax",
        "telefono principal", "ext", "extension",
    ],
    "jobtitle": [
        "job title", "title", "cargo", "puesto", "position", "job", "role",
        "puesto de trabajo", "departamento", "department", "funcional",
        "ocupacion", "posicion", "job role", "titulo", "seniority", "nivel",
    ],
    "location": [
        "location", "ubicacion", "country", "pais", "city", "ciudad",
        "region", "provincia", "country code", "address", "direccion",
        "pais ciudad", "localidad", "town", "state", "estado", "zip",
        "codigo postal",
    ],
}

# Cabeceras inequívocas: si la columna se llama así, el tipo está claro
# aunque el contenido sea ambiguo ("Empresa" -> empresa, no persona).
STRONG_HEADER_KEYWORDS: Dict[str, List[str]] = {
    "company": [
        "empresa", "company", "razon social", "compania", "organizacion",
        "nombre de empresa", "company name", "account name", "dominio",
        "domain", "website", "employer", "institution",
    ],
    "person": [
        "full name", "nombre completo", "nombre y apellidos", "contact name",
        "first name", "last name", "lastname", "apellidos", "surname",
        "persona", "candidato", "candidate", "titular", "representante",
    ],
    "email": [
        "email", "correo", "correo electronico", "mail", "buzon", "work email",
        "email corporativo", "email de contacto",
    ],
    "phone": [
        "phone", "telephone", "telefono", "movil", "celular", "whatsapp",
        "tel", "contact number", "numero de telefono",
    ],
    "jobtitle": [
        "job title", "cargo", "puesto", "position", "departamento",
        "funcional", "titulo", "puesto de trabajo", "seniority", "job role",
    ],
    "location": [
        "location", "ubicacion", "country", "pais", "city", "ciudad",
        "provincia", "address", "direccion", "codigo postal", "country code",
    ],
}

# Términos típicos de un puesto de trabajo (detección por contenido)
JOB_TITLE_WORDS: Set[str] = {
    "ceo", "cto", "cfo", "coo", "cmo", "cio", "vp", "director", "manager",
    "head", "chief", "lead", "founder", "owner", "president", "gerente",
    "responsable", "jefe", "coordinador", "consultor", "analyst", "analista",
    "ingeniero", "developer", "sales", "marketing", "comercial", "ventas",
    "account", "recruiter", "hr", "especialista", "technician", "tecnico",
    "supervisor", "administrador", "partner", "associate", "senior", "junior",
    "staff",
}

# ---------------------------------------------------------------------------
# 5.b Pesos del detector de columnas
# ---------------------------------------------------------------------------
# La combinación de señales vive aquí para que el motor de JavaScript aplique
# exactamente los mismos pesos que el servidor.
#
# - Cabecera fuerte (p. ej. "Empresa"): manda sobre el contenido.
# - Cabecera ambigua (p. ej. "Nombre"): el contenido decide.
# - Contenido fuerte: señal inequívoca (email, teléfono, forma jurídica...).
# - Contenido débil: heurística genérica (columna de nombres propios).
DETECTION_WEIGHTS: Dict[str, float] = {
    "header_strong": 0.85,      # peso de la cabecera cuando es inequívoca
    "content_with_strong_header": 0.15,  # peso del contenido si la cabecera manda
    "header": 0.55,             # peso de la cabecera ambigua
    "content": 0.75,            # peso del contenido fuerte
    "content_weak": 0.30,       # peso del contenido débil
    "bonus_both": 0.15,         # prima si cabecera y contenido coinciden
    "min_score": 0.35,          # por debajo de este valor la columna se ignora
}

COLUMN_TYPES: List[str] = [
    "company", "person", "email", "phone", "jobtitle", "location", "ignore"
]

COLUMN_TYPE_LABELS_ES: Dict[str, str] = {
    "company": "Empresa",
    "person": "Persona",
    "email": "Email",
    "phone": "Teléfono",
    "jobtitle": "Cargo",
    "location": "Ubicación",
    "ignore": "No tocar",
}

RULE_LABELS_ES: Dict[str, str] = {
    "legal_suffix": "Forma jurídica eliminada",
    "geo_suffix": "Sufijo geográfico eliminado",
    "casing": "Mayúsculas normalizadas",
    "whitespace": "Espacios normalizados",
    "punctuation": "Puntuación limpiada",
    "honorific": "Título eliminado",
    "name_order": "Orden nombre corregido",
    "email_case": "Email normalizado",
    "email_typo": "Dominio corregido",
    "email_invalid": "Email no válido",
    "phone_format": "Teléfono formateado",
    "phone_invalid": "Teléfono no válido",
    "title_case": "Cargo normalizado",
    "location_format": "Ubicación normalizada",
    "country_case": "País normalizado",
    "prefix_strip": "Prefijo eliminado",
    "empty": "Valor vacío",
}


def rules_payload() -> Dict[str, object]:
    """Diccionario serializable con todas las reglas (base para el mirror JS)."""
    return {
        "dotted": _DOTTED,
        "word_forms": _WORD_FORMS,
        "weak_forms": sorted(_WEAK_FORMS),
        "always_legal_forms": sorted(_ALWAYS_LEGAL_FORMS),
        "geo_suffixes": GEO_SUFFIXES,
        "honorifics": HONORIFICS,
        "name_particles": sorted(NAME_PARTICLES),
        "title_particles": sorted(TITLE_PARTICLES),
        "acronyms": sorted(ACRONYMS),
        "known_mixed_case": KNOWN_MIXED_CASE,
        "name_prefixes": list(NAME_PREFIXES),
        "countries": COUNTRIES,
        "calling_codes": COUNTRY_CALLING_CODES,
        "valid_calling_codes": sorted(VALID_CALLING_CODES, key=lambda c: (len(c), c)),
        "email_domain_typos": EMAIL_DOMAIN_TYPOS,
        "default_country_code": DEFAULT_COUNTRY_CODE,
        "column_types": COLUMN_TYPES,
        "column_type_labels": COLUMN_TYPE_LABELS_ES,
        "rule_labels": RULE_LABELS_ES,
        "header_keywords": HEADER_KEYWORDS,
        "strong_header_keywords": STRONG_HEADER_KEYWORDS,
        "detection_weights": DETECTION_WEIGHTS,
        "job_title_words": sorted(JOB_TITLE_WORDS),
        "legal_form_src": LEGAL_FORM_SRC,
        "geo_suffix_src": GEO_SUFFIX_SRC,
        "honorific_src": HONORIFIC_SRC,
        "honorific_trail_src": HONORIFIC_TRAIL_SRC,
    }
