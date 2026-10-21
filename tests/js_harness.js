/* tests/js_harness.js
 * Puente entre pytest y el motor de JavaScript del navegador.
 *
 * Uso:  node tests/js_harness.js <fichero.json>
 * Lee un JSON {normalize:[...], detect:[...]} y escribe en stdout un JSON
 * {normalize:[...], detect:[...]} con los resultados del motor JS.
 *
 * Se usa en tests/test_js_parity.py para comprobar que el motor del
 * navegador y el del servidor devuelven exactamente lo mismo.
 */
'use strict';
const fs = require('fs');
const path = require('path');

global.window = global;

const ROOT = path.resolve(__dirname, '..');
require(path.join(ROOT, 'app', 'static', 'rules.js'));
require(path.join(ROOT, 'app', 'static', 'engine.js'));

const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
const engine = global.DATA_CLEANER;

const normalize = (payload.normalize || []).map((c) => {
  const opts = new engine.Options(c.options || {});
  const res = engine.normalizeValue(c.value, c.kind, opts);
  return {
    value: res.value,
    changes: (res.changes || []).map((ch) => ch.rule),
  };
});

const detect = (payload.detect || []).map((d) => {
  const det = engine.detectColumn(d.name, d.values || []);
  return { type: det.type, confidence: det.confidence, reason: det.reason };
});

process.stdout.write(JSON.stringify({ normalize, detect }));
