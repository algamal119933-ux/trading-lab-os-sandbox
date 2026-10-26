/* P3-PLN-09 live adapter for the frozen prototype v0.2.5 (sha256 e17d50dc…).
   Appended after the prototype's own script by research/p3/control_room.py. It adds no screen, slot,
   navigation item or style. It supplies the live scenario (LIVE, built from verified evidence) and
   re-declares only data-bearing components, with the prototype's markup and classes. Bound: all 12
   screens and the four mobile tabs. Slice 3 (Decisions, Trades & Positions, Market Workspace, Settings) reads the sealed cohort
   named by the newest PLN-07 execution-audit record; when it is absent or unreadable those screens say
   unknown, never healthy. Read-only: no network, no write, no control. */
"use strict";
const LIVE_BOUND=['command','system','continuity','incidents','operations','risk','evidencep','history','decisions','trades','market','settings'];
const LD=t=>tm(t);
/* the live scenario rides on the prototype's closed-family scenario, overridden field by field */
SC.live=Object.assign({},SC.closed,LIVE.scenario);
CAPS.splice(0,CAPS.length,...LIVE.caps);
FORBID.splice(0,FORBID.length,...LIVE.forbid);
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

/* ---------- Project & Continuity ---------- */
function resumeBlock(){const s=sc();const forb=FORBID.concat(s.extraForbid);
 return `<section class="resume" aria-label="${x('Resume from here','استأنف من هنا')}"><div class="rh"><h2>${x('Resume from here','استأنف من هنا')}</h2><span class="asof">${x('derived','مشتق')} ${LD(LIVE.observed_utc)}</span></div>
 <div class="rv"><p class="vs" style="margin:0">${L(s.verdict)}</p></div>
 <div class="rgrid"><span class="k">${x('Last governed checkpoint','آخر نقطة تحقق محكومة')}</span><span>${L(s.lgc)}</span><span class="k">${x('Last healthy observation','آخر رصد سليم')}</span><span>${L(s.lho)}</span>
 ${kv(chip('ok',b('Known','معروف')),s.known)}${kv(chip('unk',b('Unknown','غير معروف')),s.unknown)}${kv(chip('warn',b('Affected','متأثر')),s.affected)}${kv(chip('unver',b('Unverified','غير متحقق')),s.unverified)}</div>
 ${slots()}
 <div class="forb"><span class="k sec">${x('Forbidden now','ممنوع الآن')}</span><ul>${forb.map(f=>`<li>${L(f)}</li>`).join('')}</ul></div>
 <div class="ract"><button class="btn2" id="copybrief">${x('Copy resume brief for a new session','نسخ ملخص الاستئناف لجلسة جديدة')}</button></div>${S.briefFail?`<pre class="brief" tabindex="0" aria-label="${x('Resume brief, select to copy','ملخص الاستئناف، حدده للنسخ')}">${esc(brief())}</pre>`:''}</section>`}
function brief(){return LIVE.brief}
function lawPanel(){const s=sc(),l=s.law;const R=[['capProps',b('Capability properties','خصائص القدرة')],['lifecycle',b('Natural completed trade lifecycle','دورة صفقة مكتملة طبيعيًا')],['recon',b('Reconciliation','المطابقة')],['integrity',b('Evidence integrity','سلامة الأدلة')],['identity',b('Source / cohort / lane identity','هوية المصدر / الدفعة / المسار')],['safe',b('Safe closure','إغلاق آمن')],['records',b('Archive / digest / closure records','سجلات الأرشيف / البصمة / الإغلاق')]];
 return `<h2 class="bandlabel">${x('P2 terminal law · what PASS requires','قانون إنهاء P2 · ما تتطلبه النتيجة الناجحة')}</h2><section class="band c2"><div class="col">${R.slice(0,4).map(r=>row(L(r[1]),chip(...l[r[0]]))).join('')}</div><div class="col">${R.slice(4).map(r=>row(L(r[1]),chip(...l[r[0]]))).join('')}${row(x('Prospective paper edge','الأفضلية الورقية المستقبلية'),chip('off',b('Not evaluated','لم تُقيَّم')))}<p class="cd">${x('P&L does not decide PASS or FAIL. Source: docs/p2/P2_CLOSURE.md and the FP-CONTROL-3 registry row.','الربح والخسارة لا يحددان النجاح أو الفشل. المصدر: docs/p2/P2_CLOSURE.md وصف FP-CONTROL-3 في السجل.')}</p></div></section>`}
function continuity(){const s=sc();
 const ret=S.returned?`<div class="notice why">${gl('info')}<span><b>${x('Why you are here:','لماذا أنت هنا:')}</b> ${sigText(s)}</span><button data-go="command">${x('Go to Command Center','الانتقال إلى مركز التحكم')}</button></div>`:'';
 const cps=`<h2 class="bandlabel">${x('Checkpoints','نقاط التحقق')}</h2><section class="band c3 cps">
 <div class="col"><div class="sec small">${x('Last governed checkpoint','آخر نقطة تحقق محكومة')}</div><div class="big">${L(s.lgc)}</div><div class="cd">${x('source: governance record · does not go stale','المصدر: سجل الحوكمة · لا يتقادم')}</div></div>
 <div class="col"><div class="sec small">${x('Last healthy observation','آخر رصد سليم')}</div><div class="big">${L(s.lho)}</div><div class="cd">${x('source: operational observations','المصدر: الأرصاد التشغيلية')}</div></div>
 <div class="col"><div class="sec small">${x('Current','الحالي')}</div><div class="big">${L(s.nowObs)}</div><div class="cd">${x('derived now from 6 sources','مشتق الآن من 6 مصادر')}</div></div></section>`;
 const gm=`<h2 class="bandlabel">${x('Stage & gate map','خريطة المراحل والبوابات')}</h2><section class="band c1"><div class="col twrap"><table><thead><tr><th>${x('Stage','المرحلة')}</th><th>${x('State','الحالة')}</th><th>${x('Evidence source','مصدر الدليل')}</th></tr></thead><tbody>
 ${LIVE.stages.map(r=>`<tr><td><b>${r[0]}</b></td><td>${chip(...r[1])}</td><td class="sec">${L(r[2])}</td></tr>`).join('')}</tbody></table></div></section>`;
 return `${bannerHTML()}${ret}${ladder(true)}${outcomeHTML()}${resumeBlock()}${lawPanel()}${cps}<h2 class="bandlabel">${x('Since last governed checkpoint','منذ آخر نقطة تحقق محكومة')}</h2><section class="band c1"><div class="col">${timeline(sinceCk())}</div></section>${gm}${viewerChip()}`}

