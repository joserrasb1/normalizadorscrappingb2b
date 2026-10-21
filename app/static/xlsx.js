/* xlsx.js
 * --------
 * Escritor de XLSX en JavaScript puro, sin dependencias externas.
 *
 * Por qué: el modo "100 % en el navegador" no puede cargar librerías de
 * terceros (ni CDN ni npm) sin romper la promesa de privacidad: el fichero
 * del usuario se procesa en local, pero la página sigue dejando rastro de
 * terceros si descarga código externo. Un XLSX es un ZIP con XML dentro, así
 * que lo generamos a mano (~200 líneas) con compresión "stored" (sin
 * comprimir): el tamaño final es mayor, pero el fichero se abre igual en
 * Excel, LibreOffice, Google Sheets y se importa con openpyxl.
 *
 * Uso:  window.XLSX_MIN.write(headers, rows, 'Datos limpios') -> Uint8Array
 */

(function(){
  'use strict';

  // ---------- CRC32 (para el índice del ZIP) ----------
  const CRC_TABLE = (function(){
    const table = new Uint32Array(256);
    for (let i = 0; i < 256; i++){
      let c = i;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      table[i] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes){
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  // ---------- ZIP (entradas "stored", sin compresión) ----------
  const enc = new TextEncoder();

  function dosDateTime(date){
    const time = ((date.getHours() & 0x1F) << 11)
               | ((date.getMinutes() & 0x3F) << 5)
               | ((date.getSeconds() >> 1) & 0x1F);
    const day = (((date.getFullYear() - 1980) & 0x7F) << 9)
              | (((date.getMonth() + 1) & 0x0F) << 5)
              | (date.getDate() & 0x1F);
    return {time: time, day: day};
  }

  function buildZip(files){
    const parts = [];
    const central = [];
    let offset = 0;
    const stamp = dosDateTime(new Date());

    files.forEach((file) => {
      const nameBytes = enc.encode(file.name);
      const data = file.data;
      const crc = crc32(data);

      const local = new Uint8Array(30 + nameBytes.length);
      const dv = new DataView(local.buffer);
      dv.setUint32(0, 0x04034b50, true);   // firma
      dv.setUint16(4, 20, true);            // versión necesaria
      dv.setUint16(6, 0x0800, true);        // flags (nombre en UTF-8)
      dv.setUint16(8, 0, true);             // método: stored
      dv.setUint16(10, stamp.time, true);
      dv.setUint16(12, stamp.day, true);
      dv.setUint32(14, crc, true);
      dv.setUint32(18, data.length, true);  // tamaño sin comprimir
      dv.setUint32(22, data.length, true);  // tamaño comprimido
      dv.setUint16(26, nameBytes.length, true);
      dv.setUint16(28, 0, true);            // sin campos extra
      local.set(nameBytes, 30);

      parts.push(local, data);
      central.push({name: nameBytes, crc: crc, size: data.length, offset: offset});
      offset += local.length + data.length;
    });

    let centralSize = 0;
    const centralParts = [];
    central.forEach((entry) => {
      const head = new Uint8Array(46 + entry.name.length);
      const dv = new DataView(head.buffer);
      dv.setUint32(0, 0x02014b50, true);    // firma
      dv.setUint16(4, 20, true);            // versión creator
      dv.setUint16(6, 20, true);            // versión necesaria
      dv.setUint16(8, 0x0800, true);
      dv.setUint16(10, 0, true);
      dv.setUint16(12, stamp.time, true);
      dv.setUint16(14, stamp.day, true);
      dv.setUint32(16, entry.crc, true);
      dv.setUint32(20, entry.size, true);
      dv.setUint32(24, entry.size, true);
      dv.setUint16(28, entry.name.length, true);
      dv.setUint16(30, 0, true);
      dv.setUint16(32, 0, true);
      dv.setUint16(34, 0, true);
      dv.setUint16(36, 0, true);
      dv.setUint32(38, 0, true);
      dv.setUint32(42, entry.offset, true);
      head.set(entry.name, 46);
      centralParts.push(head);
      centralSize += head.length;
    });

    const end = new Uint8Array(22);
    const edv = new DataView(end.buffer);
    edv.setUint32(0, 0x06054b50, true);
    edv.setUint16(8, central.length, true);
    edv.setUint16(10, central.length, true);
    edv.setUint32(12, centralSize, true);
    edv.setUint32(16, offset, true);

    const all = parts.concat(centralParts);
    all.push(end);
    const total = all.reduce((n, a) => n + a.length, 0);
    const out = new Uint8Array(total);
    let pos = 0;
    all.forEach((chunk) => { out.set(chunk, pos); pos += chunk.length; });
    return out;
  }

  // ---------- XML ----------
  function esc(value){
    let s = value == null ? '' : String(value);
    // Caracteres de control no válidos en XML
    s = s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  function colName(index){   // 0 -> A, 25 -> Z, 26 -> AA
    let n = index, name = '';
    do {
      name = String.fromCharCode(65 + (n % 26)) + name;
      n = Math.floor(n / 26) - 1;
    } while (n >= 0);
    return name;
  }

  const FORMULA_PREFIXES = ['=', '+', '-', '@', '\t', '\r'];
  const SAFE_NUMBER_RE = /^\d[\d\s.,()\-]*(?:ext\.?\s*\d+)?$/i;

  function protectFormula(value){
    const s = value == null ? '' : String(value);
    if (!s) return s;
    if (FORMULA_PREFIXES.indexOf(s[0]) < 0) return s;
    const rest = (s[0] === '+' || s[0] === '-') ? s.slice(1).trim() : s.trim();
    if (SAFE_NUMBER_RE.test(rest)) return s;   // un teléfono no es una fórmula
    return "'" + s;
  }

  const XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';

  function sheetXml(headers, rows){
    const out = [];
    out.push(XML_HEAD);
    out.push('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">');
    out.push('<cols><col min="1" max="1" width="34" customWidth="1"/></cols>');
    out.push('<sheetData>');

    const all = [headers || []].concat(rows || []);
    all.forEach((row, r) => {
      const rowNum = r + 1;
      out.push('<row r="' + rowNum + '">');
      (row || []).forEach((value, c) => {
        const ref = colName(c) + rowNum;
        const style = (r === 0 ? ' s="1"' : '');
        const text = esc(protectFormula(value));
        out.push('<c r="' + ref + '"' + style + ' t="inlineStr"><is><t xml:space="preserve">'
          + text + '</t></is></c>');
      });
      out.push('</row>');
    });

    out.push('</sheetData></worksheet>');
    return out.join('');
  }

  const CONTENT_TYPES = XML_HEAD +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
    '</Types>';

  const ROOT_RELS = XML_HEAD +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
    '</Relationships>';

  const STYLES = XML_HEAD +
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>' +
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>' +
    '<fills count="2"><fill><patternFill patternType="none"/></fill>' +
    '<fill><patternFill patternType="gray125"/></fill></fills>' +
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>' +
    '</styleSheet>';

  function workbookXml(sheetName){
    return XML_HEAD +
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
      '<sheets><sheet name="' + esc(sheetName || 'Datos limpios').slice(0, 31) + '" sheetId="1" r:id="rId1"/></sheets>' +
      '</workbook>';
  }

  const WORKBOOK_RELS = XML_HEAD +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' +
    '</Relationships>';

  /** Devuelve los bytes de un .xlsx (Uint8Array) */
  function write(headers, rows, sheetName){
    const files = [
      {name: '[Content_Types].xml', data: enc.encode(CONTENT_TYPES)},
      {name: '_rels/.rels', data: enc.encode(ROOT_RELS)},
      {name: 'xl/workbook.xml', data: enc.encode(workbookXml(sheetName))},
      {name: 'xl/_rels/workbook.xml.rels', data: enc.encode(WORKBOOK_RELS)},
      {name: 'xl/styles.xml', data: enc.encode(STYLES)},
      {name: 'xl/worksheets/sheet1.xml', data: enc.encode(sheetXml(headers, rows))}
    ];
    return buildZip(files);
  }

  window.XLSX_MIN = {write: write, protectFormula: protectFormula};
})();
