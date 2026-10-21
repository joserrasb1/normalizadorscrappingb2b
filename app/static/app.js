/* app.js — Lógica de la interfaz (modo navegador + modo servidor). */
(function(){
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    mode: 'browser',        // 'browser' | 'server'
    headers: [],
    rows: [],
    columns: [],
    serverKey: null,
    stats: null,
    fileName: 'prospectos.csv',
    busy: false
  };

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

  function readOptions(){
    const o = Object.assign({}, DEFAULT_OPTIONS);
    const map = {
      optLegal: 'removeLegal', optGeo: 'removeGeo', optArticles: 'removeArticles',
      optTitleCase: 'titleCase', optEmailTypos: 'fixEmailTypos',
      optGmailDots: 'gmailDots', optPlusTags: 'stripPlusTags'
    };
    Object.keys(map).forEach((id) => {
      const el = document.getElementById(id);
      if (el) o[map[id]] = el.checked;
    });
    const pf = $('#optPhoneFormat');
    if (pf) o.phoneFormat = pf.value;
    const cc = $('#optCountryCode');
    if (cc) o.defaultCountryCode = cc.value.replace(/\D/g,'') || '34';
    return o;
  }

  function setStatus(msg, kind){
    const el = $('#status');
    if (!el) return;
    el.textContent = msg || '';
    el.className = 'mt-2 hidden rounded-lg px-3 py-2 text-xs font-medium ' +
      (kind === 'error' ? 'bg-red-50 text-red-700 ring-1 ring-red-200'
       : kind === 'ok' ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
       : 'bg-slate-50 text-slate-600 ring-1 ring-slate-200');
    if (msg) el.classList.remove('hidden');
  }

  function escapeHtml(s){
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  // ---------- Carga de fichero ----------
  function handleFile(file){
    if (!file) return;
    const name = (file.name || '').toLowerCase();
    if (/\.(xlsx|xlsm)$/.test(name)){
      setStatus('El formato XLSX requiere el modo servidor (súbelo con el botón "Procesar en el servidor").', 'error');
      state.mode = 'server';
      updateModeUI();
    }
    if (state.mode === 'browser'){
      processInBrowser(file);
    } else {
      uploadToServer(file);
    }
  }

  function processInBrowser(file){
    setStatus('Procesando en tu navegador…', 'info');
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = window.CSV_UTILS.decodeBuffer(e.target.result);
        const parsed = window.CSV_UTILS.parse(text);
        if (!parsed.headers.length){ setStatus('No se pudo leer el fichero. ¿Está vacío?', 'error'); return; }
        state.headers = parsed.headers;
        state.rows = parsed.rows;
        state.fileName = file.name || 'prospectos.csv';
        state.columns = window.DATA_CLEANER.detectColumns(state.headers, state.rows);
        renderColumns();
        runLocalClean();
      } catch (err){
        setStatus('Error al leer el fichero: ' + err.message, 'error');
      }
    };
    reader.onerror = () => setStatus('Error al leer el fichero.', 'error');
    reader.readAsArrayBuffer(file);
  }

  function uploadToServer(file){
    setStatus('Subiendo y procesando en el servidor…', 'info');
    const fd = new FormData();
    fd.append('file', file);
    const opts = readOptions();
    const map = {
      remove_legal: 'removeLegal', remove_geo: 'removeGeo', remove_articles: 'removeArticles',
      title_case: 'titleCase', fix_email_typos: 'fixEmailTypos', gmail_dots: 'gmailDots',
      strip_plus_tags: 'stripPlusTags'
    };
    Object.keys(map).forEach((k) => fd.append(k, opts[map[k]] ? 'true' : 'false'));
    fd.append('phone_format', opts.phoneFormat);
    fd.append('default_country_code', opts.defaultCountryCode);
    const ctypes = {};
    state.columns.forEach(c => { ctypes[c.index] = c.applied_type; });
    if (Object.keys(ctypes).length) fd.append('column_types', JSON.stringify(ctypes));

    fetch('/api/clean', {method: 'POST', body: fd})
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error del servidor');
        state.serverKey = data.key;
        state.headers = data.headers;
        state.columns = data.columns;
        state.stats = data.stats;
        state.fileName = file.name;
        renderColumns();
        renderResults(data);
        setStatus('Listo: ' + data.total_rows + ' fila(s) procesadas.', 'ok');
      })
      .catch((err) => setStatus(err.message, 'error'));
  }

  // ---------- Motor local ----------
  function runLocalClean(){
    const opts = readOptions();
    const engine = window.DATA_CLEANER;
    const o = new engine.Options(opts);
    const outRows = [];
    const changes = [];
    const byRule = {};
    const byColumn = {};
    let processed = 0, changed = 0, empty = 0;

    state.rows.forEach((row, rIdx) => {
      const newRow = row.slice();
      state.columns.forEach((col) => {
        const type = col.applied_type;
        if (!type || type === 'ignore') return;
        const i = col.index;
        if (i >= row.length) return;
        const original = row[i] == null ? '' : String(row[i]);
        if (!original.trim()){ empty++; return; }
        processed++;
        const res = engine.normalizeValue(original, type, o);
        newRow[i] = res.value;
        if (res.changed){
          changed++;
          byColumn[col.name] = (byColumn[col.name] || 0) + 1;
          res.changes.forEach(ch => {
            byRule[ch.rule] = (byRule[ch.rule] || 0) + 1;
            if (changes.length < 300){
              changes.push({
                row: rIdx + 2, column: col.name, type: type, rule: ch.rule,
                rule_label: (engine.rules.rule_labels||{})[ch.rule] || ch.rule,
                before: original, after: res.value
              });
            }
          });
        }
      });
      outRows.push(newRow);
    });

    state.stats = {
      total_rows: state.rows.length,
      total_columns: state.headers.length,
      cells_processed: processed,
      cells_changed: changed,
      cells_empty: empty,
      by_rule: byRule,
      by_column: byColumn,
      percent_changed: processed ? Math.round(1000 * changed / processed) / 10 : 0
    };
    state.changes = changes;
    state.outRows = outRows;
    renderResults({
      rows_preview: state.rows.length ? toObjects(state.headers, outRows.slice(0, 50)) : [],
      changes: changes,
      stats: state.stats
    });
  }

  function toObjects(headers, rows){
    return rows.map(r => {
      const o = {};
      headers.forEach((h, i) => { o[h || ('columna_' + (i+1))] = r[i] == null ? '' : r[i]; });
      return o;
    });
  }

  // ---------- Render ----------
  function renderColumns(){
    const wrap = $('#columns-wrap');
    const body = $('#columns-body');
    if (!body) return;
    if (!state.columns.length){ wrap.classList.add('hidden'); return; }
    wrap.classList.remove('hidden');

    const labels = window.DATA_CLEANER.rules.column_type_labels || {};
    body.innerHTML = state.columns.map((c) => {
      const conf = Math.round((c.confidence || 0) * 100);
      const opts = Object.keys(labels).map(k =>
        `<option value="${k}"${k === c.applied_type ? ' selected' : ''}>${labels[k]}</option>`).join('');
      return `<tr class="border-b border-slate-100">
        <td class="px-3 py-2 font-medium text-slate-800">${escapeHtml(c.name || '(sin nombre)')}</td>
        <td class="px-3 py-2">
          <select data-col="${c.index}" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500">
            ${opts}
          </select>
        </td>
        <td class="px-3 py-2">
          <div class="flex items-center gap-2">
            <div class="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
              <div class="h-full rounded-full bg-emerald-500" style="width:${conf}%"></div>
            </div>
            <span class="text-[11px] text-slate-500">${conf}%</span>
          </div>
        </td>
        <td class="px-3 py-2 text-[11px] text-slate-500">${escapeHtml(c.reason || '')}</td>
      </tr>`;
    }).join('');

    $$('#columns-body select').forEach((sel) => {
      sel.addEventListener('change', () => {
        const idx = parseInt(sel.getAttribute('data-col'), 10);
        const col = state.columns.find(c => c.index === idx);
        if (col){ col.applied_type = sel.value; col.forced = true; }
        if (state.mode === 'browser') runLocalClean();
        else if (state.file) uploadToServer(state.file);
      });
    });
  }

  function renderResults(data){
    const section = $('#results');
    section.classList.remove('hidden');
    const stats = data.stats || {};
    $('#kpi-rows').textContent = stats.total_rows != null ? stats.total_rows : '0';
    $('#kpi-changed').textContent = stats.cells_changed != null ? stats.cells_changed : '0';
    $('#kpi-pct').textContent = (stats.percent_changed != null ? stats.percent_changed : 0) + '%';
    $('#kpi-cols').textContent = stats.total_columns != null ? stats.total_columns : '0';

    // Tabla de previsualización
    const tbody = $('#preview-body');
    const rows = data.rows_preview || [];
    const labels = window.DATA_CLEANER.rules.rule_labels || {};
    tbody.innerHTML = rows.map((obj) => {
      const cells = state.headers.map((h) => {
        const v = obj[h] == null ? '' : obj[h];
        return `<td class="whitespace-nowrap px-3 py-1.5 text-slate-700">${escapeHtml(v)}</td>`;
      }).join('');
      return `<tr class="border-b border-slate-100 hover:bg-slate-50">${cells}</tr>`;
    }).join('');
    $('#preview-head').innerHTML = state.headers.map((h) =>
      `<th class="whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">${escapeHtml(h)}</th>`).join('');

    // Cambios
    const changes = data.changes || [];
    $('#changes-count').textContent = changes.length;
    $('#changes-body').innerHTML = changes.length ? changes.map((c) => `
      <tr class="border-b border-slate-100">
        <td class="px-3 py-1.5 text-slate-500">${c.row}</td>
        <td class="px-3 py-1.5 font-medium text-slate-700">${escapeHtml(c.column)}</td>
        <td class="px-3 py-1.5"><span class="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700">${escapeHtml(c.rule_label || labels[c.rule] || c.rule)}</span></td>
        <td class="px-3 py-1.5 text-slate-500 line-through">${escapeHtml(c.before)}</td>
        <td class="px-3 py-1.5 font-medium text-emerald-700">${escapeHtml(c.after)}</td>
      </tr>`).join('')
      : '<tr><td colspan="5" class="px-3 py-4 text-center text-slate-400">Sin cambios detectados</td></tr>';

    // Botones de descarga
    const dl = $('#downloads');
    if (state.mode === 'server' && data.key){
      dl.classList.remove('hidden');
      $('#dl-csv').href = '/api/download/' + data.key + '/csv';
      $('#dl-xlsx').href = '/api/download/' + data.key + '/xlsx';
      $('#dl-json').href = '/api/download/' + data.key + '/json';
    } else {
      dl.classList.add('hidden');
    }
  }

  // ---------- Descargas en modo navegador ----------
  function downloadLocal(fmt){
    if (!state.outRows){ setStatus('Primero procesa un fichero.', 'error'); return; }
    const base = (state.fileName || 'prospectos').replace(/\.[^.]+$/, '');
    if (fmt === 'csv'){
      const delim = ($('#csvDelimiter') && $('#csvDelimiter').value) || ';';
      const text = window.CSV_UTILS.serialize(state.headers, state.outRows, delim, true, true);
      const blob = new Blob([text], {type: 'text/csv;charset=utf-8'});
      triggerDownload(blob, base + '_limpio.csv');
    } else if (fmt === 'json'){
      const obj = toObjects(state.headers, state.outRows);
      const blob = new Blob([JSON.stringify(obj, null, 2)], {type: 'application/json;charset=utf-8'});
      triggerDownload(blob, base + '_limpio.json');
    } else if (fmt === 'xlsx'){
      if (window.XLSX_MIN){
        const bytes = window.XLSX_MIN.write(state.headers, state.outRows, 'Datos limpios');
        const blob = new Blob([bytes], {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
        triggerDownload(blob, base + '_limpio.xlsx');
      } else {
        setStatus('No se pudo generar el Excel; usa CSV o JSON.', 'error');
      }
    }
  }

  function triggerDownload(blob, filename){
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
  }

  function updateModeUI(){
    const browser = state.mode === 'browser';
    $('#mode-browser').className = 'rounded-lg px-3 py-1.5 text-xs font-semibold transition ' +
      (browser ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800');
    $('#mode-server').className = 'rounded-lg px-3 py-1.5 text-xs font-semibold transition ' +
      (browser ? 'text-slate-500 hover:text-slate-800' : 'bg-white text-slate-900 shadow-sm');
    $('#mode-hint').textContent = browser
      ? 'El fichero NO sale de tu ordenador: todo el proceso ocurre en tu navegador.'
      : 'El fichero se procesa en memoria en el servidor y se descarta al terminar.';
  }

  // ---------- Init ----------
  function init(){
    // Tabs de modo
    $('#mode-browser').addEventListener('click', () => { state.mode = 'browser'; updateModeUI(); if (state.file) processInBrowser(state.file); });
    $('#mode-server').addEventListener('click', () => { state.mode = 'server'; updateModeUI(); if (state.file) uploadToServer(state.file); });

    // Dropzone
    const drop = $('#drop');
    const input = $('#file');
    if (drop && input){
      input.addEventListener('change', () => { state.file = input.files[0]; handleFile(state.file); });
      ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, (e) => {
        e.preventDefault(); drop.classList.add('border-indigo-400','bg-indigo-50/50');
      }));
      ['dragleave','drop'].forEach(ev => drop.addEventListener(ev, (e) => {
        e.preventDefault(); drop.classList.remove('border-indigo-400','bg-indigo-50/50');
      }));
      drop.addEventListener('drop', (e) => {
        e.preventDefault();
        const f = e.dataTransfer.files[0];
        if (f){ state.file = f; input.files = e.dataTransfer.files; handleFile(f); }
      });
      drop.addEventListener('click', () => input.click());
    }

    // Botón de ejemplo
    const demoBtn = $('#load-demo');
    if (demoBtn){
      demoBtn.addEventListener('click', async () => {
        try {
          const res = await fetch('/static/demo.csv');
          const text = await res.text();
          const parsed = window.CSV_UTILS.parse(text);
          state.headers = parsed.headers;
          state.rows = parsed.rows;
          state.fileName = 'ejemplo_prospectos.csv';
          state.columns = window.DATA_CLEANER.detectColumns(state.headers, state.rows);
          renderColumns();
          runLocalClean();
          setStatus('Ejemplo cargado (datos ficticios).', 'ok');
          $('#results').scrollIntoView({behavior:'smooth', block:'start'});
        } catch (e){ setStatus('No se pudo cargar el ejemplo.', 'error'); }
      });
    }

    // Opciones -> reprocesar
    $$('#options-panel input, #options-panel select').forEach((el) => {
      el.addEventListener('change', () => {
        if (state.mode === 'browser' && state.rows.length) runLocalClean();
        else if (state.mode === 'server' && state.file) uploadToServer(state.file);
      });
    });

    // Descargas locales
    const dlc = $('#dl-csv-local');
    if (dlc) dlc.addEventListener('click', () => downloadLocal('csv'));
    const dlj = $('#dl-json-local');
    if (dlj) dlj.addEventListener('click', () => downloadLocal('json'));
    const dlx = $('#dl-xlsx-local');
    if (dlx) dlx.addEventListener('click', () => downloadLocal('xlsx'));

    updateModeUI();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