/* ---------- Incidents ---------- */
function incidents(){const s=sc();
 if(S.inc){const i=s.incidents.find(v=>v.id===S.inc)||s.incidents[0];if(i)return incidentPage(i)}
 return `${bannerHTML()}<section class="band c1"><div class="col twrap"><table><thead><tr><th>ID</th><th>${x('Title','العنوان')}</th><th>${x('State','الحالة')}</th><th>${x('Opened','فُتحت')}</th></tr></thead><tbody>${LIVE.incidents_state&&LIVE.incidents_state.state!=='bound'?`<tr><td colspan="4" class="quiet">${chip('unk','unknown')} ${L(LIVE.incidents_state.why)}</td></tr>`:s.incidents.length?s.incidents.map(i=>`<tr class="click" data-inc="${i.id}" tabindex="0"><td>${id(i.id)}</td><td>${L(i.title)}</td><td>${chip(...ISTATE[i.s])}</td><td>${LD(i.when)}</td></tr>`).join(''):`<tr><td colspan="4" class="quiet">${gl('ok')} ${x('None open. Incidents are raised from non-INFO health findings; none at this observation.','لا حوادث مفتوحة. تُفتح الحوادث من نتائج الصحة غير INFO؛ لا شيء في هذا الرصد.')}</td></tr>`}</tbody></table></div></section>`}
/* the prototype's incident page, with live dates (a wrapper would capture this hoisted declaration) */
function incidentPage(i){const f=i.f;
 const F=[[chip('ok',b('Known','معروف')),f.known],[x('Detected by','طريقة الرصد'),f.detect],[chip('unk',b('Unknown','غير معروف')),f.unknown],[chip('warn',b('Affected','متأثر')),f.affected],[chip('unver',b('Unverified','غير متحقق')),f.unverified],[x('What remained safe','ما بقي آمنًا'),f.safe],[x('Recovery','التعافي'),f.recovery],[x('Reconciliation required?','هل تلزم المطابقة؟'),f.reconReq],[`${x('Next action','الإجراء التالي')} <span class="fc">${x('derived from contract','مستمد من العقد')}</span>`,f.next],[x('Current state','الحالة الحالية'),f.state],[x('Owner','المالك'),f.owner],['Claude',f.claude],[x('Evidence','الأدلة'),f.evidence]].filter(r=>r[1]);
 return `${bannerHTML()}<div class="shead"><button class="btn2" data-inc="">${S.lang==='ar'?'→':'←'} ${x('Incidents','الحوادث')}</button><h1 style="font-size:18px">${id(i.id)} · ${L(i.title)}</h1>${chip(...ISTATE[i.s])}<span class="asof">${x('opened','فُتحت')} ${LD(i.when)}</span></div>
 <section class="band c1"><div class="col"><div class="rgrid" style="padding:0;grid-template-columns:220px 1fr">${F.map(r=>`<span class="k">${r[0]}</span><span>${L(r[1])}</span>`).join('')}</div></div></section>
 <p class="cd" style="margin:-8px 0 16px">${x('Only what evidence proves is stated as known. Causes and outcomes that are not proven are listed as unknown.','لا يُذكر كمعروف إلا ما تثبته الأدلة. الأسباب والنتائج غير المثبتة تُدرج كغير معروفة.')}</p>
 ${false?`<h2 class="bandlabel">${x('Incident timeline','الخط الزمني للحادثة')}</h2><section class="band c1"><div class="col">${timeline(sc().events.slice(-4))}</div></section>`:''}
 <section class="band c1 ackz"><div class="col"><div><b>${x('Acknowledge incident','الإقرار بالحادثة')}</b> ${chip('off','notImpl')} ${chip('na','na')}<p class="sec small" style="margin:6px 0 0;max-width:62ch">${x('Proposed operator action. Its permission, audit record, effect on incident state and persistence will be set by the P3 operator-control contract. Nothing happens here.','إجراء تشغيلي مقترح. تُحدَّد صلاحيته وسجل تدقيقه وأثره على حالة الحادثة واستمراريته في عقد التحكم التشغيلي لـ P3. لا يحدث شيء هنا.')}</p></div><button class="btn2" aria-disabled="true" id="ack">${x('Acknowledge','إقرار')}</button></div></section>`}

