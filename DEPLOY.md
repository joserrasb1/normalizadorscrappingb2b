# Despliegue del POC

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

## 1. Desplegar la API en Render (gratis)

1. Entra en <https://dashboard.render.com> → **New → Web Service** → conecta el
   repositorio `joserrasb1/normalizadorscrappingb2b`.
2. Render detecta el `render.yaml` de la raíz. Comprueba que:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance type**: Free
3. **Deploy**. Anota la URL, del estilo
   `https://normalizadorscrappingb2b.onrender.com`.
4. Comprueba que funciona: `https://TU-URL.onrender.com/health` → `{"status":"ok"}`
   y `https://TU-URL.onrender.com/docs` → la documentación de la API.

> La primera petición puede tardar ~1 minuto: el plan gratuito arranca en frío.
> Es normal y sólo afecta a la API (la landing va en Cloudflare).

### Opcional: restringir el CORS

Por defecto la API acepta peticiones de cualquier origen (es pública, sin
cookies ni credenciales). Si prefieres limitarla, en **Render → Environment**
añade:

```
ALLOWED_ORIGINS=https://TU-PAGES.pages.dev,https://tu-dominio.com
```

## 2. Desplegar la landing en Cloudflare Pages (gratis)

1. Entra en <https://dash.cloudflare.com> → **Workers & Pages → Create → Pages**
   → **Connect to Git** → elige `joserrasb1/normalizadorscrappingb2b`.
2. En **Settings → Builds & deployments**:
   - **Framework preset**: `None`
   - **Build command**:
     ```
     python3 -m tools.build_static --api-base https://TU-URL.onrender.com --out dist
     ```
   - **Build output directory**: `dist`
   - **Environment variables** (Production):
     ```
     API_BASE=https://TU-URL.onrender.com
     ```
     (si lo defines como variable, puedes poner el build command sin
     `--api-base`; el script también la lee del entorno)
3. **Save and Deploy**. En unos segundos tendrás
   `https://TU-PAGES.pages.dev`.
4. Comprueba:
   - La landing carga **instantáneamente** (sin esperar 30 s).
   - El botón **"Cargar ejemplo"** funciona (todo se procesa en el navegador).
   - El botón **"En el servidor"** también funciona (llama a la API de Render).

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

- [ ] `https://TU-PAGES.pages.dev` carga en < 1 segundo
- [ ] "Cargar ejemplo" muestra columnas detectadas y cambios
- [ ] "En el servidor" sube el demo y descarga el CSV limpio
- [ ] `https://TU-URL.onrender.com/health` → `{"status":"ok"}`
- [ ] La consola del navegador no tiene errores (F12 → Console)
- [ ] La pestaña Network no muestra peticiones a `/api/clean` al usar el modo
      navegador (el fichero no sale del equipo)
