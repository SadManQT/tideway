"use strict";

const $ = (selector) => document.querySelector(selector);
const state = {
  config: null,
  businessId: "",
  targetDate: "",
  dashboard: null,
  audit: null,
  planComparison: null,
  pendingApproval: null,
  execution: null,
  view: "overview",
  recordQuery: "",
  recordType: "",
  recordStatus: "",
  messages: [],
  consent: false,
  busy: false,
  planError: "",
  pendingContext: null,
  executionStatus: null,
  uncertainExecution: null,
  policyError: "",
  policyValues: null,
  requestSerial: 0,
  busyLabel: "",
  busyContext: null,
  mutationToken: null
};

const MUTATING_ACTIONS = new Set(["compare-plans", "approve-plan", "execute-approved", "check-execution-status", "simulate-consent", "cancel-approval", "reset-sandbox", "save-policy"]);
const EXECUTION_ATTEMPT_KEY = "probaho.executionAttempt";

const viewMeta = {
  overview: ["Cash gap overview", "Cash gap overview", "See the scheduled gap, its sources, and the recovery choices that need approval."],
  records: ["Records", "Records", "Inspect the transactions, invoices, and bills behind every projection."],
  plans: ["Recovery plans", "Recovery plans", "Compare explainable options before a human approves a sandbox action."],
  assistant: ["Assistant", "Assistant", "Ask about the gap in plain English. The assistant can explain and propose, never approve or execute."],
  activity: ["Activity & evidence", "Activity & evidence", "Review permissions, receipts, and the local hash-chain evidence trail."]
};

const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[character]));
const hasValue = (value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
const numberValue = (value, fallback = 0) => hasValue(value) ? Number(value) : fallback;
const displayMinor = (value, decimals = null) => hasValue(value) ? money(value, decimals) : "Unavailable";

function money(minor, decimals = null) {
  if (!hasValue(minor)) return "Unavailable";
  const amount = numberValue(minor) / 100;
  const precision = decimals === null ? (Number.isInteger(amount) ? 0 : 2) : decimals;
  return `BDT ${amount.toLocaleString("en-US", {minimumFractionDigits: precision, maximumFractionDigits: precision})}`;
}

function minorInput(minor) {
  if (!hasValue(minor)) return "";
  return (Number(minor) / 100).toFixed(2);
}

function parsePaisa(value, label) {
  const text = String(value ?? "").trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) throw new Error(`${label} must be a non-negative BDT amount with at most two decimals.`);
  const parts = text.split(".");
  const whole = BigInt(parts[0]);
  const fraction = BigInt((parts[1] || "").padEnd(2, "0"));
  const minor = whole * 100n + fraction;
  if (minor > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error(`${label} is too large.`);
  return Number(minor);
}

function dateLabel(value) {
  if (!value) return "—";
  const parsed = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString("en-GB", {day: "2-digit", month: "short", year: "numeric"});
}

function dateTimeLabel(value) {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("en-GB", {timeZone: "Asia/Dhaka", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false}) + " Dhaka";
}

function shortDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString("en-GB", {day: "2-digit", month: "short"});
}

function jsonText(value) {
  try {
    return escapeHtml(JSON.stringify(value, null, 2));
  } catch (_error) {
    return escapeHtml(String(value));
  }
}

async function api(path, body) {
  const options = {headers: {"Accept": "application/json"}};
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  options.signal = controller.signal;
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.headers["X-Probaho-Token"] = state.config?.csrf_token || "";
    options.headers["X-CSRF-Token"] = state.config?.csrf_token || "";
    options.body = JSON.stringify(body);
  }
  try {
    const response = await fetch(path, options);
    const raw = await response.text();
    let result;
    try {
      result = JSON.parse(raw);
    } catch (_error) {
      const error = new Error("The server returned an unreadable response. Check the operation status before retrying.");
      error.ambiguous = true;
      throw error;
    }
    if (!result || typeof result !== "object" || Array.isArray(result)) {
      const error = new Error("The server returned an invalid response. Check the operation status before retrying.");
      error.ambiguous = true;
      throw error;
    }
    if (!response.ok) {
      const error = new Error(result.error || "The request could not be completed.");
      error.definitiveRejection = response.status >= 400 && response.status < 500 && typeof result.error === "string";
      error.ambiguous = response.status >= 500;
      throw error;
    }
    return result;
  } finally {
    clearTimeout(timeout);
  }
}

function contextSnapshot() {
  return {businessId: state.businessId, targetDate: state.targetDate};
}

function contextMatches(context) {
  return !context || (context.businessId === state.businessId && context.targetDate === state.targetDate);
}

function resetPerMessageConsent() {
  state.consent = false;
}

function invalidateAudit(reason = "workspace context changed") {
  if (state.audit) console.info(`[Probaho] audit cache invalidated: ${reason}`);
  state.audit = null;
  state.auditRequest = null;
}

function beginMutation(label, context = contextSnapshot()) {
  if (state.busy) throw new Error("Another Probaho operation is still in progress.");
  state.busy = true;
  state.busyLabel = label;
  state.busyContext = context;
  state.mutationToken = ++state.requestSerial;
  renderView();
  return state.mutationToken;
}

function endMutation(token) {
  if (!token || token !== state.mutationToken) return;
  state.busy = false;
  state.busyLabel = "";
  state.busyContext = null;
  state.mutationToken = null;
  renderView();
}

function syncBusyControls() {
  if (state.busy) {
    document.querySelectorAll("[data-action], [data-close], #business-select, #target-date, form input, form textarea, form button[type='submit']").forEach((control) => {
      if (!control.disabled) {
        control.dataset.busyDisabled = "true";
        control.disabled = true;
      }
    });
  } else {
    document.querySelectorAll("[data-busy-disabled]").forEach((control) => {
      control.disabled = false;
      delete control.dataset.busyDisabled;
    });
  }
}

function readExecutionAttempt() {
  try {
    const value = JSON.parse(sessionStorage.getItem(EXECUTION_ATTEMPT_KEY) || "null");
    if (value && typeof value.business_id === "string" && typeof value.approval_id === "string" && value.idempotency_key === `execute-${value.approval_id}` && /^\d{4}-\d{2}-\d{2}$/.test(value.targetDate)) return value;
  } catch (_error) { /* session storage may be unavailable */ }
  return null;
}

function persistExecutionAttempt(attempt) {
  try { sessionStorage.setItem(EXECUTION_ATTEMPT_KEY, JSON.stringify({business_id: attempt.business_id, approval_id: attempt.approval_id, idempotency_key: attempt.idempotency_key, targetDate: attempt.targetDate})); } catch (_error) { /* best effort only */ }
}

function clearExecutionAttempt(approvalId) {
  const stored = readExecutionAttempt();
  if (!stored || stored.approval_id !== approvalId) return;
  try { sessionStorage.removeItem(EXECUTION_ATTEMPT_KEY); } catch (_error) { /* best effort only */ }
}

function restoreExecutionAttempt() {
  const attempt = readExecutionAttempt();
  state.uncertainExecution = attempt && attempt.business_id === state.businessId && attempt.targetDate === state.targetDate ? {context: {businessId: attempt.business_id, targetDate: attempt.targetDate}, approvalId: attempt.approval_id, idempotencyKey: attempt.idempotency_key} : null;
}

function mutationDisabled() {
  return state.busy ? "disabled" : "";
}

let toastTimer;
function toast(message) {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 5000);
}

function showError(error) {
  const element = $("#app-error");
  if (!element) return;
  element.textContent = error?.message || String(error);
  element.hidden = false;
}

function clearError() {
  const element = $("#app-error");
  if (element) {
    element.textContent = "";
    element.hidden = true;
  }
}

function businesses() {
  return Array.isArray(state.config?.businesses) ? state.config.businesses : [];
}

function businessIdOf(business) {
  return business?.id || business?.business_id || "";
}

function selectedBusiness() {
  return state.dashboard?.business || businesses().find((item) => businessIdOf(item) === state.businessId) || {};
}

function selectedBusinessName() {
  return selectedBusiness().name || businesses().find((item) => businessIdOf(item) === state.businessId)?.name || state.businessId || "Business";
}

function setSelectorOptions() {
  const select = $("#business-select");
  if (select) {
    select.innerHTML = businesses().map((business) => {
      const id = businessIdOf(business);
      return `<option value="${escapeHtml(id)}" ${id === state.businessId ? "selected" : ""}>${escapeHtml(business.name || id)}</option>`;
    }).join("");
  }
  const date = $("#target-date");
  if (date) date.value = state.targetDate || "";
  const name = $("#workspace-name");
  if (name) name.textContent = selectedBusinessName();
}