/* ---------- Operations ---------- */
function operations(){const s=sc(),o=s.ops,P=LIVE.ops;
 const ov=[[x('Runtime','التشغيل'),chip(...o.runtime)],[x('Safe state','الحالة الآمنة'),chip(...o.safe)],[x('Recovery','التعافي'),chip(...o.recovery)],[x('Backup','النسخ الاحتياطي'),chip(...P.backup)],[x('Restore','الاستعادة'),chip(...P.restore)]];
 return `${bannerHTML()}
 <section class="ovl" aria-label="${x('Operations overview','نظرة عامة على العمليات')}">${ov.map(v=>`<span><span class="k">${v[0]}</span>${v[1]}</span>`).join('')}</section>
 <section class="band opsg">
  <div class="col"><div class="ptitle"><span>${x('Runtime','التشغيل')}</span></div>${row(x('Operational state','الحالة التشغيلية'),chip(...o.runtime),{insp:'runtime'})}${row(x('Safe-state status','حالة الوضع الآمن'),chip(...o.safe))}${row(x('Recovery state','حالة التعافي'),chip(...o.recovery))}</div>
  <div class="col"><div class="ptitle"><span>${x('Backup','النسخ الاحتياطي')}</span><span class="asof">${x('daily 03:30 UTC · systemd','يوميًا 03:30 UTC · systemd')}</span></div>${row(x('Backup health','سلامة النسخ'),chip(...P.backup))}${row(x('Last backup','آخر نسخة'),id(P.last_set||'—'))}${row(x('Last verified backup','آخر نسخة متحقق منها'),P.backup[0]==='ok'?id(P.last_set):chip('unk','unknown'))}${row(x('Retention / readiness','الاحتفاظ / الجاهزية'),`<span class="a">${L(P.retention)}</span>`)}</div>
  <div class="col"><div class="ptitle"><span>${x('Restore','الاستعادة')}</span></div>${row(x('Restore readiness','جاهزية الاستعادة'),chip(...P.restore))}${row(x('Recovery points','نقاط التعافي'),tm(String(P.points)))}${row(x('Last successful restore proof','آخر إثبات استعادة ناجحة'),P.restore_when?LD(P.restore_when):chip('unk','notRecorded'))}</div>
  <div class="col"><div class="ptitle"><span>${x('Recovery','التعافي')}</span></div>${row(x('Current status','الحالة الحالية'),chip(...o.recovery))}${row(x('Host reboot recovery','تعافي إعادة إقلاع الخادم'),chip(...P.reboot))}${row(x('Unresolved conditions','حالات غير محلولة'),tm(String(o.unresolved)))}${row(x('Recovery history','سجل التعافي'),`<span class="a">${L(o.hist)}</span>`)}</div>
 </section>
 <p class="cd" style="margin:-8px 0 16px">${x('Backup and restore come from the newest backup set and the persisted restore-drill record. A reboot recovery is not claimed until it is exercised.','النسخ والاستعادة مصدرهما أحدث مجموعة نسخ وسجل تمرين الاستعادة المحفوظ. لا يُدّعى تعافي إعادة الإقلاع حتى يُختبر.')}</p>
 <h2 class="bandlabel">${x('Authorized actions · operator CLI, not this view','الإجراءات المصرّح بها · سطر أوامر المشغّل وليس هذه الشاشة')}</h2>
 <section class="band c1"><div class="col">${P.acts.map(a=>`<div class="op"><div><div><b>${L(a[0])}</b></div><div class="od">${id(a[1])}</div><div class="od">${L(a[2])}</div></div><div>${chip('ok',b('Available · CLI','متاح · سطر الأوامر'))} ${chip('na',b('Not in this view','ليس في هذه الشاشة'))}</div></div>`).join('')}</div></section>
 <section class="emerg" aria-label="${x('Emergency','الطوارئ')}"><h2>${x('Emergency · Kill Switch','الطوارئ · مفتاح الإيقاف الكلي')}</h2>
 <p class="sec small" style="margin:0">${x('Separate from Safe Stop. This view never triggers it. The ledgered operator CLI stops only paper runtimes, requires a reason and records who and why.','منفصل عن الإيقاف الآمن. هذه الشاشة لا تفعّله أبدًا. سطر أوامر المشغّل المسجَّل يوقف التشغيل الورقي فقط، ويتطلب سببًا، ويسجّل من ولماذا.')}</p>
 <ul><li>${id('scripts/p3/kill_switch.py --reason "…"')}</li><li>${x('Last drill: STOPPED in 0.162 s, ledger chain PASS.','آخر تمرين: توقف خلال 0.162 ث، وسلسلة السجل ناجحة.')}</li></ul>
 <button class="btn2" aria-disabled="true" id="kill">${x('Kill Switch','مفتاح الإيقاف الكلي')} · ${x('not in this view','ليس في هذه الشاشة')}</button></section>`}

/* ---------- Risk & Authority ---------- */
function risk(){const s=sc(),off=s.dims.runtime[0]!=='ok',na=chip('off',b('Not applicable · runtime stopped','لا ينطبق · التشغيل متوقف'));
 return `${bannerHTML()}${shead('risk')}
 <section class="band c2"><div class="col"><div class="ptitle"><span>${x('Current state','الحالة الحالية')}</span></div>${row(x('Current exposure','الانكشاف الحالي'),off?`${tm('0%')} ${chip('ok',b('No open positions','لا مراكز مفتوحة'))}`:chip('unk','unknown'))}${row(x('Daily loss','الخسارة اليومية'),off?na:chip('unk','unknown'))}${row(x('Vetoes (24h)','الاعتراضات (24 س)'),off?na:chip('unk','unknown'))}${row(x('Open positions','المراكز المفتوحة'),tm(String(s.pos.length)))}</div>
 <div class="col"><div class="ptitle"><span>${x('Governed configuration','الإعداد المحكوم')}</span><span class="asof">${x('contract / config fact, not current state','حقيقة عقد / إعداد، وليست حالة حالية')}</span></div>${row(x('Risk limits','حدود المخاطر'),L(LIVE.risk_cfg.limits))}${row(x('Limits source','مصدر الحدود'),id(LIVE.risk_cfg.src))}</div></section>
 <h2 class="bandlabel">${x('Capability & Authority Matrix','مصفوفة القدرات والصلاحيات')}</h2>
 <section class="band c1"><div class="col twrap"><table><thead><tr><th>${x('Capability','القدرة')}</th><th>${x('State','الحالة')}</th><th>${x('Authority source','مصدر الصلاحية')}</th><th>${x('Since','منذ')}</th><th>${x('Expected relationship / preconditions','العلاقة المتوقعة / الشروط المسبقة')}</th></tr></thead><tbody>
 ${CAPS.map((c,i)=>`<tr class="click" data-insp="cap:${i}" tabindex="0"><td>${typeof c.k==='string'?id(c.k):L(c.k)}</td><td>${chip(...c.st)}</td><td>${typeof c.src==='string'?id(c.src):L(c.src)}</td><td>${c.since==='—'?'—':id(c.since)}</td><td class="sec">${L(c.pre)}</td></tr>`).join('')}</tbody></table>
 <p class="cd">${x('Rows come from authority truth, not from this layout. A new capability appears as a new row; an unreadable row shows Unknown and is treated as blocked.','الصفوف مصدرها حقيقة الصلاحيات لا هذا التصميم. تظهر أي قدرة جديدة كصف جديد؛ والصف غير المقروء يظهر غير معروف ويُعامل كمحظور.')}</p></div></section>`}

