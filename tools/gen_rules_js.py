# -*- coding: utf-8 -*-
"""
gen_rules_js.py
---------------
Genera `app/static/rules.js` a partir de `app/rules.py`.

Uso:
    python -m tools.gen_rules_js          # escribe el fichero
    python -m tools.gen_rules_js --check  # sólo verifica (para CI/tests)

El test `test_rules_js_sync.py` falla si el fichero generado no coincide con
`app/rules.py`, de modo que las reglas del navegador y las del servidor no
pueden divergir sin que se note.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rules import rules_payload  # noqa: E402

TARGET = ROOT / "app" / "static" / "rules.js"

HEADER = """/* GENERATED FILE - DO NOT EDIT BY HAND.
 * Source: app/rules.py   Regenerate: python -m tools.gen_rules_js
 * El motor del navegador y el del servidor comparten estas reglas.
 */
window.RULES = %s;
"""


def render() -> str:
    payload = rules_payload()
    return HEADER % json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera rules.js desde rules.py")
    parser.add_argument("--check", action="store_true", help="sólo verificar")
    args = parser.parse_args()

    content = render()
    if args.check:
        if not TARGET.exists():
            print("FALLO: falta %s" % TARGET)
            return 1
        if TARGET.read_text(encoding="utf-8") != content:
            print("FALLO: rules.js desactualizado. Ejecuta: python -m tools.gen_rules_js")
            return 1
        print("OK: rules.js sincronizado con rules.py")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print("Escrito %s (%d bytes)" % (TARGET, len(content.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
