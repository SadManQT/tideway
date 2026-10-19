"use strict";

// Explain server evidence and exact proposal terms; no new forecast or authority.
window.TidewayReview = (() => {
  const words = {
    en: {title:"Will customer payments arrive before payroll?", intro:"Compare the expected receipt date with payroll, then check actual payment history.",
      history:"settled invoices were paid late", none:"No settled payment history yet.", thin:"Limited history: the date estimate also uses wider business history.",
      expected:"Next expected receipt", payroll:"Next payroll", missing:"Receipt date needs review", after:"Expected after payroll", same:"Same day: check payment timing", before:"Expected before payroll",
      noPayroll:"No upcoming payroll identified in this horizon.", open:"Unpaid invoice total", byPayroll:"Expected by payroll", historyLink:"Check payment history", invoice:"Open invoice",
      scope:"Expected receipts are assumptions, not collected cash. An agreed early payment is still unpaid until recorded. Daily closing cash does not prove funds arrive before payroll within the day.",
      more:"Other customers", empty:"No unpaid customer invoices recorded.", recovery:"Review recovery options"},
    bn: {title:"গ্রাহকের টাকা কি বেতনের আগে আসবে?", intro:"সম্ভাব্য টাকা আসার তারিখ বেতনের তারিখের সঙ্গে মিলিয়ে দেখুন, তারপর পরিশোধের আসল ইতিহাস যাচাই করুন।",
      history:"টি পরিশোধিত ইনভয়েস দেরিতে দেওয়া হয়েছিল", none:"এখনও পরিশোধের ইতিহাস নেই।", thin:"ইতিহাস কম: তারিখের অনুমানে ব্যবসার অন্য গ্রাহকের ইতিহাসও ব্যবহৃত হয়।",
      expected:"পরের সম্ভাব্য টাকা আসবে", payroll:"পরের বেতন", missing:"টাকা আসার তারিখ যাচাই করুন", after:"বেতনের পরে আসার সম্ভাবনা", same:"একই দিন: সময় মিলিয়ে নিন", before:"বেতনের আগে আসার সম্ভাবনা",
      noPayroll:"এই সময়ের মধ্যে সামনের বেতনের রেকর্ড পাওয়া যায়নি।", open:"মোট বকেয়া ইনভয়েস", byPayroll:"বেতনের মধ্যে প্রত্যাশিত", historyLink:"পরিশোধের ইতিহাস দেখুন", invoice:"ইনভয়েস দেখুন",
      scope:"প্রত্যাশিত টাকা এখনও হাতে আসেনি। আগে পরিশোধের চুক্তি হলেও রেকর্ড না হওয়া পর্যন্ত টাকা বকেয়া। দিনের শেষের হিসাব দিয়ে একই দিনে বেতনের আগে টাকা আসা নিশ্চিত হয় না।",
      more:"অন্য গ্রাহক", empty:"কোনো বকেয়া গ্রাহক ইনভয়েস নেই।", recovery:"সমাধানের প্রস্তাব দেখুন"}
  };
  function customers(report, language = "en") {
    if (!report?.customer_receipts) return "";
    const t = words[language] || words.en;
    const row = item => {
      const next = item.next_receipt, payroll = report.payroll.next_date;
      const timing = !next ? t.missing : !payroll ? t.noPayroll : next.date > payroll ? t.after : next.date === payroll ? t.same : t.before;
      const history = item.settled_invoices ? `${item.late_settlements} / ${item.settled_invoices} ${t.history}` : t.none;
      return `<article class="receipt-review" data-customer-review="${esc(item.customer)}"><div class="row between"><h4>${esc(item.customer)}</h4><span class="pill ${!next || next.after_payroll || next.date === payroll ? 'unsettled' : ''}">${esc(timing)}</span></div>
        <p class="review-history">${esc(history)}</p>${item.limited_history ? `<p class="hint">${esc(t.thin)}</p>` : ''}
        <dl class="review-facts"><div><dt>${esc(t.expected)}</dt><dd>${next ? `${esc(day(next.date, true))} · ${money(next.amount_minor)}` : '—'}</dd></div><div><dt>${esc(t.payroll)}</dt><dd>${payroll ? esc(day(payroll, true)) : '—'}</dd></div><div><dt>${esc(t.open)}</dt><dd>${money(item.open_amount_minor)}</dd></div>${payroll ? `<div><dt>${esc(t.byPayroll)}</dt><dd>${money(item.expected_by_payroll_minor)}</dd></div>` : ''}</dl>
        <div class="row"><button type="button" class="button small ghost" data-action="owner-history" data-customer="${esc(item.customer)}">${esc(t.historyLink)}</button>${next ? `<button type="button" class="button small ghost" data-action="owner-source" data-kind="invoice" data-id="${esc(next.id)}">${esc(t.invoice)}</button>` : ''}</div></article>`;
    };
    const rows = report.customer_receipts;
    return `<section class="card section-gap customer-review"><h3>${esc(t.title)}</h3><p>${esc(t.intro)}</p>${rows.slice(0,3).map(row).join('') || `<p>${esc(t.empty)}</p>`}${rows.length>3 ? `<details><summary>${esc(t.more)} (${rows.length-3})</summary>${rows.slice(3).map(row).join('')}</details>` : ''}<p class="hint">${esc(t.scope)}</p><button type="button" class="button small ghost" data-view="rescue">${esc(t.recovery)}</button></section>`;
  }
  function percent(value, target) {
    let text = (value * 100).toLocaleString("en-US", {maximumSignificantDigits:10});
    if (isNum(target) && value > target && Number(text.replaceAll(',', '')) <= target * 100) text = String(value * 100);
    return text;
  }
  function bundle(plan, option) {
    const after = option.after || {}, hasRisk = isNum(option.probability_breach_after), hasTarget = isNum(plan.risk_target);
    const risk = option.probability_breach_after, target = plan.risk_target;
    const amount = value => isNum(value) ? money(value) : 'Not available';
    const above = hasRisk && hasTarget && risk > target;
    const status = option.feasible === false ? 'Cash shortfall remains; this option cannot be approved' : !hasRisk || !hasTarget ? 'Risk estimate needs review' : above ? 'Risk target exceeded' : 'Within the simulated risk target';
    return `<section class="review-summary" aria-label="Cost, cash and remaining risk"><h4>${option.feasible === false ? 'This option is not ready for approval' : 'Understand this option before approving'}</h4>
      <dl class="review-facts"><div><dt>Estimated economic cost</dt><dd data-review-value="cost">${amount(option.economic_cost_minor)}</dd></div><div><dt>Lowest likely cash after</dt><dd data-review-value="cash">${amount(after.minimum_cash_minor)}</dd></div><div><dt>Minimum reserve</dt><dd data-review-value="reserve">${amount(after.reserve_floor_minor)}</dd></div><div><dt>Remaining simulated risk</dt><dd data-review-value="risk">${hasRisk ? `${esc(percent(risk,target))}%` : 'Not available'}${hasTarget ? ` · target ${esc(percent(target))}%` : ''}</dd></div></dl>
      <p class="review-risk ${above ? 'negative' : ''}"><strong>${esc(status)}.</strong> ${above ? 'Each approver must explicitly accept this remaining risk.' : 'The forecast can still be wrong.'} Risk is the share of simulated cash paths falling below reserve; it is not a real-world guarantee.</p>
      <details><summary>What does this cost mean?</summary><p>Economic cost includes early-payment discounts and the implied cost of paying suppliers later. Exposure is the amount affected by the actions, not an extra fee. A supplier deferral moves a payment; it does not create cash.</p></details>
      <p class="hint">Approval does not collect cash or finish the rescue. Required people approve, counterparties agree, then the sandbox executes the agreed terms.</p></section>`;
  }
  return {customers,bundle};
})();