function isoDatePlus(value, days) {
  if (!value) return "";
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function setTargetBounds() {
  const input = $("#target-date");
  const business = selectedBusiness();
  if (!input || !business.opening_date) return;
  input.min = business.opening_date;
  input.max = isoDatePlus(business.opening_date, 366);
}

function normalisePlan(raw) {
  const item = raw && typeof raw === "object" ? raw : {};
  const action = item.action && typeof item.action === "object" ? item.action : item;
  const kind = item.kind || item.type || action.type || action.action_type || "recovery_action";
  const projected = item.projected || item.projected_projection || item.projection || {};
  const risks = Array.isArray(item.risks) ? item.risks : item.risks ? [item.risks] : [];
  return {
    ...item,
    action,
    action_id: item.action_id || action.action_id || action.id || item.id || "",
    title: item.title || item.label || action.label || kind.replaceAll("_", " "),
    kind,
    assumption: item.assumption || item.explanation || action.assumption || action.explanation || "Projection uses the records currently in this business workspace.",
    labelled_mock: Boolean(item.labelled_mock ?? item.mock ?? action.labelled_mock ?? action.mock ?? kind === "mock_financing"),
    feasible: item.feasible !== undefined ? Boolean(item.feasible) : action.feasible !== undefined ? Boolean(action.feasible) : true,
    executable: item.executable !== undefined ? Boolean(item.executable) : action.executable !== undefined ? Boolean(action.executable) : !Boolean(item.labelled_mock ?? item.mock ?? action.mock),
    projected,
    risks,
    projected_closing_cash_minor: item.projected_closing_cash_minor ?? projected.closing_cash_minor ?? projected.projected_closing_cash_minor,
    projected_minimum_cash_minor: item.projected_minimum_cash_minor ?? projected.minimum_cash_minor ?? projected.projected_minimum_cash_minor,
    projected_reserve_shortfall_minor: item.projected_reserve_shortfall_minor ?? projected.reserve_shortfall_minor ?? projected.projected_reserve_shortfall_minor,
    projected_minimum_reserve_shortfall_minor: item.projected_minimum_reserve_shortfall_minor ?? projected.minimum_reserve_shortfall_minor ?? projected.projected_minimum_reserve_shortfall_minor,
    cash_effect_minor: item.cash_effect_minor ?? action.cash_effect_minor
  };
}

function normalisePlans(value) {
  const raw = Array.isArray(value) ? value : Array.isArray(value?.plans) ? value.plans : Array.isArray(value?.options) ? value.options : [];
  return raw.map(normalisePlan);
}

function normaliseApproval(value) {
  if (!value) return null;
  return {
    ...value,
    approval_id: value.approval_id || value.id || "",
    plan_id: value.plan_id || "",
    action_id: value.action_id || value.action?.action_id || "",
    expires_at: value.expires_at || value.expiry || "",
    status: value.status || "pending"
  };
}

function projection(name) {
  return state.dashboard?.projection?.[name] || state.planComparison?.projection?.[name] || {};
}

function reserveShortfall(value) {
  return value?.minimum_reserve_shortfall_minor ?? value?.cash_gap_minor ?? value?.reserve_shortfall_minor;
}

function minimumCash(value) {
  return value?.minimum_cash_minor ?? value?.closing_cash_minor;
}

function planSourcePayload() {
  return state.planComparison || state.dashboard?.pending_plan || {};
}

function planList() {
  return normalisePlans(state.planComparison?.plans || state.dashboard?.plans);
}

function comparisonPlanId() {
  const payload = state.planComparison || state.dashboard?.pending_plan || {};
  return typeof payload.plan_id === "string" ? payload.plan_id : "";
}

function approvalPlanId() {
  return typeof state.pendingApproval?.plan_id === "string" ? state.pendingApproval.plan_id : "";
}

function activePlanId() {
  return comparisonPlanId() || approvalPlanId();
}

function projectionSources(value) {
  const refs = value?.sources || value?.source_references || [];
  return Array.isArray(refs) ? refs : [];
}

function recordCollection(kind) {
  const dashboard = state.dashboard || {};
  const direct = dashboard[kind];
  if (Array.isArray(direct)) return direct;
  const recent = dashboard.recent_records || {};
  return Array.isArray(recent[kind]) ? recent[kind] : [];
}

function recordRows() {
  const rows = [];
  recordCollection("transactions").forEach((record) => rows.push({
    ...record,
    recordType: "transaction",
    typeLabel: "Transaction",
    status: record.status || record.type || "recorded",
    date: record.date,
    description: record.description || "Transaction",
    party: ""
  }));
  recordCollection("invoices").forEach((record) => rows.push({
    ...record,
    recordType: "invoice",
    typeLabel: "Invoice",
    status: record.status || "confirmed",
    date: record.expected_collection_date || record.due_date,
    description: record.description || "Receivable",
    party: record.customer || ""
  }));
  recordCollection("bills").forEach((record) => rows.push({
    ...record,
    recordType: "bill",
    typeLabel: "Bill",
    status: record.status || "open",
    date: record.due_date,
    description: record.description || "Supplier bill",
    party: record.payee || ""
  }));
  return rows.sort((left, right) => String(right.date || "").localeCompare(String(left.date || "")));
}

function filteredRecordRows() {
  const query = state.recordQuery.trim().toLocaleLowerCase();
  return recordRows().filter((record) => {
    const searchable = [record.description, record.party, record.id, record.type, record.status, record.source].join(" ").toLocaleLowerCase();
    return (!query || searchable.includes(query)) && (!state.recordType || record.recordType === state.recordType) && (!state.recordStatus || String(record.status).toLocaleLowerCase() === state.recordStatus);
  });
}

function initialAssistantMessage() {
  return {
    role: "assistant",
    mode: "intro",
    content: "I’m Probaho, a local SME cash-flow recovery demo. I can explain the scheduled cash gap and compare recovery scenarios. I cannot approve or execute actions."
  };
}

async function refreshConfig() {
  state.config = await api("/api/config");
  const list = businesses();
  const preferred = state.config.default_business_id || list[0] && businessIdOf(list[0]);
  const storedAttempt = !state.businessId ? readExecutionAttempt() : null;
  if (storedAttempt && list.some((item) => businessIdOf(item) === storedAttempt.business_id)) {
    state.businessId = storedAttempt.business_id;
    state.targetDate = storedAttempt.targetDate;
  }
  if (!state.businessId || !list.some((item) => businessIdOf(item) === state.businessId)) state.businessId = preferred || "";
  const business = list.find((item) => businessIdOf(item) === state.businessId) || {};
  if (!state.targetDate) state.targetDate = state.config.default_target_date || business.default_target_date || "";
  const workspaceLabel = state.config.synthetic_only ? "Synthetic sandbox" : "Local workspace";
  $("#dataset-badge").textContent = workspaceLabel;
  $("#workspace-kind").textContent = workspaceLabel;
  setSelectorOptions();
  setTargetBounds();
  restoreExecutionAttempt();
}

async function refreshDashboard(render = true, expectedContext = contextSnapshot()) {
  if (!expectedContext.businessId || !expectedContext.targetDate) throw new Error("A business and target date are required.");
  const requestContext = {...expectedContext};
  const request = ++state.requestSerial;
  state.dashboardRequest = request;
  const query = `?business_id=${encodeURIComponent(requestContext.businessId)}&target_date=${encodeURIComponent(requestContext.targetDate)}`;
  const dashboard = await api(`/api/dashboard${query}`);
  if (!contextMatches(requestContext) || request !== state.dashboardRequest) return false;
  state.dashboard = dashboard;
  state.pendingApproval = normaliseApproval(dashboard.pending_approval);
  state.planComparison = dashboard.pending_plan?.plan_id ? dashboard.pending_plan : null;
  if (state.pendingApproval && !state.pendingApproval.action) {
    const pendingPlanAction = normalisePlans(dashboard.pending_plan?.plans).find((item) => item.action_id === state.pendingApproval.action_id);
    if (pendingPlanAction) state.pendingApproval.action = pendingPlanAction.action;
  }
  state.pendingContext = state.pendingApproval ? requestContext : null;
  const serverBusinessDate = state.dashboard.business?.default_target_date;
  if (!state.targetDate && serverBusinessDate) state.targetDate = serverBusinessDate;
  setSelectorOptions();
  setTargetBounds();
  clearError();
  if (render) renderView();
  return true;
}

async function loadAudit(render = true) {
  const context = contextSnapshot();
  const query = context.businessId ? `?business_id=${encodeURIComponent(context.businessId)}` : "";
  const request = ++state.requestSerial;
  state.auditRequest = request;
  const audit = await api(`/api/audit${query}`);
  if (!contextMatches(context) || request !== state.auditRequest) return;
  state.audit = audit;
  if (render) renderView();
}

async function navigate(view) {
  if (!viewMeta[view]) return;
  state.view = view;
  if (view === "activity" && !state.audit) await loadAudit(false);
  renderView();
}

function renderView() {
  const meta = viewMeta[state.view] || viewMeta.overview;
  $("#view-label").textContent = meta[0];
  $("#page-title").textContent = meta[1];
  $("#page-subtitle").textContent = meta[2];
  document.querySelectorAll(".nav-item").forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  const renderer = {overview: renderOverview, records: renderRecords, plans: renderPlans, assistant: renderAssistant, activity: renderActivity}[state.view];
  $("#view-content").innerHTML = renderer ? renderer() : "";
  syncBusyControls();
  if (state.view === "assistant") scrollChat();
}

function metricCard(label, value, note, className = "") {
  return `<article class="metric-card ${className}"><span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${value}</strong><span class="metric-note">${escapeHtml(note)}</span></article>`;
}

function scenarioCard(label, scenario, accent) {
  const value = scenario || {};
  const closing = value.closing_cash_minor;
  const shortfall = reserveShortfall(value);
  const floor = value.reserve_floor_minor;
  const lowest = minimumCash(value);
  const firstShortfall = value.first_shortfall_date;
  const width = hasValue(closing) && hasValue(projection("base").opening_cash_minor) ? Math.max(4, Math.min(100, Math.round(Math.abs(Number(closing)) / Math.max(1, Math.abs(Number(projection("base").opening_cash_minor))) * 100))) : 4;
  return `<article class="scenario-card ${escapeHtml(accent)}"><div class="scenario-top"><div><span class="scenario-kicker">SCENARIO</span><h3>${escapeHtml(label)}</h3></div><span class="scenario-chip">${escapeHtml(value.assumptions?.late_collection_days ? `${value.assumptions.late_collection_days}-day delay` : label === "Approved recovery" ? "After approved action" : "Scheduled")}</span></div><div class="scenario-bar" aria-hidden="true"><span style="width:${width}%"></span></div><div class="scenario-numbers"><div><span>Closing cash</span><strong>${displayMinor(closing)}</strong></div><div><span>Minimum cash</span><strong>${displayMinor(lowest)}</strong></div><div><span>Worst reserve shortfall</span><strong class="${hasValue(shortfall) && Number(shortfall) > 0 ? "negative" : "positive"}">${displayMinor(shortfall)}</strong></div></div><p class="scenario-footnote">${hasValue(shortfall) && Number(shortfall) > 0 ? `First shortfall: ${escapeHtml(dateLabel(firstShortfall))}` : `Reserve floor: ${displayMinor(floor)}`}</p></article>`;
}

function timelineRows() {
  const days = projection("base").days || [];
  if (!Array.isArray(days) || !days.length) return [];
  const meaningful = days.filter((day) => numberValue(day.inflow_minor) || numberValue(day.outflow_minor) || (day.source_references || []).length);
  const chosen = meaningful.length ? meaningful : days;
  const first = days[0];
  const last = days[days.length - 1];
  const result = [];
  [first, ...chosen, last].forEach((day) => {
    if (day && !result.some((item) => item.date === day.date)) result.push(day);
  });
  return result.slice(0, 8);
}

function findRecord(kind, id) {
  if (kind === "transaction") return recordCollection("transactions").find((record) => record.id === id);
  if (kind === "invoice") return recordCollection("invoices").find((record) => record.id === id);
  if (kind === "bill" || kind === "bill_rescheduled" || kind === "bill_deferred") return recordCollection("bills").find((record) => record.id === id);
  return null;
}

function sourceDescription(reference) {
  const record = findRecord(reference.kind, reference.id);
  if (record) return record.description || record.customer || record.payee || reference.id;
  if (reference.kind === "business") return "Opening cash supplied by the business profile";
  return reference.id || reference.kind || "Linked record";
}

function renderSourceRows() {
  const references = projectionSources(projection("base"));
  if (!references.length) return `<div class="empty-state compact"><strong>No source links returned.</strong><p>The server did not attach source records to this projection.</p></div>`;
  return references.slice(0, 12).map((reference) => {
    const record = findRecord(reference.kind, reference.id);
    const destination = record ? "records" : reference.kind === "business" ? "overview" : "records";
    const effect = reference.effect_minor ?? reference.amount_minor;
    const effectLabel = hasValue(effect) ? `${Number(effect) < 0 ? "−" : "+"}${money(Math.abs(Number(effect)))}` : "Unavailable";
    return `<button class="source-row" data-view="${destination}" ${record ? `data-record-id="${escapeHtml(reference.id || "")}"` : ""} title="${destination === "overview" ? "Open business context" : "Open linked record"}"><span class="source-icon">${icon("link")}</span><span class="source-copy"><strong>${escapeHtml(sourceDescription(reference))}</strong><small>${escapeHtml(reference.kind || "record")} · ${escapeHtml(reference.id || "opening-cash")} · ${escapeHtml(reference.date || reference.field || "source-linked")}</small></span><b class="${hasValue(effect) && Number(effect) < 0 ? "negative" : "positive"}">${effectLabel}</b></button>`;
  }).join("");
}

function renderTimeline() {
  const rows = timelineRows();
  if (!rows.length) {
    const base = projection("base");
    return `<div class="timeline" role="table" aria-label="Base projection timeline"><div class="timeline-head" role="row"><span>Window</span><span>Inflow</span><span>Outflow</span><span>Closing cash</span></div><div class="timeline-row" role="row"><span>Through ${escapeHtml(shortDate(state.targetDate))}</span><span class="positive">${hasValue(base.inflow_minor) ? `+${money(base.inflow_minor)}` : "Unavailable"}</span><span class="negative">${hasValue(base.outflow_minor) ? `−${money(base.outflow_minor)}` : "Unavailable"}</span><strong>${displayMinor(base.closing_cash_minor)}</strong></div></div>`;
  }
  return `<div class="timeline" role="table" aria-label="Base projection timeline"><div class="timeline-head" role="row"><span>Date</span><span>Inflow</span><span>Outflow</span><span>Closing cash</span></div>${rows.map((day) => `<div class="timeline-row" role="row"><span>${escapeHtml(shortDate(day.date))}</span><span class="positive">${hasValue(day.inflow_minor) ? `+${money(day.inflow_minor)}` : "Unavailable"}</span><span class="negative">${hasValue(day.outflow_minor) ? `−${money(day.outflow_minor)}` : "Unavailable"}</span><strong>${displayMinor(day.closing_cash_minor)}</strong></div>`).join("")}</div>`;
}

function renderOverview() {
  const base = projection("base");
  const late = projection("late_collection");
  const recovery = projection("approved_recovery");
  const business = selectedBusiness();
  const opening = business.opening_cash_minor ?? base.opening_cash_minor;
  const reserve = base.reserve_floor_minor ?? state.dashboard?.policy?.reserve_floor_minor;
  const deferredBills = Object.entries(state.dashboard?.sandbox_state?.rescheduled_bills || {});
  const current = deferredBills.length ? recovery : base;
  const shortfall = reserveShortfall(current);
  const shortfallNote = !hasValue(shortfall) ? "Projection unavailable" : Number(shortfall) > 0 ? `First shortfall ${dateLabel(current.first_shortfall_date)}` : "Reserve covered on every projected day";
  const evidence = state.dashboard?.evidence_summary || {};
  const policy = state.dashboard?.policy || {};
  const deferredCount = deferredBills.length;
  const deferredDetail = deferredBills.map(([billId, item]) => `${item.payee || billId}: ${displayMinor(item.amount_minor)} deferred to ${dateLabel(item.reschedule_to)}`).join(" · ");
  const recoveryNote = deferredCount ? `<div class="recovery-compare-note"><strong>Accepted recovery schedule active</strong><span>Baseline remains the original scheduled projection. Approved recovery includes ${deferredCount} accepted supplier deferral${deferredCount === 1 ? "" : "s"}; the later supplier burden remains visible: ${escapeHtml(deferredDetail)}.</span></div>` : "";
  return `<div class="overview-context"><div><span class="eyebrow">BUSINESS CASH POSITION</span><h2>${escapeHtml(business.name || selectedBusinessName())}</h2><p>Opening date ${escapeHtml(dateLabel(business.opening_date))} · Target date ${escapeHtml(dateLabel(state.targetDate))} · ${escapeHtml(policy.version || "policy configured")}</p></div><div class="context-badges"><span class="status-pill neutral">${icon("shield")}${state.config?.synthetic_only ? "Synthetic sandbox" : "Local workspace"}</span><span class="status-pill warning">${escapeHtml(evidence.source_reference_count ?? projectionSources(base).length)} source-linked records</span></div></div>
    <div class="metrics-grid">${metricCard("Opening cash", money(opening), "Business opening position", "opening")}${metricCard("Base closing cash", money(base.closing_cash_minor), "Original scheduled baseline", hasValue(base.closing_cash_minor) && Number(base.closing_cash_minor) < 0 ? "negative-card" : "")}${metricCard("Reserve floor", money(reserve), "Policy minimum to protect", "reserve")}${metricCard(deferredCount ? "Current reserve shortfall" : "Reserve shortfall", money(shortfall), shortfallNote, hasValue(shortfall) ? Number(shortfall) > 0 ? "negative-card" : "positive-card" : "")}</div>
    <div class="overview-grid"><section class="card projection-card"><div class="section-header"><div><span class="eyebrow">SCHEDULED PROJECTION</span><h3>Timeline and scenario comparison</h3><p>Shortfalls use the lowest cash balance across the selected date range, including accepted recovery schedules.</p></div><button class="text-button" data-view="plans">Compare recovery plans ${icon("arrow")}</button></div>${recoveryNote}<div class="scenario-grid">${scenarioCard("Base", base, "base")}${scenarioCard("Late collection", late, "late")}${scenarioCard("Approved recovery", recovery, "recovery")}</div>${renderTimeline()}<p class="disclaimer-line">${icon("alert")} Recorded projections, not a bank balance. The timeline shows the original baseline; a reminder never becomes a collection.</p></section>
    <section class="card source-card"><div class="section-header"><div><span class="eyebrow">TRACEABLE INPUTS</span><h3>Source-linked records</h3><p>Open a record or the business context to inspect each input.</p></div>${icon("link")}</div><div class="source-list">${renderSourceRows()}</div><div class="card-footer-note">${escapeHtml(evidence.audit_entries ?? 0)} audit entries · ${escapeHtml(state.dashboard?.sandbox_state?.state_hash || "sandbox state tracked locally")}</div></section></div>
    <section class="overview-note"><span class="note-icon">${icon("shield")}</span><div><strong>Approval-gated SME recovery</strong><p>Probaho can read records and propose scenarios. Only an approved action can change the synthetic sandbox state; no real-money account is connected.</p></div></section>
    <section class="card policy-card"><div class="section-header"><div><span class="eyebrow">POLICY CONTROL</span><h3>Reserve and action limits</h3><p>Editing policy invalidates pending approvals and comparisons when the change is accepted.</p></div><span class="status-pill neutral">${escapeHtml(policy.version || "Policy")}</span></div><form id="policy-form" class="policy-form"><label for="policy-reserve-floor">Reserve floor (BDT)<input id="policy-reserve-floor" name="reserve_floor" aria-label="Reserve floor BDT" inputmode="decimal" value="${escapeHtml(minorInput(policy.reserve_floor_minor))}" required></label><label for="policy-action-limit">Action limit (BDT)<input id="policy-action-limit" name="action_limit" aria-label="Action limit BDT" inputmode="decimal" value="${escapeHtml(minorInput(policy.action_limit_minor))}" required></label><label class="policy-check"><input name="payroll_priority" type="checkbox" checked disabled>Protect payroll priority (required)</label><button class="button primary" type="submit" ${mutationDisabled()}>${icon("check")}Save policy</button><div id="policy-error" class="dialog-error" role="alert">${escapeHtml(state.policyError)}</div></form></section>`;
}

function recordTable(rows) {
  if (!rows.length) return `<div class="empty-state"><strong>No matching records.</strong><p>Try another search or filter, then import a combined CSV if the ledger is empty.</p></div>`;
  return `<div class="table-scroll"><table><thead><tr><th>Record</th><th>Type</th><th>Status</th><th>Date / due</th><th>Amount</th><th>Source</th></tr></thead><tbody>${rows.map((record) => `<tr><td><div class="record-cell"><span class="record-icon">${icon(record.recordType === "invoice" ? "link" : record.recordType === "bill" ? "plan" : "records")}</span><div><strong title="${escapeHtml(record.description)}">${escapeHtml(record.description)}</strong>${record.party ? `<small>${escapeHtml(record.party)}</small>` : `<small>${escapeHtml(record.id || "record")}</small>`}</div></div></td><td><span class="type-pill">${escapeHtml(record.typeLabel)}</span><small class="subtype">${escapeHtml(record.type || "—")}</small></td><td><span class="status-pill ${escapeHtml(record.status)}">${escapeHtml(record.status)}</span></td><td>${escapeHtml(shortDate(record.date))}</td><td class="amount-cell ${record.type === "income" ? "positive" : record.type === "expense" ? "negative" : ""}">${record.type === "income" ? "+" : record.type === "expense" ? "−" : ""}${money(record.amount_minor)}</td><td><span class="source-label ${record.synthetic ? "synthetic-source" : "local-source"}">${record.synthetic ? "Synthetic demo" : "Local / imported"}</span></td></tr>`).join("")}</tbody></table></div><div class="table-meta">Showing ${rows.length} of ${recordRows().length} records · BDT only · descriptions are treated as data</div>`;
}

function renderRecords() {
  const rows = filteredRecordRows();
  const all = recordRows();
  return `<div class="records-toolbar"><div class="toolbar-left"><label class="search-box">${icon("search")}<span class="sr-only">Search records</span><input id="record-search" type="search" aria-label="Search records" placeholder="Search records, parties, or IDs" value="${escapeHtml(state.recordQuery)}"></label><label class="select-field"><span class="sr-only">Record type</span><select id="record-type-filter" aria-label="Record type"><option value="">All record types</option><option value="transaction" ${state.recordType === "transaction" ? "selected" : ""}>Transactions</option><option value="invoice" ${state.recordType === "invoice" ? "selected" : ""}>Invoices</option><option value="bill" ${state.recordType === "bill" ? "selected" : ""}>Bills</option></select></label><label class="select-field"><span class="sr-only">Record status</span><select id="record-status-filter" aria-label="Record status"><option value="">All statuses</option>${["income", "expense", "confirmed", "overdue", "open", "scheduled", "paid", "rescheduled", "cancelled"].map((status) => `<option value="${status}" ${state.recordStatus === status ? "selected" : ""}>${escapeHtml(status)}</option>`).join("")}</select></label></div><div class="toolbar-right"><button class="button secondary" data-action="export-records">${icon("download")}Export transactions CSV</button><button class="button primary" data-action="import">${icon("upload")}Import combined CSV</button></div></div><section class="card records-card"><div class="section-header"><div><span class="eyebrow">BUSINESS LEDGER</span><h3>Transactions, invoices, and bills</h3><p>Each description is rendered as escaped record data. Imports are validated atomically before write.</p></div><span class="count-badge">${all.length} total</span></div><div id="record-results">${recordTable(rows)}</div></section>`;
}

function updateRecordResults() {
  const element = $("#record-results");
  if (element) element.innerHTML = recordTable(filteredRecordRows());
}

function planProjectedClosing(plan) {
  return plan.projected_closing_cash_minor ?? plan.projected?.closing_cash_minor ?? plan.projected?.projected_closing_cash_minor;
}

function planProjectedShortfall(plan) {
  return plan.projected_minimum_reserve_shortfall_minor ?? plan.projected_reserve_shortfall_minor ?? plan.projected?.minimum_reserve_shortfall_minor ?? plan.projected?.cash_gap_minor ?? plan.projected?.reserve_shortfall_minor;
}

function planActionText(plan) {
  return plan.action?.label || plan.action?.type || plan.title || plan.kind;
}

function planCard(plan, planId) {
  const mock = plan.labelled_mock || plan.mock || plan.kind === "mock_financing";
  const executable = plan.executable !== false && !mock;
  const feasible = plan.feasible !== false;
  const projectedClosing = planProjectedClosing(plan);
  const actionId = plan.action_id;
  const reminder = String(plan.kind).toLowerCase().includes("reminder");
  let actionControl = "";
  if (mock) actionControl = `<button class="button secondary" disabled aria-label="Non-executable mock financing">Non-executable mock financing</button>`;
  else if (!executable || !feasible) actionControl = `<button class="button secondary" disabled>${escapeHtml(feasible ? "Not executable" : "Not feasible")}</button>`;
  else if (state.pendingApproval?.action_id === actionId && state.pendingApproval?.plan_id === activePlanId()) actionControl = `<button class="button secondary" disabled>Approval recorded</button>`;
  else if (state.planComparison?.status === "approved" && state.planComparison?.plan_id === activePlanId()) actionControl = `<button class="button secondary" disabled>Approval recorded</button>`;
  else if (!planId) actionControl = `<button class="button primary" data-action="compare-plans">Compare before approval</button>`;
  else actionControl = `<button class="button primary" data-action="approve-plan" data-action-id="${escapeHtml(actionId)}">${icon("check")}Approve plan</button>`;
  const mockNotice = mock ? `<div class="mock-notice">${icon("alert")}Illustrative only. No lender, credit decision, or money movement is connected.</div>` : "";
  const effectLabel = mock ? "Illustrative financing amount" : "Projected relief (not cash received)";
  const reminderNotice = reminder ? `<div class="reminder-notice">${icon("alert")}Reminder draft only — it does not collect cash. Projected relief (not cash received): ${displayMinor(plan.cash_effect_minor)}.</div>` : "";
  const risks = plan.risks.length ? `<ul class="risk-list">${plan.risks.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")}</ul>` : "";
  const action = plan.action || {};
  const detailRows = [["Payee / customer", action.payee || action.customer], ["Record", action.bill_id || action.invoice_id], ["Amount", action.amount_minor], ["Currency", action.currency], ["Original due", action.original_due_date || action.original_expected_collection_date], ["Deferred due", action.reschedule_to || action.new_due_date], ["Target", action.date || state.targetDate]].filter(([, value]) => value !== undefined && value !== null && value !== "");
  const structuredReview = detailRows.length ? `<div class="plan-review-grid">${detailRows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(label === "Amount" ? money(value) : String(value))}</strong></div>`).join("")}</div>` : "";
  const financingDetails = mock ? `<div class="financing-details"><span>Principal <b>${displayMinor(plan.principal_minor ?? plan.amount_minor)}</b></span><span>Fee <b>${displayMinor(plan.fee_minor)}</b></span><span>Repayment <b>${displayMinor(plan.repayment_minor ?? plan.assumptions?.repayment)}</b></span><span>Term <b>${escapeHtml(plan.term || "Unavailable")}</b></span><span>Eligibility <b>${escapeHtml(plan.assumptions?.eligibility || "Illustrative only")}</b></span></div>` : "";
  return `<article class="plan-card ${mock ? "mock-plan" : ""}"><div class="plan-card-head"><div><span class="plan-kind">${escapeHtml(String(plan.kind).replaceAll("_", " "))}</span><h3>${escapeHtml(plan.title)}</h3></div><span class="feasibility ${feasible ? "feasible" : "blocked"}">${feasible ? "Feasible scenario" : "Constraint not met"}</span></div><p class="plan-assumption"><strong>Assumption</strong> ${escapeHtml(plan.assumption)}</p>${structuredReview}<div class="plan-facts"><div><span>Action</span><strong>${escapeHtml(planActionText(plan))}</strong></div><div><span>Projected closing</span><strong>${projectedClosing === undefined ? "Unavailable" : money(projectedClosing)}</strong></div><div><span>${effectLabel}</span><strong>${displayMinor(plan.cash_effect_minor)}</strong></div><div><span>Projected minimum cash</span><strong>${displayMinor(plan.projected_minimum_cash_minor ?? plan.projected?.minimum_cash_minor)}</strong></div><div><span>Worst reserve shortfall</span><strong>${displayMinor(planProjectedShortfall(plan))}</strong></div></div>${financingDetails}${risks}${mockNotice}${reminderNotice}<div class="plan-card-footer">${actionControl}</div></article>`;
}

function findPlan(actionId) {
  return planList().find((plan) => plan.action_id === actionId);
}

function approvalAction() {
  return state.pendingApproval?.action && typeof state.pendingApproval.action === "object" ? state.pendingApproval.action : findPlan(state.pendingApproval?.action_id)?.action || {};
}

function isSupplierAction(action) {
  return ["supplier_reschedule", "reschedule"].includes(action?.type || action?.action_type);
}

function matchingConsent() {
  const approval = state.pendingApproval;
  const consents = Array.isArray(state.dashboard?.supplier_consents) ? state.dashboard.supplier_consents : [];
  const matches = consents.filter((item) => item.business_id === state.businessId && item.plan_id === approval?.plan_id && item.action_id === approval?.action_id);
  return matches.length ? matches[matches.length - 1] : null;
}

function approvalPanel() {
  if (state.execution) return executionPanel(state.execution);
  if (!state.pendingApproval) {
    if (!state.uncertainExecution) return "";
    return `<section class="execution-panel pending-panel uncertain-only"><div class="execution-head"><div><span class="eyebrow">EXECUTION STATUS CHECK</span><h3>Previous request needs confirmation</h3><p>No automatic retry was made. The original request for approval <code>${escapeHtml(state.uncertainExecution.approvalId || "—")}</code> may have reached the sandbox.</p></div><span class="status-pill warning">Uncertain</span></div><div class="uncertain-box is-uncertain" role="status"><strong>Check the idempotent receipt before taking any further action.</strong><span>Context: ${escapeHtml(state.uncertainExecution.context?.businessId || "—")} · ${escapeHtml(dateLabel(state.uncertainExecution.context?.targetDate))}</span><button class="button secondary" data-action="check-execution-status" ${mutationDisabled()}>Check execution status</button></div></section>`;
  }
  const action = approvalAction();
  const actionText = action.label || action.title || action.type || state.pendingApproval.action_id;
  const supplier = isSupplierAction(action);
  const consent = supplier ? matchingConsent() : null;
  const accepted = !supplier || consent?.status === "accepted";
  const consentBlock = supplier ? `<div class="consent-box ${consent?.status || "missing"}"><div><strong>Supplier consent simulation</strong><p>Operator simulation only — this is <b>not genuine supplier acceptance</b> and does not contact the supplier.</p></div><span class="status-pill ${consent?.status === "accepted" ? "approved" : consent?.status === "rejected" || consent?.status === "revoked" ? "warning" : "neutral"}">${escapeHtml(consent?.status || "awaiting consent")}</span><div class="consent-actions"><button class="button secondary" data-action="simulate-consent" data-accepted="true" ${mutationDisabled()}>Simulate supplier acceptance</button><button class="button secondary" data-action="simulate-consent" data-accepted="false" ${mutationDisabled()}>Simulate supplier rejection</button></div></div>` : "";
  const reviewRows = [["Payee / customer", action.payee || action.customer], ["Bill / invoice", action.bill_id || action.invoice_id], ["Amount", action.amount_minor], ["Currency", action.currency], ["Original due", action.original_due_date || action.original_expected_collection_date], ["Deferred due", action.reschedule_to || action.new_due_date], ["Target", action.date || state.pendingApproval.target_date]].filter(([, value]) => value !== undefined && value !== null && value !== "");
  const review = `<div class="approval-review-grid">${reviewRows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(label === "Amount" ? money(value) : String(value))}</strong></div>`).join("")}</div>`;
  const executionWarning = supplier && !accepted ? "Accept the simulated supplier consent before executing." : "Execution changes only the local synthetic sandbox.";
  const statusCheck = `<div class="uncertain-box ${state.uncertainExecution ? "is-uncertain" : ""}" role="status">${state.uncertainExecution ? "<strong>Execution status is uncertain.</strong><span>No automatic retry was made. Check the server receipt first.</span>" : "<span>Already attempted this action? Check its idempotent receipt without executing again.</span>"}<button class="button secondary" data-action="check-execution-status" ${mutationDisabled()}>Check execution status</button></div>`;
  return `<section class="execution-panel pending-panel"><div class="execution-head"><div><span class="eyebrow">HUMAN APPROVAL RECORDED</span><h3>Execution panel</h3><p>${escapeHtml(actionText)} is approved for the synthetic sandbox only.</p></div><span class="status-pill approved">${icon("check")}Approved</span></div>${review}<div class="approval-facts"><div><span>Approval ID</span><strong>${escapeHtml(state.pendingApproval.approval_id || "—")}</strong></div><div><span>Expires</span><strong>${escapeHtml(state.pendingApproval.expires_at ? dateTimeLabel(state.pendingApproval.expires_at) : "Server-managed expiry")}</strong></div><div><span>Permission</span><strong>${escapeHtml(state.pendingApproval.permission || "human_approval")}</strong></div></div>${consentBlock}${statusCheck}<p class="execution-boundary">${escapeHtml(executionWarning)} Confirm the approved action before continuing.</p><div class="execution-actions"><button class="button primary" data-action="execute-approved" ${!accepted || mutationDisabled() || state.uncertainExecution ? "disabled" : ""}>${icon("arrow")}Execute approved action</button><button class="button secondary" data-action="cancel-approval" ${mutationDisabled()}>Cancel approval</button></div></section>`;
}

