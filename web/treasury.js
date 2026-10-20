"use strict";

// Treasury hub UI. Read-only views for lenders and finance teams; the server
// computes, scopes, signs and verifies everything. Every server string is escaped.
window.TidewayTreasury = (() => {
  let key = "", epoch = 0, tab = "twcf", scenario = "likely", synthetic = false, pending = false;
  let results = {}, requested = new Set(), passport = null, verification = null, drill = null, fileCheck = null, failure = "";
  const tabs = {twcf: "13-week cash flow", health: "Working-capital health", scan: "Payment integrity", passport: "Credit passport"};
  const scenarioNames = {scheduled: "Scheduled", likely: "Likely (TidePay)", stress: "Stress (TidePay p80)"};
  const severityPill = {high: "storm", medium: "unsettled", low: "info"};
  const ruleNames = {duplicate_bill: "Possible duplicate", split_below_threshold: "Split below threshold", amount_outlier: "Amount outlier",
    bank_details_changed: "Bank details changed", lookalike_payee: "Look-alike payee", round_amount: "Round amount"};

  function sync() {
    const next = `${state.operator?.id}|${state.businessId}|${state.dashboard?.snapshot_hash}`;
    if (next !== key) { key = next; epoch++; results = {}; requested = new Set(); passport = null; verification = null; drill = null; fileCheck = null; failure = ""; }
  }
  const units = (minor) => {
    if (!isNum(minor)) return "—";
    if (minor === 0) return "–";
    const text = Math.abs(minor / 100).toLocaleString("en-US", {maximumFractionDigits: 0});
    return minor < 0 ? `−${text}` : text;
  };
  const percent = (value, digits = 1) => isNum(Number(value)) && value !== null && value !== "" ? `${(Number(value) * 100).toFixed(digits)}%` : "—";
  const short = (value) => esc(String(value || "").slice(0, 12)) + (String(value || "").length > 12 ? "…" : "");
  const button = (action, label, cls = "primary", extra = "") => `<button type="button" class="button ${cls}" data-action="treasury-${action}" ${pending ? "disabled" : ""} ${extra}>${label}</button>`;
  const json = (title, value) => `<details class="section-gap"><summary>${esc(title)}</summary><pre class="lab-json">${esc(JSON.stringify(value, null, 2))}</pre></details>`;
  const bar = (score) => `<svg class="tw-bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true"><rect class="tw-bar-track" width="100" height="8" rx="4"></rect><rect class="tw-bar-fill ${score >= 75 ? "good" : score >= 50 ? "watch" : "weak"}" width="${Math.max(0, Math.min(100, Number(score) || 0))}" height="8" rx="4"></rect></svg>`;

  function gauge(score, band) {
    const radius = 52, circumference = 2 * Math.PI * radius, value = Math.max(0, Math.min(100, Number(score) || 0));
    const cls = value >= 75 ? "good" : value >= 50 ? "watch" : "weak";
    return `<svg class="tw-gauge" viewBox="0 0 128 128" role="img" aria-label="Working-capital health ${esc(score)} of 100, ${esc(band)}">
      <circle class="tw-gauge-track" cx="64" cy="64" r="${radius}"></circle>
      <circle class="tw-gauge-fill ${cls}" cx="64" cy="64" r="${radius}" stroke-dasharray="${(circumference * value / 100).toFixed(2)} ${circumference.toFixed(2)}" transform="rotate(-90 64 64)"></circle>
      <text class="tw-gauge-score" x="64" y="66" text-anchor="middle">${esc(score ?? "—")}</text>
      <text class="tw-gauge-label" x="64" y="86" text-anchor="middle">${esc(band)} · of 100</text></svg>`;
  }

  // ---------------------------------------------------------------- 13-week cash flow
  function renderTwcf() {
    const r = results.twcf;
    if (!r) return loadingHtml("Building the 13-week cash flow from the projection engine…");
    const s = r.scenarios[scenario], t = s.totals, weeks = s.weeks;
    const customers = t.receipts_by_customer.map((item) => item.customer);
    const sumOf = (field) => weeks.reduce((total, week) => total + week[field], 0);
    const customerWeek = (week, name) => week.receipts_by_customer.find((item) => item.customer === name)?.amount_minor || 0;
    const lines = [
      ["Opening cash", (w) => w.opening_cash_minor, t.opening_cash_minor, "tw-strong"],
      ...customers.map((name) => [`Receipts: ${name}`, (w) => customerWeek(w, name), t.receipts_by_customer.find((item) => item.customer === name).amount_minor, "tw-indent"]),
      ["Other receipts", (w) => w.other_receipts_minor, sumOf("other_receipts_minor"), "tw-indent"],
      ["Total receipts", (w) => w.receipts_minor, t.receipts_minor, "tw-sub"],
      ["Supplier bills", (w) => -w.supplier_bills_minor, -t.supplier_bills_minor, "tw-indent"],
      ["Payroll", (w) => -w.payroll_minor, -t.payroll_minor, "tw-indent"],
      ["Other disbursements", (w) => -w.other_disbursements_minor, -t.other_disbursements_minor, "tw-indent"],
      ["Total disbursements", (w) => -w.disbursements_minor, -t.disbursements_minor, "tw-sub"],
      ["Net cash flow", (w) => w.net_flow_minor, t.net_flow_minor, "tw-strong"],
      ["Closing cash", (w) => w.closing_cash_minor, t.closing_cash_minor, "tw-strong"],
      ["Lowest cash in week", (w) => w.lowest_cash_minor, t.lowest_cash_minor, ""],
      ["Reserve floor", (w) => w.reserve_floor_minor, r.reserve_floor_minor, "tw-muted"],
    ];
    const head = `<tr><th>${esc(r.currency)} (whole units)</th>${weeks.map((w) => `<th class="num ${w.below_reserve ? "tw-below" : ""}" title="${esc(w.start_date)} to ${esc(w.end_date)}">W${w.week}<span class="tw-date">${esc(day(w.start_date))}</span></th>`).join("")}<th class="num">13 weeks</th></tr>`;
    const body = lines.map(([label, pick, total, cls]) => `<tr class="${cls}"><td>${esc(label)}</td>${weeks.map((w) => { const v = pick(w); return `<td class="num ${w.below_reserve ? "tw-below" : ""} ${v < 0 ? "negative" : ""}">${units(v)}</td>`; }).join("")}<td class="num ${total < 0 ? "negative" : ""}">${units(total)}</td></tr>`).join("");
    const series = (name) => r.scenarios[name].daily.map((item) => ({date: item.date, value: item.closing_cash_minor}));
    const low = s.daily.find((item) => item.date === t.lowest_cash_date);
    const chart = chartSvg({lines: [{cls: "line-base", label: "Scheduled", points: series("scheduled")}, {cls: "line-likely", label: "Likely (TidePay)", points: series("likely")},
      {cls: "line-what", label: "Stress (TidePay p80)", points: series("stress")}], reserve: r.reserve_floor_minor,
      markers: low ? [{date: low.date, value: low.closing_cash_minor, cls: "marker-breach", label: `Lowest ${scenarioNames[scenario]} cash ${money(low.closing_cash_minor)}`, text: "lowest", textCls: "label-reserve"}] : [], height: 230});
    const rec = s.reconciliation;
    const below = t.weeks_below_reserve;
    return `<div class="row between"><div><h3>13-week cash flow</h3><p class="small muted">${esc(s.label)}</p></div>
        <div class="row"><div class="lab-tabs tw-scenarios" role="group" aria-label="Scenario">${Object.entries(scenarioNames).map(([id, label]) => `<button type="button" class="button small ${id === scenario ? "teal" : "ghost"}" data-action="treasury-scenario" data-scenario="${id}" aria-pressed="${id === scenario}">${esc(label)}</button>`).join("")}</div>
        <a class="button small ghost" href="/api/export?kind=twcf&business_id=${encodeURIComponent(state.businessId)}">${icon("download")}TWCF CSV</a></div></div>
      <div class="metrics section-gap">
        ${metric("Opening cash", money(t.opening_cash_minor), `As of ${day(r.start_date, true)}`)}
        ${metric("Week-13 closing", money(t.closing_cash_minor), `Net ${money(t.net_flow_minor)} over 13 weeks`, t.closing_cash_minor < r.reserve_floor_minor ? "bad" : "")}
        ${metric("Lowest cash", money(t.lowest_cash_minor), `${day(t.lowest_cash_date, true)} · week ${t.lowest_week}`, t.lowest_cash_minor < r.reserve_floor_minor ? "bad" : "")}
        ${metric("Weeks below reserve", `${below.length} of 13`, below.length ? `First: week ${t.first_week_below_reserve} · reserve ${money(r.reserve_floor_minor)}` : `Reserve ${money(r.reserve_floor_minor)} holds`, below.length ? "bad" : "good")}
      </div>
      <div class="section-gap">${chart}<div class="legend"><span><i class="base"></i>Scheduled</span><span><i></i>Likely (TidePay)</span><span><i class="what"></i>Stress (p80)</span><span><i class="reserve"></i>Reserve floor</span></div></div>
      <div class="table-wrap section-gap tw-table"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>
      <div class="row section-gap"><span class="pill ${rec.matches ? "ok" : "storm"}">${icon(rec.matches ? "check" : "x")}${rec.matches ? "Reconciles exactly with the projection engine" : "Does not reconcile"}</span>
        <span class="small muted">Week-13 closing ${money(rec.twcf_closing_cash_minor)} = engine ${money(rec.engine_closing_cash_minor)} · daily minimum ${money(rec.twcf_minimum_cash_minor)} = engine ${money(rec.engine_minimum_cash_minor)}</span></div>
      <p class="small muted section-gap">Highlighted weeks have a day below the reserve floor. Table amounts are in the ${esc(r.currency)} ledger (whole units; the CSV has exact minor units). Beyond week 13: receipts ${money(t.beyond_horizon_receipts_minor)}, disbursements ${money(t.beyond_horizon_disbursements_minor)}. ${esc(r.method)}</p>`;
  }

  // ---------------------------------------------------------------- health
  function renderHealth() {
    const r = results.health;
    if (!r) return loadingHtml("Scoring working-capital health and running 1,000 simulated futures…");
    const rows = r.components.map((c) => `<tr><td><strong>${esc(c.label)}</strong><div class="small muted tw-formula">${esc(c.formula)}</div></td>
      <td>${esc(c.display)}</td><td class="tw-score-cell">${c.available ? `${bar(c.score)}<span class="tw-score-num">${esc(c.score)}</span>` : `<span class="pill">Unavailable</span>`}</td>
      <td class="num">${esc(c.weight)}</td><td class="num">${esc(c.points)}</td></tr>`).join("");
    const tips = r.suggestions.length ? r.suggestions.map((s, index) => `<li class="tw-tip"><span class="tw-tip-no">${index + 1}</span><div><strong>${esc(s.label)} <span class="pill ok">up to +${esc(s.max_gain_points)} pts</span></strong><p class="small">${esc(s.text)}</p></div></li>`).join("")
      : `<li class="small muted">Every component already scores full marks.</li>`;
    return `<div class="tw-health-head"><div>${gauge(r.score, r.band)}</div>
        <div><h3>Working-capital health</h3><p>A transparent 0–100 composite from this business's own records: collection speed, overdue share, customer concentration, runway, reserve coverage and simulated breach risk.</p>
        <p class="small muted">Bands: ${r.bands.map((b) => `${esc(b.label)} ≥ ${esc(b.from)}`).join(" · ")}. Weights and anchors are Tideway design parameters, not industry benchmarks. Not a credit rating.</p></div></div>
      <h3 class="section-gap">What would move the score most</h3><ol class="tw-tips">${tips}</ol>
      <div class="table-wrap section-gap"><table><thead><tr><th>Component and formula</th><th>Measured</th><th>Score</th><th class="num">Weight</th><th class="num">Points</th></tr></thead><tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3"><strong>Composite score</strong> (weighted mean of available components; weight used ${esc(r.weight_total_used)}/100)</td><td class="num">100</td><td class="num"><strong>${esc(r.score)}</strong></td></tr></tfoot></table></div>
      <div class="kv section-gap">${r.context_metrics.map((m) => `<div><span>${esc(m.label)} · not scored</span><strong>${esc(m.display)}</strong><span>${esc(m.note)}</span></div>`).join("")}
        <div><span>Simulation</span><strong>${esc(r.simulation.runs)} futures · seed ${esc(r.simulation.seed)}</strong><span>Payroll-unfunded risk ${percent(r.simulation.probability_payroll_unfunded)}</span></div></div>
      <p class="small muted section-gap">${esc(r.method)}</p>${json("Component inputs (ledger minor units)", r.components.map((c) => ({id: c.id, inputs: c.inputs})))}`;
  }

  // ---------------------------------------------------------------- payment integrity
  function evidenceValue(name, value) {
    if (Array.isArray(value)) return value.map((item) => evidenceValue(name, item)).join(", ");
    if (name.endsWith("_minor") && isNum(value)) return money(value);
    return String(value);
  }
  function findingHtml(f) {
    const ev = Object.entries(f.evidence || {}).map(([name, value]) => `<div><span>${esc(name.replaceAll("_", " "))}</span><strong>${esc(evidenceValue(name, value))}</strong></div>`).join("");
    return `<article class="action-card tw-finding"><div class="row between"><strong>${esc(f.title)}</strong>
      <span class="row"><span class="pill ${severityPill[f.severity] || ""}">${esc(f.severity)}</span><span class="pill">${esc(ruleNames[f.rule] || f.rule)}</span>${f.source === "synthetic" ? '<span class="pill violet">synthetic sample</span>' : ""}</span></div>
      <p class="small">${esc(f.explanation)}</p><div class="kv section-gap">${ev}<div><span>bills</span><strong>${esc(f.bill_ids.join(", "))}</strong></div><div><span>amount involved</span><strong>${esc(money(f.amount_minor))}</strong></div></div>
      <p class="tiny muted">Finding ${esc(f.finding_id)} · advisory only, blocks nothing</p></article>`;
  }
  function renderScan() {
    const r = results.scan;
    const toggle = `<label class="check tw-toggle"><input type="checkbox" data-treasury-synthetic ${synthetic ? "checked" : ""} ${pending ? "disabled" : ""}> Also run on a synthetic test sample (in-memory only, never saved)</label>`;
    if (!r) return `<h3>Payment-integrity scan</h3>${toggle}${loadingHtml("Scanning supplier bills…")}`;
    const ledger = r.ledger_findings, sample = r.synthetic_sample;
    const counts = ["high", "medium", "low"].map((level) => `<span class="pill ${severityPill[level]}">${ledger.filter((f) => f.severity === level).length} ${level}</span>`).join("");
    let syn = "";
    if (sample) {
      syn = `<section class="tw-synthetic section-gap"><div class="row between"><h3>${esc(sample.label)}</h3><span class="pill violet">${esc(sample.bills)} synthetic bills</span></div>
        <div class="metrics section-gap">${metric("Precision", percent(sample.precision), `${sample.true_positives} true / ${sample.false_positives} false positives`)}${metric("Recall", percent(sample.recall), `${sample.planted_anomalies - sample.false_negatives} of ${sample.planted_anomalies} planted anomalies found`)}
        ${metric("Clean controls flagged", String(sample.clean_bills_flagged.length), `of ${sample.clean_bills} clean bills`)}${metric("Findings", String(sample.findings.length), "on the synthetic sample")}</div>
        <div class="table-wrap section-gap"><table><thead><tr><th>Planted anomaly</th><th>Bills</th><th>Detected</th><th>Finding</th></tr></thead><tbody>${sample.labels.map((l) => `<tr><td>${esc(ruleNames[l.rule] || l.rule)}</td><td>${esc(l.bill_ids.join(", "))}</td><td>${l.detected ? `<span class="pill ok">${icon("check")}found</span>` : `<span class="pill storm">${icon("x")}missed</span>`}</td><td>${esc(l.finding_id || "—")}</td></tr>`).join("")}</tbody></table></div>
        <p class="small muted">${esc(sample.caveat)}</p>
        <details class="section-gap" open><summary>Synthetic findings (${sample.findings.length})</summary>${sample.findings.map(findingHtml).join("")}</details>
        ${json("Synthetic sample bills", sample.sample_bills)}</section>`;
    }
    return `<div class="row between"><div><h3>Payment-integrity scan</h3><p class="small muted">${esc(r.authority)}</p></div><div class="row">${button("scan", `${icon("refresh")}Re-scan`, "ghost small")}</div></div>
      ${toggle}
      <div class="row section-gap"><span class="pill info">${esc(r.bills_scanned)} ledger bills scanned</span>${counts}<span class="pill">Two-person threshold ${esc(money(r.threshold_minor))}</span></div>
      <h3 class="section-gap">Ledger findings</h3>
      ${ledger.length ? ledger.map(findingHtml).join("") : `<div class="alert info section-gap">${icon("check")}<div><strong>No rule fired on this ledger.</strong><p class="small">Demo ledgers contain few anomalies. Tick the synthetic test sample to see every rule fire with evidence.</p></div></div>`}
      ${syn}
      <details class="section-gap"><summary>Rules (deterministic: same records, same findings)</summary><ul class="small">${r.rules.map((rule) => `<li><strong>${esc(ruleNames[rule.rule] || rule.rule)}</strong>: ${esc(rule.description)}</li>`).join("")}</ul><p class="small muted">Threshold source: ${esc(r.threshold_source)}.</p></details>`;
  }

  // ---------------------------------------------------------------- credit passport
  function verdictHtml(v, title) {
    if (!v) return "";
    const label = v.valid ? "Valid" : {signature_mismatch: "Tampered or not issued here", expired: "Expired", wrong_business: "Wrong business", malformed: "Malformed", not_yet_valid: "Not yet valid"}[v.reason] || "Invalid";
    return `<div class="alert ${v.valid ? "success" : "critical"} tw-verdict section-gap">${icon(v.valid ? "check" : "alert")}<div><strong>${esc(title)}: <span class="pill ${v.valid ? "ok" : "storm"}">${icon(v.valid ? "check" : "x")}${esc(label)}</span></strong>
      <p class="small">${esc(v.message)}</p>${v.valid ? `<p class="tiny muted">Issuance logged in audit trail: ${v.issuance_logged ? "yes" : "no"} · records changed since issue: ${v.records_changed_since_issue ? "yes" : "no"}</p>` : ""}<p class="tiny muted">${esc(v.note)}</p></div></div>`;
  }
  function renderPassport() {
    const p = passport;
    const issue = canApprove() ? button("issue", `${icon("lock")}Issue a 30-day passport (PIN)`) : `<span class="pill">Viewer: can verify, cannot issue</span>`;
    let card = "";
    if (p) {
      const likely = p.twcf.likely;
      card = `<section class="tw-passport section-gap"><div class="row between"><div><span class="pill teal">${icon("shield")}Signed · Ed25519 public key</span><h3>${esc(p.business.name)} credit passport</h3><p class="tiny muted">Passport ${esc(p.passport_id)} · issuer key ${esc(p.issuer.key_id)}</p></div>
        <div class="row">${button("download", `${icon("download")}Download JSON`, "ghost small")}${button("verify", `${icon("check")}Verify`, "ghost small")}${button("tamper", `${icon("alert")}Tamper drill`, "ghost small")}</div></div>
        <div class="kv section-gap">
          <div><span>As of</span><strong>${esc(day(p.as_of, true))}</strong></div><div><span>Expires</span><strong>${esc(day(p.expires_at, true))}</strong></div>
          <div><span>Health score</span><strong>${esc(p.health.score)} / 100 · ${esc(p.health.band)}</strong></div>
          <div><span>Week-13 closing (likely)</span><strong>${esc(money(likely.closing_cash_minor))}</strong></div>
          <div><span>Lowest likely cash</span><strong>${esc(money(likely.lowest_cash_minor))}</strong></div>
          <div><span>Weeks below reserve (likely)</span><strong>${esc(likely.weeks_below_reserve.length)} of 13</strong></div>
          <div><span>Reserve-breach risk</span><strong>${percent(p.breach_risk.probability_breach)} of ${esc(p.breach_risk.runs)} futures</strong></div>
          <div><span>Audit-chain head</span><strong class="lab-hash">${short(p.audit.head_hash)}</strong></div>
          <div><span>Snapshot hash</span><strong class="lab-hash">${short(p.snapshot_hash)}</strong></div>
          <div><span>Signature</span><strong class="lab-hash">${short(p.signature)}</strong></div></div>
        ${verdictHtml(verification, "Verification")}
        ${drill ? `<div class="tw-drill section-gap"><h3>Tamper drill</h3><p class="small">Changed one number in a copy, in this browser: <code>${esc(drill.field)}</code> ${esc(units(drill.before))} → ${esc(units(drill.after))} (${esc(p.business.currency)}). The server re-checked both documents.</p>
          <div class="cols-2">${verdictHtml(drill.original, "Original")}${verdictHtml(drill.tampered, "Edited copy")}</div></div>` : ""}
        ${json("Signed passport JSON", p)}</section>`;
    }
    return `<div class="row between"><div><h3>Verifiable credit passport</h3><p>A signed, expiring summary a business can hand a lender: 13-week cash flow, health score and components, breach risk, snapshot hash and audit-chain head.</p></div>${issue}</div>
      <div class="alert info section-gap">${icon("shield")}<div><strong>Honest limits</strong><p class="small">Each passport carries an Ed25519 public-key signature, so a lender can verify it offline with <code>python scripts/verify_passport.py passport.json</code> without contacting Tideway. The issuer key is demo-grade (derived from the instance key; no HSM or revocation list). Synthetic data; not a credit rating, offer or guarantee. Issuing writes one audit entry and changes no financial record.</p></div></div>
      ${card}
      <div class="row section-gap"><label class="field">Verify a passport file<input id="treasury-passport-file" type="file" accept="application/json,.json"></label>${button("verify-file", `${icon("upload")}Verify file`, "ghost")}</div>
      ${verdictHtml(fileCheck, "File")}`;
  }

  function loadingHtml(text) {
    if (failure) return `<div class="alert critical section-gap">${icon("alert")}<div><strong>Could not load</strong><p class="small">${esc(failure)}</p>${button("retry", "Try again", "ghost small")}</div></div>`;
    return `<p role="status" class="muted section-gap">${esc(text)}</p>`;
  }

  function render() {
    sync();
    const body = {twcf: renderTwcf, health: renderHealth, scan: renderScan, passport: renderPassport}[tab]();
    if (tab !== "passport" && !results[tab] && !pending && !failure && !requested.has(tab)) {
      requested.add(tab);
      setTimeout(() => action("load", {}).catch((error) => { failure = error.message; renderApp(); }), 0);
    }
    return `<fieldset class="lab-controls-group" ${pending ? "disabled" : ""}><section class="card"><div class="card-head"><div><h2>Treasury</h2><p>For lenders, banks and finance teams that serve SMEs: the same records, read-only, in the formats they use.</p></div>
      <span class="pill">${esc(currency())} ledger · as of ${esc(day(state.dashboard.state.current_date, true))}</span></div>
      <div class="lab-tabs" role="group" aria-label="Treasury tools">${Object.entries(tabs).map(([id, label]) => `<button type="button" class="button small ${id === tab ? "teal" : "ghost"}" data-action="treasury-tab" data-tab="${id}" aria-pressed="${id === tab}" ${pending ? "disabled" : ""}>${esc(label)}</button>`).join("")}</div>
      ${pending ? '<p role="status" class="small muted">Calculating from the selected business records…</p>' : '<p class="small muted">Read-only: nothing on this page can approve, block, pay or change a record.</p>'}</section>
      <section class="card section-gap lab-panel tw-panel">${body}</section></fieldset>`;
  }

  async function request(path, body) {
    const origin = state.businessId, actor = state.operator?.id, serial = epoch;
    pending = true; renderApp();
    try {
      const result = await api(path, {business_id: origin, ...body});
      if (state.businessId !== origin || state.operator?.id !== actor || epoch !== serial) return null;
      return result;
    } finally { pending = false; renderApp(); }
  }

  async function action(name, data) {
    sync();
    if (name === "tab") { tab = data.tab; failure = ""; renderApp(); return; }
    if (name === "scenario") { if (scenarioNames[data.scenario]) scenario = data.scenario; renderApp(); return; }
    if (name === "retry") { failure = ""; requested.delete(tab); renderApp(); return; }
    if (pending) return;
    if (name === "load" || name === "scan") {
      const current = tab;
      if (current === "passport") return;
      const result = await request(`/api/treasury/${current}`, current === "scan" ? {synthetic_sample: synthetic} : {});
      if (result) { results[current] = result; failure = ""; renderApp(); }
      return;
    }
    if (name === "issue") {
      if (!canApprove()) throw new Error("Only the owner or accountant can issue a passport.");
      const answer = await askPin("Issue a credit passport", "Signs a 30-day summary of this business's 13-week cash flow, health score and audit head for a lender. The issuance is recorded in the audit trail; no financial record changes.");
      if (!answer) return;
      const result = await request("/api/treasury/passport/issue", {pin: answer.pin});
      if (result) { passport = result.passport; verification = null; drill = null; toast("Credit passport issued and recorded in the audit trail."); renderApp(); }
      return;
    }
    if (name === "verify") {
      if (!passport) throw new Error("Issue a passport first.");
      const result = await request("/api/treasury/passport/verify", {passport});
      if (result) { verification = result; renderApp(); }
      return;
    }
    if (name === "download") {
      if (!passport) throw new Error("Issue a passport first.");
      const url = URL.createObjectURL(new Blob([JSON.stringify(passport, null, 2)], {type: "application/json"}));
      const link = document.createElement("a"); link.href = url; link.download = `tideway-${state.businessId}-credit-passport.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Credit passport JSON downloaded.");
      return;
    }
    if (name === "tamper") {
      if (!passport) throw new Error("Issue a passport first.");
      const copy = JSON.parse(JSON.stringify(passport));
      const before = copy.twcf.likely.closing_cash_minor;
      copy.twcf.likely.closing_cash_minor = before + 5000000;  // claim 50,000 more closing cash
      const original = await request("/api/treasury/passport/verify", {passport});
      if (!original) return;
      const tampered = await request("/api/treasury/passport/verify", {passport: copy});
      if (tampered) { drill = {field: "twcf.likely.closing_cash_minor", before, after: copy.twcf.likely.closing_cash_minor, original, tampered}; renderApp(); }
      return;
    }
    if (name === "verify-file") {
      const file = document.querySelector("#treasury-passport-file")?.files[0];
      if (!file || file.size > 200000) throw new Error("Select a passport JSON file up to 200 KB.");
      let document_;
      try { document_ = JSON.parse(await file.text()); } catch (_error) { throw new Error("That file is not valid JSON."); }
      const result = await request("/api/treasury/passport/verify", {passport: document_});
      if (result) { fileCheck = result; renderApp(); }
    }
  }

  function renderApp() { renderGlobal(); }
  let renderGlobal = () => {};
  document.addEventListener("change", (event) => {
    if (!event.target?.hasAttribute?.("data-treasury-synthetic")) return;
    synthetic = event.target.checked;
    action("scan", {}).catch((error) => toast(error.message));
  });
  return {render, action, bind(renderer) { renderGlobal = renderer; },
    reset() { key = ""; epoch++; results = {}; requested = new Set(); passport = null; verification = null; drill = null; fileCheck = null; failure = ""; pending = false; tab = "twcf"; scenario = "likely"; synthetic = false; }};
})();
