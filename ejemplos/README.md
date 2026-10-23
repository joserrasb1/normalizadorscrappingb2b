# Ficheros CSV de prueba

Para probar la herramienta en [normalizadorscrappingb2b.pages.dev](https://normalizadorscrappingb2b.pages.dev) o localmente.

| Fichero | Uso | Qué comprueba |
|---|---|---|
| `01_crm_espanol.csv` | **Recomendado para primera prueba** | CSV con comas, mayúsculas/minúsculas, formas jurídicas (S.L., S.A., S.L.U.), "Apellido, Nombre", honoríficos, emails en mayúsculas, corrección de dominios (`gmial.com`), teléfonos con formatos distintos, países/ciudades, ubicación "España (Barcelona)". |
| `02_internacional.csv` | Internacional | Múltiples países (UK, Alemania, Francia, México, Argentina, Colombia, Chile, Portugal, Italia, Países Bajos, Suecia, Egipto, Japón). Formas jurídicas (`SARL`, `GmbH`, `S.p.A.`, `B.V.`, `AB`, `S.A. de C.V.`). Apellidos con acentos y mayúsculas. |
| `03_telefonos_y_formatos.csv` | Teléfonos | Prefijos `+34`, `0034`, `(34)`, guiones/puntos/espacios, extensiones `ext.`, dos números en una celda, `TEL:`, corrección de dominios tipográficos (`gmial`, `yaho`, `outlok`, `hotmail.es`). |
| `04_delimitador_punto_coma.csv` | **Prueba de autodetección** | Separado por `;` (muy común en Excel español). Cabeceras `Razón Social`, "Apellido, Nombre", teléfonos con `+`, etc. |
| `05_casos_problematicos.csv` | Edge cases | `no disponible`, `N/A`, `-`, honoríficos vacíos, "Apellido, Nombre", URL como empresa/persona, espacios múltiples, todo mayúsculas, correo con `(at)`, comas en cargo/ubicación, `gmial`/`hotmial`/`yaho`. |
| `06_solo_emails.csv` | Mínimo | Solo columna `EMAIL`. Útil para ver la detección automática de columna. |

## Cómo usarlo

1. Abre la web → **Probar gratis**
2. Sube uno de estos CSV
3. El sistema detecta automáticamente columnas y tipos
4. Revisa el mapeo en la tabla (puedes cambiar el tipo con el desplegable si lo detecta mal)
5. Ajusta las opciones (quitar formas jurídicas, normalizar mayúsculas, corregir typos de email...)
6. Pulsa **Procesar** y descarga el resultado

## Trucos para ver las mejoras

- Con `01_crm_espanol.csv` verás: `ACME SOLUTIONS EUROPE S.L.` → se quita `S.L.` / se normaliza; `JUAN.PEREZ@ACME.COM` → minúsculas; `jose.martinez@gmial.com` → corregido a `gmail.com`; `612 34 56 78` → formateado.
- Con `04_delimitador_punto_coma.csv` comprueba que detecta `;` automáticamente.
- Con `05_casos_problematicos.csv` verás qué valores se dejan tal cual (`no disponible`, `N/A`) y cuáles se normalizan.
