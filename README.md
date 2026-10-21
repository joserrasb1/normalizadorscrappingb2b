# Data Cleaner B2B — Normalizador de datos para scraping y BBDD B2B

POC web **gratuita** (sin registro, sin tarjeta) que limpia y normaliza datos de
prospectos: **empresa, persona, email, teléfono, cargo y ubicación**.

Sube un CSV/TSV/XLSX "sucio" de scraping o de un CRM y obtienes una tabla
limpia, un informe de todos los cambios aplicados y la descarga en CSV, Excel o
JSON.

- 🧠 **Sin IA**: todo son reglas y RegEx deterministas (reproducibles y
  auditables). Hay un punto de extensión documentado para IA en el futuro.
- 🔒 **Modo navegador**: el fichero **no sale de tu ordenador**; se procesa con
  JavaScript en el propio navegador.
- 🧪 **159 tests** que garantizan que el motor del servidor (Python) y el del
  navegador (JavaScript) devuelven **exactamente lo mismo**.

---

## 1. Arranque rápido (local)

```bash
cd normalizadorscrappingb2b
python3 -m venv .venv && source .venv/bin/activate     # opcional
pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

Abre <http://127.0.0.1:8000>. La landing tiene un botón **"Cargar ejemplo"**
que procesa un dataset ficticio con 9 filas sucias.

Con Docker no hay nada especial: cualquier `pip install -r requirements.txt` +
`uvicorn main:app` vale.

## 2. Los dos modos de procesamiento

| | En mi navegador | En el servidor |
|---|---|---|
| Dónde se procesa | En tu equipo (JS) | En memoria (Python) |
| Qué sale del equipo | Nada | El fichero, mientras dura la petición |
| Formatos | CSV / TSV / TXT | CSV / TSV / TXT / XLSX |
| Descargas | CSV, JSON, Excel | CSV, JSON, Excel |
| Ideal para | Datos sensibles | XLSX y uso por API |

El modo servidor **no persiste nada**: el resultado se guarda 15 minutos en
memoria con una clave aleatoria (para poder descargarlo) y se descarta solo.

El modo navegador **no carga ninguna librería de datos de terceros** (ni CDN ni
npm): el motor, el parser CSV y el exportador XLSX son código propio del
proyecto, así que ningún script externo toca el fichero del usuario. El único
recurso de terceros es la hoja de estilos Tailwind (no ve los datos).

## 3. API

| Método | Ruta | Descripción |
|---|---|---|
| `GET`  | `/` | Landing + demo |
| `GET`  | `/health` | Estado del servicio |
| `POST` | `/api/detect` | Sube un fichero y devuelve las columnas detectadas (sin normalizar) |
| `POST` | `/api/clean` | Sube un fichero, normaliza y devuelve JSON + previsualización + clave de descarga |
| `GET`  | `/api/download/{clave}/csv\|xlsx\|json` | Descarga del resultado (15 min) |

Parámetros de `POST /api/clean` (form): `file`, `column_types` (JSON `{"0":"company"}`),
`remove_legal`, `remove_geo`, `remove_articles`, `title_case`, `fix_email_typos`,
`gmail_dots`, `strip_plus_tags`, `phone_format` (`auto|national|e164|international|raw`),
`default_country_code`.

Ejemplo:

```bash
curl -s -F "file=@prospectos.csv" http://127.0.0.1:8000/api/clean | python3 -m json.tool
```

Documentación interactiva: `/docs` (OpenAPI).

## 4. Qué limpia exactamente

| Tipo | Reglas |
|---|---|
| **Empresa** | Formas jurídicas (`S.L.U.`, `S.A.`, `S.L.`, `Inc.`, `Ltd`, `GmbH`, `SARL`, `S.p.A.`, `B.V.`, `S.L. de R.L. de C.V.`…), sufijos geográficos (`Europe`, `Spain`, `Global`…), artículos (`The`), URLs → dominio, Title Case inteligente, espacios y puntuación |
| **Persona** | Títulos (`Mr.`, `Dra.`, `Don`, `Doña`), orden `Apellido, Nombre` → `Nombre Apellido`, mayúsculas/minúsculas, partículas (`de`, `del`, `van`, `von`), acrónimos y prefijos (`McDonald`, `O'Brien`) |
| **Email** | Minúsculas, espacios, `< >`, `mailto:`, puntos sobrantes, typos de dominio (`gmial.com` → `gmail.com`), etiqueta `+tag` y puntos de Gmail (opcionales) |
| **Teléfono** | Prefijo internacional (`+34`, `0034`), formato nacional (`612 345 678`), `E.164`, separadores, extensiones |
| **Cargo** | Title Case (`GERENTE DE VENTAS` → `Gerente de Ventas`), partículas y acrónimos (`VP of Sales`, `CFO`) |
| **Ubicación** | Código postal inicial, `España (Madrid)` → `Madrid, España`, `Madrid, Comunidad de Madrid, España` → `Madrid, España`, país normalizado |

