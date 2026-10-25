/* P3-PLN-09 live adapter for the frozen prototype v0.2.5 (sha256 e17d50dc…).
   Appended after the prototype's own script by research/p3/control_room.py. It adds no screen, slot,
   navigation item or style. It supplies the live scenario (LIVE, built from verified evidence) and
   re-declares only data-bearing components, with the prototype's markup and classes. Bound so far:
   the shell (identity bar, Truth Strip, navigation), Command Center and System. The other screens
   render with an explicit "not yet bound" notice, and their DEMO tags stay. Read-only: no network,
   no write, no control. */
"use strict";
const LIVE_BOUND=['command','system'];
const LD=t=>tm(t);
/* the live scenario rides on the prototype's closed-family scenario, overridden field by field */
SC.live=Object.assign({},SC.closed,LIVE.scenario);
CAPS.splice(0,CAPS.length,...LIVE.caps);
Object.keys(LIVE.prov).forEach(k=>{PROV[k]=LIVE.prov[k]});
S.scenario='live';
document.title='Trading Lab OS — Control Room (live projection, read-only)';
/* client-side freshness: past the budget the view says it is stale, as the frozen viewStale state does */
const LIVE_AGE_S=()=>Math.max(0,Math.round(Date.now()/1000-LIVE.observed_epoch));
const ageTxt=s=>s<90?`${s}s`:s<5400?`${Math.round(s/60)}m`:`${Math.round(s/3600)}h`;
function liveFreshness(){const s=SC.live,a=LIVE_AGE_S();
  if(a<=LIVE.budget_s){s.viewStale=false;s.dims.freshness=['ok','fresh',b(ageTxt(a),ageTxt(a))];return}
  if(s.viewStale)return;
  s.viewStale=true;const age=b(ageTxt(a),ageTxt(a));
  Object.keys(s.dims).forEach(k=>{if(k!=='authority')s.dims[k]=['stale',s.dims[k][1],age]});
  s.dims.freshness=['unk','unknown'];
  s.banner=['stale',b(`This view was generated ${ageTxt(a)} ago and has not been regenerated since. What you see may no longer be true. The trading system cannot be judged from this view.`,`أُنشئت هذه الشاشة قبل ${ageTxt(a)} ولم يُعَد إنشاؤها منذ ذلك. ما تراه قد لا يكون صحيحًا الآن. لا يمكن الحكم على نظام التداول من هذه الشاشة.`)];
  s.verdict=b(`Status unknown since ${LIVE.observed_utc}.`,`الحالة غير معروفة منذ ${LIVE.observed_utc}.`);
  s.nowObs=b('No current observation','لا يوجد رصد حالي')}

/* ---------- shell ---------- */
function proto(){const p=document.getElementById('proto');if(p){p.innerHTML='';p.hidden=true}}
function pban(){return `<div class="pban" role="note">${x(`LIVE PROJECTION · READ-ONLY · NOT EVIDENCE AUTHORITY · observed ${LIVE.observed_utc} on ${LIVE.hostname}`,`عرض مباشر · للقراءة فقط · ليس مرجعًا للأدلة · رُصد ${LIVE.observed_utc} على ${LIVE.hostname}`)}</div>`}
function shead(k){const bound=LIVE_BOUND.includes(k);
  return `<div class="shead"><h1>${L(NAME[k])}</h1><span class="asof">${x('as of','حتى')} ${LD(LIVE.observed_utc)}</span>${bound?'':`<span class="mocktag">${x('DEMO data','بيانات تجريبية')}</span>`}</div>`}
function idbar(){const s=sc(),req=s.owner[0]==='req';
  return `<header class="idbar"><span class="brand">Trading Lab OS</span><span class="sep"></span>
  <button class="stagechip" data-go="continuity">${gl('info')} ${L(LIVE.ident.stage)} <span class="muted">· ${id(LIVE.ident.ref)}</span></button>
  <span class="mode">${x('PAPER','ورقي')}</span><span class="lock">${LOCK}${x('Real money blocked','المال الحقيقي محظور')}</span>
  <span class="grow"></span>
  <span class="ownerind ${req?'req':''}">${req?gl('owner')+' ':''}${x('Owner','المالك')}: ${ownerWord(s)}</span>
  <span class="heart ${s.viewStale?'st':''}" id="heart"></span>
  <span class="langt" role="group" aria-label="Language"><button data-lang="ar" aria-pressed="${S.lang==='ar'}">AR</button><button data-lang="en" aria-pressed="${S.lang==='en'}">EN</button></span></header>`}
function heart(){const h=document.getElementById('heart');if(!h)return;const a=ageTxt(LIVE_AGE_S());
  h.textContent=sc().viewStale?`${x('View','العرض')}: ${x('stale','متوقف')} ${a}`:`${x('View','العرض')}: ${x('observed','رُصد')} ${a}`}
