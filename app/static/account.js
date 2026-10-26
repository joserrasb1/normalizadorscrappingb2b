/* -*- coding: utf-8 -*-
 * account.js — sesión de usuario, checkout de Stripe y estado del plan.
 *
 * Depende de la API (FastAPI). Todos los fetches van con credentials
 * 'include' porque la sesión vive en una cookie httpOnly.
 */
(function(){
  'use strict';

  var API_BASE = (function(){
    var meta = document.querySelector('meta[name="api-base"]');
    return (meta && meta.getAttribute('content')) || '';
  })();

  var state = {
    user: null,
    org: null,
    plan: 'free',
    pendingPlan: null,   // plan que el usuario quería contratar
    pendingUseFile: false, // true si accedió para poder usar la herramienta
    mode: 'login',
    busy: false,
    authSubtitleOverride: null
  };

function $(sel){ return document.querySelector(sel); }
  function on(el, ev, fn){ if (el) el.addEventListener(ev, fn); }
  function show(el){ if (el) el.classList.remove('hidden'); }
  function hide(el){ if (el) el.classList.add('hidden'); }

  function billingEmail(){
    var cfg = window.DATA_CLEANER_CONFIG || {};
    return cfg.billingEmail || 'joserrasb@gmail.com';
  }

  function planLabel(plan){
    if (!plan || plan === 'free') return 'Free';
    if (plan === 'basic') return 'Basic';
    if (plan === 'pro') return 'Pro';
    return plan;
  }

  function request(path, options){
    var opts = options || {};
    var init = {
      method: opts.method || 'GET',
      credentials: 'include',
      headers: {}
    };
    if (opts.json !== undefined){
      init.body = JSON.stringify(opts.json);
      init.headers['Content-Type'] = 'application/json';
    }
    return fetch(API_BASE + path, init).then(function(res){
      return res.text().then(function(txt){
        var data = {};
        try { data = txt ? JSON.parse(txt) : {}; } catch (e){ data = { detail: txt }; }
        return { ok: res.ok, status: res.status, data: data };
      });
    }).catch(function(err){
      return { ok: false, status: 0, data: { detail: 'No se pudo contactar con la API.' } };
    });
  }

  // ---------------------------------------------------------------- UI ----
  function toast(message, kind){
    var el = $('#account-toast');
    if (!el) return;
    el.textContent = message;
    el.className = 'fixed bottom-5 left-1/2 z-[60] -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm font-semibold shadow-lg ' +
      (kind === 'error'
        ? 'bg-rose-600 text-white'
        : 'bg-slate-900 text-white');
    show(el);
    window.clearTimeout(toast._t);
    toast._t = window.setTimeout(function(){ hide(el); }, kind === 'error' ? 8000 : 4000);
  }

  function renderAccount(){
    var btn = $('#btn-account');
    var panel = $('#account-panel');
    var email = $('#account-email');
    var plan = $('#account-plan');

    if (state.user){
      if (btn) btn.textContent = state.plan && state.plan !== 'free' ? planLabel(state.plan) : 'Mi cuenta';
      if (email) email.textContent = state.user.email;
      if (plan) plan.textContent = 'Plan ' + planLabel(state.plan) +
        (state.org && state.org.name ? ' · ' + state.org.name : '');
      // En plan Free no hay suscripción que gestionar: el botón lleva a los
      // planes en lugar de abrir el portal de Stripe (que no permite comprar).
      var portalBtn = $('#account-portal');
      if (portalBtn) portalBtn.textContent = (!state.plan || state.plan === 'free')
        ? 'Ver planes' : 'Gestionar suscripción';
    } else {
      if (btn) btn.textContent = 'Acceder';
      hide(panel);
    }
  }

  // ------------------------------------------------------------ Modal ----
  function setAuthMode(mode){
    state.mode = mode === 'register' ? 'register' : 'login';
    var login = $('#auth-tab-login');
    var register = $('#auth-tab-register');
    var nameRow = $('#auth-name-row');
    var submit = $('#auth-submit');
    var title = $('#auth-title');
    var subtitle = $('#auth-subtitle');

    var active = 'bg-white text-slate-900 shadow-sm';
    var idle = 'text-slate-500 hover:text-slate-800';
    if (login) login.className = 'flex-1 rounded-md px-3 py-1.5 text-sm font-semibold ' +
      (state.mode === 'login' ? active : idle);
    if (register) register.className = 'flex-1 rounded-md px-3 py-1.5 text-sm font-semibold ' +
      (state.mode === 'register' ? active : idle);
    if (state.mode === 'register') show(nameRow); else hide(nameRow);
    if (submit) submit.textContent = state.mode === 'register' ? 'Crear cuenta' : 'Entrar';
    if (title) title.textContent = state.mode === 'register' ? 'Crea tu cuenta' : 'Accede a tu cuenta';
    if (subtitle && !state.authSubtitleOverride) {
      subtitle.textContent = state.mode === 'register'
        ? 'Empieza con el plan Free: 10 pruebas al mes, sin tarjeta.'
        : 'Entra para contratar un plan y gestionar tu cuota.';
    }
    hide($('#auth-error'));
  }

  function openAuth(mode, pendingPlan, message){
    state.pendingPlan = pendingPlan || null;
    state.authSubtitleOverride = message || null;
    setAuthMode(mode || 'login');
    var subtitle = $('#auth-subtitle');
    if (subtitle && message){
      subtitle.textContent = message;
    }
    var pwd = $('#auth-password');
    if (pwd) pwd.value = '';
    show($('#auth-modal'));
    var email = $('#auth-email');
    if (email) window.setTimeout(function(){ email.focus(); }, 30);
  }

  function closeAuth(){
    hide($('#auth-modal'));
    hide($('#auth-error'));
    state.authSubtitleOverride = null;
  }

  function authError(message){
    var el = $('#auth-error');
    if (!el) return;
    el.textContent = message;
    show(el);
  }

  function submitAuth(event){
    if (event) event.preventDefault();
    if (state.busy) return;
    var email = ($('#auth-email') || {}).value || '';
    var password = ($('#auth-password') || {}).value || '';
    var name = (($('#auth-name') || {}).value || '').trim();

    if (!email || !password){ authError('Introduce email y contraseña.'); return; }
    if (password.length < 8){ authError('La contraseña debe tener al menos 8 caracteres.'); return; }

    state.busy = true;
    var payload = state.mode === 'register'
      ? { email: email, password: password, full_name: name || null }
      : { email: email, password: password };
    var path = state.mode === 'register' ? '/auth/register' : '/auth/login';

    request(path, { method: 'POST', json: payload }).then(function(res){
      state.busy = false;
      if (!res.ok){
        var detail = res.data && res.data.detail;
        if (typeof detail !== 'string') detail = 'No se pudo completar la operación.';
        authError(detail);
        return;
      }
      closeAuth();
      var plan = state.pendingPlan;
      state.pendingPlan = null;
      refreshSession().then(function(user){
        if (!user){
          // El servidor aceptó el alta/login pero el navegador no conservó la
          // sesión (cookies de terceros bloqueadas, modo incógnito, etc.).
          authError('Tu cuenta es correcta, pero el navegador no ha guardado la sesión. ' +
            'Permite las cookies para este sitio (o prueba sin incógnito) y vuelve a entrar.');
          show($('#auth-modal'));
          return;
        }
        // Si el usuario accedió porque quería usar la herramienta sin sesión,
        // le recordamos que ya puede procesar el archivo.
        if (state.pendingUseFile){
          toast('Ya puedes pulsar "Procesar" para analizar tu fichero.');
        }
        if (plan) startCheckout(plan);
      });
    });
  }

  // ---------------------------------------------------------- Sesión ----
  function refreshSession(){
    return request('/auth/me').then(function(res){
      if (res.ok && res.data && res.data.id){
        state.user = { id: res.data.id, email: res.data.email };
        state.org = res.data.organization || null;
        state.plan = res.data.plan || 'free';
      } else {
        state.user = null;
        state.org = null;
        state.plan = 'free';
      }
      renderAccount();
      try { window.dispatchEvent(new CustomEvent('dcb:session', { detail: { user: state.user } })); } catch (e) {}
      return state.user;
    });
  }

  function logout(){
    request('/auth/logout', { method: 'POST' }).then(function(){
      state.user = null;
      state.org = null;
      state.plan = 'free';
      hide($('#account-panel'));
      renderAccount();
      try { window.dispatchEvent(new CustomEvent('dcb:session', { detail: { user: null } })); } catch (e) {}
      toast('Sesión cerrada.');
    });
  }

  // --------------------------------------------------------- Checkout ----
  function mailtoFallback(plan, reason){
    var subject = encodeURIComponent('Plan ' + planLabel(plan) + ' — Data Cleaner B2B');
    var body = encodeURIComponent(
      'Hola,\n\nQuiero contratar el plan ' + planLabel(plan) + '.\n\n' +
      (reason ? reason + '\n\n' : '') +
      'Empresa: \nVolumen mensual estimado: \n\nGracias.'
    );
    window.location.href = 'mailto:' + billingEmail() + '?subject=' + subject + '&body=' + body;
  }

  function startCheckout(plan){
    var key = String(plan || '').trim().toLowerCase();

    // "A medida" no tiene precio automático: va a ventas por email.
    if (key !== 'basic' && key !== 'pro'){
      mailtoFallback(plan, '');
      return;
    }

    if (!state.user){
      openAuth('login', key);
      return;
    }

    request('/billing/checkout/' + encodeURIComponent(key), { method: 'POST' }).then(function(res){
      if (res.ok && res.data && res.data.checkout_url){
        window.location.href = res.data.checkout_url;
        return;
      }
      if (res.status === 401){
        state.user = null;
        renderAccount();
        openAuth('login', key);
        return;
      }
      var detail = (res.data && res.data.detail) || 'No se pudo iniciar el pago.';
      if (typeof detail !== 'string') detail = 'No se pudo iniciar el pago.';
      // Mostrar el motivo real (p. ej. el error concreto de Stripe) en lugar
      // de abrir el correo automáticamente: el 90% de las veces se arregla
      // corrigiendo la configuración, no escribiendo a soporte.
      toast(detail, 'error');
    });
  }

  function openPortal(){
    if (!state.user){ openAuth('login', null); return; }
    // Sin plan de pago no hay nada que gestionar: llevamos a los precios.
    if (!state.plan || state.plan === 'free'){
      hide($('#account-panel'));
      var pricing = document.getElementById('precios');
      if (pricing && pricing.scrollIntoView){
        pricing.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      return;
    }
    request('/billing/portal').then(function(res){
      if (res.ok && res.data && res.data.portal_url){
        window.location.href = res.data.portal_url;
        return;
      }
      toast((res.data && res.data.detail) || 'No se pudo abrir la gestión de la suscripción.', 'error');
    });
  }

  // ------------------------------------------------------- Regreso ------
  function handleCheckoutReturn(){
    var params = new URLSearchParams(window.location.search);
    if (params.get('checkout') !== 'success') return;
    var sessionId = params.get('session_id');
    if (!sessionId) return;

    request('/billing/confirm', { method: 'POST', json: { session_id: sessionId } })
      .then(function(res){
        if (res.ok){
          toast('¡Suscripción activada! Plan ' + planLabel(res.data.plan) + '.');
          refreshSession();
        } else {
          toast('Estamos comprobando el pago...', 'error');
        }
        // Limpia la URL para no repetir la confirmación al recargar.
        var url = window.location.pathname + window.location.hash;
        window.history.replaceState({}, '', url);
      });
  }

  // ------------------------------------------------------------ Init ----
  function init(){
    on($('#btn-account'), 'click', function(e){
      if (e && e.stopPropagation) e.stopPropagation();
      if (state.user){
        var panel = $('#account-panel');
        if (panel) panel.classList.toggle('hidden');
      } else {
        openAuth('login', null);
      }
    });
    // Cerrar el desplegable al hacer clic fuera.
    document.addEventListener('click', function(e){
      var panel = $('#account-panel');
      if (!panel || panel.classList.contains('hidden')) return;
      if (panel.contains(e.target)) return;
      if (e.target && e.target.closest && e.target.closest('#btn-account')) return;
      hide(panel);
    });
    on($('#auth-close'), 'click', closeAuth);
    on($('#auth-overlay'), 'click', function(e){ if (e.target === e.currentTarget) closeAuth(); });
    on($('#auth-tab-login'), 'click', function(){ setAuthMode('login'); });
    on($('#auth-tab-register'), 'click', function(){ setAuthMode('register'); });
    on($('#auth-form'), 'submit', submitAuth);
    on($('#account-logout'), 'click', logout);
    on($('#account-portal'), 'click', openPortal);
    document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeAuth(); });

    refreshSession().then(handleCheckoutReturn);
  }

  document.addEventListener('DOMContentLoaded', init);

  // Expuesto para app.js (botones de plan) y para depuración.
  window.DCB = window.DCB || {};
  window.DCB.account = {
    state: state,
    refreshSession: refreshSession,
    startCheckout: startCheckout,
    openAuth: openAuth,
    logout: logout,
    openPortal: openPortal,
    toast: toast
  };
})();
