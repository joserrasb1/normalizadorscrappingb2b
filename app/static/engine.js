/* GENERATED-MIRROR RUNTIME - engine.js
 * Fuente: app/rules.py (reglas), app/text_utils.py, app/normalizers.py,
 *         app/detection.py.
 * Mantener sincronizado con el servidor. Se comprueba con tests.
 */
(function(){
  'use strict';
  const R = window.RULES || {};
  const dotted = R.dotted || {};
  const wordForms = R.word_forms || [];
  const weakForms = new Set(R.weak_forms || []);
  const alwaysLegalForms = new Set(R.always_legal_forms || []);
  const geoSuffixes = (R.geo_suffixes || []).slice().sort((a,b)=>b.length-a.length);
  const honorifics = (R.honorifics || []).slice().sort((a,b)=>b.length-a.length);
  const nameParticles = new Set(R.name_particles || []);
  const titleParticles = new Set(R.title_particles || []);
  const acronyms = new Set((R.acronyms||[]).map(x=>x.toLowerCase()));
  const knownMixed = R.known_mixed_case || {};
  const namePrefixes = R.name_prefixes || [];
  const countries = R.countries || {};
  const countryAliases = {};
  Object.keys(countries).forEach(k=>{countryAliases[k]=countries[k];});
  const emailTypos = R.email_domain_typos || {};
  const defaultCC = R.default_country_code || '34';
  const callingCodes = R.calling_codes || {};
  const validCallingCodes = new Set(R.valid_calling_codes || []);
  const W = R.detection_weights || {
    header_strong: 0.85, content_with_strong_header: 0.15, header: 0.55,
    content: 0.75, content_weak: 0.30, bonus_both: 0.15, min_score: 0.35
  };

  const ctrlRe = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;
  const spaceLike = /[\u00A0\u2007\u202F\u200B\u2060\uFEFF]/g;
  const dashes = /[\u2010-\u2015\u2212\u2043]/g;
  const quotes = /[\u2018\u2019\u201C\u201D\u00AB\u00BB]/g;
  const hyphenSplit = /([-\u2010-\u2015])/;
  // Equivalente a re.compile(r"[^\W\d_]+", re.UNICODE) en Python:
  // letras y marcas (el \W de JavaScript es sólo ASCII).
  const alphaRun = /[\p{L}\p{M}]+/gu;
  const letterRe = /\p{L}/gu;

  const legalFormRe = R.legal_form_src ? new RegExp(R.legal_form_src,'gi') : null;
  const geoSuffixRe = R.geo_suffix_src ? new RegExp(R.geo_suffix_src,'gi') : null;
  const honorificRe = R.honorific_src ? new RegExp(R.honorific_src,'i') : null;
  const honorificTrailRe = R.honororific_trail_src ? new RegExp(R.honorific_trail_src,'i') : null;
  const emailRe = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}$/;

  function cleanText(v){
    if(v==null)return '';
    let s=String(v);
    s=s.replace(ctrlRe,' ').replace(spaceLike,' ').replace(dashes,'-').replace(quotes,"'");
    s=s.replace(/\r\n/g,' ').replace(/\n/g,' ').replace(/\r/g,' ');
    s=s.replace(/\t/g,' ');
    s=s.replace(/\s+/g,' ');
    return s.trim();
  }
  function collapseSpaces(t){ return t.replace(/\s{2,}/g,' ').trim(); }
  // Equivalente a text_utils.strip_edge_punctuation: NO quita el punto final
  // ("S.L.U." perdería el punto y quedaría corrupto).
  function stripEdgePunct(t){
    let s=String(t==null?'':t).trim();
    s=s.replace(/^[ \t,;_\/|·•-]+/,'').replace(/[ \t,;_\/|·•-]+$/,'').trim();
    s=s.replace(/^\.+/,'').trim();
    return s.trim();
  }
  function lettersOf(t){ return String(t==null?'':t).match(letterRe)||[]; }
  function isAllCaps(t){ const L=lettersOf(t); if(!L.length)return false; return L.every(c=>c===c.toUpperCase()); }
  function isAllLower(t){ const L=lettersOf(t); if(!L.length)return false; return L.every(c=>c===c.toLowerCase()); }
  function isMostlyCaps(t,threshold){
    threshold = (threshold==null)?0.85:threshold;
    const L=lettersOf(t);
    if(L.length<3)return false;
    const upper=L.filter(c=>c===c.toUpperCase()).length;
    return (upper/L.length)>=threshold;
  }

  function capWord(word){
    if(!word)return word;
    const low=word.toLowerCase();
    if(knownMixed[low]) return knownMixed[low];
    if(acronyms.has(low)) return word.toUpperCase();
    if(/\d/.test(word)) return word;
    for(let i=0;i<namePrefixes.length;i++){
      const p=namePrefixes[i];
      if(low.indexOf(p.toLowerCase())===0 && word.length>p.length){
        const rest=word.slice(p.length);
        return p+rest[0].toUpperCase()+rest.slice(1).toLowerCase();
      }
    }
    return word[0].toUpperCase()+word.slice(1).toLowerCase();
  }
  function capToken(token){
    let out=[], pos=0, m;
    alphaRun.lastIndex=0;
    while((m=alphaRun.exec(token))!==null){
      out.push(token.slice(pos,m.index));
      out.push(capWord(m[0]));
      pos=m.index+m[0].length;
    }
    out.push(token.slice(pos));
    return out.join('');
  }
  function titleToken(token,particles,first){
    const core=token.replace(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/g,'').toLowerCase();
    if(core && !first && particles.has(core)) return token.toLowerCase();
    return capToken(token);
  }
  function smartTitle(text,particles){
    const toks=text.split(' '), out=[];
    for(let i=0;i<toks.length;i++){
      if(!toks[i]) continue;
      out.push(titleToken(toks[i],particles,i===0));
    }
    return out.join(' ');
  }

  const ALWAYS_FORMS = new Set();
  wordForms.forEach(w=>{ if(w.replace(/\s/g,'').length>=4) ALWAYS_FORMS.add(w); });
  alwaysLegalForms.forEach(w=>ALWAYS_FORMS.add(w));
  Object.keys(dotted).forEach(k=>{
    const letters=k.replace(/[^a-z]/gi,'').toLowerCase();
    if(letters.length>=3) ALWAYS_FORMS.add(letters);
  });

  function isRemovableLegal(matched){
    const text=String(matched==null?'':matched).trim().replace(/^\.+|\.+$/g,'');
    if(!text)return false;
    if(matched.indexOf('.')>=0)return true;
    const key=text.replace(/[^a-z]/gi,'').toLowerCase();
    if(!key)return false;
    if(ALWAYS_FORMS.has(key))return true;
    if(weakForms.has(key)) return text===text.toUpperCase();
    return key.length>=4;
  }
  function legalFormMatches(text){
    const out=[];
    if(!legalFormRe)return out;
    legalFormRe.lastIndex=0;
    let m;
    while((m=legalFormRe.exec(text))!==null){
      out.push(m[0]);
      if(m[0].length===0) legalFormRe.lastIndex++;
    }
    return out;
  }
  function hasLegalForm(text){
    const found=legalFormMatches(text);
    for(let i=0;i<found.length;i++) if(isRemovableLegal(found[i])) return true;
    return false;
  }
  function stripLegalForms(text,changes){
    let s=text, changed=true;
    const edges=/^[ \t,;.\-_/|·•&]+|[ \t,;.\-_/|·•&]+$/g;
    while(changed){
      changed=false;
      if(!legalFormRe)return s;
      legalFormRe.lastIndex=0;
      const matches=[];
      let m;
      while((m=legalFormRe.exec(s))!==null) matches.push({m,idx:m.index,end:m.index+m[0].length});
      for(let i=matches.length-1;i>=0;i--){
        const mm=matches[i], matched=mm.m[0];
        if(!isRemovableLegal(matched)) continue;
        const head=s.slice(0,mm.idx).replace(edges,'').trim();
        const tail=s.slice(mm.end).replace(edges,'').trim();
        if(head && !tail){
          s=s.slice(0,mm.idx).replace(/[\s,;.\-_/|·•&]+$/,'');
          changes.push({rule:'legal_suffix',before:matched.trim(),after:''});
          changed=true; break;
        }
        if(tail && !head){
          s=s.slice(mm.end).replace(/^[\s,;.\-_/|·•&]+/,'');
          changes.push({rule:'legal_suffix',before:matched.trim(),after:''});
          changed=true; break;
        }
      }
    }
    return s;
  }
  function stripGeoSuffix(text,changes){
    let s=text, changed=true;
    const edges=/^[ \t,;.\-_/|·•&]+|[ \t,;.\-_/|·•&]+$/g;
    while(changed){
      changed=false;
      if(!geoSuffixRe)return s;
      geoSuffixRe.lastIndex=0;
      const matches=[];
      let m;
      while((m=geoSuffixRe.exec(s))!==null) matches.push({m,idx:m.index,end:m.index+m[0].length});
      for(let i=matches.length-1;i>=0;i--){
        const mm=matches[i];
        const head=s.slice(0,mm.idx).replace(edges,'').trim();
        const tail=s.slice(mm.end).replace(edges,'').trim();
        if(head && !tail){
          s=s.slice(0,mm.idx).replace(/[\s,;.\-_/|·•&]+$/,'');
          changes.push({rule:'geo_suffix',before:mm.m[0].trim(),after:''});
          changed=true; break;
        }
      }
    }
    return s;
  }
  function tidy(s){ s=collapseSpaces(s); s=s.replace(/\s*,\s*,\s*/g,', '); s=s.replace(/^\s*,\s*/,'').replace(/\s*,\s*$/,''); s=s.replace(/\s*&\s*$/,'').replace(/\s*-\s*$/,''); return s.trim(); }

  const urlRe=/^(?:https?:\/\/)?(?:www\.)?([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)(?:\/.*)?$/;
  function normalizeCompany(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    const um=urlRe.exec(value);
    if(um && um[1].indexOf('.')>=0){
      const domain=um[1], root=domain.split('.')[0];
      if(root && root.toLowerCase()!==domain.toLowerCase()){
        if(value!==root) changes.push({rule:'prefix_strip',before:value,after:root});
        value=root;
      }
    }
    if(opts.removeLegal!==false){ const s2=stripLegalForms(value,changes); if(s2) value=s2; }
    if(opts.removeGeo!==false){ const s2=stripGeoSuffix(value,changes); if(s2) value=s2; }
    value=tidy(value);
    if(opts.removeArticles!==false){
      const am=/^(?:the|The)\s+(.+)$/.exec(value);
      if(am && value.split(' ').length>1){
        if(value!==am[1]) changes.push({rule:'prefix_strip',before:value,after:am[1]});
        value=am[1];
      }
    }
    if(opts.titleCase!==false && isMostlyCaps(value)){
      const nv=smartTitle(value,titleParticles);
      if(nv!==value) changes.push({rule:'casing',before:value,after:nv});
      value=nv;
    }
    value=tidy(stripEdgePunct(value));
    if(!value) value=tidy(stripEdgePunct(cleanText(original)))||original;
    return {original,value,changes,changed:value!==original};
  }

  function normalizePerson(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    if(honorificRe){
      honorificRe.lastIndex=0;
      const nm=value.replace(honorificRe,'');
      if(nm!==value){ changes.push({rule:'honorific',before:value.slice(0,value.length-nm.length).trim(),after:''}); value=nm.trim(); }
    }
    if(honorificTrailRe){
      honorificTrailRe.lastIndex=0;
      const nm=value.replace(honorificTrailRe,'');
      if(nm!==value){ changes.push({rule:'honorific',before:value.slice(nm.length).trim(),after:''}); value=nm.trim(); }
    }
    if(value.split(',').length===2){
      const [l,r]=value.split(','), left=l.trim(), right=r.trim();
      if(left&&right){
        const cand=right+' '+left;
        if(cand!==value) changes.push({rule:'name_order',before:value,after:cand});
        value=cand;
      }
    }
    value=tidy(value);
    if(opts.titleCase!==false && (isMostlyCaps(value)||isAllLower(value))){
      const nv=smartTitle(value,nameParticles);
      if(nv!==value) changes.push({rule:'casing',before:value,after:nv});
      value=nv;
    }
    value=tidy(stripEdgePunct(value));
    if(!value) value=cleanText(original);
    return {original,value,changes,changed:value!==original};
  }

  function normalizeEmail(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    value=value.replace(/^[<>]+|[<>]+$/g,'').trim().replace(/^['"]+|['"]+$/g,'');
    if(value.toLowerCase().indexOf('mailto:')===0) value=value.slice(7).trim();
    value=value.replace(/\s/g,'');
    const low=value.toLowerCase();
    if(low!==value){ changes.push({rule:'email_case',before:value,after:low}); value=low; }
    const sep=value.indexOf('@');
    if(sep<0){ changes.push({rule:'email_invalid',before:original,after:value}); return {original,value,changes,changed:value!==original}; }
    let local=value.slice(0,sep), domain=value.slice(sep+1);
    const fl=local.replace(/^\.+|\.+$/g,'');
    if(fl!==local){ changes.push({rule:'email_case',before:local,after:fl}); local=fl; value=local+'@'+domain; }
    if(!emailRe.test(value)){ changes.push({rule:'email_invalid',before:original,after:value}); return {original,value,changes,changed:value!==original}; }
    if(opts.fixEmailTypos!==false && emailTypos[domain]){
      const fd=emailTypos[domain], fv=local+'@'+fd;
      changes.push({rule:'email_typo',before:value,after:fv}); value=fv; domain=fd;
    }
    if(opts.stripPlusTags && value.indexOf('+')>=0){
      const at=value.indexOf('@'), l2=value.slice(0,at).split('+')[0], fv=l2+'@'+value.slice(at+1);
      if(l2){ changes.push({rule:'email_case',before:value,after:fv}); value=fv; }
    }
    if(opts.gmailDots && value.indexOf('@gmail.com')>=0 && value.indexOf('.')>=0 && value.indexOf('+')<0){
      const at=value.indexOf('@'), l2=value.slice(0,at).replace(/\./g,''), fv=l2+'@'+value.slice(at+1);
      changes.push({rule:'email_case',before:value,after:fv}); value=fv;
    }
    return {original,value,changes,changed:value!==original};
  }

  function normalizePhone(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    let ext='';
    const em=/(?:ext|ext\.?|x|#|anexo)\s*(\d{1,6})\s*$/i.exec(value);
    if(em){ ext=em[1]; value=value.slice(0,em.index).trim(); }
    let explicitIntl=value.indexOf('+')>=0;
    let digits=value.replace(/\D/g,'');
    if(!digits){ changes.push({rule:'phone_invalid',before:original,after:value}); return {original,value,changes,changed:value!==original}; }
    const dcc=opts.defaultCountryCode||defaultCC;
    let cc=null, national=digits;
    if(digits.indexOf('00')===0 && digits.length>10){ digits=digits.slice(2); explicitIntl=true; }
    if(explicitIntl){
      // El usuario ya escribió el prefijo internacional: se busca el código
      // más largo que encaje ("+44 20 7946 0958" -> 44 / 2079460958).
      for(let sz of [3,2,1]){
        const c2=digits.slice(0,sz);
        if(validCallingCodes.has(c2)){
          const n2=digits.slice(sz);
          if(n2.length>=7 && n2.length<=12){ cc=c2; national=n2; break; }
        }
      }
      if(cc===null) national=digits;
    }
    else if(digits.length===11 && digits.indexOf('34')===0 && '6789'.indexOf(digits[2])>=0){ cc='34'; national=digits.slice(2); }
    else if(digits.length===11 && digits.indexOf('1')===0){ cc='1'; national=digits.slice(1); }
    else {
      for(let sz of [3,2,1]){
        const c2=digits.slice(0,sz), n2=digits.slice(sz);
        if(n2.length===9 && '6789'.indexOf(n2[0])>=0 && validCallingCodes.has(c2)){ cc=c2; national=n2; break; }
      }
      if(cc===null && dcc && digits.indexOf(dcc)===0){ national=digits.slice(dcc.length); if(national.length===9) cc=dcc; }
    }
    if(cc===null){
      if(national.length===10 && national[0]==='0') national=national.slice(1);
      if(national.length===10 && national[0]==='8') national=national.slice(1);
    }
    let fmt=opts.phoneFormat||'auto';
    if(fmt==='auto'){
      if(explicitIntl) fmt='international';
      else if(cc===null||cc===dcc) fmt='national';
      else fmt='e164';
    }
    function grp(n){ if(n.length===9) return n.slice(0,3)+' '+n.slice(3,6)+' '+n.slice(6,9); if(n.length===10) return n.slice(0,3)+' '+n.slice(3,6)+' '+n.slice(6,10); return n; }
    let out;
    if(fmt==='raw') out=digits;
    else if(fmt==='e164') out='+'+(cc||dcc)+national;
    else if(fmt==='international') out='+'+(cc||dcc)+' '+grp(national);
    else {
      if(cc===null||cc===dcc) out=grp(national);
      else out='+'+cc+' '+grp(national);
    }
    out=out.trim(); if(ext) out=out+' ext. '+ext;
    if(out!==original) changes.push({rule:'phone_format',before:original,after:out});
    return {original,value:out,changes,changed:out!==original};
  }

  function normalizeJobtitle(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    value=value.replace(/\s*[-–—|/]\s*$/,'');
    if(opts.titleCase!==false && (isAllCaps(value)||isAllLower(value))){
      const nv=smartTitle(value,titleParticles);
      if(nv!==value) changes.push({rule:'title_case',before:value,after:nv});
      value=nv;
    }
    value=tidy(stripEdgePunct(value));
    if(!value) value=cleanText(original);
    return {original,value,changes,changed:value!==original};
  }

  function isCountry(text){ const t=text.trim().toLowerCase(); return !!countryAliases[t]; }
  function normalizeLocation(raw,opts){
    opts=opts||{};
    const original=raw==null?'':String(raw);
    let value=cleanText(original), changes=[];
    if(!value) return {original,value,changes,changed:false};
    const pm=/^\s*\d{4,6}\s*[-/]?\s*(?=[A-Za-zÀ-ÿ])/.exec(value);
    if(pm){ const nv=value.slice(pm[0].length).trim(); if(nv){ if(value!==nv) changes.push({rule:'prefix_strip',before:value,after:nv}); value=nv; } }
    const par=/^(.+?)\s*\((.+)\)\s*$/.exec(value);
    if(par){
      const left=par[1].trim(), right=par[2].trim();
      if(isCountry(left)&&!isCountry(right)){ const nv=right+', '+left; if(nv!==value) changes.push({rule:'location_format',before:value,after:nv}); value=nv; }
      else if(isCountry(right)&&!isCountry(left)){ const nv=left+', '+right; if(nv!==value) changes.push({rule:'location_format',before:value,after:nv}); value=nv; }
    }
    const parts=value.split(',').map(p=>p.trim()).filter(Boolean);
    if(parts.length>=2){
      if(isCountry(parts[parts.length-1])){ const nv=parts[0]+', '+parts[parts.length-1]; if(nv!==value) changes.push({rule:'location_format',before:value,after:nv}); value=nv; }
      else if(isCountry(parts[0])){ const nv=parts[parts.length-1]+', '+parts[0]; if(nv!==value) changes.push({rule:'location_format',before:value,after:nv}); value=nv; }
    }
    value=tidy(value);
    if(opts.titleCase!==false && isAllCaps(value)){
      const nv=smartTitle(value,titleParticles);
      if(nv!==value) changes.push({rule:'country_case',before:value,after:nv});
      value=nv;
    }
    value=tidy(stripEdgePunct(value));
    if(!value) value=cleanText(original);
    return {original,value,changes,changed:value!==original};
  }

  const NORMALIZERS={company:normalizeCompany,person:normalizePerson,email:normalizeEmail,phone:normalizePhone,jobtitle:normalizeJobtitle,location:normalizeLocation};
  function normalizeValue(value,kind,opts){ opts=opts||{}; const fn=NORMALIZERS[kind]; if(!fn)return {original:value==null?'':String(value),value:value==null?'':String(value),changes:[],changed:false}; return fn(value==null?'':String(value),opts); }

  // ------------------------------------------------------------------
  // Detector (réplica de app/detection.py)
  // ------------------------------------------------------------------
  const headerKw=R.header_keywords||{};
  const strongHeaderKw=R.strong_header_keywords||{};
  const jobWords=new Set(R.job_title_words||[]);
  const _phoneClean=/[\s()+\-.]/g, _digit=/\d/g;
  const _personRe=/^[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü'’\-]+(?:\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü'’\-]+){1,3}$/;
  const _countryNames=new Set(Object.keys(countryAliases));
  const _typePriority=['company','person','email','phone','jobtitle','location'];

  function tokensOf(text){
    let s=String(text==null?'':text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    s=s.replace(/[^a-z0-9]+/g,' ');
    return s.split(' ').filter(Boolean);
  }
  function matchKeyword(hTokens,kwTokens){
    if(!kwTokens.length||kwTokens.length>hTokens.length)return null;
    const n=kwTokens.length;
    for(let i=0;i+n<=hTokens.length;i++){
      let ok=true;
      for(let j=0;j<n;j++){ if(hTokens[i+j]!==kwTokens[j]){ ok=false; break; } }
      if(ok) return n===hTokens.length?1.0:Math.min(0.9,0.6+0.1*n);
    }
    return null;
  }
  function headerScore(name){
    const tokens=tokensOf(name), scores={}, strong={};
    if(!tokens.length) return {scores,strong};
    Object.keys(headerKw).forEach(ctype=>{
      let best=0;
      (headerKw[ctype]||[]).forEach(kw=>{
        const v=matchKeyword(tokens,tokensOf(kw));
        if(v!==null&&v>best) best=v;
      });
      if(best) scores[ctype]=best;
    });
    Object.keys(strongHeaderKw).forEach(ctype=>{
      (strongHeaderKw[ctype]||[]).forEach(kw=>{
        if(matchKeyword(tokens,tokensOf(kw))!==null){ strong[ctype]=true; return; }
      });
    });
    return {scores,strong};
  }
  function sampleArr(vals,limit){ const out=[]; limit=limit||40; for(let i=0;i<vals.length;i++){ const s=String(vals[i]==null?'':vals[i]).trim(); if(s){ out.push(s); if(out.length>=limit) break; } } return out; }
  function looksLikePerson(value){
    let v=String(value==null?'':value).trim();
    if(!v) return false;
    if(hasLegalForm(v)) return false;
    if(honorificRe){ honorificRe.lastIndex=0; v=v.replace(honorificRe,'').trim(); }
    if(!v) return false;
    const parts=v.split(',');
    if(parts.length===2&&parts[0].trim()&&parts[1].trim()) return true;
    return _personRe.test(v);
  }
  function contentScores(sample){
    const scores={}, strong={};
    if(!sample.length) return {scores,strong};
    const n=sample.length;
    let emails=0; for(let i=0;i<sample.length;i++) if(emailRe.test(sample[i])) emails++;
    if(emails/n>=0.6){ scores.email=emails/n; strong.email=true; }
    let phones=0; for(let i=0;i<sample.length;i++){ const d=(sample[i].replace(_phoneClean,'').match(_digit)||[]).length; if(d>=7&&d>=0.5*sample[i].replace(/\s/g,'').length) phones++; }
    if(phones/n>=0.6){ scores.phone=phones/n; strong.phone=true; }
    let persons=0; for(let i=0;i<sample.length;i++) if(looksLikePerson(sample[i])) persons++;
    if(persons/n>=0.6){ scores.person=persons/n; strong.person=true; }
    let locs=0; for(let i=0;i<sample.length;i++){ const parts=sample[i].split(',').map(p=>p.trim().toLowerCase()).filter(Boolean); if(parts.some(p=>_countryNames.has(p))) locs++; else if(parts.length===2&&parts.every(p=>/^[a-z\s]+$/.test(p))) locs+=0.5; }
    if(locs/n>=0.6){ scores.location=Math.min(1,locs/n); strong.location=true; }
    let jobs=0; for(let i=0;i<sample.length;i++){ const words=new Set((sample[i].toLowerCase().match(/[a-záéíóúñü]+/g)||[])); for(let w of words){ if(jobWords.has(w)){jobs++;break;} } }
    if(jobs/n>=0.6){ scores.jobtitle=jobs/n; strong.jobtitle=true; }
    let legal=0; for(let i=0;i<sample.length;i++) if(hasLegalForm(sample[i])) legal++;
    if(legal/n>=0.5){ scores.company=legal/n; strong.company=true; return {scores,strong}; }
    const others=Math.max.apply(null,[scores.email||0,scores.phone||0,scores.person||0,scores.location||0,scores.jobtitle||0]);
    if(others<0.5){ let caps=0; for(let i=0;i<sample.length;i++) if(/^\p{Lu}/u.test(sample[i])) caps++; if(caps/n>=0.5) scores.company=0.5; }
    return {scores,strong};
  }
  function detectColumn(name,values){
    const hs=headerScore(name), cs=contentScores(sampleArr(values));
    const hS=hs.scores, hStrong=hs.strong, cS=cs.scores, cStrong=cs.strong;
    const combined={};
    const keys=new Set([...Object.keys(hS),...Object.keys(cS)]);
    keys.forEach(ctype=>{
      const h=hS[ctype]||0, c=cS[ctype]||0;
      let s;
      if(hStrong[ctype]){
        s=h*W.header_strong + c*W.content_with_strong_header;
      } else {
        const cw=cStrong[ctype]?W.content:W.content_weak;
        s=h*W.header + c*cw;
        if(h>0&&c>0) s+=W.bonus_both;
      }
      combined[ctype]=Math.round(s*1000)/1000;
    });
    const names=Object.keys(combined);
    if(!names.length) return {type:'ignore',confidence:0,reason:'sin pistas'};
    const ranked=names.slice().sort();
    ranked.sort((a,b)=>{
      const ra=[combined[a],hStrong[a]?1:0,-_typePriority.indexOf(a)], rb=[combined[b],hStrong[b]?1:0,-_typePriority.indexOf(b)];
      if(ra[0]!==rb[0]) return rb[0]-ra[0];
      if(ra[1]!==rb[1]) return rb[1]-ra[1];
      return ra[2]-rb[2];
    });
    const best=ranked[0], bs=combined[best];
    const reason=[];
    if(hS[best]) reason.push('cabecera');
    if(cS[best]) reason.push('contenido');
    if(bs<W.min_score) return {type:'ignore',confidence:Math.round((1-bs)*1000)/1000,reason:'no se reconoce el tipo',scores:combined};
    return {type:best,confidence:Math.round(Math.min(1,bs)*1000)/1000,reason:reason.join(' + ')||'heurística',scores:combined};
  }
  function detectColumns(headers,rows){ const out=[]; const ncols=headers.length; for(let i=0;i<ncols;i++){ const name=headers[i]||''; const values=[]; for(let r=0;r<rows.length;r++) if(i<rows[r].length) values.push(rows[r][i]); const det=detectColumn(name,values); out.push({index:i,name,applied_type:det.type,confidence:det.confidence,reason:det.reason,label:(R.column_type_labels||{})[det.type]||det.type,forced:false}); } return out; }

  window.DATA_CLEANER = {
    rules:R, cleanText, smartTitle, stripLegalForms, stripGeoSuffix,
    isAllCaps, isAllLower, isMostlyCaps, hasLegalForm, looksLikePerson,
    normalizeCompany, normalizePerson, normalizeEmail, normalizePhone, normalizeJobtitle, normalizeLocation,
    normalizeValue, detectColumn, detectColumns,
    Options:function(o){ this.removeLegal=o&&o.removeLegal!==false; this.removeGeo=o&&o.removeGeo!==false; this.removeArticles=o&&o.removeArticles!==false; this.titleCase=o&&o.titleCase!==false; this.fixEmailTypos=o&&o.fixEmailTypos!==false; this.gmailDots=!!(o&&o.gmailDots); this.stripPlusTags=!!(o&&o.stripPlusTags); this.phoneFormat=(o&&o.phoneFormat)||'auto'; this.defaultCountryCode=(o&&o.defaultCountryCode)||defaultCC; }
  };
})();