function executionPanel(result) {
  const receipt = result.receipt && typeof result.receipt === "object" ? result.receipt : result;
  const reminder = String(result.action_type || receipt.action_type || "").toLowerCase().includes("reminder");
  const before = result.state_before || receipt.state_before || {};
  const after = result.state_after || receipt.state_after || {};
  const readBack = result.read_back || receipt.read_back || null;
  const recordedAfter = readBack?.recorded_after_state || {};
  const currentSandbox = state.dashboard?.sandbox_state || {};
  const currentStateHash = state.dashboard?.evidence_summary?.state_hash || state.dashboard?.sandbox_state?.state_hash;
  const recordedStateHash = recordedAfter.state_hash || after.state_hash;
  const mismatch = Boolean(readBack && currentStateHash && recordedStateHash && currentStateHash !== recordedStateHash);
  const verified = readBack?.verified === true;
  const verificationFailure = readBack?.verified === false || mismatch;
  const readBackTitle = !readBack ? "Atomic read-back unavailable" : verificationFailure ? "Atomic read-back needs review" : "Atomic read-back verified";
  const readBackSource = readBack?.source || "Unavailable";
  const receiptId = result.execution_id || receipt.execution_id || receipt.receipt_id || "—";
  return `<section class="execution-panel result-panel"><div class="execution-head"><div><span class="eyebrow">SANDBOX EXECUTION RESULT</span><h3>Receipt recorded</h3><p>${reminder ? "Reminder draft recorded; no receivable was collected and cash effect remains BDT 0." : "Execution is complete in the local synthetic sandbox. No real-money movement occurred."}</p></div><span class="status-pill approved">${icon("check")}${escapeHtml(result.status || receipt.status || "Recorded")}</span></div><div class="receipt-grid"><div><span>Receipt</span><strong>${escapeHtml(receiptId)}</strong></div><div><span>Permission</span><strong>${escapeHtml(result.permission || receipt.permission || "sandbox_execute")}</strong></div><div><span>Cash effect</span><strong>${displayMinor(result.cash_effect_minor ?? receipt.cash_effect_minor)}</strong></div></div><div class="state-compare"><div><span>Before state</span><strong>${displayMinor(before.cash_minor ?? before.balance_minor)}</strong><small>version ${escapeHtml(before.version ?? "Unavailable")}</small></div><div class="state-arrow">${icon("arrow")}</div><div><span>Recorded after state</span><strong>${displayMinor(recordedAfter.cash_minor ?? recordedAfter.balance_minor ?? after.cash_minor ?? after.balance_minor)}</strong><small>version ${escapeHtml(recordedAfter.version ?? after.version ?? "Unavailable")}</small></div></div><div class="projection-receipt-grid"><div><span>Projection before</span><pre>${jsonText(result.projection_before || receipt.projection_before || null)}</pre></div><div><span>Projection after</span><pre>${jsonText(result.projection_after || receipt.projection_after || null)}</pre></div></div><div class="current-state-note"><span class="eyebrow">CURRENT DASHBOARD STATE</span><strong>Actual post-commit dashboard state</strong><small>Current cash ${displayMinor(currentSandbox.cash_minor ?? currentSandbox.balance_minor)} · version ${escapeHtml(currentSandbox.version ?? "Unavailable")} · hash ${escapeHtml(currentStateHash || "Unavailable")}</small></div><div class="read-back ${verificationFailure ? "read-back-warning" : ""}"><div><span class="eyebrow">READ-BACK</span><strong>${escapeHtml(readBackTitle)}</strong></div><div class="read-back-facts"><span>Source <b>${escapeHtml(readBackSource)}</b></span><span>Verified <b>${readBack?.verified === true ? "Yes" : readBack?.verified === false ? "No" : "Unavailable"}</b></span>${mismatch ? "<span>Current dashboard state <b>Differs from recorded state</b></span>" : ""}</div><p class="read-back-context">The receipt preserves recorded_after_state from the atomic mutation; the current dashboard state is shown separately above.</p><pre>${jsonText(recordedAfter || readBack)}</pre></div><details class="receipt-details"><summary>View receipt JSON</summary><pre>${jsonText(receipt)}</pre></details></section>`;
}

