# Despliegue del POC

## Estado actual (ya desplegado)

| Pieza | URL | Estado |
|---|---|---|
| Landing + modo navegador | <https://normalizadorscrappingb2b.pages.dev> | ✅ Cloudflare Pages |
| API Python | <https://normalizadorscrappingb2b.onrender.com> | ✅ Render Free |
| Salud de la API | <https://normalizadorscrappingb2b.onrender.com/health> | ✅ `{"status":"ok"}` |

El auto-deploy está activo: **cada `git push` a `main` reconstruye la landing**
en Cloudflare Pages y redespliega la API en Render.

Arquitectura elegida: **landing + modo navegador en Cloudflare Pages** (gratis,
sin límite de tráfico, **nunca duerme**) y **API Python en Render Free**
(gratis, duerme a los 15 min, pero solo la usa quien sube un XLSX o llama a la
API).

```
┌─────────────────────────────┐        ┌──────────────────────────┐
│  Cloudflare Pages (gratis)  │  fetch │  Render Free (gratis)    │
│  landing + modo navegador   │ ─────► │  /api/clean, /api/detect │
│  → el fichero NO sale       │  CORS  │  /api/download/...       │
└─────────────────────────────┘        └──────────────────────────┘
   100 % en el cliente                  sólo XLSX / API
   (instantáneo, sin cold start)        (duerme a los 15 min)
```

---

## 1. Desplegar la API en Render (gratis) — ✅ ya hecho

1. Entra en <https://dashboard.render.com> → **New → Web Service** → conecta el
   repositorio `joserrasb1/normalizadorscrappingb2b`.
2. Render detecta el `render.yaml` de la raíz. Comprueba que:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance type**: Free
3. **Deploy**. Anota la URL, del estilo
   `https://normalizadorscrappingb2b.onrender.com`.
4. Comprueba que funciona: `https://normalizadorscrappingb2b.onrender.com/health` → `{"status":"ok"}`
   y `https://normalizadorscrappingb2b.onrender.com/docs` → la documentación de la API.

> La primera petición puede tardar ~1 minuto: el plan gratuito arranca en frío.
> Es normal y sólo afecta a la API (la landing va en Cloudflare).

### Opcional: restringir el CORS

Por defecto la API acepta peticiones de cualquier origen (es pública, sin
cookies ni credenciales). Si prefieres limitarla, en **Render → Environment**
añade:

```
ALLOWED_ORIGINS=https://normalizadorscrappingb2b.pages.dev
```

## 2. Desplegar la landing en Cloudflare Pages (gratis) — ✅ ya hecho

> **Tu API ya está desplegada**: `https://normalizadorscrappingb2b.onrender.com`
> (comprobado: `/health` → `{"status":"ok"}`). Usa esa URL en los campos de abajo.

1. Entra en <https://dash.cloudflare.com> → **Workers & Pages → Create → Pages**
   → **Connect to Git** → elige `joserrasb1/normalizadorscrappingb2b`.
2. En **Settings → Builds & deployments**:
   - **Framework preset**: `None`
   - **Build command**:
     ```
     python3 -m tools.build_static --api-base https://normalizadorscrappingb2b.onrender.com --out dist
     ```
   - **Build output directory**: `dist`
   - **Environment variables** (Production):
     ```
     API_BASE=https://normalizadorscrappingb2b.onrender.com
     ```
     (si lo defines como variable, puedes poner el build command sin
     `--api-base`; el script también la lee del entorno)
3. **Save and Deploy**. En unos segundos tendrás
   `https://normalizadorscrappingb2b.pages.dev`.
4. Comprueba:
   - La landing carga **instantáneamente** (sin esperar 30 s).
   - El botón **"Cargar ejemplo"** funciona (todo se procesa en el navegador).
   - El botón **"En el servidor"** también funciona (llama a la API de Render).

### Notas sobre la build en Cloudflare

- **No hace falta `pip install`**: `tools/build_static.py` sólo usa la
  biblioteca estándar (no importa `fastapi` ni `openpyxl`). La build tarda
  segundos.
