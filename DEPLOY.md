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

### Cookies de sesión y CORS (importante para el login y el pago)

La landing (Cloudflare Pages) y la API (Render) están en **dominios
distintos**. Para que la cookie de sesión viaje en las peticiones `fetch`
cross-site hacen falta tres cosas en **Render → Environment**:

```
ALLOWED_ORIGINS=https://normalizadorscrappingb2b.pages.dev
SESSION_COOKIE_SAMESITE=none
SESSION_COOKIE_SECURE=true
```

- `ALLOWED_ORIGINS` con la lista exacta de orígenes **activa las credenciales**
  en el CORS (con `*` el navegador rechaza las peticiones con cookie).
- `SESSION_COOKIE_SAMESITE=none` + `SESSION_COOKIE_SECURE=true` son
  obligatorios para que la cookie cruce de `pages.dev` a `onrender.com`.
- Si en algún momento sirves la landing y la API desde el **mismo origen**,
  deja `SESSION_COOKIE_SAMESITE=lax` y `SESSION_COOKIE_SECURE=false`.

> `SameSite=None` + `Secure` no funcionan en `http://localhost`: en local deja
> `lax` / `false`.

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

## 3. Activar los pagos con Stripe (paso a paso)

La API ya tiene el código de billing listo (`/billing/checkout/{plan}`,
`/billing/portal`, `/billing/webhook`, `/billing/status`, `/billing/confirm`).
Lo que falta es la cuenta de Stripe y las variables de entorno.

### 3.1 Crear los dos productos y sus precios

1. Entra en <https://dashboard.stripe.com> (empieza en **modo test**).
2. **Products → Add product**:
   - **Basic** — 29 €/mes → en *Pricing* añade **Recurring → Monthly, 29 EUR**.
   - **Pro** — 49 €/mes → en *Pricing* añade **Recurring → Monthly, 49 EUR**.
3. Anota los **Price IDs** (`price_...`). Son los que van en
   `STRIPE_PRICE_BASIC` y `STRIPE_PRICE_PRO`.

> Puedes copiar los IDs en modo test con el botón de copiar de cada precio.
> El webhook **no distingue** entre test y live: usa siempre el modo que
> tengas abierto en el dashboard.

### 3.2 Configurar el Customer Portal (para cancelar / cambiar tarjeta)

1. **Settings → Billing → Customer portal → Activate**.
2. Deja marcadas al menos: *Cancel subscription*, *Update payment method*,
   *Update subscription* y *See invoice history*.
3. (Opcional) En *Products* puedes definir precios "alternativos" para que el
   cliente pueda hacer upgrade/downgrade desde el portal.

### 3.3 Registrar el webhook

1. **Developers → Webhooks → Add endpoint**.
2. URL:
   ```
   https://normalizadorscrappingb2b.onrender.com/billing/webhook
   ```
3. **Events** (marca exactamente estos tres):
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Pulsa **Add endpoint** y copia el **Signing secret** (`whsec_...`).

> El webhook se verifica siempre con firma (`STRIPE_WEBHOOK_SECRET`). Si el
> secreto está vacío y `ENV=production`, la API responde **503** y no acepta
> eventos: es intencionado, para que nadie active planes sin pagar.

### 3.4 Variables de entorno en Render

En **Render → tu servicio → Environment → Add**, añade:

| Variable | Valor |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_...` (o `sk_live_...`) |
| `STRIPE_PRICE_BASIC` | `price_...` del plan Basic |
| `STRIPE_PRICE_PRO` | `price_...` del plan Pro |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` del paso 3.3 |
| `APP_URL` | `https://normalizadorscrappingb2b.pages.dev` |
| `ALLOWED_ORIGINS` | `https://normalizadorscrappingb2b.pages.dev` |
| `SESSION_COOKIE_SAMESITE` | `none` |
| `SESSION_COOKIE_SECURE` | `true` |
| `ENV` | `production` |

Guarda y Render redespliega automáticamente.

### 3.5 Probar el flujo de pago

1. Abre <https://normalizadorscrappingb2b.pages.dev> → **Acceder** → crea una
   cuenta.