/* ---------- Evidence & Reconciliation ---------- */
function evidencep(){const s=sc(),d=s.dims.recon,R=LIVE.evidence_rows.slice().sort((a,z)=>(a[1][0]==='ok')-(z[1][0]==='ok'));
 return `${bannerHTML()}${shead('evidencep')}<section class="sit"><div class="vl"><p class="vs">${x('Reconciliation','المطابقة')} ${chip(...d)}</p><p class="asof">${x('Sources','المصادر')}: ${id('P2_CLOSURE')} · ${id('restore drill')} · ${id('execution audit')}</p></div></section>
 <section class="band c1"><div class="col twrap"><table><thead><tr><th>${x('Check','الفحص')}</th><th>${x('Result','النتيجة')}</th><th>${x('Source','المصدر')}</th></tr></thead><tbody>${R.map(r=>`<tr class="click" data-insp="recon" tabindex="0"><td>${L(r[0])}</td><td>${chip(...r[1])}</td><td class="sec">${id(r[2])}</td></tr>`).join('')}</tbody></table></div></section>`}

/* ---------- slice 3: sealed cohort (read-only) ---------- */
function sealedNote(o){if(o.state==='bound')return `<p class="cd">${x(`Sealed cohort ${o.cohort} · read-only record · no paper cohort is running now`,`المجموعة المختومة ${o.cohort} · سجل للقراءة فقط · لا مجموعة ورقية تعمل الآن`)}</p>`;
 return `<div class="banner b-info" role="status"><span class="bg" aria-hidden="true">${G.unk}</span><p>${chip('unk','unknown')} ${L(o.why)}</p></div>`}
/* ---------- Decisions ---------- */
function decisions(){const s=sc(),D3=LIVE.decisions,V=D3.rows;
 if(D3.state!=='bound'||!V.length)return `${bannerHTML()}${shead('decisions')}${sealedNote(D3)}<section class="band c1"><div class="col twrap"><table><thead><tr><th>${x('Time','الوقت')}</th><th>${x('Pair','الزوج')}</th><th>${x('Outcome','النتيجة')}</th></tr></thead><tbody><tr><td colspan="3" class="quiet">${chip('unk','unknown')}</td></tr></tbody></table></div></section>`;
 const d=V.find(v=>v.id===S.dec)||V[V.length-1];
 return `${bannerHTML()}${shead('decisions')}${sealedNote(D3)}<section class="band" style="grid-template-columns:4fr 8fr"><div class="col twrap"><table><thead><tr><th>${x('Time','الوقت')}</th><th>${x('Pair','الزوج')}</th><th>${x('Outcome','النتيجة')}</th></tr></thead><tbody>${V.slice().reverse().map(v=>`<tr class="click" data-dec="${v.id}" tabindex="0" ${v.id===d.id?'style="background:var(--raised)"':''}><td>${LD(v.t)}</td><td>${id(v.p)}</td><td>${chip(...v.o)}</td></tr>`).join('')}</tbody></table><p class="cd">${x(`${V.length} of ${D3.n} decisions listed: every enter / exit intent and admission, plus the last decision per pair.`,`${V.length} من ${D3.n} قرارًا: كل نية دخول / خروج وكل قبول، وآخر قرار لكل زوج.`)}</p></div>
 <div class="col"><div class="ptitle"><span>${x('Decision / Execution Trace','مسار القرار / التنفيذ')} ${id(d.p)} · ${LD(d.t)}</span>${chip('unver',b('Sealed record','سجل مختوم'))}</div>
 ${PIPE.map((p,i)=>`<div class="row" style="grid-template-columns:24px 150px 1fr;${d.tr[i][0]==='off'?'opacity:.55':''}"><span class="muted num">${i+1}</span><span class="k">${L(p)}</span><span class="v">${gl(d.tr[i][0])} ${L(d.tr[i][1])}${d.tr[i][0]==='off'?` <span class="a">${x('not reached','لم تُبلغ')}</span>`:''}</span></div>`).join('')}
 <p class="sec small">${x('Reason','السبب')}: ${L(d.r)}</p>${row(x('Market / Data Truth context','سياق حقيقة السوق / البيانات'),`${id(d.tf||'—')} · ${id(d.t0||'—')}`)}${row(x('Evidence refs','مراجع الأدلة'),id(d.refs))}${row(x('Runtime / source identity','هوية التشغيل / المصدر'),id(d.ident))}<p class="cd">${x('Per-stage outputs are shown only where the runtime logged them; a stage it does not log reads "not logged".','تُعرض مخرجات كل مرحلة فقط حيث سجّلها التشغيل؛ والمرحلة غير المسجّلة تظهر "غير مسجّل".')}</p></div></section>`}
