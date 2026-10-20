"use strict";

// Portfolio radar: lender-side early warning over a SYNTHETIC SME portfolio.
// The server generates the fictional portfolio from a seed and never reads tenant
// workspaces. Every value is escaped; interventions are advisory text, never actions.
window.TidewayPortfolio = (() => {
  let epoch = 0, data = null, pending = false, queued = false, error = "", showAll = false, tierFilter = "all";
  let sort = {key: "rank", dir: 1};
  let draft = {shockDays: "0", sector: "all"};
  const TIER = {red: ["Red", "storm"], amber: ["Amber", "unsettled"], green: ["Green", "clear"]};
  const TIERS = ["red", "amber", "green"];
  const ACTIONS = {rm_call_urgent: ["RM call · urgent", "storm"], rm_call: ["RM call", "unsettled"],
    rm_review_structural: ["RM review", "unsettled"], mock_invoice_financing: ["MOCK financing comparison", "mock"],
    monitor: ["Monitor", "info"], no_action: ["No action", "clear"]};
  const ROWS_COLLAPSED = 15;
  const title = (text) => text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
  const pill = (tier) => `<span class="pill ${TIER[tier]?.[1] || ""}">${esc(TIER[tier]?.[0] || tier)}</span>`;
  const share = (value) => isNum(value) ? `${value > 0 && value < 0.01 ? "<1" : value < 1 && value > 0.99 ? ">99" : Math.round(value * 100)}%` : "—";
  const nativeMoney = (minor, code) => money(minor, code, {native: true});
  const shortMoney = (minor, code) => `${esc(code)} ${esc(compact(minor))}`;
  const current = (row) => (data?.shock && row.stressed) ? row.stressed : row;
  const breachDay = (value) => value === null || value === undefined ? "—" : value === 0 ? "Day 0 (now)" : `Day ${value}`;
  // SVG geometry and CSS classes only: the app's CSP (style-src 'self') blocks inline style attributes.
  const bar = (p, tier) => `<svg class="pf-bar ${esc(tier)}" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true"><rect class="pf-track" width="100" height="6" rx="3"></rect><rect class="pf-fill" width="${Math.max(2, Math.min(100, Math.round(p * 100)))}" height="6" rx="3"></rect></svg>`;
  const SORTS = {
    rank: (r) => r.rank, name: (r) => r.name.toLowerCase(), tier: (r) => TIERS.indexOf(current(r).tier),
    risk: (r) => -current(r).breach_probability, risk30: (r) => -current(r).p_breach_30d,
    when: (r) => current(r).days_to_breach ?? 999, shortfall: (r) => -current(r).expected_shortfall_minor / r.monthly_payroll_minor,
    market: (r) => `${r.currency}|${r.sector}`
  };

  function sortedRows() {
    const key = SORTS[sort.key] ? sort.key : "rank";
    const rows = data.smes.filter((r) => tierFilter === "all" || current(r).tier === tierFilter);
    return rows.slice().sort((a, b) => {
      const x = SORTS[key](a), y = SORTS[key](b);
      return (x < y ? -1 : x > y ? 1 : a.rank - b.rank) * sort.dir;
    });
  }
  function head(label, key, cls = "", hint = "") {
    const active = sort.key === key, arrow = active ? (sort.dir === 1 ? " ▲" : " ▼") : "";
    return `<th class="${cls}" ${active ? `aria-sort="${sort.dir === 1 ? "ascending" : "descending"}"` : ""}><button type="button" class="pf-sort" data-action="portfolio-sort" data-key="${esc(key)}" ${hint ? `title="${esc(hint)}"` : ""}>${esc(label)}${arrow}</button></th>`;
  }
  function heat(count, max, tier) {
    const level = count ? Math.min(6, Math.max(1, Math.round(6 * count / Math.max(1, max)))) : 0;
    return `<td class="pf-cell pf-h-${esc(tier)} pf-l${level} ${level >= 4 ? "pf-hot" : ""}">${esc(count)}</td>`;
  }
  function tierTable(byKey, label, format = title) {
    const entries = Object.entries(byKey);
    // Shade each tier column against its own maximum so red concentrations stand out.
    const max = Object.fromEntries(TIERS.map((t) => [t, Math.max(1, ...entries.map(([, tiers]) => tiers[t]))]));
    return `<div class="table-wrap"><table class="pf-heat"><thead><tr><th>${esc(label)}</th>${TIERS.map((t) => `<th class="num">${esc(TIER[t][0])}</th>`).join("")}<th class="num">Red %</th></tr></thead><tbody>
      ${entries.map(([key, tiers]) => {const total = TIERS.reduce((s, t) => s + tiers[t], 0);
        return `<tr><td>${esc(format(key))}</td>${TIERS.map((t) => heat(tiers[t], max[t], t)).join("")}<td class="num">${esc(share(total ? tiers.red / total : 0))}</td></tr>`;}).join("")}
    </tbody></table></div>`;
  }

  function kpis(summary) {
    const ccy = Object.entries(summary.expected_shortfall_by_currency_minor);
    const metric = (label, value, note, cls = "") => `<div class="metric ${cls}"><span class="label">${esc(label)}</span><span class="value">${value}</span><span class="note">${esc(note)}</span></div>`;
    const markets = new Set(data.smes.map((r) => r.currency)).size, sectors = new Set(data.smes.map((r) => r.sector)).size;
    return `<div class="metrics pf-kpis">
      ${metric("Portfolio", `${esc(summary.smes)} SMEs`, `${markets} currencies · ${sectors} sectors · ${data.generated.horizon_days}-day horizon`)}
      ${metric("Red", esc(summary.tiers.red), `breach risk ≥ ${share(data.thresholds.red_at_least)}`, "bad")}
      ${metric("Amber", `<span class="pf-amber">${esc(summary.tiers.amber)}</span>`, `${share(data.thresholds.amber_at_least)}–${Math.round(data.thresholds.red_at_least * 100 - 1)}% breach risk`)}
      ${metric("Green", esc(summary.tiers.green), `below ${share(data.thresholds.amber_at_least)} breach risk`, "good")}
    </div>
    <div class="metrics pf-kpis section-gap">
      ${metric("At risk within 14 days", esc(summary.at_risk_within_14d), `P(breach by day 14) ≥ ${share(data.thresholds.amber_at_least)}`, summary.at_risk_within_14d ? "bad" : "")}
      ${metric("At risk within 30 days", esc(summary.at_risk_within_30d), `P(breach by day 30) ≥ ${share(data.thresholds.amber_at_least)}`)}
      ${metric("Mean breach probability", esc(share(summary.mean_breach_probability)), "average across SMEs, 60 days")}
      <div class="metric"><span class="label">Expected shortfall</span><span class="value pf-ccy">${ccy.map(([code, minor]) => `<span title="${esc(nativeMoney(minor, code))}">${shortMoney(minor, code)}</span>`).join("")}</span><span class="note">per currency, never summed across currencies</span></div>
    </div>`;
  }

  function shockCard() {
    const sectors = data.generated.sectors, s = data.shock;
    const days = Number(draft.shockDays) || 0;
    let result = `<p class="small muted section-gap">Choose a delay and apply it to compare tier migration. The baseline uses the same random draws, so a delay can never lower a breach probability.</p>`;
    if (s) {
      const m = s.migration;
      const max = Math.max(1, ...TIERS.flatMap((b) => TIERS.map((a) => m[b][a])));
      result = `<div class="alert warning section-gap"><div><strong>Stress applied: +${esc(s.customer_delay_days)} days, ${esc(s.sector === "all" ? "all sectors" : title(s.sector))}</strong><span>${esc(s.description)}</span></div></div>
        <h3 class="section-gap">Tier migration (before → after)</h3>
        <div class="table-wrap"><table class="pf-heat pf-matrix"><thead><tr><th>Before ↓ · after →</th>${TIERS.map((t) => `<th class="num">${esc(TIER[t][0])}</th>`).join("")}</tr></thead><tbody>
        ${TIERS.map((b) => `<tr><td>${pill(b)}</td>${TIERS.map((a) => TIERS.indexOf(a) < TIERS.indexOf(b) ? heat(m[b][a], max, "red") : a === b ? `<td class="pf-cell">${esc(m[b][a])}</td>` : heat(m[b][a], max, "green")).join("")}</tr>`).join("")}
        </tbody></table></div>
        <p class="small section-gap"><strong>${esc(s.newly_at_risk.length)}</strong> SME${s.newly_at_risk.length === 1 ? "" : "s"} move to a worse tier. Mean breach probability ${esc(share(data.summary.mean_breach_probability))} → ${esc(share(s.summary_after.mean_breach_probability))}.</p>
        ${s.newly_at_risk.length ? `<ul class="pf-newly">${s.newly_at_risk.slice(0, 6).map((r) => `<li><span>${esc(r.name)} <span class="muted small">${esc(title(r.sector))} · ${esc(r.currency)}</span></span><span>${pill(r.before_tier)} <span class="pf-arrow">→</span> ${pill(r.after_tier)} <span class="small muted">${esc(share(r.before_probability))} → ${esc(share(r.after_probability))}</span></span></li>`).join("")}</ul>${s.newly_at_risk.length > 6 ? `<p class="small muted">and ${esc(s.newly_at_risk.length - 6)} more in the table below.</p>` : ""}` : ""}`;
    }
    return `<section class="card pf-shock"><div class="card-head"><div><h2>Macro stress</h2><p>What if customers pay later across the portfolio, or in one sector?</p></div>${s ? '<span class="pill violet">Stressed view</span>' : '<span class="pill">Baseline</span>'}</div>
      <label class="field">Extra customer payment delay: <output data-portfolio-out="shockDays">${esc(days)} days</output>
        <input type="range" min="0" max="60" step="5" value="${esc(days)}" data-portfolio-field="shockDays" aria-label="Extra customer payment delay in days" ${pending ? "disabled" : ""}></label>
      <div class="row section-gap"><label class="field">Sector in scope<select data-portfolio-field="sector" ${pending ? "disabled" : ""}><option value="all">All sectors</option>${sectors.map((x) => `<option value="${esc(x)}" ${draft.sector === x ? "selected" : ""}>${esc(title(x))}</option>`).join("")}</select></label>
        <button type="button" class="button primary" data-action="portfolio-apply" ${pending ? "disabled" : ""}>Run stress test</button>
        ${s ? `<button type="button" class="button ghost" data-action="portfolio-clear" ${pending ? "disabled" : ""}>Back to baseline</button>` : ""}</div>
      ${result}</section>`;
  }

  function table() {
    const rows = sortedRows(), visible = showAll ? rows : rows.slice(0, ROWS_COLLAPSED), s = data.shock;
    const filters = ["all", ...TIERS].map((t) => {const n = t === "all" ? data.smes.length : data.smes.filter((r) => current(r).tier === t).length;
      return `<button type="button" class="button small ${tierFilter === t ? "teal" : "ghost"}" data-action="portfolio-tier" data-tier="${esc(t)}">${esc(t === "all" ? "All" : TIER[t][0])} · ${esc(n)}</button>`;}).join("");
    return `<section class="card section-gap"><div class="card-head"><div><h2>Ranked early-warning list</h2><p>Sorted by breach probability by default. Click a column to re-sort. ${s ? "Risk shows baseline → stressed." : ""}</p></div><div class="row">${filters}</div></div>
      <div class="table-wrap"><table class="pf-table"><thead><tr>${head("#", "rank", "num")}${head("SME", "name")}${head("Market", "market")}${head("Tier", "tier")}${head("Breach risk (60d)", "risk", "", "Share of simulated futures in which cash falls below the SME's reserve floor")}${head("By day 30", "risk30", "num")}${head("Typical first breach", "when", "num", "Median first breach day among the futures that breach")}${head("Expected shortfall", "shortfall", "num", "Mean reserve shortfall across all futures; sorted by months of payroll so currencies are comparable")}<th>Top driver</th><th>Early intervention (advisory)</th></tr></thead><tbody>
      ${visible.map((r) => {const c = current(r), act = ACTIONS[c.intervention.code] || [c.intervention.code, ""];
        const driver = c.top_driver.kind === "customer" ? `${esc(c.top_driver.name)}<span class="small muted pf-sub">${esc(share(c.top_driver.share))} of late cash before breaches</span>`
          : c.top_driver.kind === "structural" ? `<strong>Scheduled outflows</strong><span class="small muted pf-sub">breach even if every customer pays on time</span>` : `<span class="muted">—</span>`;
        const risk = s && r.stressed?.in_scope ? `${bar(c.breach_probability, c.tier)}<strong>${esc(share(r.breach_probability))} <span class="pf-arrow">→</span> ${esc(share(c.breach_probability))}</strong>` : `${bar(c.breach_probability, c.tier)}<strong>${esc(share(c.breach_probability))}</strong>`;
        return `<tr><td class="num">${esc(r.rank)}</td><td><strong>${esc(r.name)}</strong><span class="small muted pf-sub">${esc(r.sme_id)} · ${esc(r.customers)} customers · cash ${esc(r.cash_to_payroll)}× payroll</span></td>
          <td class="nowrap">${esc(r.country)} · ${esc(r.currency)}<span class="small muted pf-sub">${esc(title(r.sector))}</span></td>
          <td>${pill(c.tier)}${s && r.stressed?.in_scope && r.stressed.tier !== r.tier ? `<span class="small muted pf-sub">was ${esc(TIER[r.tier][0])}</span>` : ""}</td>
          <td class="nowrap">${risk}</td><td class="num">${esc(share(c.p_breach_30d))}</td><td class="num">${esc(breachDay(c.days_to_breach))}</td>
          <td class="num"><span title="${esc(nativeMoney(c.expected_shortfall_minor, r.currency))}">${c.expected_shortfall_minor ? shortMoney(c.expected_shortfall_minor, r.currency) : "—"}</span><span class="small muted pf-sub">worst 5%: ${c.worst_shortfall_minor ? shortMoney(c.worst_shortfall_minor, r.currency) : "—"}</span></td>
          <td>${driver}</td><td class="pf-intervention"><span class="pill ${esc(act[1])}">${esc(act[0])}</span><span class="pf-sub">${esc(c.intervention.text)}</span></td></tr>`;}).join("")}
      </tbody></table></div>
      ${rows.length > ROWS_COLLAPSED ? `<div class="row section-gap"><button type="button" class="button small ghost" data-action="portfolio-more">${showAll ? "Show top " + ROWS_COLLAPSED : `Show all ${esc(rows.length)}`}</button></div>` : ""}
      ${!rows.length ? '<p class="small muted section-gap">No SMEs in this tier.</p>' : ""}</section>`;
  }

  function backtestCard() {
    const b = data.backtest, r = b.radar, s = b.baseline_scheduled_projection, c = b.baseline_cash_to_payroll;
    const num = (v, digits = 3) => isNum(v) ? v.toFixed(digits) : "—";
    const better = (a, x, lower = false) => isNum(a) && isNum(x) && (lower ? a < x : a > x) ? " pf-win" : "";
    const ratio = (m) => isNum(m.red_precision) ? `${share(m.red_precision)} <span class="small muted">(${esc(m.true_positives)}/${esc(m.flagged)})</span>` : "—";
    return `<section class="card section-gap"><div class="card-head"><div><h2>Backtest: did the radar see it coming?</h2><p>Each SME gets one realised future drawn from the generative payment process with an independent seed (not the radar's own draws), including unexpected costs the radar cannot see.</p></div><span class="pill">${esc(b.breached)} of ${esc(b.n)} SMEs actually breached</span></div>
      <div class="table-wrap"><table class="pf-backtest"><thead><tr><th>Metric</th><th class="num">Portfolio radar</th><th class="num">Scheduled projection</th><th class="num">Cash ÷ payroll</th></tr></thead><tbody>
        <tr><td>ROC AUC <span class="small muted">(ranking; higher is better)</span></td><td class="num${better(r.auc, Math.max(s.auc ?? 0, c.auc ?? 0))}">${esc(num(r.auc))}</td><td class="num">${esc(num(s.auc))}</td><td class="num">${esc(num(c.auc))}</td></tr>
        <tr><td>Brier score <span class="small muted">(calibration; lower is better; base rate ${esc(num(b.brier_climatology))})</span></td><td class="num${better(r.brier, s.brier, true)}">${esc(num(r.brier))}</td><td class="num">${esc(num(s.brier))} <span class="small muted">0/1</span></td><td class="num">—</td></tr>
        <tr><td>Red-tier precision <span class="small muted">(flagged SMEs that breached)</span></td><td class="num">${ratio(r)}</td><td class="num">${ratio(s)}</td><td class="num">—</td></tr>
        <tr><td>Red-tier recall <span class="small muted">(breaches flagged red)</span></td><td class="num${better(r.red_recall, s.red_recall)}">${esc(share(r.red_recall))}</td><td class="num">${esc(share(s.red_recall))}</td><td class="num">—</td></tr>
      </tbody></table></div>
      <p class="small muted section-gap">Scheduled projection = every invoice paid on its due date (red = scheduled breach). Synthetic and in-distribution for TidePay, so this is a consistency check, not real-world validation. In the pooled evaluation mid-range probabilities run below observed breach rates: read them as a ranking. Outcome seed ${esc(b.outcome_seed)}. The multi-portfolio evaluation with confidence intervals is in evidence/portfolio/portfolio-report.json.</p></section>`;
  }

  function render() {
    if (!data && !pending && !error && !queued) { queued = true; setTimeout(() => { queued = false; if (!data && !pending) load().catch(() => {}); }, 0); }
    const intro = `<div class="card-head"><div><h2>Portfolio radar</h2><p>Early warning for banks, lenders and large buyers: which SMEs are likely to breach their cash reserve in the next 60 days, why, and what to do first.</p></div><div class="row"><span class="pill mock">SYNTHETIC portfolio</span><span class="pill">Never reads tenant workspaces</span><span class="pill info">Advisory only</span></div></div>`;
    if (!data) {
      return `<div class="pf" data-currency-original="native"><section class="card">${intro}${error ? `<div class="alert critical"><div><strong>Radar unavailable</strong><span>${esc(error)}</span></div></div><div class="row section-gap"><button type="button" class="button primary" data-action="portfolio-load">Try again</button></div>` : '<p role="status" class="muted">Simulating 60 synthetic SMEs with TidePay…</p>'}</section></div>`;
    }
    return `<div class="pf" data-currency-original="native"><fieldset class="lab-controls-group" ${pending ? "disabled" : ""}>
      <section class="card">${intro}
        <div class="alert info"><div><strong>${esc(data.label)}</strong><span>${esc(data.method)} ${esc(data.generated.runs)} futures per SME, seed ${esc(data.generated.seed)}. Tiers: red ≥ ${esc(share(data.thresholds.red_at_least))}, amber ≥ ${esc(share(data.thresholds.amber_at_least))}.</span></div></div>
        ${pending ? '<p role="status" class="small muted section-gap">Re-running the radar…</p>' : ""}
        <div class="section-gap">${kpis(data.shock ? data.shock.summary_after : data.summary)}</div>
        ${data.shock ? `<p class="small muted section-gap">Headline figures show the stressed portfolio (+${esc(data.shock.customer_delay_days)} days). Baseline: ${esc(data.summary.tiers.red)} red, ${esc(data.summary.tiers.amber)} amber, ${esc(data.summary.tiers.green)} green.</p>` : ""}
      </section>
      <div class="grid cols-2 section-gap">${shockCard()}
        <section class="card"><div class="card-head"><div><h2>Where the risk sits</h2><p>Count of SMEs per tier${data.shock ? " after the stress" : ""}. Darker cells hold more SMEs within each tier column.</p></div></div>
          ${tierTable((data.shock ? data.shock.summary_after : data.summary).sector_tier, "Sector")}
          <div class="section-gap">${tierTable((data.shock ? data.shock.summary_after : data.summary).currency_tier, "Currency", (x) => x)}</div></section></div>
      ${table()}${backtestCard()}
      <p class="small muted section-gap">${data.limits.map((x) => esc(x)).join(" ")}</p></fieldset></div>`;
  }

  async function load() {
    if (pending) return;
    const serial = epoch, days = Math.min(60, Math.max(0, Math.round(Number(draft.shockDays) || 0))), sector = draft.sector || "all";
    pending = true; error = ""; renderApp();
    try {
      const query = new URLSearchParams({shock_days: String(days), sector});
      const result = await api(`/api/portfolio/radar?${query}`);
      if (serial !== epoch) return;
      data = result;
    } catch (e) {
      if (serial === epoch) error = e.message || "The radar could not be loaded.";
      throw e;
    } finally {
      if (serial === epoch) { pending = false; renderApp(); }
    }
  }

  async function action(name, info) {
    if (name === "sort") {
      const key = info.key;
      if (!SORTS[key]) return;
      sort = sort.key === key ? {key, dir: -sort.dir} : {key, dir: 1};
      renderApp(); return;
    }
    if (name === "tier") { tierFilter = ["all", ...TIERS].includes(info.tier) ? info.tier : "all"; showAll = false; renderApp(); return; }
    if (name === "more") { showAll = !showAll; renderApp(); return; }
    if (pending) return;
    if (name === "clear") { draft = {shockDays: "0", sector: "all"}; await load(); return; }
    if (name === "apply" || name === "load") { await load(); return; }
  }

  function renderApp() { renderGlobal(); }
  // app.js passes its renderer after defining the application's lexical state.
  let renderGlobal = () => {};
  const remember = (event) => {
    const name = event.target?.dataset?.portfolioField;
    if (!name) return;
    draft[name] = event.target.value;
    const out = document.querySelector(`[data-portfolio-out="${name}"]`);
    if (out) out.textContent = `${Number(event.target.value) || 0} days`;
  };
  document.addEventListener("input", remember);
  document.addEventListener("change", remember);
  return {render, action, bind(renderer) { renderGlobal = renderer; }, validateCurrency() { /* no money inputs; amounts stay in each SME's currency */ },
    reset() { epoch++; data = null; pending = false; error = ""; showAll = false; tierFilter = "all"; sort = {key: "rank", dir: 1}; draft = {shockDays: "0", sector: "all"}; }};
})();
