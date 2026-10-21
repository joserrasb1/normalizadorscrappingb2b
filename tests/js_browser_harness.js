/* tests/js_browser_harness.js
 * Reproduce el flujo completo del MODO NAVEGADOR (app.js::processInBrowser +
 * runLocalClean) fuera del navegador, para poder compararlo con el servidor.
 *
 * Uso:  node tests/js_browser_harness.js <fichero.csv> [fichero.json]
 *
 * Lee el fichero, lo parsea con csv.js, detecta columnas con engine.js,
 * normaliza cada celda y escribe en stdout un JSON con el resultado.
 * No usa `document`, por lo que app.js no se carga aquí.
 */
'use strict';

const fs = require('fs');
const path = require('path');

global.window = global;

const ROOT = path.resolve(__dirname, '..');
require(path.join(ROOT, 'app', 'static', 'rules.js'));
require(path.join(ROOT, 'app', 'static', 'engine.js'));
require(path.join(ROOT, 'app', 'static', 'csv.js'));

const DEFAULT_OPTIONS = {
  removeLegal: true,
  removeGeo: true,
  removeArticles: true,
  titleCase: true,
  fixEmailTypos: true,
  gmailDots: false,
  stripPlusTags: false,
  phoneFormat: 'auto',
  defaultCountryCode: '34'
};

const inputFile = process.argv[2];
if (!inputFile){
  process.stderr.write('uso: node js_browser_harness.js <fichero.csv>\n');
  process.exit(2);
}

let options = Object.assign({}, DEFAULT_OPTIONS);
if (process.argv[3]){
  options = Object.assign(options, JSON.parse(fs.readFileSync(process.argv[3], 'utf-8')));
}

const buf = fs.readFileSync(inputFile);
const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
const text = global.CSV_UTILS.decodeBuffer(ab);

const parsed = global.CSV_UTILS.parse(text);
const engine = global.DATA_CLEANER;
const columns = engine.detectColumns(parsed.headers, parsed.rows);
const opts = new engine.Options(options);

const outRows = [];
const changes = [];
const byRule = {};
const byColumn = {};
let processed = 0, changed = 0, empty = 0;

parsed.rows.forEach((row, rIdx) => {
  const newRow = row.slice();
  columns.forEach((col) => {
    const type = col.applied_type;
    if (!type || type === 'ignore') return;
    const i = col.index;
    if (i >= row.length) return;
    const original = row[i] == null ? '' : String(row[i]);
    if (!original.trim()){ empty++; return; }
    processed++;
    const res = engine.normalizeValue(original, type, opts);
    newRow[i] = res.value;
    if (res.changed){
      changed++;
      byColumn[col.name] = (byColumn[col.name] || 0) + 1;
      res.changes.forEach((ch) => {
        byRule[ch.rule] = (byRule[ch.rule] || 0) + 1;
        changes.push({
          row: rIdx + 2,
          column: col.name,
          type: type,
          rule: ch.rule,
          before: original,
          after: res.value
        });
      });
    }
  });
  outRows.push(newRow);
});

const stats = {
  total_rows: parsed.rows.length,
  total_columns: parsed.headers.length,
  cells_processed: processed,
  cells_changed: changed,
  cells_empty: empty,
  by_rule: byRule,
  by_column: byColumn,
  percent_changed: processed ? Math.round(1000 * changed / processed) / 10 : 0
};

process.stdout.write(JSON.stringify({
  headers: parsed.headers,
  rows: parsed.rows,
  delimiter: parsed.delimiter,
  columns: columns.map((c) => ({
    index: c.index, name: c.name, type: c.applied_type,
    confidence: c.confidence, reason: c.reason
  })),
  out_rows: outRows,
  changes: changes,
  stats: stats,
  csv: global.CSV_UTILS.serialize(parsed.headers, outRows, ';', true, true)
}));