/* ---------- Trades & Positions ---------- */
function trades(){const s=sc(),T=LIVE.trades_closed;const ex=CAPS.filter(c=>c.exec);
 const open=s.pos.length?'':`<tr><td colspan="8" class="sec">${x('No open positions.','لا مراكز مفتوحة.')} ${x('No paper cohort is running.','لا مجموعة ورقية تعمل.')}</td></tr>`;
 const body=T.state!=='bound'?`<p class="quiet">${chip('unk','unknown')} ${L(T.why)}</p>`:T.rows.length?`<table><thead><tr><th>${x('Pair','الزوج')}</th><th>${x('Side','الاتجاه')}</th><th class="r">${x('Entry','الدخول')}</th><th class="r">${x('Exit','الخروج')}</th><th>${x('Exit reason','سبب الخروج')}</th><th>${x('Reconciliation','المطابقة')}</th><th>${x('Verified outcome','النتيجة المتحقق منها')}</th><th class="r">${x('PnL','الربح/الخسارة')}</th></tr></thead><tbody>${T.rows.map(r=>`<tr><td>${id(r.pair)} <span class="muted">#${r.trade_id}</span></td><td>${x('Long','شراء')}</td><td class="r">${id(r.entry)}</td><td class="r">${id(r.exit)}</td><td>${id(r.reason)}</td><td>${chip(...r.recon)}</td><td>${chip(...r.outcome)}</td><td class="r">${r.pnl===null?chip('unk','unknown'):tm(r.pnl)}</td></tr>`).join('')}</tbody></table>`:`<p class="quiet">${chip('off','noData')} ${x('No completed trade lifecycle in the sealed record.','لا توجد دورة صفقة مكتملة في السجل المختوم.')}</p>`;
 return `${bannerHTML()}${shead('trades')}
 <div class="capstrip"><span class="sec">${x('Execution capabilities','قدرات التنفيذ')}:</span>${ex.map(c=>`${L(c.k)} ${chip(...c.st)}`).join(' ')}<span class="cd">${x('rows supplied by authority truth','الصفوف مصدرها حقيقة الصلاحيات')}</span></div>
 <h2 class="bandlabel">${x('Open','المفتوحة')}</h2><section class="band c1"><div class="col twrap"><table><thead><tr><th>${x('Pair','الزوج')}</th><th>${x('Side','الاتجاه')}</th><th>${x('Verification','التحقق')}</th><th>${x('Size','الحجم')}</th><th class="r">${x('Entry','الدخول')}</th><th>${x('Risk at entry','المخاطرة عند الدخول')}</th><th>${x('Exit contract','عقد الخروج')}</th><th class="r">${x('PnL','الربح/الخسارة')}</th></tr></thead><tbody>${open}</tbody></table></div></section>
 <h2 class="bandlabel">${x('Closed','المغلقة')}</h2><section class="band c1"><div class="col twrap">${sealedNote(T)}${body}<p class="cd">${x('Realised PnL as recorded in the sealed trade ledger. Reconciliation per leg comes from the PLN-07 execution audit. P&L decides nothing.','الربح/الخسارة المحقق كما في سجل الصفقات المختوم. مطابقة كل طرف من تدقيق التنفيذ PLN-07. الربح والخسارة لا يحددان شيئًا.')} ${id(T.src)}</p></div></section>`}
/* ---------- Market Workspace ---------- */
function liveCandles(pair){const M=LIVE.market,bars=(M.candles[pair]||[]);if(!bars.length)return `<p class="quiet">${chip('unk','unknown')}</p>`;
 const n=bars.length,w=880,h=260,cw=w/n;let out='';const mx=Math.max(...bars.map(v=>v[2])),mn=Math.min(...bars.map(v=>v[3])),Y=v=>12+(mx-v)/((mx-mn)||1)*(h-24);
 for(let g=0;g<5;g++){const y=12+g*(h-24)/4;out+=`<line x1="0" x2="${w}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="1"/>`}
 bars.forEach((v,i)=>{const X=i*cw+cw/2,up=v[4]>=v[1];out+=`<line x1="${X}" x2="${X}" y1="${Y(v[2])}" y2="${Y(v[3])}" stroke="var(--tx3)"/><rect x="${X-cw*.3}" y="${Y(Math.max(v[1],v[4]))}" width="${cw*.6}" height="${Math.max(1,Math.abs(Y(v[1])-Y(v[4])))}" fill="${up?'none':'var(--tx3)'}" stroke="${up?'var(--tx2)':'var(--tx3)'}"/>`});
 const t0=bars[0][0],step=n>1?(bars[n-1][0]-t0)/(n-1):3600000;
 (M.marks[pair]||[]).forEach(m=>{const ms=Date.parse(m[0].replace(' ','T')+(m[0].endsWith('Z')?'':'Z'));const i=Math.round((ms-t0)/step);if(i<0||i>=n)return;const mX=i*cw+cw/2;out+=`<path d="M${mX-6} ${h-4} L${mX+6} ${h-4} L${mX} ${h-14}Z" fill="var(--warn)"/><text x="${mX+10}" y="${h-6}" fill="var(--tx2)" font-size="11" font-family="var(--sans)">${m[1]}</text>`});
 const svg=`<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${x(`Candle chart, sealed record ${pair}`,`رسم الشموع، السجل المختوم ${pair}`)}">${out}</svg>`;
 const t=b(`CURRENT MARKET STATE UNKNOWN · no runtime, no feed · chart shows the sealed P2 record ending ${M.end_utc}`,`حالة السوق الحالية غير معروفة · لا تشغيل ولا تغذية · يعرض الرسم السجل المختوم لـ P2 المنتهي ${M.end_utc}`);
 return `<div class="chartwrap unkchart">${svg}<div class="chartov s-unk" dir="${S.lang==='ar'?'rtl':'ltr'}" role="status">${gl('unk')} ${L(t)}</div></div>`}