2. Pulsa **Empezar con Basic** → se abre Stripe Checkout.
3. Paga con la tarjeta de test `4242 4242 4242 4242` (cualquier expiry y CVC).
4. Al volver, el plan debe estar activo y el botón de la cabecera mostrar
   "Basic".
5. En **Stripe → Developers → Webhooks** debe verse el evento
   `checkout.session.completed` con respuesta **200**.
6. Cancela la suscripción desde el portal y comprueba que el plan vuelve a
   `free`.

### 3.6 Antes de pasar a producción (live)

- [ ] Cambia las claves `sk_test_...` → `sk_live_...`.
- [ ] Crea los productos y precios **también en modo live** y actualiza
      `STRIPE_PRICE_BASIC` / `STRIPE_PRICE_PRO`.
- [ ] Vuelve a registrar el webhook apuntando al mismo endpoint (Stripe crea
      un endpoint nuevo por entorno) y actualiza `STRIPE_WEBHOOK_SECRET`.
- [ ] Configura el email de ventas en `app/static/app.js`
      (`BILLING_EMAIL`), que es el fallback cuando Stripe no está disponible.

## 4. Despliegue monolítico (alternativa, 1 clic)

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
      - key: ENV
        value: production
      - key: SECRET_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: APP_URL
        value: https://normalizadorscrappingb2b.pages.dev
      - key: ALLOWED_ORIGINS
        value: https://normalizadorscrappingb2b.pages.dev
      - key: SESSION_COOKIE_SAMESITE
        value: none
      - key: SESSION_COOKIE_SECURE
        value: "true"
      - key: STRIPE_SECRET_KEY
        sync: false
      - key: STRIPE_PRICE_BASIC
        sync: false
      - key: STRIPE_PRICE_PRO
        sync: false
      - key: STRIPE_WEBHOOK_SECRET
        sync: false
    healthCheckPath: /health
```

## 5. Probarlo en local (simulando el despliegue partido)

```bash
# terminal 1: la API
python3 -m uvicorn main:app --port 8000

# terminal 2: el sitio estático (como si fuera Cloudflare)
python3 -m tools.build_static --api-base http://127.0.0.1:8000 --out dist
python3 -m http.server 8001 --directory dist
# abre http://127.0.0.1:8001
```

## 6. Cuando el POC se venda

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

## 7. Checklist antes de compartir el link

- [ ] `https://normalizadorscrappingb2b.pages.dev` carga en < 1 segundo
- [ ] "Cargar ejemplo" muestra columnas detectadas y cambios
- [ ] "En el servidor" sube el demo y descarga el CSV limpio
- [ ] `https://normalizadorscrappingb2b.onrender.com/health` → `{"status":"ok"}`
- [ ] Una URL inexistente (`/no-existe`) devuelve **404** con la página propia
- [ ] La consola del navegador no tiene errores (F12 → Console)
- [ ] La pestaña Network no muestra peticiones a `/api/clean` al usar el modo
      navegador (el fichero no sale del equipo)
- [ ] "Acceder" → crear cuenta funciona y la cabecera muestra el plan
- [ ] "Empezar con Basic" abre Stripe Checkout y al pagar se activa el plan
- [ ] "Gestionar suscripción" abre el Customer Portal de Stripe
- [ ] `https://normalizadorscrappingb2b.onrender.com/billing/status` devuelve
      401 sin sesión (protegido) y 200 con sesión

## 8. Pendiente antes de vender de verdad

- [ ] **Base de datos persistente**: la API usa SQLite en `/tmp/app.db`, que se
      borra en cada reinicio de Render (se pierden cuentas, planes y usage).
      Crear una BD en **Neon** o **Supabase** y poner `DATABASE_URL` en Render.
- [ ] Migrar de `create_all` a **Alembic** para no perder cambios de esquema.
- [ ] Historial de procesamientos (paso 4) con **R2** + TTL.
- [ ] Multi-usuario e invitaciones (paso 5) + API keys.
- [ ] Quitar la etiqueta "POC" de la landing.