function renderPlans() {
  const payload = planSourcePayload();
  const plans = planList();
  const planId = activePlanId();
  const approvalPlan = comparisonPlanId();
  const base = projection("base");
  const recovery = projection("approved_recovery");
  const accepted = Object.keys(state.dashboard?.sandbox_state?.rescheduled_bills || {}).length > 0;
  const gap = reserveShortfall(accepted ? recovery : base);
  const gapLabel = accepted ? "Current accepted gap" : "Current gap";
  return `<div class="plans-intro card"><div><span class="eyebrow">RECOVERY DECISION</span><h2>Compare before anything can execute</h2><p>Plans use the selected records and policy. Probaho proposes; a human approves; only the local sandbox can execute.</p></div><div class="intro-actions"><span class="gap-callout">${gapLabel} <strong>${displayMinor(gap)}</strong></span><button class="button primary" data-action="compare-plans" ${mutationDisabled()}>${icon("refresh")}Compare recovery plans</button></div></div>${state.planError ? `<div class="inline-error" role="alert">${escapeHtml(state.planError)}</div>` : ""}<section class="plans-grid">${plans.length ? plans.map((plan) => planCard(plan, approvalPlan)).join("") : `<div class="empty-state card"><strong>No plan comparison yet.</strong><p>Run a comparison to create a hash-linked proposal for this business and target date.</p><button class="button primary" data-action="compare-plans" ${mutationDisabled()}>Compare recovery plans</button></div>`}</section>${planId ? `<p class="plan-hash">Comparison or approved proposal <code>${escapeHtml(planId)}</code> · Plans are deterministic and linked to the selected ledger.</p>` : ""}${approvalPanel()}<section class="card plan-boundaries"><div><span class="eyebrow">BOUNDARIES</span><h3>What the action labels mean</h3></div><div class="boundary-grid"><p><strong>Collection reminder</strong><br>A reminder is a draft and never counts as collected cash.</p><p><strong>Supplier reschedule</strong><br>Requires supplier consent and changes only the synthetic schedule after approval.</p><p><strong>Mock financing</strong><br>Illustrative comparison only and always non-executable.</p></div></section>`;
}

