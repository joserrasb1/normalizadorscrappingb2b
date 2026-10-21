/* tests/js_csv_harness.js
 * Puente para comparar el parser CSV de JavaScript (app/static/csv.js) con
 * el de Python (app/tabular.py::parse_csv_text).
 *
 * Uso:  node tests/js_csv_harness.js <fichero.json>
 * Entrada:  {"texts": ["...", "..."]}  (o {"text": "..."} para un único caso)
 * Salida:   [{"headers": [...], "rows": [[...]], "delimiter": ";"}, ...]
 */
'use strict';
const fs = require('fs');
const path = require('path');

global.window = global;
const ROOT = path.resolve(__dirname, '..');
require(path.join(ROOT, 'app', 'static', 'csv.js'));

const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
const texts = payload.texts || (payload.text != null ? [payload.text] : []);

const results = texts.map((text) => {
  const parsed = global.CSV_UTILS.parse(text);
  return {
    headers: parsed.headers,
    rows: parsed.rows,
    delimiter: parsed.delimiter
  };
});

process.stdout.write(JSON.stringify(results.length === 1 && payload.texts == null ? results[0] : results));
