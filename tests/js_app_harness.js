/* tests/js_app_harness.js
 * Comprueba que app.js resuelve correctamente la URL base de la API a partir
 * del <meta name="api-base">, sin necesidad de un navegador real.
 *
 * Uso:  node tests/js_app_harness.js <api-base-en-el-meta>
 */
'use strict';
const path = require('path');

const metaValue = process.argv[2] === undefined ? '' : process.argv[2];

// Stub mínimo del DOM: sólo lo que app.js toca al cargar.
global.window = global;
global.document = {
  querySelector: (sel) => {
    if (sel === 'meta[name="api-base"]') {
      return { getAttribute: () => metaValue };
    }
    return null;
  },
  getElementById: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => ({ click: () => {}, setAttribute: () => {} }),
  body: { appendChild: () => {}, removeChild: () => {} },
};
global.Blob = function () {};
global.URL = { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} };

require(path.join(__dirname, '..', 'app', 'static', 'app.js'));

process.stdout.write(JSON.stringify({
  apiBase: (global.DATA_CLEANER_CONFIG || {}).apiBase
}));