function renderMessage(message) {
  const label = message.role === "user" ? "You" : message.mode === "provider_error" ? "AI connection issue" : message.mode === "openai" || message.mode === "ai" ? "AI" : "Local demo";
  const trace = (message.trace || []).map((item) => `<span class="trace-chip">${icon("check")}${escapeHtml(item.tool || item.name || "read operation")}${item.receipt ? ` · #${escapeHtml(item.receipt)}` : ""}</span>`).join("");
  const proposalNote = message.role === "assistant" && message.actions?.length ? `<div class="proposal-note">Suggested action information is proposal-only. The assistant cannot approve or execute.</div>` : "";
  return `<div class="message ${message.role} ${message.mode === "provider_error" ? "error" : ""}"><span class="message-avatar">${message.role === "user" ? "YOU" : icon("spark")}</span><div><div class="message-body">${escapeHtml(message.content)}${trace ? `<div class="trace-list">${trace}</div>` : ""}${proposalNote}</div><span class="message-label">${label}</span></div></div>`;
}

function scrollChat() {
  const messages = $("#chat-messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function renderAssistant() {
  if (!state.messages.length) state.messages = [initialAssistantMessage()];
  const prompts = ["What is the cash gap?", "Compare recovery plans", "Explain this projection"];
  const consent = state.config?.ai_configured ? `<label class="chat-consent"><input id="ai-consent" type="checkbox" ${state.consent ? "checked" : ""}>Use AI for this message. If enabled, share this current conversation plus redacted tool output with OpenAI. Raw ledger descriptions stay local.</label>` : `<p class="offline-note">Offline mode · Local demo answers use deterministic records and rules. AI consent is unavailable until an AI provider is configured.</p>`;
  return `<div class="assistant-layout"><section class="card chat-card"><div class="chat-header"><div class="assistant-identity"><span class="assistant-avatar">${icon("spark")}</span><div><strong>Probaho Assistant</strong><span>${state.config?.ai_configured ? "AI available with per-message consent" : "Offline mode · Local demo"}</span></div></div><span class="assistant-badge">READ + PROPOSE</span></div><div class="chat-messages" id="chat-messages">${state.messages.map(renderMessage).join("")}${state.busy ? `<div class="thinking">Reviewing the business records…</div>` : ""}</div><form id="chat-form" class="chat-composer"><div class="chat-input-row"><label for="chat-input" class="sr-only">Message Probaho Assistant</label><textarea id="chat-input" name="message" rows="1" maxlength="3000" placeholder="Ask about the cash gap…" required ${state.busy ? "disabled" : ""}></textarea><button class="button primary" type="submit" aria-label="Send message" ${state.busy ? "disabled" : ""}>${icon("arrow")}</button></div>${consent}</form></section><aside class="assistant-info"><section class="card"><span class="eyebrow">SUGGESTED PROMPTS</span><h3>Start with the current gap</h3>${prompts.map((prompt) => `<button class="prompt-button" data-action="prompt" data-prompt="${escapeHtml(prompt)}">${escapeHtml(prompt)}${icon("arrow")}</button>`).join("")}</section><section class="card boundaries-card"><span class="eyebrow">ASSISTANT BOUNDARIES</span><h3>Explainable and approval-gated</h3><div class="permission-item">${icon("check")}Reads business-scoped records</div><div class="permission-item">${icon("check")}Explains projections and assumptions</div><div class="permission-item">${icon("check")}Can suggest recovery plans</div><div class="permission-item blocked">${icon("shield")}Cannot approve or execute actions</div></section></aside></div>`;
}

async function sendMessage(message) {
  const text = String(message || "").trim();
  if (state.busy || !text) return;
  const context = contextSnapshot();
  const history = state.messages.filter((item) => item.mode !== "intro" && (item.role === "user" || item.role === "assistant")).slice(-8).map((item) => ({role: item.role, content: item.content}));
  state.messages.push({role: "user", content: text});
  const mutation = beginMutation("Reviewing business records", context);
  try {
    const result = await api("/api/chat", {
      business_id: context.businessId,
      target_date: context.targetDate,
      message: text,
      history,
      external_consent: Boolean(state.config?.ai_configured && state.consent)
    });
    invalidateAudit("assistant response recorded local evidence");
    if (contextMatches(context)) {
      const actions = Array.isArray(result.actions) ? result.actions : [];
      const persistedComparison = actions.some((item) => item?.type === "plan_comparison");
      if (persistedComparison) {
        state.planComparison = null;
        state.pendingApproval = null;
        state.execution = null;
        state.pendingContext = null;
        await refreshDashboard(false, context);
      }
      state.messages.push({role: "assistant", content: result.text || "No assistant text was returned.", mode: result.mode || "local_demo", trace: result.trace || [], actions});
    }
  } catch (error) {
    invalidateAudit("assistant response recorded an error receipt");
    if (contextMatches(context)) state.messages.push({role: "assistant", mode: "provider_error", content: error.message});
  } finally {
    resetPerMessageConsent();
    endMutation(mutation);
    $("#chat-input")?.focus();
  }
}

function activitySummary(entry) {
  const details = entry?.details && typeof entry.details === "object" ? entry.details : {};
  if (entry?.action === "plan.compare") return `Proposal ${details.plan_id || "recorded"} · ${Array.isArray(details.actions) ? details.actions.length : "?"} options`;
  if (entry?.action === "plan.approve") return `Approval ${details.approval_id || "recorded"} · ${details.action_id || "action unavailable"}`;
  if (entry?.action === "plan.execute") return `Receipt ${details.execution_id || "recorded"} · ${details.action?.type || details.action_type || "sandbox action"}`;
  if (entry?.action === "supplier.consent") return `${details.accepted ? "Accepted" : "Rejected"} simulated supplier consent · ${details.action_id || "action unavailable"}`;
  if (entry?.action === "ledger.import") return `${details.total_added ?? "?"} records imported · ${details.source || "local file"}`;
  if (entry?.action === "agent.tool") return `${details.tool || "Read/propose tool"} · scoped to ${details.business_id || "business"}`;
  if (entry?.action === "agent.answer") return `${details.mode || "Assistant"} response · ${details.tools_used ?? 0} tool calls`;
  if (entry?.action === "policy.update") return `Policy ${details.version || "updated"} · reserve/action limits changed`;
  if (entry?.action === "sandbox.reset") return "Synthetic schedule reset; records and receipts preserved";
  if (typeof entry?.details === "string") return entry.details.slice(0, 180);
  return entry?.action || "Recorded operation";
}

function renderActivity() {
  if (!state.audit) return `<div class="loading-state">Loading activity and evidence…</div>`;
  const entries = Array.isArray(state.audit.entries) ? [...state.audit.entries].reverse() : [];
  const tiers = Array.isArray(state.config?.permission_tiers) ? state.config.permission_tiers : [];
  const valid = Boolean(state.audit.hash_chain_valid);
  return `<div class="evidence-summary"><div class="hash-status ${valid ? "valid" : "invalid"}">${icon(valid ? "shield" : "alert")}<div><strong>${valid ? "Hash-chain status: consistent" : "Hash-chain status: needs review"}</strong><p>${escapeHtml(state.audit.environment || "Local synthetic sandbox")} · ${entries.length} entries shown for this business</p></div></div><div class="activity-actions"><button class="button secondary" data-action="refresh-activity">${icon("refresh")}Refresh</button><button class="button secondary" data-action="export-results">${icon("download")}Export results</button><button class="button primary" data-action="export-evidence">${icon("download")}Export evidence</button></div></div><div class="activity-grid"><section class="card audit-card"><div class="section-header"><div><span class="eyebrow">AUDIT TRAIL</span><h3>What happened, and how</h3><p>Receipts are recorded with permission tiers and chained hashes. Expand a row for full receipt details.</p></div></div>${entries.length ? `<div class="table-scroll"><table><thead><tr><th>Receipt</th><th>Operation</th><th>Permission</th><th>Time</th><th>Summary</th></tr></thead><tbody>${entries.slice(0, 100).map((entry) => `<tr><td>#${escapeHtml(entry.id)}</td><td><strong>${escapeHtml(entry.action)}</strong><small class="hash">${escapeHtml(String(entry.entry_hash || "").slice(0, 16))}…</small></td><td><span class="type-pill">${escapeHtml(entry.permission)}</span></td><td>${escapeHtml(entry.timestamp ? new Date(entry.timestamp).toLocaleString("en-GB", {timeZone: "Asia/Dhaka", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit"}) : "—")}</td><td class="audit-summary"><details><summary>${escapeHtml(activitySummary(entry))}</summary><pre>${jsonText(entry.details)}</pre></details></td></tr>`).join("")}</tbody></table></div>` : `<div class="empty-state"><strong>No activity yet.</strong><p>Compare a plan or import a record to create a local receipt.</p></div>`}<div class="table-meta">Synthetic local evidence verifies internal hash-chain consistency; it is not third-party certification.</div></section><aside class="card permission-card"><span class="eyebrow">PERMISSION MODEL</span><h3>Permission tiers</h3><p class="muted">Every operation is attributed to one of these boundaries.</p><div class="tier-list">${tiers.map((tier, index) => `<div class="tier-row"><span>${index + 1}</span><div><strong>${escapeHtml(tier)}</strong><small>${tier === "human_approval" ? "Required before action approval" : tier === "sandbox_execute" ? "Synthetic state only" : tier === "agent_read" ? "Read-only records" : "Proposal generation"}</small></div></div>`).join("")}</div><div class="evidence-note">${icon("shield")}<span>${escapeHtml(state.audit.note || "Evidence is local to this synthetic demo.")}</span></div></aside></div>`;
}

function downloadText(filename, text, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportUrl(kind) {
  return `/api/export?kind=${encodeURIComponent(kind)}&business_id=${encodeURIComponent(state.businessId)}`;
}

function sampleCsv() {
  const businessId = state.businessId || "business-id";
  return `record_type,business_id,id,date,description,amount,type,currency,due_date,status,customer,payee,issue_date,expected_collection_date,priority,reschedule_allowed\ntransaction,${businessId},txn-example-001,2026-10-05,Client service receipt,25000,income,BDT,,,,,,,,\ninvoice,${businessId},inv-example-001,2026-10-01,Service receivable,35000,,BDT,2026-10-31,confirmed,Nila Traders,,2026-10-01,2026-10-31,,\nbill,${businessId},bill-example-001,,Supplier materials,12000,,BDT,2026-10-28,open,,,,,high,true\n`;
}

function csvPreviewRows(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') { cell += '"'; index += 1; }
      else quoted = !quoted;
    } else if (character === "," && !quoted) {
      row.push(cell); cell = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(cell); cell = "";
      if (row.some((value) => value.trim() !== "")) rows.push(row);
      row = [];
    } else cell += character;
  }
  if (cell || row.length) { row.push(cell); if (row.some((value) => value.trim() !== "")) rows.push(row); }
  return rows;
}

function validateCombinedCsv(text) {
  if (!text.trim()) throw new Error("The CSV is empty.");
  const rows = csvPreviewRows(text);
  if (rows.length < 2) throw new Error("CSV must contain a header row and at least one data row.");
  const headers = rows[0].map((header) => header.replace(/^\ufeff/, "").trim().toLowerCase());
  if (new Set(headers).size !== headers.length) throw new Error("CSV headers must be unique.");
  const typeIndex = headers.indexOf("record_type");
  if (typeIndex === -1) throw new Error("Combined Probaho CSV requires a record_type column.");
  const counts = {transaction: 0, invoice: 0, bill: 0};
  rows.slice(1).forEach((row, index) => {
    const kind = String(row[typeIndex] || "").trim().toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(counts, kind)) throw new Error(`Row ${index + 2}: record_type must be transaction, invoice or bill.`);
    counts[kind] += 1;
  });
  return {rows: rows.length - 1, counts};
}

