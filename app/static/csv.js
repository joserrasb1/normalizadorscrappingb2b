/* csv.js
 * -------
 * Parser y serializador CSV/TSV en JavaScript puro (sin dependencias).
 *
 * Espejo de `app/tabular.py` para que el modo navegador maneje los mismos
 * casos: comillas, campos con saltos de línea, BOM, detección de delimitador.
 */

(function(){
  'use strict';

  const DELIMITERS = [',', ';', '\t', '|'];

  function decodeBuffer(buffer){
    // UTF-8 con BOM
    const bytes = new Uint8Array(buffer);
    if (bytes.length >= 3 && bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) {
      return new TextDecoder('utf-8').decode(bytes.subarray(3));
    }
    // UTF-16
    if (bytes.length >= 2 && bytes[0] === 0xFF && bytes[1] === 0xFE) {
      return new TextDecoder('utf-16le').decode(bytes.subarray(2));
    }
    try {
      return new TextDecoder('utf-8', {fatal: false}).decode(bytes);
    } catch (e) {
      return new TextDecoder('windows-1252').decode(bytes);
    }
  }

  function sniffDelimiter(text){
    const counts = {',':0, ';':0, '\t':0, '|':0};
    let inQuotes = false;
    const sample = text.slice(0, 20000);
    for (let i = 0; i < sample.length; i++){
      const ch = sample[i];
      if (ch === '"') inQuotes = !inQuotes;
      else if (!inQuotes && Object.prototype.hasOwnProperty.call(counts, ch)) counts[ch]++;
    }
    let best = ',', bestCount = -1;
    for (const d of DELIMITERS){
      if (counts[d] > bestCount){ best = d; bestCount = counts[d]; }
    }
    return bestCount === 0 ? ',' : best;
  }

  /** Parsea texto CSV/TSV -> {headers, rows, delimiter} */
  function parse(text, delimiter){
    if (text && text.charCodeAt(0) === 0xFEFF) text = text.slice(1);  // BOM UTF-8
    if (delimiter === undefined || delimiter === null || delimiter === '') {
      delimiter = sniffDelimiter(text);
    }
    const rows = [];
    let row = [];
    let field = '';
    let inQuotes = false;
    let i = 0;
    const MAX_ROWS = 50000;
    const MAX_FIELD = 32000;
    const MAX_COLS = 200;

    while (i < text.length){
      const ch = text[i];
      if (inQuotes){
        if (ch === '"'){
          if (text[i+1] === '"'){ field += '"'; i += 2; continue; }
          inQuotes = false; i++; continue;
        }
        field += ch; i++; continue;
      }
      // Una comilla sólo abre un campo citado si el campo está vacío (al inicio).
      // Igual que el módulo `csv` de Python: una comilla suelta en medio de un
      // campo se trata como texto literal y no rompe el resto del fichero.
      if (ch === '"' && field === ''){ inQuotes = true; i++; continue; }
      if (ch === delimiter){ row.push(field.slice(0, MAX_FIELD)); field = ''; i++; continue; }
      if (ch === '\r'){ i++; continue; }
      if (ch === '\n'){
        row.push(field.slice(0, MAX_FIELD)); field = '';
        rows.push(row); row = [];
        if (rows.length > MAX_ROWS) break;
        i++; continue;
      }
      field += ch; i++;
    }
    if (field !== '' || row.length){
      row.push(field.slice(0, MAX_FIELD));
      rows.push(row);
    }

    if (!rows.length) return {headers: [], rows: [], delimiter: delimiter};

    let headers = rows[0].map(h => String(h));
    let data = rows.slice(1);
    while (data.length && data[data.length-1].every(c => !String(c).trim())) data.pop();

    const width = Math.min(MAX_COLS, Math.max(headers.length, ...data.map(r => r.length), 0));
    if (!headers.some(h => String(h).trim())){
      // Cabecera vacía -> nombres genéricos y se descarta la fila de cabecera
      headers = Array.from({length: width}, (_, k) => 'Columna ' + (k+1));
      data = rows.slice(1);
      while (data.length && data[data.length-1].every(c => !String(c).trim())) data.pop();
    }
    headers = headers.slice(0, width);
    while (headers.length < width) headers.push('');
    data = data.map(r => { const c = r.slice(0, width); while (c.length < width) c.push(''); return c; });

    return {headers: headers, rows: data, delimiter: delimiter};
  }

  const FORMULA_PREFIXES = ['=', '+', '-', '@', '\t', '\r'];
  // Un teléfono o un número con signo no es una fórmula: se deja intacto
  // para que el CRM importe el teléfono tal cual (mismo criterio que Python).
  const SAFE_NUMBER_RE = /^\d[\d\s.,()\-]*(?:ext\.?\s*\d+)?$/i;

  function looksLikeNumber(value){
    const s = String(value == null ? '' : value);
    const rest = (s[0] === '+' || s[0] === '-') ? s.slice(1).trim() : s.trim();
    return SAFE_NUMBER_RE.test(rest);
  }

  function protectFormula(value){
    const s = value == null ? '' : String(value);
    if (!s) return s;
    if (FORMULA_PREFIXES.indexOf(s[0]) < 0) return s;
    if (looksLikeNumber(s)) return s;
    return "'" + s;
  }

  /** Serializa tabla a CSV (con BOM opcional) */
  function serialize(headers, rows, delimiter, bom, protect){
    delimiter = delimiter || ';';
    const doProtect = protect !== false;
    const esc = (v) => {
      let s = v == null ? '' : String(v);
      if (doProtect) s = protectFormula(s);
      if (s.indexOf('"') >= 0) s = s.replace(/"/g, '""');
      if (s.indexOf(delimiter) >= 0 || s.indexOf('"') >= 0 || s.indexOf('\n') >= 0 || s.indexOf('\r') >= 0){
        return '"' + s + '"';
      }
      return s;
    };
    const lines = [];
    lines.push(headers.map(esc).join(delimiter));
    for (const r of rows) lines.push(r.map(esc).join(delimiter));
    // Terminador de línea también en la última fila (igual que csv.writer de Python)
    const text = lines.join('\r\n') + '\r\n';
    return (bom === false ? '' : '﻿') + text;
  }

  window.CSV_UTILS = {
    decodeBuffer, sniffDelimiter, parse, serialize, protectFormula
  };
})();