Decisiones de diseño importantes:

- **Las formas jurídicas cortas y ambiguas sólo se eliminan en mayúsculas**
  (`Nova SE` → `Nova`, pero `Nova Se` se queda). "Group" y "Holdings" nunca se
  tocan: son parte del nombre comercial real ("Grupo Indra", "Acme Holdings").
- **El punto final nunca se borra**: `S.L.U.` perdería el punto y quedaría
  corrupto.

## 5. Detección automática de columnas

El detector combina la cabecera y el contenido de las celdas:

- **Cabecera inequívoca** (`Empresa`, `Email`, `Cargo`, `País`, `Teléfono`) →
  manda sobre el contenido.
- **Cabecera ambigua** (`Nombre`, `Contacto`) → decide el contenido. Una columna
  "Nombre" llena de `ACME Services Europe, S.L.U.` se detecta como **empresa**,
  no como persona.
- **Contenido**: emails, densidad de dígitos, cargos típicos, `ciudad, país` y
  **formas jurídicas** (un valor con `S.L.U.` es una empresa, nunca una
  persona).
- Si la confianza es baja, la columna se marca como **"No tocar"** y el usuario
  puede forzar el tipo desde la interfaz.

Los pesos viven en `app/rules.py` (`DETECTION_WEIGHTS`) y se comparten con el
motor de JavaScript.

## 6. Arquitectura

```
normalizadorscrappingb2b/          ← raíz de este repositorio
├── main.py                     API FastAPI (subida, limpieza, descargas)
├── render.yaml                 despliegue gratuito en Render
├── app/
│   ├── rules.py                ⭐ fuente única de verdad de las reglas
│   ├── text_utils.py           utilidades de texto (Title Case, mayúsculas…)
│   ├── normalizers.py          normalizadores por tipo + registro de cambios
│   ├── detection.py            detección del tipo de cada columna
│   ├── tabular.py              lectura/escritura CSV, TSV, XLSX (+ anti CSV-injection)
│   ├── engine.py               orquestador + estadísticas de calidad
│   ├── security.py             límites, saneado de nombres, cabeceras seguras
│   ├── store.py                almacén en memoria con TTL de 15 minutos
│   ├── static/
│   │   ├── rules.js             🔁 GENERADO desde rules.py
│   │   ├── engine.js            espejo en JavaScript del motor Python
│   │   ├── csv.js               parser/serializador CSV
│   │   ├── xlsx.js              escritor XLSX propio (sin librerías externas)
│   │   ├── app.js               interfaz (modo navegador / modo servidor)
│   │   └── demo.csv             dataset de ejemplo
│   └── templates/index.html    landing
├── tools/gen_rules_js.py       genera app/static/rules.js desde app/rules.py
└── tests/                      159 tests (pytest)
```

### Fuente única de verdad

`app/rules.py` contiene **todos** los diccionarios y patrones. El fichero
`app/static/rules.js` se genera a partir de él:

```bash
python -m tools.gen_rules_js          # regenerar
python -m tools.gen_rules_js --check  # sólo verificar (CI)
```