function market(){const M=LIVE.market;
 if(M.state!=='bound'||!M.pairs.length)return `${bannerHTML()}${shead('market')}${sealedNote(M.state==='bound'?{state:'none',why:b('The sealed record holds no candles.','لا يحتوي السجل المختوم على شموع.')}:M)}<section class="band c1"><div class="col"><p class="quiet">${chip('unk','unknown')} ${x('Current market state unknown: no runtime, no feed.','حالة السوق الحالية غير معروفة: لا تشغيل ولا تغذية.')}</p></div></section>`;
 if(!M.pairs.includes(S.pair))S.pair=M.pairs[0];if(!M.timeframes.includes(S.tf))S.tf=M.timeframes[0];
 const caps=[[b('Candles (OHLCV)','الشموع (OHLCV)'),'off',b('No live feed · sealed record only','لا تغذية مباشرة · السجل المختوم فقط')],[b('Order book depth','عمق دفتر الأوامر'),'na','notProvided'],[b('Regime / higher-timeframe context','نظام السوق / سياق الإطار الأعلى'),'unk','unkInv']];
 return `${bannerHTML()}${shead('market')}
 <section class="band c1"><div class="col">
 <div class="capstrip"><span class="sec">${x('Pair','الزوج')}</span><span class="tfs">${M.pairs.map(p=>`<button data-pair="${p}" aria-pressed="${S.pair===p}">${id(p)}</button>`).join('')}</span><span class="sep"></span>
 <span class="sec">${x('Timeframe','الإطار الزمني')}</span><span class="tfs">${M.timeframes.map(t=>`<button data-tf="${t}" aria-pressed="${S.tf===t}">${tm(t)}</button>`).join('')}</span></div>
 <p class="cd" style="margin:0 0 8px">${x('Pairs and timeframe come from the sealed cohort record; markers are its recorded fills.','الأزواج والإطار الزمني من سجل المجموعة المختومة؛ والعلامات هي تنفيذاتها المسجلة.')} ${id(M.src)}</p>
 ${liveCandles(S.pair)}</div></section>
 <section class="band c2"><div class="col"><div class="ptitle"><span>${x('Market / Data Truth · capabilities','حقيقة السوق / البيانات · القدرات')}</span><span class="asof">${x('upstream of the Decision / Execution Trace','منبع مسار القرار / التنفيذ')}</span></div>${caps.map(c=>row(L(c[0]),chip(c[1],c[2]))).join('')}</div>
 <div class="col"><div class="ptitle"><span>${x('Context','السياق')}</span>${chip('unk','unknown')}</div>${row(x('Data age','عمر البيانات'),chip(...sc().sys.feed))}${row(x('Regime','نظام السوق'),chip('unk','unkInv'))}${row(x('Volatility','التذبذب'),chip('unk','unkInv'))}${row(x('Liquidity','السيولة'),chip('unk','unkInv'))}${row(x('Higher-timeframe context','سياق الإطار الأعلى'),chip('unk','unkInv'))}<p class="cd">${x('Neutral candles by design: colour is reserved for system state.','شموع محايدة عمدًا: اللون محجوز لحالة النظام.')}</p></div></section>`}
/* ---------- Settings: viewer preferences only ---------- */
function settings(){const T=LIVE.settings;
 const sig=[b('Significant absence','غياب طويل'),b('Meaningful events since last view','أحداث مهمة منذ آخر مشاهدة'),b('New incident','حادثة جديدة'),b('Host / runtime restart','إعادة تشغيل الخادم / التشغيل'),b('Owner gate opened','فتح بوابة المالك')];
 const na=chip('off',b('Not active · a static view keeps no viewer state','غير مفعّل · العرض الثابت لا يحفظ حالة العارض'));
 return `${shead('settings')}<section class="band c2"><div class="col"><div class="ptitle"><span>${x('Return detection','رصد العودة')}</span><span class="asof">${x('viewer preference · UI only','تفضيل العارض · الواجهة فقط')}</span></div>${sig.map(v=>row(L(v),na)).join('')}${row(x('Absence threshold','حد الغياب'),na)}<p class="cd">${x('These settings decide only whether Resume opens first. They never change what Resume says.','تحدد هذه الإعدادات فقط ما إذا كان الاستئناف يُفتح أولًا. ولا تغيّر أبدًا ما يقوله.')}</p></div>
 <div class="col"><div class="ptitle"><span>${x('Display','العرض')}</span></div>${row(x('Language','اللغة'),x('English','العربية'))}${row(x('Theme','السمة'),x('Dark','داكنة'))}${row(x('Time display','عرض الوقت'),L(T.time))}${row(x('Density','الكثافة'),x('Comfortable','مريحة'))}${row(x('Inspector','المُفتِّش'),x('Auto: dock on wide screens','تلقائي: مثبّت على الشاشات العريضة'))}${row(x('Notifications','التنبيهات'),`${chip('ok',T.notify)} <span class="a">${id(T.notify_src)}</span>`)}${row(x('Remote access','الوصول عن بُعد'),chip('off',b('Not implemented · P3-PLN-06','غير منفّذ · P3-PLN-06')))}<p class="cd">${x('Settings never change risk, mode or authority.','الإعدادات لا تغيّر المخاطر أو الوضع أو الصلاحيات أبدًا.')}</p></div></section>`}

/* ---------- Mobile: Status / Resume / Incidents / More (monitoring and continuity only) ----------
   The frozen mobile components, re-declared only where they carry data: the stage label and project
   line come from the live identity and the governed workstream record, Operations from the persisted
   backup and drill records, Decisions and Trades from the sealed cohort. Nothing on mobile acts: no
   action, no acknowledgement, no Kill Switch. Incidents is re-declared below (explicit empty and UNKNOWN
   states). Resume keeps the prototype's own body: every field it shows (step, verdict, outcome, lifecycle,
   checkpoint, known/unknown, responsibility, forbidden list) is projected from evidence by control_room.py.
   Risk, Evidence, History, System and Market keep the prototype's own bodies over the live scenario. */
