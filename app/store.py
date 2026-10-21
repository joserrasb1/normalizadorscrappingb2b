# -*- coding: utf-8 -*-
"""
store.py
--------
Almacén en memoria con caducidad para los resultados de la última
normalización (para poder descargar CSV/XLSX/JSON después del POST).

No se persiste nada en disco: los datos se olvidan pasado el TTL. Cada
usuario tiene su propia entrada (clave aleatoria), de modo que dos
personas normalizando a la vez no se pisan.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Dict, Optional

TTL_SECONDS = 15 * 60  # 15 minutos
MAX_ENTRIES = 50


class ResultStore:
    """Almacén en memoria, seguro para hilos, con TTL y tope de entradas."""

    def __init__(self, ttl: int = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max = max_entries

    def _purge(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if now - v["ts"] > self._ttl]
        for k in expired:
            self._data.pop(k, None)
        if len(self._data) > self._max:
            ordered = sorted(self._data.items(), key=lambda kv: kv[1]["ts"])
            for k, _ in ordered[: len(self._data) - self._max]:
                self._data.pop(k, None)

    def put(self, payload: Dict[str, Any]) -> str:
        self._purge()
        key = secrets.token_urlsafe(16)
        with self._lock:
            self._data[key] = {"ts": time.time(), "payload": payload}
        return key

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if time.time() - entry["ts"] > self._ttl:
                self._data.pop(key, None)
                return None
            return entry["payload"]

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


store = ResultStore()
