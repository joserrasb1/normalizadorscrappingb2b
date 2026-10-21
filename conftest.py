# -*- coding: utf-8 -*-
"""
conftest.py
-----------
Fixtures comunes para la suite de tests del Normalizador B2B.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.normalizers import Options  # noqa: E402


@pytest.fixture
def opts() -> Options:
    """Opciones por defecto del normalizador."""
    return Options()


@pytest.fixture
def client():
    """TestClient de FastAPI para la API."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as c:
        yield c