async function comparePlans() {
  const context = contextSnapshot();
  const mutation = beginMutation("Comparing recovery plans", context);
  state.planError = "";
  try {
    const result = await api("/api/plan/compare", {business_id: context.businessId, target_date: context.targetDate});
    if (!contextMatches(context)) return;
    state.planComparison = result;
    state.execution = null;
    await refreshDashboard(false, context);
    invalidateAudit("agent comparison created a new proposal");
    toast("Recovery plans compared. Review assumptions before approval.");
  } catch (error) {
    state.planError = error.message;
    toast(error.message);
  } finally {
    endMutation(mutation);
  }
}

async function approvePlan(actionId) {
  const context = contextSnapshot();
  const planId = comparisonPlanId();
  if (!planId) throw new Error("Compare the current recovery plans before approval.");
  const plan = findPlan(actionId);
  if (!plan) throw new Error("That plan is no longer available. Compare again.");
  const mutation = beginMutation("Approving recovery plan", context);
  try {
    const result = await api("/api/plan/approve", {business_id: context.businessId, plan_id: planId, action_id: actionId});
    if (!contextMatches(context)) return;
  state.pendingApproval = {...normaliseApproval(result), action: result.action || plan.action, permission: result.permission || "human_approval"};
  state.pendingContext = context;
  state.execution = null;
  invalidateAudit("plan approval changed activity");
  state.planError = "";
  toast("Plan approved. Review the execution panel before executing.");
  } finally {
    endMutation(mutation);
  }
}