Un test falla si se cambia una regla en Python y no se regenera el fichero JS,
de modo que los dos motores no pueden divergir en silencio.

## 7. Tests

```bash
python3 -m pytest tests/ -q
```

| Fichero | Qué cubre |
|---|---|
| `test_normalizers.py` | Los 6 normalizadores (empresa, persona, email, teléfono, cargo, ubicación) |
| `test_detection.py` | Detección de columnas y prioridades cabecera/contenido |
| `test_tabular.py` | CSV/TSV/XLSX, delimitadores, cabeceras vacías, CSV-injection |
| `test_engine.py` | Normalización de tablas, estadísticas, tipos forzados |
| `test_api.py` | API completa: subida, descargas, seguridad, cabeceras HTTP |
| `test_rules_sync.py` | `rules.js` sincronizado con `rules.py` |
| `test_js_parity.py` | El motor JS y el motor Python dan el mismo resultado (usa `node`) |
| `test_browser_mode.py` | El flujo completo del navegador (parseo → detección → limpieza → export) es idéntico al del servidor |
| `test_xlsx_writer.py` | El XLSX que genera el navegador es válido (se abre con openpyxl) |

`test_js_parity.py`, `test_browser_mode.py` y `test_xlsx_writer.py` se saltan
automáticamente si `node` no está instalado.

Los puentes entre Python y JavaScript viven en `tests/js_*.js`:
`js_harness.js` (motor), `js_csv_harness.js` (parser CSV),
`js_browser_harness.js` (flujo completo) y `js_xlsx_harness.js` (exportador).

## 8. Seguridad y privacidad

- Límite de subida: 10 MB; máximo 50 000 filas y 200 columnas.
- Extensiones admitidas: `.csv`, `.tsv`, `.txt`, `.xlsx`.
- Se bloquean nombres de fichero con rutas sospechosas, bytes nulos y exceso de
  caracteres de control.
- Las exportaciones neutralizan fórmulas (`=`, `+`, `-`, `@`) para evitar CSV
  injection en Excel, **excepto** cuando el valor es un teléfono o un número
  (`+34 911 234 567` se exporta tal cual, no como `'+34 911 234 567`).
- Cabeceras de seguridad: CSP, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, HSTS.
- Sin cookies, sin analítica, sin almacenamiento permanente.

## 9. Despliegue

El proyecto es **autocontenido**: este repositorio no depende de nada externo
(todo el motor, el parser y el exportador son código propio). Se despliega
como cualquier app FastAPI.

Render (gratis) — el `render.yaml` de la raíz ya está listo, así que basta con
"New > Blueprint" y apuntar a este repositorio:

```yaml
services:
  - type: web
    name: normalizadorscrappingb2b
    env: python
    plan: free
    region: frankfurt
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn main:app --host 0.0.0.0 --port $PORT"
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.9
    healthCheckPath: /health
```

## 10. Extensión futura (IA)

El POC es 100 % determinista, pero el motor está preparado para que la IA
entre **después** de las reglas:

1. Las reglas primero limpian (formas jurídicas, mayúsculas, emails…).
2. Un clasificador por columna podría sugerir el tipo de columna con más
   precisión que la heurística actual (`app/detection.py`).
3. Un paso de *enriquecimiento* podría deduplicar empresas, deduplicar
   contactos o detectar emails inválidos con un modelo.

El punto de extensión natural es `app/engine.py::normalize_table`, que hoy
recibe `column_types` de la detección y los overrides del usuario.

## 11. Límites conocidos

- La detección de columnas es heurística: siempre conviene revisar la
  previsualización (por eso el desplegable por columna).
- El modo navegador no **lee** XLSX (sí CSV/TSV/TXT); para XLSX hay que usar el
  modo servidor. Sí puede **exportar** a Excel: `app/static/xlsx.js` genera el
  XLSX a mano (ZIP + XML, sin librerías externas ni CDN).
- El formateo de teléfonos asume el prefijo por defecto de España (`34`),
  configurable en la interfaz.