function timeline(evs,compact){return `<ul class="tl">${evs.map(e=>e.gap?`<li class="gap">${L(e.gap)}</li>`:`<li class="${e.ck?'ck':''}"><span class="t">${LD(e.t)}</span>${gl(e.s)}<span>${L(e.d)}</span>${compact?'':`<span class="src">${x('source','المصدر')}: ${L(e.src)}</span>`}</li>`).join('')}</ul>`}
/* a screen not yet bound keeps its prototype body, under the prototype's own info banner */
function unboundNotice(){return `<div class="banner b-info" role="status"><span class="bg" aria-hidden="true">${G.info}</span><p>${x('This screen is not yet bound to live evidence (P3-PLN-09 in progress). Values tagged DEMO are the frozen prototype reference, not this system.','هذه الشاشة غير مربوطة بالأدلة المباشرة بعد (P3-PLN-09 قيد التنفيذ). القيم الموسومة DEMO هي مرجع النموذج المجمّد وليست هذا النظام.')}</p></div>`}

/* ---------- Command Center ---------- */
function projectNow(){const p=LIVE.project;
  return `<h2 class="bandlabel">${x('Project now','المشروع الآن')}</h2><section class="band c1"><div class="col">
  <div class="pnow">${p.chips.map(c=>`<span>${chip(c[0],c[1])}</span>`).join('')}<span class="sec gate">${x('Next Owner gate','بوابة المالك التالية')}: <b>${L(p.gate)}</b></span></div>
  <div class="pnow" style="margin-top:8px">${p.workstreams.map(w=>`<span title="${esc(w[4])}">${chip(w[0],b(`${w[1]} · ${w[3]}`,`${w[1]} · ${w[3]}`))}</span>`).join('')}</div>
  <div class="cd" style="margin-top:8px">${x('Last governed checkpoint','آخر نقطة تحقق محكومة')}: ${L(sc().lgc)} · ${x('Workstream record','سجل مسارات العمل')} ${LD(p.ws_updated)} · <button class="lnk" data-go="continuity">${x('Open Project & Continuity','فتح المشروع والاستمرارية')}</button></div></div></section>`}
function decCol(){const s=sc();const h=`<div class="ptitle"><button data-go="decisions">${x('Latest decision','آخر قرار')}</button></div>`;
  return `<div class="col">${h}<p class="quiet">${L(s.dec.none)}</p></div>`}
function riskCol(){const s=sc(),off=s.dims.runtime[0]!=='ok',st=s.viewStale;
  const na=chip('off',b('Not applicable · runtime stopped','لا ينطبق · التشغيل متوقف'));
  return `<div class="col ${st?'stl':''}"><div class="ptitle"><button data-go="risk">${x('Risk & exposure','المخاطر والانكشاف')}</button>${st?chip('stale','stale'):''}</div>
  <div class="sec small">${x('Exposure','الانكشاف')}</div><div class="big num">${off?tm('0%'):'—'}</div>${off?chip('ok',b('No open positions','لا مراكز مفتوحة')):chip('unk','unknown')}
  ${row(x('Daily loss','الخسارة اليومية'),off?na:chip('unk','unknown'))}${row(x('Vetoes (24h)','الاعتراضات (24 س)'),off?na:chip('unk','unknown'))}${row(x('Real money','المال الحقيقي'),chip('blocked','blocked'),{insp:'cap:6'})}</div>`}
function posCol(){const s=sc();
  return `<div class="col"><div class="ptitle"><button data-go="trades">${x('Open positions','المراكز المفتوحة')}</button></div>
  <div class="sec">${s.pos.length?x(`${s.pos.length} open`,`${s.pos.length} مفتوح`):x('None open','لا مراكز مفتوحة')}</div></div>`}
function incSummary(){const o=openIncs();
  return o.length?o.map(i=>`<button class="exrow" data-inc="${i.id}">${gl(i.s==='recovering'?'rec':'inc')}<b>${id(i.id)}</b><span>${L(i.title)}</span><span class="ol">${x('Open','فتح')}</span></button>`).join(''):`<p class="quiet">${gl('ok')} ${x('None open.','لا حوادث مفتوحة.')} <span class="muted">${x('No incident is recorded for P3.','لا توجد حادثة مسجلة لـ P3.')}</span></p>`}
function activeCaps(){const pick=[0,1,2,3,6].map(i=>CAPS[i]);const unk=CAPS.filter(c=>c.st[0]==='unk').length;
  return `<h2 class="bandlabel">${x('Active capabilities','القدرات الفعّالة')}</h2><section class="band c1"><div class="col"><div class="pnow">${pick.map((c,i)=>`<button class="capb" data-insp="cap:${[0,1,2,3,6][i]}">${L(c.k)} ${chip(...c.st)}</button>`).join('')}${unk?`<span>${chip('unk',b(`${unk} unknown — treated as blocked`,`${unk} غير معروف — يُعامل كمحظور`))}</span>`:''}<button class="lnk" data-go="risk">${x('Full matrix in Risk & Authority','المصفوفة الكاملة في المخاطر والصلاحيات')}</button></div></div></section>`}
