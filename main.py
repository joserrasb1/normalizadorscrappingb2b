# -*- coding: utf-8 -*-
"""
main.py
-------
Aplicación FastAPI del Normalizador de Datos para Scraping / BBDD B2B.

Arquitectura híbrida:
- Modo servidor (API): sube CSV/TSV/TXT/XLSX -> se procesa en memoria
  con el motor Python -> devuelve JSON + previsualización + descargas CSV/XLSX/JSON.
- Modo navegador (cliente): la misma página carga rules.js + engine.js +
  csv.js + xlsx.js (código propio, sin librerías externas) y procesa el
  fichero 100% en local con FileReader. No se envía ningún fichero al
  servidor en ese modo. Privacidad máxima.

Sin almacenamiento persistente. Los resultados se guardan 15 minutos en
memoria con clave aleatoria y se borran al expirar.
"""

from __future__ import annotations

import io
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.detection import detect_columns
from app.engine import normalize_table
from app.normalizers import Options
from app.security import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    check_content_security,
    check_filename_security,
    secure_filename,
    secure_http_headers,
)
from app.store import store
from app.tabular import (
    decode_bytes,
    parse_csv_text,
    read_table,
    to_json_rows,
    write_csv,
    write_xlsx,
)
from app.auth.router import router as auth_router
from app.db.base import Base
from app.db.session import engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rechaza requests con Content-Length superior al límite y añade cabeceras."""

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Payload demasiado grande (máx %d bytes)" % MAX_UPLOAD_BYTES},
                    )
            except ValueError:
                pass
        response = await call_next(request)
        for k, v in secure_http_headers():
            response.headers[k] = v
        return response


app = FastAPI(
    title="Data Cleaner B2B — Normalizador de Datos para Scraping",
    description=(
        "Limpia y normaliza nombres de empresa, contactos, emails, teléfonos, "
        "cargos y ubicaciones. Sin almacenamiento. POC con pruebas gratuitas."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(BodySizeLimitMiddleware)

# Crear tablas al inicio (para dev con sqlite, en prod usar Alembic)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

app.include_router(auth_router)

# --- CORS ---------------------------------------------------------------
# La landing puede servirse desde Cloudflare Pages (otro dominio) y llamar a
# esta API. La API es pública, sin cookies ni credenciales, así que por
# defecto se permite cualquier origen; en producción conviene acotarlo:
#   ALLOWED_ORIGINS="https://tu-landing.pages.dev,https://tu-dominio.com"
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Archivos estáticos (rules.js, engine.js)
static_dir = os.path.join(BASE_DIR, "app", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Landing page con demo híbrida (servidor + navegador)."""
    html_path = os.path.join(BASE_DIR, "app", "templates", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body><h1>Data Cleaner B2B</h1><p>Falta app/templates/index.html</p></body></html>"


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        content={"status": "ok", "service": "data-cleaner-b2b", "version": __version__}
    )