function mStatus(){const s=sc();const exc=Object.keys(s.dims).filter(k=>s.dims[k][0]!=='ok');const o=openIncs();
 return `${bannerHTML()}<p class="vs">${L(s.verdict)}</p>${mResp()}<div class="mcard small">${x('Project','المشروع')}: ${L(LIVE.ident.stage)}<br>${LIVE.project.chips.map(c=>chip(c[0],c[1])).join(' ')}<br>${x('Next Owner gate','بوابة المالك التالية')}: ${L(LIVE.project.gate)}</div>
 <div class="mcard small">${s.dec.none?L(s.dec.none):`${x('Last decision','آخر قرار')} ${chip('unk','unknown')}`}<br>${x('Exposure','الانكشاف')} ${expoTxt()} · ${s.pos.length?chip('unk','unknown'):x('no open positions','لا مراكز مفتوحة')}<br>${x('Open incidents','حوادث مفتوحة')}: ${tm(String(o.length))}</div>
 ${exc.length?`<div class="mcard">${exc.map(k=>`<div class="mrow"><span class="k">${gl(s.dims[k][0])} ${L(DIMN[k])}</span><span>${L(s.exc[k]||'')}</span></div>`).join('')}</div>`:''}`}
function mDetail(k){const s=sc();
 if(k.startsWith('inc:')){const i=s.incidents.find(v=>v.id===k.slice(4));if(!i)return `<div class="mcard small">${chip('unk','unknown')}</div>`;const f=i.f;return `<div class="mcard"><b>${id(i.id)}</b> ${chip(...ISTATE[i.s])}<br>${L(i.title)}</div><div class="mcard small">${[['ok','Known','معروف',f.known],['ok','Remained safe','بقي آمنًا',f.safe],['unk','Unknown','غير معروف',f.unknown],['warn','Affected','متأثر',f.affected],['unver','Unverified','غير متحقق',f.unverified]].filter(r=>r[3]).map(r=>`<div class="mrow"><span class="k">${gl(r[0])} ${x(r[1],r[2])}</span><span>${L(r[3])}</span></div>`).join('')}${f.next?`<div class="mrow"><span class="k">${x('Next','التالي')}</span><span>${L(f.next)} <span class="fc">${x('from contract','من العقد')}</span></span></div>`:''}</div><p class="cd">${x('Acknowledge: not in this view; the operator CLI records it.','الإقرار: ليس في هذا العرض؛ يسجّله سطر أوامر المشغّل.')}</p>`}
 if(k==='operations'){const o=s.ops,P=LIVE.ops;return `<div class="mcard small">${[[x('Runtime','التشغيل'),chip(...o.runtime)],[x('Safe state','الحالة الآمنة'),chip(...o.safe)],[x('Recovery','التعافي'),chip(...o.recovery)],[x('Backup','النسخ الاحتياطي'),chip(...P.backup)],[x('Restore','الاستعادة'),chip(...P.restore)],[x('Host reboot recovery','تعافي إعادة إقلاع الخادم'),chip(...P.reboot)]].map(r=>`<div class="mrow"><span class="k">${r[0]}</span><span>${r[1]}</span></div>`).join('')}</div><p class="cd">${x('Actions are operator CLI only. The Kill Switch is never in this view and never on mobile.','الإجراءات عبر سطر أوامر المشغّل فقط. مفتاح الإيقاف الكلي ليس في هذا العرض أبدًا ولا على الجوال.')}</p>`}
 if(k==='market')return `<div class="mcard small">${x('Charts are intentionally not shown on mobile.','الرسوم البيانية لا تُعرض على الجوال عمدًا.')}<br>${x('Data age','عمر البيانات')} ${chip(...s.sys.feed)}</div>`;
 if(k==='decisions'){const D3=LIVE.decisions,V=D3.rows;
  if(D3.state!=='bound'||!V.length)return `<div class="mcard small">${L(s.dec.none)}<br>${chip('unk','unknown')} ${D3.why?L(D3.why):''}</div>`;
  const d=V[V.length-1];
  return `<div class="mcard small">${L(s.dec.none)}<br>${x('Last sealed decision','آخر قرار مختوم')} ${chip(...d.o)} ${id(d.p)} · ${LD(d.t)} ${chip('unver',b('Sealed record','سجل مختوم'))}</div>${PIPE.map((p,i)=>`<div class="mrow"><span class="k">${L(p)}</span><span>${gl(d.tr[i][0])} ${L(d.tr[i][1])}</span></div>`).join('')}`}
 if(k==='trades'){const T=LIVE.trades_closed;
  const open=`<div class="mcard small">${s.pos.length?chip('unk','unknown'):`${x('No open positions.','لا مراكز مفتوحة.')} ${x('No paper cohort is running.','لا مجموعة ورقية تعمل.')}`}</div>`;
  const closed=T.state!=='bound'?`<div class="mcard small">${chip('unk','unknown')} ${T.why?L(T.why):''}</div>`:T.rows.length?T.rows.map(r=>`<div class="mcard small">${id(r.pair)} <span class="muted">#${r.trade_id}</span> · ${chip(...r.recon)} · ${r.pnl===null?chip('unk','unknown'):tm(r.pnl)}</div>`).join(''):`<div class="mcard small">${chip('off','noData')} ${x('No completed trade lifecycle in the sealed record.','لا توجد دورة صفقة مكتملة في السجل المختوم.')}</div>`;
  return open+closed}
 if(k==='risk')return `<div class="mcard small">${CAPS.map(c=>`<div class="mrow"><span class="k">${typeof c.k==='string'?id(c.k):L(c.k)}</span><span>${chip(...c.st)}</span></div>`).join('')}</div>`;
 if(k==='evidencep')return `<div class="mcard small">${x('Reconciliation','المطابقة')} ${chip(...s.dims.recon)}<br>${x('Evidence','الأدلة')} ${chip(...s.dims.evidence)}</div>`;
 if(k==='history')return `<div class="mcard">${timeline(s.events,true)}</div>`;
 if(k==='system')return `<div class="mcard small">${[['host','Host','الخادم'],['containers','Containers','الحاويات'],['feed','Feed','التغذية'],['clock','Clock','الساعة']].map(r=>`<div class="mrow"><span class="k">${x(r[1],r[2])}</span><span>${chip(...s.sys[r[0]])}</span></div>`).join('')}</div>`;
 return `<div class="mcard small">${x('Settings are viewer preferences on desktop. They never change risk, mode or authority.','الإعدادات تفضيلات للعارض على سطح المكتب. لا تغيّر المخاطر أو الوضع أو الصلاحيات أبدًا.')}</div>`}