const _protoCommand=command;
function liveCommand(){const s=sc();
  return _protoCommand().replace(`${x('Derived','مشتق')} ${D(s.now)}`,`${x('Derived','مشتق')} ${LD(LIVE.observed_utc)}`)
    .replace(x('P&L does not decide the P2 outcome and is not used to judge system health.','الربح والخسارة لا يحددان نتيجة P2 ولا يُستخدمان للحكم على سلامة النظام.'),
             x('P&L decides nothing and is not used to judge system health.','الربح والخسارة لا يحددان شيئًا ولا يُستخدمان للحكم على سلامة النظام.'))}

/* ---------- System ---------- */
function system(){const y=sc().sys,I=LIVE.identity,H=LIVE.health_findings;
  const sevc=v=>v==='INFO'?'ok':v==='WARNING'?'warn':'inc';
  const timers=H.filter(f=>f.check.startsWith('timer:')).map(f=>`${id(f.check.slice(6))} ${chip(sevc(f.severity),b(f.detail,f.detail))}`).join('<br>');
  const space=H.filter(f=>f.check.startsWith('free_space:')||f.check.startsWith('mount:')).map(f=>`${id(f.check)} ${chip(sevc(f.severity),b(f.detail,f.detail))}`).join('<br>');
  return `${bannerHTML()}${shead('system')}<section class="band c2"><div class="col"><div class="ptitle"><span>${x('Can stop trading','قد يوقف التداول')}</span></div>${row(x('Runtime','التشغيل'),chip(...sc().dims.runtime),{insp:'runtime'})}${row(x('Market feed','تغذية السوق'),chip(...y.feed))}${row(x('Exchange API','واجهة البورصة'),chip(...y.api))}${row(x('Clock','الساعة'),chip(...y.clock))}</div>
  <div class="col"><div class="ptitle"><span>${x('Host','الخادم')}</span></div>${row(x('Host','الخادم'),chip(...y.host))}${row(x('Containers','الحاويات'),chip(...y.containers))}${row(x('Monitor','المراقبة'),chip(...y.monitor))}${row(x('Last boot','آخر إقلاع'),LD(y.boot))}${row(x('Boot ID','معرّف الإقلاع'),id(I.boot_id||'—'))}${row(x('Disk / mounts','القرص / نقاط التحميل'),space)}${row(x('Timers','المؤقتات'),timers)}</div></section>
  <section class="band c1"><div class="col"><div class="ptitle"><span>${x('Build & identity','البناء والهوية')}</span></div>${row(x('Runtime source','مصدر التشغيل'),`${id((I.runtime_pin||'—').slice(0,12))} ${I.runtime_clean?chip('ok',b('Clean','نظيف')):chip('warn',b('Not clean','غير نظيف'))}`,{insp:'runtime'})}${row(x('Governance main','الفرع الرئيسي للحوكمة'),id((I.main||'—').slice(0,12)))}${row(x('Relationship','العلاقة'),`${chip('ok',b('As declared','كما هو مُعلَن'))} <span class="a">${x('runtime pinned at the P2 freeze; main advances with P3','التشغيل مثبّت عند تجميد P2؛ والفرع الرئيسي يتقدم مع P3')}</span>`)}</div></section>${awareness()}`}

function awareness(){return `<section class="band c1"><div class="col"><div class="ptitle"><span>${x('Owner awareness','إطلاع المالك')}</span><span class="asof">P3-PLN-06</span></div>${row(x('Off-host observation','الرصد من خارج الجهاز'),chip('off','notImpl'))}${row(x('Owner notification','تنبيه المالك'),chip('ok',b('Desktop notification on WARNING / CRITICAL · this host only','تنبيه سطح المكتب عند WARNING / CRITICAL · هذا الجهاز فقط')))}<p class="cd">${x('A host that is down cannot report its own absence; this needs something that is not on the host.','الجهاز المتوقف لا يستطيع الإبلاغ عن غيابه؛ يحتاج ذلك شيئًا خارج الجهاز.')}</p></div></section>`}

/* ---------- route: bound screens live, unbound screens keep their body under the notice ---------- */
Object.keys(SCREENS).forEach(k=>{if(LIVE_BOUND.includes(k))return;const f=SCREENS[k];SCREENS[k]=()=>unboundNotice()+f()});
SCREENS.command=liveCommand;SCREENS.system=system;
liveFreshness();
setInterval(()=>{const was=SC.live.viewStale;liveFreshness();if(SC.live.viewStale!==was)render()},30000);
render();
