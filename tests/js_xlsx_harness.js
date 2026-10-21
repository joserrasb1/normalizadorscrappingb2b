/* tests/js_xlsx_harness.js
 * Genera un XLSX con el escritor de app/static/xlsx.js y lo escribe en disco
 * (binario) para que Python pueda abrirlo con openpyxl y verificarlo.
 *
 * Uso:  node tests/js_xlsx_harness.js <entrada.json> <salida.xlsx>
 */
'use strict';
const fs = require('fs');
const path = require('path');

global.window = global;
const ROOT = path.resolve(__dirname, '..');
require(path.join(ROOT, 'app', 'static', 'xlsx.js'));

const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
const bytes = window.XLSX_MIN.write(payload.headers, payload.rows, payload.sheet_name || 'Datos limpios');
fs.writeFileSync(process.argv[3], Buffer.from(bytes));