/* Mobile Incidents: the prototype's list, plus an explicit empty state (the prototype renders nothing)
   and UNKNOWN when the health run gave no findings. Navigation only: rows open the read-only detail. */
function mInc(){const s=sc();const st=LIVE.incidents_state||{state:'unknown',why:b('Incident source not observed.','مصدر الحوادث غير مرصود.')};
 if(st.state!=='bound')return `<div class="mcard small">${chip('unk','unknown')} ${L(st.why)}</div>`;
 if(!s.incidents.length)return `<div class="mcard small">${gl('ok')} ${x('None open.','لا حوادث مفتوحة.')} <span class="muted">${x('Incidents are raised from non-INFO health findings, §19 checks included; none at this observation.','تُفتح الحوادث من نتائج الصحة غير INFO، ومنها فحوص §19؛ لا شيء في هذا الرصد.')}</span></div>`;
 return `<div class="mlist">${s.incidents.map(i=>`<button data-mdet="inc:${i.id}"><span>${id(i.id)}<br><span class="sec small">${L(i.title)}</span></span>${chip(...ISTATE[i.s])}</button>`).join('')}</div>`}
function mobile(){const s=sc();const d=s.dims;
 const tabs=[['status',b('Status','الحالة'),'◧'],['resume',b('Resume','استئناف'),'↺'],['incidents',b('Incidents','الحوادث'),'■'],['more',b('More','المزيد'),'⋯']];
 const body=S.mdetail?`<button class="btn2" data-mdet="">${S.lang==='ar'?'→':'←'} ${x('Back','رجوع')}</button><div style="margin-top:10px">${mDetail(S.mdetail)}</div>`:S.mtab==='status'?mStatus():S.mtab==='resume'?mResume():S.mtab==='incidents'?mInc():mMore();
 const allok=Object.values(d).every(v=>v[0]==='ok');
 return `<div class="phone" dir="${S.lang==='ar'?'rtl':'ltr'}" lang="${S.lang}">${pban()}
 <div class="mbar"><b>TLOS</b><span class="sec">${L(LIVE.ident.stage)}</span><span class="mode">${x('PAPER','ورقي')}</span><span class="lock" title="${x('Real money blocked','المال الحقيقي محظور')}">${LOCK}</span><span class="grow"></span><span class="heart ${s.viewStale?'st':''}" id="heart"></span></div>
 <div class="mglyph">${Object.keys(d).map(k=>`<span title="${esc(L(DIMN[k]))}" class="gl s-${d[k][0]}">${G[d[k][0]]}</span>`).join('')}<span class="sec" style="font-size:12px">${allok?x('all 6 ok','الستة سليمة'):x(`${Object.values(d).filter(v=>v[0]!=='ok').length} need attention`,`${Object.values(d).filter(v=>v[0]!=='ok').length} تحتاج انتباهًا`)}</span></div>
 <div class="mscroll ${s.viewStale?'viewstale':''}">${body}</div>
 <nav class="mtabs" aria-label="${x('Mobile','الجوال')}">${tabs.map(([k,l,ic])=>`<button data-mtab="${k}" ${S.mtab===k&&!S.mdetail?'aria-current="page"':''}><span aria-hidden="true">${ic}</span>${L(l)}${k==='incidents'&&openIncs().length?` <span class="badge">${openIncs().length}</span>`:''}</button>`).join('')}</nav></div>`}
/* device: the prototype's device toggle sits in the hidden prototype panel; a narrow viewport opens the
   mobile view, and #mobile / #desktop in the address override it (view state only, nothing stored) */
function liveDevice(){const h=(location.hash||'').toLowerCase();if(h==='#mobile')return 'mobile';if(h==='#desktop')return 'desktop';
 return window.matchMedia&&window.matchMedia('(max-width: 720px)').matches?'mobile':'desktop'}
S.device=liveDevice();
window.addEventListener('hashchange',()=>{S.device=liveDevice();S.mdetail=null;render()});

/* ---------- route: bound screens live, unbound screens keep their body under the notice ---------- */
Object.keys(SCREENS).forEach(k=>{if(LIVE_BOUND.includes(k))return;const f=SCREENS[k];SCREENS[k]=()=>unboundNotice()+f()});
SCREENS.command=liveCommand;SCREENS.system=system;SCREENS.continuity=continuity;SCREENS.incidents=incidents;
SCREENS.operations=operations;SCREENS.risk=risk;SCREENS.evidencep=evidencep;SCREENS.history=historyScr;
SCREENS.decisions=decisions;SCREENS.trades=trades;SCREENS.market=market;SCREENS.settings=settings;
liveFreshness();
setInterval(()=>{const was=SC.live.viewStale;liveFreshness();if(SC.live.viewStale!==was)render()},30000);
render();
