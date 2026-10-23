/**
 * functions/_middleware.js
 * ------------------------
 * Proxy same-origin hacia la API de Render.
 *
 * ¿Por qué? La landing vive en `*.pages.dev` y la API en `*.onrender.com`.
 * Si el navegador llama a la API directamente, la cookie de sesión es una
 * cookie de TERCEROS: Safari (y Chrome/Firefox con protección de cookies) la
 * descarta, el login devuelve 200 pero la siguiente petición ya no lleva
 * sesión y el usuario vuelve al formulario en bucle.
 *
 * Con este proxy todas las llamadas van a `https://<landing>/auth/...`,
 * `/api/...` y `/billing/...`, el navegador las ve como same-origin (cookies
 * de primera parte) y no hace falta CORS ni `SameSite=None`.
 *
 * La API se sigue pudiendo llamar directamente por su URL; esto sólo añade
 * una puerta de entrada en el mismo origen.
 */

const DEFAULT_API = "https://normalizadorscrappingb2b.onrender.com";

// Rutas que se reenvían a la API.
const PREFIXES = ["/api/", "/auth/", "/billing/"];
const EXACT = ["/health", "/docs", "/openapi.json", "/redoc"];

// Cabeceras que no deben reenviarse tal cual (las gestiona Cloudflare).
const DROP_REQUEST = [
  "host",
  "cf-connecting-ip",
  "cf-ipcountry",
  "cf-ray",
  "cf-visitor",
  "cdn-loop",
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-real-ip",
  "accept-encoding",
  "connection",
  "keep-alive",
];

// Cabeceras de respuesta que no se copian (las recalcula Cloudflare).
const DROP_RESPONSE = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
];

function shouldProxy(pathname) {
  if (EXACT.indexOf(pathname) !== -1) return true;
  return PREFIXES.some(function (prefix) {
    return pathname.indexOf(prefix) === 0;
  });
}

export async function onRequest(context) {
  const request = context.request;
  const url = new URL(request.url);

  if (!shouldProxy(url.pathname)) {
    return context.next();
  }

  const apiOrigin = (context.env && context.env.API_ORIGIN) || DEFAULT_API;
  const target = new URL(url.pathname + url.search, apiOrigin);

  const headers = new Headers(request.headers);
  DROP_REQUEST.forEach(function (name) {
    headers.delete(name);
  });

  const init = {
    method: request.method,
    headers: headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    // Streaming: sirve igual para JSON, formularios y subidas de ficheros.
    init.body = request.body;
  }

  let upstream;
  try {
    upstream = await fetch(target.toString(), init);
  } catch (err) {
    return new Response(
      JSON.stringify({
        detail:
          "La API no responde en este momento. Inténtalo de nuevo en unos segundos.",
      }),
      {
        status: 502,
        headers: { "content-type": "application/json; charset=utf-8" },
      }
    );
  }

  const out = new Headers();
  upstream.headers.forEach(function (value, key) {
    const lower = key.toLowerCase();
    if (lower === "set-cookie") return;
    if (DROP_RESPONSE.indexOf(lower) !== -1) return;
    out.set(key, value);
  });

  // Set-Cookie puede venir varias veces: hay que copiarlas una a una.
  let cookies = [];
  if (typeof upstream.headers.getSetCookie === "function") {
    cookies = upstream.headers.getSetCookie();
  } else {
    const raw = upstream.headers.get("set-cookie");
    if (raw) cookies = [raw];
  }
  cookies.forEach(function (cookie) {
    out.append("set-cookie", cookie);
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: out,
  });
}
