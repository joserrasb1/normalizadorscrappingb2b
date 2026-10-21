# -*- coding: utf-8 -*-
"""
engine.py
---------
Orquestador: aplica los normalizadores a una tabla completa y produce
el informe de cambios y las estadísticas de calidad.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .detection import detect_columns
from .normalizers import Options, normalize_value
from .rules import COLUMN_TYPE_LABELS_ES, RULE_LABELS_ES


@dataclass
class TableResult:
    headers: List[str]
    rows: List[List[str]]
    columns: List[Dict[str, object]] = field(default_factory=list)
    changes: List[Dict[str, object]] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)


def normalize_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    options: Optional[Options] = None,
    column_types: Optional[Dict[int, str]] = None,
    preview_rows: int = 0,
    max_changes: int = 5000,
) -> TableResult:
    """
    Normaliza una tabla completa.

    - `column_types`: mapa {índice: tipo}. Si no se indica, se detecta.
    - `preview_rows`: si > 0, sólo se calculan los cambios de las primeras
      N filas (para previsualizar sin coste).
    - `max_changes`: tope de cambios detallados que se guardan.
    """
    opts = options or Options()
    headers = list(headers)
    total_rows = len(rows)

    detected = detect_columns(headers, rows)
    types: Dict[int, str] = {}
    columns: List[Dict[str, object]] = []
    for col in detected:
        idx = int(col["index"])
        forced = (column_types or {}).get(idx)
        ctype = forced or str(col["type"])
        col = dict(col)
        col["applied_type"] = ctype
        col["label"] = COLUMN_TYPE_LABELS_ES.get(ctype, ctype)
        col["forced"] = bool(forced)
        columns.append(col)
        if ctype and ctype != "ignore":
            types[idx] = ctype

    out_rows: List[List[str]] = []
    changes: List[Dict[str, object]] = []
    cells_processed = 0
    cells_changed = 0
    by_rule: Dict[str, int] = {}
    by_column: Dict[str, int] = {}
    empty_cells = 0
    limit = preview_rows if preview_rows and preview_rows > 0 else total_rows

    for r_idx, row in enumerate(rows):
        new_row = list(row)
        if r_idx < limit:
            for c_idx, ctype in types.items():
                if c_idx >= len(row):
                    continue
                original = row[c_idx]
                if original is None:
                    original = ""
                original = str(original)
                if not original.strip():
                    empty_cells += 1
                    continue
                cells_processed += 1
                res = normalize_value(original, ctype, opts)
                if c_idx < len(new_row):
                    new_row[c_idx] = res.value
                if res.changed:
                    cells_changed += 1
                    by_column[str(headers[c_idx]) if c_idx < len(headers) else str(c_idx)] = (
                        by_column.get(
                            str(headers[c_idx]) if c_idx < len(headers) else str(c_idx), 0
                        ) + 1
                    )
                    for ch in res.changes:
                        by_rule[ch.rule] = by_rule.get(ch.rule, 0) + 1
                        if len(changes) < max_changes:
                            changes.append(
                                {
                                    "row": r_idx + 2,  # +1 cabecera, +1 base 1
                                    "column_index": c_idx,
                                    "column": str(headers[c_idx]) if c_idx < len(headers) else "",
                                    "type": ctype,
                                    "rule": ch.rule,
                                    "rule_label": RULE_LABELS_ES.get(ch.rule, ch.rule),
                                    "before": original,
                                    "after": res.value,
                                }
                            )
        out_rows.append(new_row)

    stats: Dict[str, object] = {
        "total_rows": total_rows,
        "total_columns": len(headers),
        "cells_processed": cells_processed,
        "cells_changed": cells_changed,
        "cells_empty": empty_cells,
        "by_rule": by_rule,
        "by_rule_labels": {k: RULE_LABELS_ES.get(k, k) for k in by_rule},
        "by_column": by_column,
        "types_detected": {
            ctype: sum(1 for c in columns if c.get("applied_type") == ctype)
            for ctype in {str(c.get("applied_type")) for c in columns}
        },
    }
    if total_rows:
        # Ojo: `round()` de Python usa redondeo "banker's" (6.25 -> 6.2) mientras
        # que Math.round() de JavaScript redondea siempre hacia arriba (6.25 -> 6.3).
        # Para que el modo navegador y el servidor muestren el mismo %, aquí se
        # replica exactamente el redondeo de JS.
        stats["percent_changed"] = (
            math.floor(1000.0 * cells_changed / max(1, cells_processed) + 0.5) / 10.0
        )

    return TableResult(
        headers=headers,
        rows=out_rows,
        columns=columns,
        changes=changes,
        stats=stats,
    )