- **Versión de Python**: la imagen de build de Cloudflare Pages trae Python
  3.13.3 por defecto; el script es compatible con 3.9+. Si Cloudflare te
  pide instalar dependencias, añade `SKIP_DEPENDENCY_INSTALL=1` como variable
  de entorno (no hace falta nada del `requirements.txt`).
- El repo tiene un `.python-version` (3.11.9) para que **Render** use una
  versión fija. Cloudflare lo ignora salvo que lo sobrescribas con
  `PYTHON_VERSION`.
- La build genera un fichero `_headers` con las cabeceras de seguridad (CSP
  que permite conectar con la API). Cloudflare Pages lo aplica solo.
- La build genera también un `404.html`. **Es importante**: sin él, Cloudflare
  Pages asume que el sitio es una SPA y devuelve 200 con la landing en
  cualquier ruta inexistente (soft 404, malo para SEO).
- Si añades rutas nuevas y quieres ver el despliegue al momento: **Deployments**
  muestra cada build; el botón para relanzar la última es **Retry deployment**
  (el "Create deployment" solo aparece en la vista de un despliegue concreto).

> **Importante**: primero despliega la API en Render y **después** Pages,
> porque la build necesita la URL de la API. Si luego cambias la URL de
> Render, vuelve a desplegar Pages.

### Dominio propio (opcional)

En **Pages → Custom domains** → **Set up a custom domain**. El SSL se emite
automáticamente. Si usas tu propio dominio en Cloudflare, añade también el
dominio a `ALLOWED_ORIGINS` en Render.

---

## 3. Despliegue monolítico (alternativa, 1 clic)

Si prefieres no usar dos plataformas, en Render basta con el `render.yaml` de la
raíz: el servicio sirve **la landing y la API** desde el mismo origen. Todo
funciona igual, salvo que la landing suffer cold starts (30-60 s) cuando el
servicio está dormido.

```yaml
# render.yaml (ya está en la raíz, no hay que tocarlo)
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

## 4. Probarlo en local (simulando el despliegue partido)

```bash
# terminal 1: la API
python3 -m uvicorn main:app --port 8000

# terminal 2: el sitio estático (como si fuera Cloudflare)
python3 -m tools.build_static --api-base http://127.0.0.1:8000 --out dist
python3 -m http.server 8001 --directory dist
# abre http://127.0.0.1:8001
```

## 5. Cuando el POC se venda

| Momento | Plan | Coste | Por qué |
|---|---|---|---|
| Primeros clientes | **Render Starter** | 7 €/mes | Sin cold start, sin cambios de código: subes de plan y listo |
| Usage real | **Render Standard** | 25 €/mes | 2 GB de RAM (XLSX grandes) y 1 CPU |
| Escala / coste | **Google Cloud Run** | por uso | Escala a cero: pagas sólo lo que usas; el free tier cubre 2 M peticiones/mes |
| Serious business | **Hetzner VPS** (~4 €/mes) | fijo | El más barato, pero requiere que operes el servidor (Docker + updates) |

El salto de Render a Cloud Run es indoloro: el comando de arranque
(`uvicorn main:app --host 0.0.0.0 --port $PORT`) y el `Dockerfile` son los
mismos, sólo cambia el comando de arranque a `gunicorn`/`uvicorn` con
`--workers`.

## 6. Checklist antes de compartir el link

- [ ] `https://normalizadorscrappingb2b.pages.dev` carga en < 1 segundo
- [ ] "Cargar ejemplo" muestra columnas detectadas y cambios
- [ ] "En el servidor" sube el demo y descarga el CSV limpio
- [ ] `https://normalizadorscrappingb2b.onrender.com/health` → `{"status":"ok"}`
- [ ] Una URL inexistente (`/no-existe`) devuelve **404** con la página propia
- [ ] La consola del navegador no tiene errores (F12 → Console)
- [ ] La pestaña Network no muestra peticiones a `/api/clean` al usar el modo
      navegador (el fichero no sale del equipo)