async function executeApproved() {
  if (!state.pendingApproval?.approval_id) throw new Error("No pending approval is available.");
  const context = contextSnapshot();
  const approvalId = state.pendingApproval.approval_id;
  const key = `execute-${approvalId}`;
  const mutation = beginMutation("Executing approved action", context);
  const attempt = {business_id: context.businessId, approval_id: approvalId, idempotency_key: key, targetDate: context.targetDate};
  state.uncertainExecution = {context, approvalId, idempotencyKey: key};
  persistExecutionAttempt(attempt);
  try {
    const result = await api("/api/plan/execute", {business_id: context.businessId, approval_id: approvalId, idempotency_key: key});
    if (!contextMatches(context)) return;
    state.execution = result;
    state.pendingApproval = null;
    state.uncertainExecution = null;
    clearExecutionAttempt(approvalId);
    state.planComparison = null;
    await refreshDashboard(false, context);
    invalidateAudit("execution completed");
    toast("Approved action executed in the synthetic sandbox. Receipt and read-back are shown below.");
  } catch (error) {
    if (error.ambiguous || error.name === "TypeError" || error.name === "AbortError" || /network|fetch|timeout|unreadable|invalid response/i.test(error.message || "")) {
      state.uncertainExecution = {context, approvalId, idempotencyKey: key};
      toast("Execution status is uncertain. Check execution status before retrying.");
      return;
    }
    state.uncertainExecution = null;
    clearExecutionAttempt(approvalId);
    throw error;
  } finally {
    endMutation(mutation);
  }
}

async function checkExecutionStatus() {
  const approvalId = state.uncertainExecution?.approvalId || state.pendingApproval?.approval_id;
  if (!approvalId) throw new Error("No approved action is available for a status check.");
  const context = state.uncertainExecution?.context || contextSnapshot();
  const key = state.uncertainExecution?.idempotencyKey || `execute-${approvalId}`;
  const mutation = beginMutation("Checking execution status", context);
  try {
    const result = await api(`/api/execution?business_id=${encodeURIComponent(context.businessId)}&idempotency_key=${encodeURIComponent(key)}`);
    if (!contextMatches(context)) return;
    if (result.found && result.receipt) {
      state.execution = result.receipt;
      state.pendingApproval = null;
      state.planComparison = null;
      state.uncertainExecution = null;
      clearExecutionAttempt(approvalId);
      await refreshDashboard(false, context);
      invalidateAudit("execution status read-back");
      toast("Execution receipt found. No second execution was attempted.");
    } else {
      state.uncertainExecution = null;
      clearExecutionAttempt(approvalId);
      toast("No execution receipt found. The approved action remains unexecuted; you may review and try once.");
    }
  } finally {
    endMutation(mutation);
  }
}

async function resetSandbox() {
  if (!window.confirm("Reset the synthetic schedule for this business? Ledger records and execution history will be preserved; accepted deferrals and pending approvals will be invalidated.")) return;
  const context = contextSnapshot();
  const mutation = beginMutation("Resetting sandbox schedule", context);
  const unresolvedApproval = state.uncertainExecution?.approvalId;
  try {
    const result = await api("/api/sandbox/reset", {business_id: context.businessId});
    if (!contextMatches(context)) return;
    state.pendingApproval = null;
    state.execution = null;
    state.planComparison = null;
    state.uncertainExecution = null;
    clearExecutionAttempt(unresolvedApproval);
    await refreshDashboard(false, context);
    invalidateAudit("sandbox schedule reset");
    if (state.view === "activity") await loadAudit(false);
    const receipt = result.receipt || result;
    toast(`Sandbox schedule reset only. Ledger and history preserved. Version ${receipt.sandbox_version ?? state.dashboard?.sandbox_state?.version ?? "updated"}.`);
  } finally {
    endMutation(mutation);
  }
}