@app.post("/api/clean")
async def clean_upload(
    file: UploadFile = File(...),
    column_types: Optional[str] = Form(None),
    remove_legal: bool = Form(True),
    remove_geo: bool = Form(True),
    remove_articles: bool = Form(True),
    title_case: bool = Form(True),
    fix_email_typos: bool = Form(True),
    gmail_dots: bool = Form(False),
    strip_plus_tags: bool = Form(False),
    phone_format: str = Form("auto"),
    default_country_code: str = Form("34"),
) -> JSONResponse:
    """Sube un CSV/TSV/TXT/XLSX y lo normaliza en memoria."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Fichero sin nombre")

    fn_check = check_filename_security(file.filename)
    if not fn_check.safe:
        raise HTTPException(status_code=400, detail="; ".join(fn_check.blocked_reasons))

    ext = "." + file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Extensión no permitida. Usa .csv, .tsv, .txt o .xlsx",
        )

    try:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413, detail="Tamaño excede límite (%d bytes)" % MAX_UPLOAD_BYTES
            )
        if len(data) == 0:
            raise HTTPException(status_code=400, detail="Fichero vacío")

        cc = check_content_security(data)
        if not cc.safe:
            raise HTTPException(status_code=400, detail="; ".join(cc.blocked_reasons))

        headers, rows, meta = read_table(data, file.filename)

        ctype_map: Dict[int, str] = {}
        if column_types:
            try:
                parsed = json.loads(column_types)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            ctype_map[int(k)] = str(v)
                        except Exception:
                            pass
            except Exception:
                pass

        opts = Options(
            remove_legal=remove_legal,
            remove_geo=remove_geo,
            remove_articles=remove_articles,
            title_case=title_case,
            fix_email_typos=fix_email_typos,
            gmail_dots=gmail_dots,
            strip_plus_tags=strip_plus_tags,
            phone_format=phone_format,
            default_country_code=default_country_code,
        )

        res = normalize_table(headers, rows, options=opts, column_types=ctype_map)

        cleaned_rows = to_json_rows(res.headers, res.rows)
        # Guardamos los datos brutos para las descargas
        csv_bytes = write_csv(res.headers, res.rows)
        xlsx_bytes = write_xlsx(res.headers, res.rows, report_rows=_changes_to_report(res.changes))

        key = store.put(
            {
                "headers": res.headers,
                "rows": res.rows,
                "csv": csv_bytes,
                "xlsx": xlsx_bytes,
                "json": json.dumps(cleaned_rows, ensure_ascii=False).encode("utf-8"),
                "filename": secure_filename(file.filename, default="prospectos.csv"),
                "ts": time.time(),
            }
        )

        return JSONResponse(
            content={
                "ok": True,
                "key": key,
                "headers": res.headers,
                "rows_preview": cleaned_rows[:50],
                "total_rows": res.stats.get("total_rows", len(rows)),
                "columns": res.columns,
                "changes": res.changes[:200],
                "stats": res.stats,
                "meta": meta,
                "options": opts.as_dict(),
                "expires_in": 900,
                "downloads": {
                    "csv": f"/api/download/{key}/csv",
                    "xlsx": f"/api/download/{key}/xlsx",
                    "json": f"/api/download/{key}/json",
                },
            }
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error inesperado al procesar el fichero")


@app.post("/api/detect")
async def detect(file: UploadFile = File(...)) -> JSONResponse:
    """Detecta columnas y devuelve una previsualización (sin normalizar)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Fichero sin nombre")
    fn_check = check_filename_security(file.filename)
    if not fn_check.safe:
        raise HTTPException(status_code=400, detail="; ".join(fn_check.blocked_reasons))
    ext = "." + file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Extensión no permitida")
    try:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Tamaño excede límite")
        if len(data) == 0:
            raise HTTPException(status_code=400, detail="Fichero vacío")
        cc = check_content_security(data)
        if not cc.safe:
            raise HTTPException(status_code=400, detail="; ".join(cc.blocked_reasons))
        headers, rows, meta = read_table(data, file.filename)
        cols = detect_columns(headers, rows[:100])
        return JSONResponse(
            content={
                "ok": True,
                "headers": headers,
                "preview": to_json_rows(headers, rows[:20]),
                "columns": cols,
                "meta": meta,
            }
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error inesperado")


@app.get("/api/download/{key}/{fmt}")
async def download(key: str, fmt: str):
    """Descarga el resultado normalizado (CSV/XLSX/JSON)."""
    payload = store.get(key)
    if not payload:
        raise HTTPException(status_code=404, detail="Resultado expirado o no encontrado")
    base = secure_filename(payload.get("filename", "prospectos"), default="prospectos")
    if fmt == "csv":
        fname = base.rsplit(".", 1)[0] + "_limpio.csv"
        return Response(
            content=payload["csv"],
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="%s"' % fname},
        )
    if fmt == "xlsx":
        fname = base.rsplit(".", 1)[0] + "_limpio.xlsx"
        return StreamingResponse(
            io.BytesIO(payload["xlsx"]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="%s"' % fname},
        )
    if fmt == "json":
        fname = base.rsplit(".", 1)[0] + "_limpio.json"
        return Response(
            content=payload["json"],
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="%s"' % fname},
        )
    raise HTTPException(status_code=400, detail="Formato no válido")


def _changes_to_report(changes: List[Dict[str, Any]]) -> List[List[str]]:
    rows = []
    for c in changes:
        rows.append(
            [
                c.get("column", ""),
                c.get("rule_label", c.get("rule", "")),
                c.get("before", ""),
                c.get("after", ""),
            ]
        )
    return rows


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
