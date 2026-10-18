"use strict";

// The simple view explains server figures; it never calculates a forecast or approves money.
window.TidewayOwner = (() => {
  let key = "", epoch = 0, language = "en", draft = {}, report = null, coach = null, pending = false, request = null;
  let renderApp = () => {};
  const words = {
    "en": {
      "title": "Your next cash decision",
      "simple": "Simple view",
      "detailed": "Detailed view",
      "language": "বাংলা",
      "through": "Scheduled cash through",
      "asof": "Simulation date",
      "low": "Lowest likely cash",
      "gap": "Cash needed to keep your reserve",
      "payroll": "Next payroll",
      "unknown": "No upcoming payroll identified",
      "room": "Can I afford an extra expense?",
      "amount": "One-off expense",
      "date": "Expense date",
      "test": "Check this expense",
      "after": "Lowest cash after this expense",
      "expected": "Spending room with expected receipts",
      "conservative": "Spending room without unpaid customer receipts",
      "private": "Download private decision brief",
      "dependency": "Which receipts matter most?",
      "removal": "If their unpaid receipts do not arrive, lowest cash falls by",
      "nonadditive": "Each customer is tested separately; do not add these impacts together.",
      "story": "Where do these numbers come from?",
      "checks": "Check your data first",
      "coach": "Choose what matters to you",
      "coachIntro": "Compare recovery priorities using saved ledger records. The extra-expense preview above is excluded. A preview changes nothing.",
      "cap": "Maximum discount (%)",
      "protected": "Keep these relationships untouched",
      "compare": "Compare three priorities",
      "cost": "Estimated economic cost",
      "risk": "Simulated reserve-breach risk",
      "asks": "People who must agree",
      "save": "Review as a new proposal",
      "noAction": "No action needed on this planned path",
      "infeasible": "No feasible recovery found",
      "needsReview": "Needs review",
      "limit": "Equal choices can occur. This planner searches a bounded set; it does not guarantee the best possible solution.",
      "approval": "Saving creates an unapproved proposal. Normal PIN checks, required human approvals and counterparty consent still apply.",
      "readonly": "Read-only preview",
      "scope": "These are daily closing ledger projections, not a bank balance or a guarantee. Unpaid receipts and unsettled agreements are assumptions. The expense is not saved. Fees or funding costs are not added automatically.",
      "source": "Open source record",
      "cashIn": "Money in",
      "cashOut": "Money out",
      "closing": "Closing cash",
      "flagged": "flagged records",
      "thin": "customers with fewer than three settled invoices",
      "unpaid": "unpaid invoices",
      "records": "Review records",
      "inbox": "Add missing records",
      "priorities": {
        "lowest_cost": "Keep costs down",
        "fewest_asks": "Ask fewer people",
        "lowest_risk": "Reduce simulated risk"
      },
      "statuses": {
        "payroll_unfunded": "Payroll needs attention",
        "buffer_shortfall": "Your cash buffer needs attention",
        "likely_path_holds": "The likely path holds your cash buffer",
        "no_payroll_identified": "Check your payroll records",
        "no_records": "Start with your business records",
        "historical_horizon": "Choose a later target to see future cash"
      },
      "afterGap": "Reserve shortfall after this expense",
      "actionLabels": {
        "supplier_deferral": "Ask for later payment",
        "early_payment_offer": "Offer an early-payment discount"
      }
    },
    "bn": {
      "title": "টাকা নিয়ে আপনার পরের সিদ্ধান্ত",
      "simple": "সহজ ভিউ",
      "detailed": "বিস্তারিত ভিউ",
      "language": "English",
      "through": "এই তারিখ পর্যন্ত নির্ধারিত হিসাব",
      "asof": "সিমুলেশনের তারিখ",
      "low": "সম্ভাব্য সর্বনিম্ন নগদ",
      "gap": "রিজার্ভ ধরে রাখতে ঘাটতি",
      "payroll": "পরের বেতন",
      "unknown": "সামনের বেতনের রেকর্ড পাওয়া যায়নি",
      "room": "আরেকটি খরচ করতে পারব?",
      "amount": "একবারের খরচ",
      "date": "খরচের তারিখ",
      "test": "খরচের প্রভাব দেখুন",
      "after": "এই খরচের পরে সর্বনিম্ন নগদ",
      "expected": "প্রত্যাশিত টাকা এলে বাড়তি খরচের সীমা",
      "conservative": "গ্রাহকের বকেয়া না এলে খরচের সীমা",
      "private": "ব্যক্তিগত সিদ্ধান্তের সারাংশ ডাউনলোড",
      "dependency": "কোন গ্রাহকের টাকা বেশি জরুরি?",
      "removal": "তাঁর বকেয়া না এলে সর্বনিম্ন নগদ কমে",
      "nonadditive": "প্রতিটি গ্রাহককে আলাদা করে পরীক্ষা করা হয়েছে; এই প্রভাবগুলো যোগ করবেন না।",
      "story": "হিসাবগুলো কোথা থেকে এসেছে?",
      "checks": "আগে তথ্য মিলিয়ে নিন",
      "coach": "আপনার অগ্রাধিকার বেছে নিন",
      "coachIntro": "সংরক্ষিত লেজার থেকে তিনটি অগ্রাধিকার তুলনা করুন। উপরের বাড়তি খরচের প্রিভিউ এখানে ধরা হয় না। প্রিভিউতে কিছু বদলাবে না।",
      "cap": "সর্বোচ্চ ছাড় (%)",
      "protected": "এই সম্পর্কগুলো অপরিবর্তিত রাখুন",
      "compare": "তিনটি অগ্রাধিকার তুলনা করুন",
      "cost": "আনুমানিক অর্থনৈতিক খরচ",
      "risk": "সিমুলেশনে রিজার্ভ ভাঙার ঝুঁকি",
      "asks": "যতজনের সম্মতি লাগবে",
      "save": "নতুন প্রস্তাব হিসেবে পর্যালোচনা",
      "noAction": "এই নির্ধারিত হিসাবে পদক্ষেপ দরকার নেই",
      "infeasible": "কার্যকর সমাধান পাওয়া যায়নি",
      "needsReview": "আরও যাচাই দরকার",
      "limit": "একই সমাধান একাধিকবার আসতে পারে। সীমিত বিকল্প পরীক্ষা করা হয়; এটিই সর্বোত্তম সমাধান—এমন নিশ্চয়তা নেই।",
      "approval": "সংরক্ষণ করলে অননুমোদিত প্রস্তাব তৈরি হবে। আগের নিয়মে PIN, প্রয়োজনীয় মানব অনুমোদন ও সংশ্লিষ্ট পক্ষের সম্মতি লাগবে।",
      "readonly": "শুধু প্রিভিউ",
      "scope": "এটি প্রতিদিনের শেষের লেজারভিত্তিক হিসাব, ব্যাংক ব্যালেন্স বা নিশ্চয়তা নয়। বকেয়া টাকা ও অসম্পন্ন চুক্তি অনুমান হিসেবে ধরা হয়েছে। খরচটি সংরক্ষিত হয় না। ফি বা ঋণের খরচ নিজে থেকে যোগ হয় না।",
      "source": "মূল রেকর্ড দেখুন",
      "cashIn": "টাকা আসবে",
      "cashOut": "টাকা যাবে",
      "closing": "দিন শেষে নগদ",
      "flagged": "সতর্কতা থাকা রেকর্ড",
      "thin": "গ্রাহকের তিনটির কম পরিশোধের ইতিহাস",
      "unpaid": "বকেয়া ইনভয়েস",
      "records": "রেকর্ড যাচাই",
      "inbox": "নতুন রেকর্ড যোগ",
      "priorities": {
        "lowest_cost": "খরচ কম রাখুন",
        "fewest_asks": "কম মানুষকে অনুরোধ করুন",
        "lowest_risk": "সিমুলেশনের ঝুঁকি কমান"
      },
      "statuses": {
        "payroll_unfunded": "বেতনের টাকা জোগাড়ে নজর দিন",
        "buffer_shortfall": "নগদের রিজার্ভে ঘাটতি আছে",
        "likely_path_holds": "সম্ভাব্য হিসাবে নগদের রিজার্ভ থাকছে",
        "no_payroll_identified": "বেতনের রেকর্ড যাচাই করুন",
        "no_records": "ব্যবসার রেকর্ড দিয়ে শুরু করুন",
        "historical_horizon": "সামনের হিসাব দেখতে পরের তারিখ বাছুন"
      },
      "afterGap": "এই খরচের পরে রিজার্ভের ঘাটতি",
      "actionLabels": {
        "supplier_deferral": "পরে পরিশোধের অনুরোধ",
        "early_payment_offer": "আগে টাকা পেতে ছাড়ের প্রস্তাব"
      }
    }
  };
  const w = () => words[language];
  const field = (name, fallback = "") => draft[name] ?? fallback;
  const amountText = n => money(n); // Existing illustrative display FX never changes native inputs or server calculations.
  const button = (action, text, extra = "") => `<button type="button" class="button small ${action === 'propose' ? 'primary' : 'ghost'}" data-action="owner-${action}" ${pending?'disabled':''} ${extra}>${esc(text)}</button>`;
  function sync() {
    const next = `${state.operator?.id}|${state.businessId}|${state.targetDate}|${state.dashboard?.snapshot_hash}|${state.dashboard?.plan?.plan_hash}`;
    if (next !== key) { key = next; epoch++; draft = {}; report = state.dashboard?.owner_view; coach = null; request = null; }
  }
  function minor(raw, maximum = 100000000000000n) {
    if (!/^\d+(?:\.\d{1,2})?$/.test(String(raw))) throw new Error(language === 'bn' ? 'দশমিকের পরে সর্বোচ্চ দুই ঘর দিয়ে শূন্য বা ধনাত্মক পরিমাণ লিখুন।' : 'Enter a nonnegative amount with at most two decimal places.');
    const [whole, fraction = ''] = String(raw).split('.');
    const value = BigInt(whole)*100n + BigInt(fraction.padEnd(2, '0'));
    if (value > maximum) throw new Error('Amount exceeds the allowed limit.');
    return Number(value);
  }
  function expense() {
    const amount = selectedMinor(draft.amount,0), date = field('date', report.expense.date);
    // Historical views can still export their original zero-expense report.
    if (report.likely.available && (!date || date < report.as_of || date > report.end_date)) throw new Error('Choose an expense date within the displayed planning horizon.');
    return {expense_minor:amount, ...(report.likely.available?{expense_date:date}:{})};
  }
  const common = () => ({business_id:state.businessId,target_date:state.targetDate,expected_snapshot:state.dashboard.snapshot_hash});
  function render() {
    sync();
    const r = report, t = w();
    if (!r) return '';
    const checks = r.data_checks, available = r.likely.available, canSave = canApprove() && !state.dashboard.policy.agent_paused && state.dashboard.policy.autonomy_level !== 'advise';
    const names = [...new Set([...state.dashboard.records.invoices.map(x=>x.customer), ...state.dashboard.records.bills.map(x=>x.payee)])].sort();
    const cap = Math.min(state.dashboard.policy.max_discount_bps, state.dashboard.plan?.owner_constraints?.max_discount_bps ?? state.dashboard.policy.max_discount_bps);
    const bound = x => x.available ? amountText(x.ceiling_minor) : '—';
    const source = x => button('source', `${x.party} · ${x.id}`, `data-kind="${esc(x.kind)}" data-id="${esc(x.id)}" title="${esc(t.source)}"`);
    return `<div class="owner-view" lang="${language}"><fieldset class="owner-controls" aria-label="Owner decisions" ${pending?'disabled':''}><div class="owner-toolbar"><span class="pill">${esc(t.simple)}</span><div class="row">${button('language',t.language,'aria-label="Switch Owner view language"')}${button('detailed',t.detailed)}</div></div>
      ${onboardingHtml(state.dashboard)}
      <section class="card owner-head"><span class="eyebrow">${esc(t.title)}</span><h2>${esc(t.statuses[r.status])}</h2><p>${esc(t.asof)} ${esc(day(r.as_of,true))} · ${esc(t.through)} ${esc(day(r.end_date,true))}</p><div class="row section-gap">${button('brief',t.private)}<span class="pill">${esc(t.readonly)}</span></div></section>
      ${(state.dashboard.warnings||[]).filter(x=>x.severity==='critical').slice(0,2).map(x=>`<div class="alert critical section-gap"><div><strong>${esc(x.title)}</strong><p>${esc(moneyProse(x.detail))}</p><button class="button small ghost" data-view="${['reserve_breach','payroll_at_risk'].includes(x.code)?'rescue':'security'}">${['reserve_breach','payroll_at_risk'].includes(x.code)?(language==='bn'?'সমাধানের প্রস্তাব দেখুন':'Review recovery'):(language==='bn'?'নিরাপত্তা যাচাই করুন':'Review security')}</button></div></div>`).join('')}
      <section class="metrics section-gap">${metric(t.low,amountText(r.likely.minimum_cash_minor),r.likely.minimum_cash_date?day(r.likely.minimum_cash_date):'—',r.likely.reserve_shortfall_minor?'bad':'good')}${metric(t.gap,amountText(r.likely.reserve_shortfall_minor),`${language==='bn'?'রিজার্ভ':'Reserve'} ${amountText(r.reserve_floor_minor)}`,r.likely.reserve_shortfall_minor?'bad':'good')}${metric(t.payroll,r.payroll.identified?amountText(r.payroll.next_amount_minor):'—',r.payroll.identified?day(r.payroll.next_date,true):t.unknown)}</section>
      <section class="card section-gap"><h3>${esc(t.room)}</h3><div class="owner-fields section-gap"><label class="field">${esc(t.amount)} (${esc(displayCurrency())})${moneyInput(draft.amount,r.expense.amount_minor,`data-owner-field="amount" ${!available?'disabled':''}`)}</label><label class="field">${esc(t.date)}<input data-owner-field="date" type="date" min="${esc(r.as_of)}" max="${esc(r.end_date)}" value="${esc(field('date',r.expense.date))}" ${!available?'disabled':''}></label>${available?button('expense',t.test):''}</div>
      <div class="owner-results"><div><span>${esc(t.expected)}</span><strong>${bound(r.spending_room.likely)}</strong></div><div><span>${esc(t.conservative)}</span><strong>${bound(r.spending_room.without_unpaid_customers)}</strong></div><div><span>${esc(t.after)}<small>${amountText(r.expense.amount_minor)} · ${esc(day(r.expense.date))}</small></span><strong>${amountText(r.after_expense.minimum_cash_minor)}</strong><small>${esc(t.afterGap)}: ${amountText(r.after_expense.reserve_shortfall_minor)}</small></div></div><p class="hint">${esc(t.scope)}</p></section>
      <section class="grid cols-2 section-gap"><div class="card"><h3>${esc(t.dependency)}</h3>${r.dependencies.length?r.dependencies.slice(0,3).map(x=>`<div class="owner-dependency"><strong>${esc(x.customer)}</strong><p>${esc(t.removal)} <b>${amountText(x.impact_on_lowest_cash_minor)}</b></p></div>`).join(''):`<p>${language==='bn'?'এই হিসাবে বকেয়া গ্রাহকের ওপর নির্ভরতা নেই।':'No unpaid-customer dependency identified.'}</p>`}<p class="hint">${esc(t.nonadditive)} ${r.dependency_coverage.complete?'':`${r.dependency_coverage.tested}/${r.dependency_coverage.customers_total} customers tested, in name order.`}</p></div>
      <div class="card"><h3>${esc(t.checks)}</h3><ul class="owner-checks"><li>${checks.quarantined_records} ${esc(t.flagged)}</li><li>${checks.customers_under_three_settlements.length} ${esc(t.thin)}</li><li>${checks.unpaid_invoices} ${esc(t.unpaid)}</li><li>${esc(r.payroll.identified?(language==='bn'?'বেতনের রেকর্ড আছে':'Upcoming payroll recorded'):t.unknown)}</li></ul><div class="row"><button class="button small ghost" data-view="records">${esc(t.records)}</button><button class="button small ghost" data-view="inbox">${esc(t.inbox)}</button></div></div></section>
      <section class="card section-gap"><details><summary>${esc(t.story)}</summary><div class="owner-timeline">${r.calendar.map(d=>`<article><h4>${esc(day(d.date,true))}</h4><p>${esc(t.cashIn)} ${amountText(d.inflow_minor)} · ${esc(t.cashOut)} ${amountText(d.outflow_minor)} · <strong>${esc(t.closing)} ${amountText(d.closing_cash_minor)}</strong></p><div class="row">${d.sources.map(source).join('')}</div>${d.sources_complete?'':`<p class="hint">${d.sources.length}/${d.source_count} source records displayed.</p>`}</article>`).join('') || `<p>${language==='bn'?'এই সময়ের জন্য কোনো নির্ধারিত রেকর্ড নেই।':'No scheduled records in this window.'}</p>`}</div></details></section>
      <section class="card section-gap"><h3>${esc(t.coach)}</h3><p>${esc(t.coachIntro)}</p><div class="owner-fields section-gap"><label class="field">${esc(t.cap)}<input data-owner-field="cap" inputmode="decimal" value="${esc(field('cap',cap/100))}"></label>${button('coach',t.compare)}</div><details class="section-gap"><summary>${esc(t.protected)}</summary><div class="owner-protected">${names.map(name=>`<label class="check"><input type="checkbox" data-owner-protect="${esc(name)}" ${(draft.protected||[]).includes(name)||state.dashboard.plan?.excluded_counterparties?.includes(name)?'checked':''} ${state.dashboard.plan?.excluded_counterparties?.includes(name)?'disabled':''}>${esc(name)}</label>`).join('')}</div></details>
      ${pending?`<p role="status">${language==='bn'?'হিসাব হচ্ছে…':'Calculating…'}</p>`:''}${coach?`<div class="owner-options section-gap">${coach.options.map(o=>`<article class="owner-option"><h4>${esc(t.priorities[o.priority])}</h4>${o.status==='proposal_available'?`<dl><dt>${esc(t.cost)}</dt><dd>${amountText(o.cost_minor)}</dd><dt>${esc(t.risk)}</dt><dd>${(o.risk*100).toFixed(2)}% ${o.risk_target_met?'':`<span class="pill storm">${language==='bn'?'১০% লক্ষ্যের ওপরে':'Above 10% target'}</span>`}</dd><dt>${esc(t.asks)}</dt><dd>${o.asks}</dd></dl><ul>${o.actions.map(a=>`<li><strong>${esc(t.actionLabels[a.type]||a.type)}</strong>: ${esc(a.counterparty)} · ${amountText(a.amount_minor)} · ${esc(day(a.to_date))}</li>`).join('')}</ul>${canSave?button('propose',t.save,`data-priority="${esc(o.priority)}"`):''}`:`<p>${esc(t[o.status==='no_action_needed'?'noAction':o.status==='infeasible'?'infeasible':'needsReview'])}</p>${o.reason?`<p class="hint">${esc(o.reason)}</p>`:''}`}</article>`).join('')}</div><p class="hint">${esc(t.limit)}</p>`:''}<p class="hint">${esc(t.approval)}</p></section></fieldset></div>`;
  }
  async function action(name, data) {
    sync();
    if (name === 'detailed') {state.ownerDetailed=true;renderApp();return;}
    if (name === 'simple') {state.ownerDetailed=false;renderApp();return;}
    if (pending || state.busy) return;
    if (name === 'language') {language=language==='en'?'bn':'en';renderApp();return;}
    if (name === 'source') {state.recordFilter=data.kind;state.recordQuery=data.id;state.view='records';renderApp();return;}
    const origin = key, serial = epoch;
    let path = name, body = common();
    if (name==='expense') {body={...body,...expense()};path='analyze';}
    else if (name==='brief') {body={...body,display_currency:displayCurrency(),expense_minor:report.expense.amount_minor,...(report.likely.available?{expense_date:report.expense.date}:{})};}
    else if (name==='coach') {body={...body,max_discount_bps:minor(field('cap',Math.min(state.dashboard.policy.max_discount_bps,state.dashboard.plan?.owner_constraints?.max_discount_bps??state.dashboard.policy.max_discount_bps)/100),10000n),protected_counterparties:draft.protected||[]};}
    else if (name==='propose') {
      const option = coach?.options.find(x=>x.priority===data.priority);
      if (!option || option.status!=='proposal_available') throw new Error('Compare priorities again before saving.');
      const fingerprint = `${origin}|${option.option_id}`;
      if (!request || request.fingerprint!==fingerprint) request={fingerprint,id:crypto.randomUUID()};
      body={...body,max_discount_bps:coach.criteria.max_discount_bps,protected_counterparties:coach.criteria.protected_counterparties,priority:option.priority,option_id:option.option_id,request_id:request.id};
    } else return;
    pending=true;renderApp();
    await act('Owner view',async()=>{
      try {
        const answer = await api(`/api/owner/${path}`,body);
        if (key!==origin || epoch!==serial) return;
        if (name==='expense') report=answer;
        else if (name==='coach') coach=answer;
        else if (name==='propose') {await loadDashboard();state.view='rescue';toast(language==='bn'?'নতুন অননুমোদিত প্রস্তাব তৈরি হয়েছে।':'Fresh unapproved proposal created. Review it normally.');}
        else if (name==='brief') {
          const url=URL.createObjectURL(new Blob([answer.html],{type:'text/html;charset=utf-8'}));
          const link=document.createElement('a');link.href=url;link.download=`tideway-${state.businessId}-private-decision.html`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
          toast(language==='bn'?'ব্যক্তিগত সারাংশ ডাউনলোড হয়েছে।':'Private brief downloaded. Open it locally or print to PDF.');
        }
      } finally {pending=false;renderApp();}
    });
  }
  document.addEventListener('input',event=>{
    const el=event.target;
    if (el?.dataset?.ownerField) {draft[el.dataset.ownerField]=el.hasAttribute('data-money-currency')?moneyDraft(el,true):el.value;if(el.dataset.ownerField==='cap'){coach=null;request=null;document.querySelector('.owner-options')?.remove();}}
  });
  document.addEventListener('change',event=>{
    if (event.target?.hasAttribute('data-owner-protect')) {draft.protected=[...document.querySelectorAll('[data-owner-protect]:checked')].map(x=>x.dataset.ownerProtect);coach=null;request=null;renderApp();}
  });
  return {render,action,validateCurrency(){sync();if(draft.amount?.error)throw new Error('Fix the invalid Owner expense before changing currency.');},bind(renderer){renderApp=renderer;},reset(){key='';epoch++;draft={};report=null;coach=null;request=null;pending=false;language='en';}};
})();
