/* app.js — Lógica de la interfaz (modo navegador + modo servidor). */
(function(){
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // URL base de la API. Vacío = mismo origen (la landing y la API en el mismo
  // servidor). Se rellena con <meta name="api-base" content="..."> cuando la
  // landing se sirve desde Cloudflare Pages y la API vive en otro dominio.
  const API_BASE = (function(){
    const meta = document.querySelector('meta[name="api-base"]');
    let base = meta ? (meta.getAttribute('content') || '') : '';
    base = base.trim();
    return base.replace(/\/+$/, '');
  })();

  const state = {
    mode: 'browser',        // 'browser' | 'server'
    headers: [],
    rows: [],
    columns: [],
    serverKey: null,
    stats: null,
    fileName: 'prospectos.csv',
    busy: false,
    file: null,
    pendingUse: false       // true cuando se procesa un fichero nuevo (consume 1 uso)
  };

  // ---------- Prueba gratuita (sólo UI) ----------
  // Este POC no tiene cuentas ni backend de licencias: el contador vive en
  // localStorage. Al integrar el cobro habrá que validar la licencia también en
  // el servidor (hoy se puede saltar borrando esta clave del navegador).
  const FREE_LIMIT = 10;
  const USAGE_KEY = 'dcb2b_uses_v1';
  // Cambia este email por el de ventas antes de publicar.
  const BILLING_EMAIL = 'joserrasb@gmail.com';
  const PLAN_PRICES = { 'Basic': '29 €/mes', 'Pro': '49 €/mes', 'a medida': 'a medida' };
  let memoryUses = 0; // fallback cuando localStorage no está disponible (tests, modo privado)

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

  // ---------- Contador de la prueba gratuita ----------
  function usesCount(){
    try {
      const raw = window.localStorage.getItem(USAGE_KEY);
      if (raw == null) return memoryUses;
      const n = parseInt(raw, 10);
      return isFinite(n) && n > 0 ? Math.min(n, FREE_LIMIT) : 0;
    } catch (e){
      return memoryUses;
    }
  }

  let usageState = {
    remaining: FREE_LIMIT,
    limit: FREE_LIMIT,
    used: 0,
    hasSession: false
  };

  function remainingUses(){
    if (usageState.hasSession){
      return Math.max(0, usageState.remaining);
    }
    return FREE_LIMIT;
  }

  function fetchUsage(){
    // Si hay sesión iniciada, usar las cuotas del usuario/organización
    if (window.DCB && window.DCB.account && window.DCB.account.state && window.DCB.account.state.user){
      return fetch(API_BASE + '/auth/me', { credentials: 'include' })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data && data.usage && typeof data.usage.rows_used === 'number' && typeof data.usage.rows_limit === 'number'){
            usageState.hasSession = true;
            usageState.used = data.usage.rows_used;
            usageState.limit = data.usage.rows_limit;
            usageState.remaining = Math.max(0, usageState.limit - usageState.used);
          } else if (data && data.user){
            // Usuario logueado pero sin registro de usage aún - usar límites del plan
            usageState.hasSession = true;
            usageState.used = 0;
            usageState.limit = data.limits && data.limits.rows_month ? data.limits.rows_month : FREE_LIMIT;
            usageState.remaining = usageState.limit;
          } else {
            usageState.hasSession = false;
            usageState.remaining = FREE_LIMIT;
          }
          renderUsage();
          return usageState;
        })
        .catch(() => {
          usageState.hasSession = false;
          usageState.remaining = FREE_LIMIT;
          renderUsage();
          return usageState;
        });
    }
    usageState.hasSession = false;
    usageState.remaining = FREE_LIMIT;
    renderUsage();
    return Promise.resolve(usageState);
  }

  function showPaywall(){
    const m = $('#paywall');
    if (!m) return;
    m.classList.remove('hidden');
    m.style.display = 'block';
    document.body.classList.add('overflow-hidden');
  }

  function hidePaywall(){
    const m = $('#paywall');
    if (!m) return;
    m.classList.add('hidden');
    m.style.display = '';
    document.body.classList.remove('overflow-hidden');
  }

  function billingHref(plan){
    const subject = 'Quiero el plan ' + plan + ' de Data Cleaner B2B';
    const body = 'Hola,\n\nQuiero contratar el plan ' + plan + ' (' +
      (PLAN_PRICES[plan] || plan) + ').\n\n' +
      '- Empresa:\n- Nº de usuarios:\n- Volumen aproximado (filas/mes):\n\nGracias.';
    return 'mailto:' + BILLING_EMAIL +
      '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(body);
  }

  // ---------- Carga de fichero ----------
  function requireAuthToUse(){
    try {
      if (window.DCB && window.DCB.account && window.DCB.account.state && window.DCB.account.state.user){
        return true;
      }
    } catch(e){}
    try {
      const account = window.DCB && window.DCB.account;
      if (account && account.state) account.state.pendingUseFile = true;
      const msg = 'Para probar la herramienta necesitas crear una cuenta. Regístrate gratis y tendrás 10 documentos de prueba.';
      if (account && account.openAuth){
        try {
          account.openAuth('register', null, msg);
        } catch(ex) {
          try { account.openAuth('register', null); } catch(ex2) {}
        }
        return false;
      }
    } catch(e){}
    // Fallback: intentar abrir modal de cuenta
    try {
      const btn = document.getElementById('btn-account');
      if (btn) btn.click();
    } catch(e){}
    return false;
  }

  function handleFile(file){
    if (!file) return;
    if (!requireAuthToUse()){
      cancelUse();
      setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
      return;
    }
    if (remainingUses() <= 0){
      cancelUse();
      showPaywall();
      return;
    }
    state.pendingUse = true;
    state.mode = 'server';
    uploadToServer(file);
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
        finishUse();
      } catch (err){
        cancelUse();
        setStatus('Error al leer el fichero: ' + err.message, 'error');
      }
    };
    reader.onerror = () => { cancelUse(); setStatus('Error al leer el fichero.', 'error'); };
    reader.readAsArrayBuffer(file);
  }

  function uploadToServer(file){
    setStatus('Subiendo y procesando en el servidor… (si el servicio gratuito está ' +
              'dormido, la primera petición puede tardar hasta 1 minuto)', 'info');
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

    fetch(API_BASE + '/api/clean', {method: 'POST', body: fd})
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
        finishUse();
        setStatus('Listo: ' + data.total_rows + ' fila(s) procesadas.', 'ok');
      })
      .catch((err) => { cancelUse(); setStatus(serverErrorMessage(err), 'error'); });
  }

  function serverErrorMessage(err){
    if (err instanceof TypeError){
      return 'No se pudo contactar con el servidor. Si la página se sirve desde ' +
             'Cloudflare, revisa que la URL de la API (meta "api-base") sea correcta. ' +
             'Mientras tanto, usa el modo "En mi navegador", que funciona sin servidor.';
    }
    return err.message;
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
    // Siempre servidor
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
    if (data.key){
      dl.classList.remove('hidden');
      $('#dl-csv').href = API_BASE + '/api/download/' + data.key + '/csv';
      $('#dl-xlsx').href = API_BASE + '/api/download/' + data.key + '/xlsx';
      $('#dl-json').href = API_BASE + '/api/download/' + data.key + '/json';
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
    state.mode = 'server';
    const hint = $('#mode-hint');
    if (hint) hint.textContent = 'El fichero se procesa en memoria en el servidor y se descarta al terminar.';
  }



  // ---------- Init ----------
  function init(){
    // Enlaces del pie a la API (/docs y /health): deben apuntar a la API,
    // no al origen que sirve la landing (puede ser Cloudflare Pages).
    const linkDocs = $('#link-api-docs');
    const linkHealth = $('#link-api-health');
    if (linkDocs) linkDocs.href = API_BASE + '/docs';
    if (linkHealth) linkHealth.href = API_BASE + '/health';

    // Prueba gratuita: contador, paywall y botones de compra
    renderUsage();
    $$('[data-billing-plan]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const plan = btn.getAttribute('data-billing-plan');
        const account = window.DCB && window.DCB.account;
        // Si hay módulo de cuenta (Stripe) delegamos; si no, email a ventas.
        if (account && account.startCheckout){
          account.startCheckout(plan);
          return;
        }
        window.location.href = billingHref(plan);
      });
    });
    const closeBtn = $('#paywall-close');
    if (closeBtn) closeBtn.addEventListener('click', hidePaywall);
    const overlay = $('#paywall-overlay');
    if (overlay) overlay.addEventListener('click', (e) => {
      if (e.target === overlay) hidePaywall();
    });
    const plansLink = $('#paywall-plans');
    if (plansLink) plansLink.addEventListener('click', hidePaywall);
    const demoFromPaywall = $('#paywall-demo');
    if (demoFromPaywall) demoFromPaywall.addEventListener('click', () => {
      hidePaywall();
      const demoBtn = $('#load-demo');
      if (demoBtn) demoBtn.click();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hidePaywall(); });

    // Tabs de modo
    // Solo modo servidor

    // Dropzone
    const drop = $('#drop');
    const input = $('#file');
    if (drop && input){
      input.addEventListener('change', () => {
        const f = input.files && input.files[0];
        if (f){
          if (!requireAuthToUse()){
            input.value = '';
            setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
            return;
          }
          state.file = f;
          handleFile(f);
          return;
        }
        input.value = '';
      });
      drop.addEventListener('dragenter', (e) => {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.add('border-indigo-400','bg-indigo-50/50');
      }, { passive: false });
      drop.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        drop.classList.add('border-indigo-400','bg-indigo-50/50');
      }, { passive: false });
      drop.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove('border-indigo-400','bg-indigo-50/50');
      }, { passive: false });
      drop.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove('border-indigo-400','bg-indigo-50/50');
        const dt = e.dataTransfer;
        const f = dt && dt.files && dt.files[0];
        if (f){
          if (!requireAuthToUse()){
            setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
            return;
          }
          state.file = f;
          try {
            if (input) {
              const dataTransfer = new DataTransfer();
              dataTransfer.items.add(f);
              input.files = dataTransfer.files;
            }
          } catch(err){}
          handleFile(f);
          return;
        }
      });
      drop.addEventListener('click', (e) => {
        if (e.target === input) {
          if (!requireAuthToUse()){
            e.preventDefault();
            input.value = '';
            setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
            return;
          }
          return;
        }
        if (!requireAuthToUse()){
          e.preventDefault();
          e.stopPropagation();
          setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
          return;
        }
        if (input) {
          e.preventDefault();
          e.stopPropagation();
          try { input.click(); } catch(err){}
        }
      });
    }

    // Botón de ejemplo
    const demoBtn = $('#load-demo');
    if (demoBtn){
      demoBtn.onclick = null;
      demoBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();

        // Comprobar auth y abrir modal si no hay sesión
        if (!requireAuthToUse()) {
          try {
            if (window.DCB && window.DCB.account && typeof window.DCB.account.openAuth === 'function') {
              window.DCB.account.openAuth('register', 'Para probar la herramienta necesitas crear una cuenta. Regístrate gratis y tendrás 10 documentos de prueba.');
              return;
            }
          } catch (err) {}
          setStatus('Necesitas iniciar sesión o crear una cuenta para probar la herramienta (10 pruebas gratis).', 'error');
          return;
        }

        if (remainingUses() <= 0) {
          showPaywall();
          return;
        }

        try {
          const res = await fetch('/static/demo.csv', { cache: 'no-store' });
          if (!res.ok) throw new Error('fetch failed');
          const text = await res.text();
          if (!text || !text.trim()) throw new Error('empty');

          // Cargar como fichero para subirlo directamente al servidor
          const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
          const file = new File([blob], 'ejemplo_prospectos.csv', { type: 'text/csv' });

          state.file = file;
          state.pendingUse = true;
          state.mode = 'server';

          setStatus('Cargando ejemplo...', 'ok');
          uploadToServer(file);

          const resultsEl = $('#results');
          if (resultsEl) resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
          console.error(err);
          setStatus('No se pudo cargar el ejemplo.', 'error');
        }
      }, { capture: true });
    }

    // Opciones -> reprocesar
    $$('#options-panel input, #options-panel select').forEach((el) => {
      el.addEventListener('change', () => {
        if (state.file) uploadToServer(state.file);
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

  // Expuesto para depuración en la consola del navegador y para los tests.
  window.DATA_CLEANER_CONFIG = {
    apiBase: API_BASE,
    billingEmail: BILLING_EMAIL,
    freeLimit: FREE_LIMIT,
    usage: {
      remaining: remainingUses,
      used: usesCount,
      reset: function(){ setUses(0); }
    }
  };
})();