async function simulateConsent(accepted) {
  if (!state.pendingApproval?.plan_id || !state.pendingApproval?.action_id) throw new Error("The approved action is missing its plan binding.");
  const context = contextSnapshot();
  const mutation = beginMutation(accepted ? "Simulating supplier acceptance" : "Simulating supplier rejection", context);
  try {
    await api("/api/sandbox/consent", {business_id: context.businessId, plan_id: state.pendingApproval.plan_id, action_id: state.pendingApproval.action_id, accepted});
    if (!contextMatches(context)) return;
    await refreshDashboard(false, context);
    invalidateAudit("supplier consent simulation changed activity");
    toast(accepted ? "Supplier acceptance simulated locally; it is not genuine supplier acceptance." : "Supplier rejection simulated locally; execution remains blocked.");
  } finally {
    endMutation(mutation);
  }
}

async function cancelApproval() {
  if (!state.pendingApproval?.approval_id) throw new Error("No pending approval is available.");
  const context = contextSnapshot();
  const mutation = beginMutation("Cancelling approval", context);
  try {
    await api("/api/plan/cancel", {business_id: context.businessId, approval_id: state.pendingApproval.approval_id});
    if (!contextMatches(context)) return;
    state.pendingApproval = null;
    state.planComparison = null;
    invalidateAudit("approval cancelled");
    await refreshDashboard(false, context);
    toast("Approval cancelled. No sandbox action was executed.");
  } finally {
    endMutation(mutation);
  }
}

async function savePolicy(form) {
  const context = contextSnapshot();
  const values = new FormData(form);
  const reserve_floor_minor = parsePaisa(values.get("reserve_floor"), "Reserve floor");
  const action_limit_minor = parsePaisa(values.get("action_limit"), "Action limit");
  const mutation = beginMutation("Saving policy", context);
  state.policyError = "";
  try {
    await api("/api/policy", {business_id: context.businessId, reserve_floor_minor, action_limit_minor, payroll_priority: true});
    if (!contextMatches(context)) return;
    state.planComparison = null;
    state.pendingApproval = null;
    invalidateAudit("policy update invalidated proposal cache");
    await refreshDashboard(false, context);
    toast("Policy saved. Pending approvals and comparisons were invalidated when required.");
  } catch (error) {
    state.policyError = error.message;
    throw error;
  } finally {
    endMutation(mutation);
  }
}

async function previewFile(file) {
  const info = $("#file-info");
  const preview = $("#import-preview");
  if (!file) {
    if (info) info.textContent = "No file selected";
    if (preview) preview.textContent = "No rows validated yet.";
    return;
  }
  if (info) info.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
  try {
    if (file.size > 1500000) throw new Error("The file exceeds the 1.5 MB limit.");
    const text = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    const result = validateCombinedCsv(text);
    if (preview) preview.textContent = `${result.rows} rows validated locally · ${result.counts.transaction} transactions · ${result.counts.invoice} invoices · ${result.counts.bill} bills. Server validation still runs before write.`;
    $("#import-error").textContent = "";
  } catch (error) {
    if (preview) preview.textContent = "Validation did not pass.";
    $("#import-error").textContent = error.message;
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const close = target.closest("[data-close]");
  if (close) {
    document.getElementById(close.dataset.close)?.close();
    return;
  }
  const view = target.closest("[data-view]");
  if (view) {
    try {
      if (view.dataset.recordId) {
        state.recordQuery = view.dataset.recordId;
        state.recordType = "";
      }
      await navigate(view.dataset.view);
    } catch (error) { toast(error.message); }
    return;
  }
  const action = target.closest("[data-action]");
  if (!action) return;
  try {
    switch (action.dataset.action) {
      case "import":
        $("#import-form").reset();
        $("#file-info").textContent = "No file selected";
        $("#import-preview").textContent = "No rows validated yet.";
        $("#import-error").textContent = "";
        $("#import-dialog").showModal();
        break;
      case "sample-csv":
        downloadText("probaho-example-combined.csv", sampleCsv());
        break;
      case "export-records":
        window.location.href = exportUrl("transactions");
        break;
      case "export-evidence":
        window.location.href = exportUrl("evidence");
        break;
      case "export-results":
        window.location.href = exportUrl("results");
        break;
      case "refresh-activity":
        await loadAudit();
        break;
      case "reset-sandbox":
        await resetSandbox();
        break;
      case "compare-plans":
        await comparePlans();
        break;
      case "approve-plan":
        action.disabled = true;
        await approvePlan(action.dataset.actionId);
        action.disabled = false;
        break;
      case "execute-approved":
        await executeApproved();
        break;
      case "check-execution-status":
        await checkExecutionStatus();
        break;
      case "simulate-consent":
        await simulateConsent(action.dataset.accepted === "true");
        break;
      case "cancel-approval":
        await cancelApproval();
        break;
      case "prompt":
        await sendMessage(action.dataset.prompt);
        break;
      default:
        break;
    }
  } catch (error) {
    action.disabled = false;
    if (state.view === "plans") { state.planError = error.message; renderView(); }
    toast(error.message);
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "record-search") {
    state.recordQuery = event.target.value;
    updateRecordResults();
  }
});

document.addEventListener("change", async (event) => {
  try {
    if ((event.target.id === "business-select" || event.target.id === "target-date") && state.busy) {
      event.target.value = event.target.id === "business-select" ? state.businessId : state.targetDate;
      toast(`Please wait for ${state.busyLabel || "the current operation"} to finish before changing workspace context.`);
      return;
    }
    if (event.target.id === "business-select") {
      state.businessId = event.target.value;
      const business = businesses().find((item) => businessIdOf(item) === state.businessId) || {};
      state.targetDate = business.default_target_date || state.config.default_target_date || state.targetDate;
       state.planComparison = null; state.pendingApproval = null; state.execution = null; invalidateAudit("business changed"); state.messages = []; state.uncertainExecution = null;
      state.policyError = "";
      resetPerMessageConsent();
      restoreExecutionAttempt();
      await refreshDashboard(false);
      if (state.view === "activity") await loadAudit(false);
      renderView();
    } else if (event.target.id === "target-date") {
      if (!event.target.value) throw new Error("Choose a target date.");
      const business = selectedBusiness();
      if (business.opening_date && (event.target.value < business.opening_date || event.target.value > isoDatePlus(business.opening_date, 366))) throw new Error(`Target date must be between ${dateLabel(business.opening_date)} and ${dateLabel(isoDatePlus(business.opening_date, 366))}.`);
      state.targetDate = event.target.value;
       state.planComparison = null; state.pendingApproval = null; state.execution = null; invalidateAudit("target date changed"); state.messages = []; state.uncertainExecution = null;
      state.policyError = "";
      resetPerMessageConsent();
      restoreExecutionAttempt();
      await refreshDashboard(false);
      if (state.view === "activity") await loadAudit(false);
      renderView();
    } else if (event.target.id === "record-type-filter") {
      state.recordType = event.target.value;
      updateRecordResults();
    } else if (event.target.id === "record-status-filter") {
      state.recordStatus = event.target.value;
      updateRecordResults();
    } else if (event.target.id === "ai-consent") {
      state.consent = Boolean(event.target.checked);
    } else if (event.target.id === "csv-file") {
      await previewFile(event.target.files?.[0]);
    }
  } catch (error) {
    showError(error);
    toast(error.message);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.target.id === "chat-input" && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    event.target.form.requestSubmit();
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  if (state.busy) return;
  let mutation = null;
  try {
    if (form.id === "chat-form") {
      await sendMessage(new FormData(form).get("message"));
      return;
    }
    if (form.id === "policy-form") {
      await savePolicy(form);
      return;
    }
    if (form.id !== "import-form") return;
    const context = contextSnapshot();
    mutation = beginMutation("Importing records", context);
    const file = $("#csv-file").files?.[0];
    if (!file) throw new Error("Choose a combined CSV file first.");
    if (file.size > 1500000) throw new Error("The file exceeds the 1.5 MB limit.");
    const csv = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    const validation = validateCombinedCsv(csv);
    const submit = form.querySelector("[type=submit]");
    if (submit) submit.disabled = true;
    const result = await api("/api/import", {business_id: context.businessId, csv, replace_demo: Boolean($("#import-replace-demo").checked)});
    if (!contextMatches(context)) return;
    $("#import-dialog").close();
    form.reset();
    state.planComparison = null;
    state.pendingApproval = null;
    resetPerMessageConsent();
    invalidateAudit("record import invalidated proposal and evidence cache");
    await refreshConfig();
    await refreshDashboard(false, context);
    renderView();
    const total = result.total_added ?? Object.values(result.added || {}).reduce((sum, value) => sum + numberValue(value), 0);
    const skipped = result.duplicates_skipped ? Object.values(result.duplicates_skipped).reduce((sum, value) => sum + numberValue(value), 0) : 0;
    toast(`Imported ${total} records from ${validation.rows} validated rows. ${skipped} identical records skipped.`);
  } catch (error) {
    if (form.id === "policy-form") {
      state.policyError = error.message;
      toast(error.message);
      renderView();
      return;
    }
    $("#import-error").textContent = error.message;
  } finally {
    endMutation(mutation);
  }
});

(async function boot() {
  try {
    await refreshConfig();
    await refreshDashboard(false);
    renderView();
  } catch (error) {
    showError(error);
    $("#view-content").innerHTML = `<div class="empty-state card"><strong>Probaho could not load this workspace.</strong><p>${escapeHtml(error.message)} Check that the local Probaho server is running, then refresh.</p></div>`;
  }
}());
