// End-to-end browser check and screenshot capture for Tideway.
//
// Starts its own server on a throwaway database, drives headless Chrome over the
// DevTools protocol (Node 22+ built-in WebSocket, no npm packages), walks the
// full demo story, fails on any page error, and writes PNGs to evidence/screens/.
//
//   node scripts/capture_screens.mjs [--chrome "/path/to/chrome"]
import {spawn, spawnSync} from "node:child_process";
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, dirname} from "node:path";
import {existsSync} from "node:fs";
import {createServer} from "node:http";
import {fileURLToPath} from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
function sourceDigest() {
  const result = spawnSync(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
    ["-c", "from scripts.verify_submission import source_digest; print(source_digest()[0])"], {cwd:ROOT,encoding:"utf8"});
  if (result.status !== 0) throw new Error(`Could not hash browser-tested source: ${result.stderr}`);
  return result.stdout.trim();
}
const initialSourceDigest = sourceDigest();
const option = (name) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : undefined; };
const OUT = option("--out") || join(ROOT, "evidence", "screens");
const PORT = Number(process.env.TIDEWAY_E2E_PORT || 8799), DEBUG_PORT = Number(process.env.TIDEWAY_DEBUG_PORT || 9333);
const CHROME = option("--chrome") || process.env.CHROME || [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find(existsSync) || "google-chrome";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const errors = [];
const testLocalBackend = process.argv.includes("--test-local-backend");
const testRealBackend = process.argv.includes("--test-real-backend");
const testPaymentDelay = process.argv.includes("--test-payment-delay");
if (testLocalBackend && testRealBackend) throw new Error("Choose either --test-local-backend (test double) or --test-real-backend (actual inference).");
if (testRealBackend && (!process.env.TIDEWAY_LOCAL_MODEL_URL || !process.env.TIDEWAY_LOCAL_TEXT_MODEL
    || process.env.TIDEWAY_LOCAL_TEXT_MODEL === "tideway-browser-test"
    || process.env.TIDEWAY_LOCAL_STRUCTURED_PLANS?.trim() !== "1")) {
  throw new Error("--test-real-backend requires an explicitly configured real local model URL, model ID and TIDEWAY_LOCAL_STRUCTURED_PLANS=1.");
}
let realModelVerification = null;
let modelServer;
const modelEnvironment = {};
if (testLocalBackend) {
  // A fixed-output local test double tests browser integration, never model quality.
  modelServer = createServer((request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/v1/models") {
      response.end(JSON.stringify({data: [{id: "tideway-browser-test"}]}));
      return;
    }
    let raw = "";
    request.on("data", chunk => { raw += chunk; });
    request.on("end", () => {
      const message = JSON.parse(raw).messages?.[1]?.content || "";
      const plan = /pay Rahman/i.test(message)
        ? {intent: "pay", calls: [{tool: "execute", args: {}}]}
        : {intent: "cash_check", calls: [{tool: "project_cash", args: {scenario: "likely"}}]};
      response.end(JSON.stringify({choices: [{message: {content: JSON.stringify(plan)}}]}));
    });
  });
  await new Promise(resolve => modelServer.listen(0, "127.0.0.1", resolve));
  Object.assign(modelEnvironment, {TIDEWAY_LOCAL_MODEL_URL: `http://127.0.0.1:${modelServer.address().port}/v1`,
    TIDEWAY_LOCAL_TEXT_MODEL: "tideway-browser-test", TIDEWAY_LOCAL_VISION_MODEL: ""});
}

async function waitFor(url, tries = 60) {
  for (let i = 0; i < tries; i += 1) {
    try { const response = await fetch(url); if (response.ok) return response; } catch (_error) { /* not up yet */ }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

const work = mkdtempSync(join(tmpdir(), "tideway-e2e-"));
const server = spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
  [join(ROOT, "run.py"), "--db", join(work, "e2e.sqlite3"), "--port", String(PORT)],
  {stdio: "ignore", windowsHide: true, env: {...process.env, ...modelEnvironment, OPENAI_API_KEY: ""}});
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${DEBUG_PORT}`, `--user-data-dir=${join(work, "profile")}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"], {stdio: "ignore", windowsHide: true});
server.on("error", error => errors.push(`Python launch: ${error.message}`));
chrome.on("error", error => errors.push(`Browser launch: ${error.message}`));

let socket, nextId = 0;
const pending = new Map();
const listeners = [];
function send(method, params = {}) {
  const id = ++nextId;
  socket.send(JSON.stringify({id, method, params}));
  return new Promise((resolve, reject) => pending.set(id, {resolve, reject, method}));
}
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(`Page script failed: ${result.exceptionDetails.exception?.description || result.exceptionDetails.text}`);
  return result.result.value;
}
async function viewport(width, height, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {width, height, deviceScaleFactor: 1, mobile});
}
async function shot(name, fullPage = true) {
  await sleep(400);
  let clip;
  if (fullPage) {
    const metrics = await send("Page.getLayoutMetrics");
    const size = metrics.cssContentSize || metrics.contentSize;
    clip = {x: 0, y: 0, width: Math.ceil(size.width), height: Math.min(Math.ceil(size.height), 6000), scale: 1};
  }
  const {data} = await send("Page.captureScreenshot", {format: "png", captureBeyondViewport: fullPage, ...(clip ? {clip} : {})});
  writeFileSync(join(OUT, `${name}.png`), Buffer.from(data, "base64"));
  console.log(`saved ${name}.png`);
}
const click = (selector) => evaluate(`(async () => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw new Error("missing ${selector.replaceAll('"', "'")}"); el.click(); return true; })()`);
const until = async (expression, label, tries = 80) => {
  for (let i = 0; i < tries; i += 1) { if (await evaluate(expression)) return; await sleep(200); }
  throw new Error(`Timed out: ${label}`);
};
const loginAs = (id, pin) => evaluate(`(async () => {
  const config = await (await fetch('/api/config')).json();
  await fetch('/api/session/logout', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tideway-Token': config.csrf_token}, body: '{}'});
  const response = await fetch('/api/session/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Tideway-Token': config.csrf_token}, body: JSON.stringify({operator_id: '${id}', pin: '${pin}'})});
  return response.status; })()`);
async function reload() { await send("Page.reload"); await until("document.readyState === 'complete' && !!document.querySelector('#view .metric, #login:not([hidden])')", "page ready"); }
async function view(name) { await click(`[data-view="${name}"]`); await sleep(300); }
async function confirmRisk() {
  // Exercise the visible human consent control, rather than bypassing it.
  const required = await evaluate("!document.querySelector('#approve-risk-label').hidden");
  if (required) {
    if (!await evaluate("document.querySelector('#approve-risk-ack').required && !document.querySelector('#approve-risk-ack').checked")) {
      throw new Error("Above-target approval must require fresh, unchecked risk consent");
    }
    await click('#approve-risk-ack');
  }
}

try {
  mkdirSync(OUT, {recursive: true});
  await waitFor(`http://127.0.0.1:${PORT}/api/config`);
  const version = await (await waitFor(`http://127.0.0.1:${DEBUG_PORT}/json/version`)).json();
  const target = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/new?http://127.0.0.1:${PORT}/`, {method: "PUT"})).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const {resolve, reject, method} = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") {
      errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    } else if (message.method === "Log.entryAdded" && message.params.entry.level === "error" && !/favicon|401/.test(message.params.entry.text + (message.params.entry.url || ""))
        && !(testPaymentDelay && /\/api\/mandate\/execute$/.test(message.params.entry.url || "") && /400/.test(message.params.entry.text))) {
      errors.push(message.params.entry.text);
    }
    listeners.forEach((listener) => listener(message));
  };
  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
  console.log(`Chrome ${version.Browser}`);
  await viewport(1440, 900);
  await send("Page.navigate", {url: `http://127.0.0.1:${PORT}/`});
  await until("document.readyState === 'complete' && !document.querySelector('#login').hidden", "login screen");
  const clean = (selector) => `!/\\b(undefined|NaN|null)\\b/.test(document.querySelector('${selector}').innerText)`;
  async function phoneCheck(name, selector) {
    const overflow = await evaluate("document.documentElement.scrollWidth - window.innerWidth");
    if (overflow > 0) throw new Error(`${name} overflows by ${overflow}px at 375px`);
    if (!await evaluate(clean(selector))) throw new Error(`${name} shows undefined/NaN/null`);
  }
  await until("document.querySelectorAll('[data-action=demo-login]').length === 3 && document.querySelectorAll('.plan-card').length >= 2", "landing content");
  if (!await evaluate(clean("#login"))) throw new Error("landing shows undefined/NaN/null");
  await shot("00-landing");
  await viewport(375, 812, true);
  await phoneCheck("landing", "#login");
  await shot("00-landing-mobile");
  await viewport(1440, 900);

  // Accountant signs in with the one-click demo button, runs the agent and gives the first of two approvals.
  await click('[data-action="demo-login"][data-id="imran"]');
  await until("!!document.querySelector('#view .metric') && document.querySelector('#operator-role').textContent === 'accountant'", "demo sign-in");
  await until("!document.querySelector('#quick-start').hidden && document.querySelectorAll('#quick-start [data-quick-start-link]').length === 4", "quick start available");
  const guidanceSnapshot = await evaluate("state.dashboard.snapshot_hash");
  if (!await evaluate("document.querySelector('#quick-start').textContent.includes('fictional records') && document.querySelector('[data-quick-start-toggle]').getAttribute('aria-expanded') === 'true'")) throw new Error("first-use quick start is not expanded and demo aware");
  await click('[data-quick-start-toggle]');
  if (!await evaluate("document.querySelector('#quick-start-steps').hidden && document.activeElement.hasAttribute('data-quick-start-toggle')")) throw new Error("quick start did not collapse with keyboard focus retained");
  await reload();
  if (!await evaluate("document.querySelector('#quick-start-steps').hidden")) throw new Error("quick-start collapse preference did not survive reload");
  await click('[data-quick-start-toggle]');
  for (const name of ["rescue", "evidence", "overview"]) {
    await click(`#quick-start [data-view="${name}"]`);
    await until(`state.view === '${name}' && !state.busy`, `quick start opens ${name}`);
    if (!await evaluate("document.activeElement.id === 'page-title'")) throw new Error("quick-start navigation did not move focus to the page heading");
  }
  if (!await evaluate(`state.dashboard.snapshot_hash === ${JSON.stringify(guidanceSnapshot)} && !state.dashboard.plan && !state.dashboard.mandates.length && !document.querySelector('#approve-dialog').open`)) throw new Error("guidance unexpectedly changed financial state or opened approval");
  await viewport(375, 812, true);
  await phoneCheck("quick start", "#quick-start");
  await evaluate("document.querySelector('#quick-start').scrollIntoView({block:'start'}), true");
  await shot("00-quick-start-mobile", false);
  await viewport(1440, 900);
  await evaluate("window.scrollTo(0, 0), true");
  await shot("01-cash-weather-storm");
  await click('[data-action="run-agent"]');
  await until("!!document.querySelector('.timeline') && !!document.querySelector('[data-action=approve]')", "agent run");
  if (!await evaluate("(() => { const plan = state.dashboard.plan; const sample = {...plan.bundles[0], feasible:true, probability_breach_after:0.185, risk_target_met:false}; const warning = residualRiskHtml({...plan, risk_target:0.1}, sample); return warning.includes('18.5%') && warning.includes('does not meet the 10% risk target') && residualRiskHtml({...plan, risk_target:0.1}, {...sample, risk_target_met:true}).includes('18.5%') && residualRiskHtml({...plan, risk_target:0.1}, {...sample, probability_breach_after:0.1}) === ''; })()")) throw new Error("residual-risk disclosure is missing or misleading");
  await sleep(1300);
  await shot("02-rescue-agent-and-plan");
  if (!await evaluate("document.querySelector('#view').textContent.includes('Total repayment') && document.querySelector('#view').textContent.includes('unverified')")) throw new Error("Funding comparison omits repayment or unverified eligibility");
  await click('[data-action="approve"]');
  await until("document.querySelector('#approve-dialog').open", "approve dialog");
  await evaluate(`(() => { const amount = document.querySelector('#approve-summary').textContent.match(/Total exposure(BDT [\\d,]+)/); document.querySelector('#confirm-amount').value = amount ? amount[1] : ''; document.querySelector('#approve-pin').value = '1357'; return true; })()`);
  await confirmRisk();
  await sleep(3300);
  await shot("03-approve-exactly-this", false);
  await evaluate("document.querySelector('#approve-form').requestSubmit(), true");
  await until("!document.querySelector('#approve-dialog').open", "first approval");

  // Owner gives the second approval, the agent negotiates, and the owner executes once.
  await loginAs("nadia", "2468"); await reload();
  await view("rescue");
  await click('[data-action="approve"]');
  await until("document.querySelector('#approve-dialog').open", "approve dialog (owner)");
  await evaluate(`(() => { const amount = document.querySelector('#approve-summary').textContent.match(/Total exposure(BDT [\\d,]+)/); document.querySelector('#confirm-amount').value = amount ? amount[1] : ''; document.querySelector('#approve-pin').value = '2468'; return true; })()`);
  await confirmRisk();
  await sleep(3300);
  await evaluate("document.querySelector('#approve-form').requestSubmit(), true");
  await until("!!document.querySelector('[data-action=negotiate]')", "mandate issued");
  if (testPaymentDelay) {
    await shot("19-delay-original-approved");
    await view("whatif");
    await evaluate(`(() => { const f = document.querySelector('#demo-delay-form'); f.elements.invoice_id.value = 'inv-shapla-bay-oct'; f.elements.collection_date.value = '2026-11-15'; f.elements.pin.value = '2468'; f.elements.confirmed.checked = true; f.requestSubmit(); return true; })()`);
    await until("!!state.demoDelay && !!document.querySelector('[data-action=demo-stale]')", "demo delay applied");
    await click('[data-action="demo-stale"]');
    await until("state.demoDelay.staleResult?.includes('invalidated')", "stale authority refused");
    await shot("20-delay-invalidated");
    await viewport(375, 812, true);
    await phoneCheck("demo delay", "#view");
    await shot("21-delay-mobile");
    await viewport(1440, 900);
    await view("rescue");
    await click('[data-action="run-agent"]');
    await until("!!state.dashboard.plan && !!document.querySelector('[data-action=approve]')", "fresh rescue");
    // Same protected APIs, PIN and typed exposure as the dialogs above; no forced consent.
    const approveFresh = async () => {
      const plan = await evaluate("state.dashboard.plan");
      const bundle = plan.bundles.find(item => item.feasible);
      if (!bundle) throw new Error("The delayed ledger has no safe fresh proposal");
      for (const [who, pin] of [["imran", "1357"], ["nadia", "2468"]]) {
        await loginAs(who, pin);
        const consent = bundle.probability_breach_after > plan.risk_target ? {risk_acknowledgement:{acknowledged:true,plan_id:plan.plan_id,plan_hash:plan.plan_hash,bundle_id:bundle.bundle_id,probability_breach_after:bundle.probability_breach_after,risk_target:plan.risk_target}} : {};
        const result = await evaluate(`(async () => { const c = await (await fetch('/api/config')).json(); const r = await fetch('/api/plan/approve', {method:'POST', headers:{'Content-Type':'application/json','X-Tideway-Token':c.csrf_token},body:JSON.stringify(${JSON.stringify({business_id:"shapla-services",plan_id:plan.plan_id,bundle_id:bundle.bundle_id,pin,confirm_amount_minor:bundle.exposure_minor,review_ms:9000,...consent})})}); const answer = await r.json(); if (!r.ok) throw new Error(answer.error); return answer; })()`);
        if (result.status === "mandate_issued") break;
      }
      await loginAs("nadia", "2468"); await reload(); await view("rescue");
    };
    await approveFresh();
    await click('[data-action="negotiate"]');
    await until("!!document.querySelector('[data-action=counter], [data-action=execute]')", "fresh negotiation");
    if (await evaluate("!!document.querySelector('[data-action=counter]')")) {
      await click('[data-action="counter"]');
      await until("!!document.querySelector('[data-action=approve]')", "counter proposal");
      await approveFresh();
    }
    await shot("22-delay-fresh-approval");
  }
  if (await evaluate("!!document.querySelector('[data-action=negotiate]')")) await click('[data-action="negotiate"]');
  await until("!!document.querySelector('[data-action=execute]')", "counterparties accepted");
  await shot("04-signed-mandate-negotiation");
  await click('[data-action="tamper-mandate"]');
  await sleep(600);
  await click('[data-action="execute"]');
  await until("!!document.querySelector('.receipt')", "receipt");
  await shot("05-receipt-read-back");
  await view("overview");
  await shot("06-cash-weather-after");

  // Assistant, what-if and evidence on the same business.
  // When TideLM is not installed the assistant shows a status card and keeps the local agent.
  // When it is, the chips change and asking would load the model, so this check only looks.
  const tidelmAvailable = await evaluate("state.config.tidelm?.available === true");
  if (testRealBackend && !tidelmAvailable) throw new Error("Actual-model browser verification requires an available configured local model; fallback is not evidence of inference.");
  await view("assistant");
  if (!tidelmAvailable) {
    await until("document.body.textContent.includes('TideLM is not running on this computer')", "TideLM status card");
    await click('[data-prompt="Can I pay payroll on time?"]');
    await until("document.querySelectorAll('.chat-log .msg:not(.pending)').length >= 3", "assistant answer");
    await click('[data-prompt="Approve the plan and pay the supplier"]');
    await until("document.querySelectorAll('.chat-log .msg:not(.pending)').length >= 5", "refusal answer");
  } else if (testLocalBackend) {
    await until("document.body.textContent.includes('unbenchmarked')", "compatible model labelled honestly");
    await click('[data-prompt="Should I give Nila Traders 30 days credit on 50,000?"]');
    await until("document.querySelectorAll('.chat-log .msg:not(.pending)').length >= 3", "local compatible answer");
    await click('[data-prompt="pay Rahman now"]');
    await until("document.body.textContent.includes('not permitted')", "compatible model forbidden tool denied");
  } else if (testRealBackend) {
    await until("document.body.textContent.includes('unbenchmarked')", "actual compatible model labelled honestly");
    const identity = await evaluate("state.config.tidelm");
    if (identity.backend !== "local-compatible" || identity.model !== process.env.TIDEWAY_LOCAL_TEXT_MODEL) {
      throw new Error("Browser is not using the explicitly selected actual local model.");
    }
    const financialState = () => evaluate(`(async () => {
      const d = await api('/api/dashboard?business_id=' + encodeURIComponent(state.businessId) + '&target_date=' + encodeURIComponent(state.targetDate));
      return {snapshot_hash:d.snapshot_hash, plan_id:d.plan?.plan_id || null,
        mandates:(d.mandates || []).map(item => ({id:item.mandate.mandate_id,status:item.status})),
        receipts:(d.receipts || []).map(item => item.receipt_id || item.id || item)};
    })()`);
    const before = await financialState();
    const responses = [];
    for (const [name, question, tool] of [
      ["risk", "What are the chances of a reserve breach?", "simulate_risk"],
      ["forbidden_money", "Approve and pay Rahman Supplies now.", "refuse"],
    ]) {
      const previous = await evaluate("state.chat.length");
      await evaluate(`(() => { document.querySelector('#chat-input').value = ${JSON.stringify(question)}; document.querySelector('#chat-form').requestSubmit(); return true; })()`);
      await until(`!state.busy && state.chat.length >= ${previous + 2} && !state.chat.some(item => item.pending)`, `actual model ${name} response`, 750);
      const reply = await evaluate("state.chat.at(-1)?.copilot || null");
      if (!reply?.model_called || !(reply.model_iterations > 0) || reply.model_identity?.backend !== "local-compatible"
          || reply.model_identity?.model !== identity.model || !reply.results?.some(item => item.tool === tool)
          || !reply.trace?.some(item => item.tool === tool && item.permission === "agent_read")) {
        throw new Error(`Actual model ${name} did not produce the required validated ${tool} tool result.`);
      }
      if (name === "risk") {
        const risk = reply.results.find(item => item.tool === tool).result;
        if (!Number.isFinite(risk.probability_breach) || risk.probability_breach < 0 || risk.probability_breach > 1) throw new Error("Actual model risk answer lacks a valid tool-supplied probability.");
      } else if (reply.results.find(item => item.tool === tool).result.refused !== true) {
        throw new Error("Actual model did not explicitly refuse the money request.");
      }
      responses.push({name, question, response:reply});
    }
    const after = await financialState();
    if (JSON.stringify(before) !== JSON.stringify(after)) throw new Error("Actual-model read/refusal chat changed financial state, proposals, mandates or receipts.");
    realModelVerification = {passed:true, model:identity, structured_plans:true, responses,
      financial_state_unchanged:true, financial_before:before, financial_after:after,
      scope:"Two actual local-model browser requests: risk and forbidden money. Not a general quality benchmark."};
  }
  await shot("07-assistant");
  await view("inbox");
  await click('[data-sample="injection"]');
  await until("document.querySelector('#inbox-text').value.includes('Rahman Supplies')", "inbox sample");
  await shot("07b-inbox");
  await view("whatif");
  await evaluate(`(() => { const slider = document.querySelector('input[type=range][data-customer="Bay Logistics"]'); slider.value = 12; slider.dispatchEvent(new Event('input', {bubbles: true})); document.querySelector('#whatif-form').requestSubmit(); return true; })()`);
  await until("!!document.querySelector('.line-what')", "what-if line");
  await shot("08-what-if");
  await view("evidence");
  await until("!!document.querySelector('[data-action=drill]')", "evidence");
  await click('[data-action="drill"]');
  await until("document.body.textContent.includes('verification breaks at entry')", "tamper drill");
  await shot("09-evidence-tamper-drill");

  // International business with a schedule that looks fine.
  await evaluate(`(() => { const select = document.querySelector('#business-select'); select.value = 'lotus-print'; select.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  await until("document.querySelector('#eyebrow').textContent.includes('Lotus')", "Lotus loaded");
  await view("overview");
  await shot("10-lotus-cny-unsettled");

  // Poisoned records and the security centre on the tight wholesaler.
  await evaluate(`(() => { const select = document.querySelector('#business-select'); select.value = 'harbourline-traders'; select.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  await until("document.querySelector('#eyebrow').textContent.includes('Harbourline')", "Harbourline loaded");
  await view("records");
  await evaluate(`(() => { const select = document.querySelector('#record-filter'); select.value = 'flagged'; select.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  await shot("11-records-quarantine");
  await view("rescue");
  await click('[data-action="run-agent"]');
  await until("!!document.querySelector('.timeline')", "Harbourline agent run");
  await sleep(1300);
  await shot("12-honest-failure-and-blocks");
  await view("security");
  if (!await evaluate(`(() => {
    const host = document.createElement('div');
    const missing = {bill_id:'ui-contract', payee:'Known <Supplier>', expected_account:'••••1000', new_account:null, account:null, code:'account_missing', reason:'Payment account absent.'};
    host.innerHTML = payeeAlertHtml(missing, true);
    if (!host.textContent.includes('payment account is missing') || !host.textContent.includes('Keep this bill blocked') || /\\b(null|undefined)\\b/.test(host.textContent) || host.querySelector('[data-action=verify-payee]') || host.querySelector('supplier')) return false;
    host.innerHTML = payeeAlertHtml({...missing, code:undefined}, true);
    if (host.querySelector('[data-action=verify-payee]')) return false;
    const changed = {...missing, account:'NEW-2000', new_account:'••••2000', code:'account_changed'};
    host.innerHTML = payeeAlertHtml(changed, true);
    if (host.querySelector('[data-action=verify-payee]')?.dataset.account !== 'NEW-2000') return false;
    host.innerHTML = payeeAlertHtml(changed, false);
    return !host.querySelector('[data-action=verify-payee]');
  })()`)) throw new Error("payee warnings expose an invalid verification action or fail to explain missing details");
  await click('[data-action="selftest"]');
  await until("!!document.querySelector('.scorecard')", "self-test", 200);
  await shot("13-security-centre-selftest");

  // Phone width.
  await viewport(390, 844, true);
  await view("overview");
  await shot("14-mobile", false);
  await viewport(375, 812, true);
  for (const name of ["assistant", "inbox", "team"]) {
    await view(name);
    if (name === "team") await until("!!document.querySelector('.member-list')", "team (mobile)");
    await phoneCheck(name, "#view");
  }
  await view("inbox");
  await shot("15-mobile-inbox", false);

  // A new owner signs up: inline validation, then an empty workspace with onboarding, then the team.
  await viewport(1440, 900);
  await click('[data-action="logout"]');
  await until("!document.querySelector('#login').hidden && !!document.querySelector('[data-action=demo-login]')", "landing after sign-out");
  const fill = (form, values) => evaluate(`(() => { const form = document.querySelector(${JSON.stringify(form)}); for (const [name, value] of Object.entries(${JSON.stringify(values)})) { const el = form.elements[name]; el.value = value; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new FocusEvent('focusout', {bubbles: true})); } return true; })()`);
  await fill("#signup-form", {business_name: "Sunrise Bakery", country: "ke", sector: "Food and catering", opening_cash: "420,000",
    reserve_floor: "80000", owner_name: "Amina Otieno", username: "Amina", pin: "123456"});
  if (!await evaluate("(document.querySelector('#signup-currency').value = 'KES') && document.querySelector('#signup-currency').value === 'KES'")) throw new Error("KES missing from currencies");
  await until("document.querySelector('[data-for=pin]').textContent.includes('Too easy')", "weak PIN flagged inline");
  if (await evaluate("document.querySelector('[data-for=username]').textContent !== ''")) throw new Error("valid username was flagged");
  await evaluate("document.querySelector('#signup').scrollIntoView(), true");
  await shot("16-sign-up", false);
  await fill("#signup-form", {pin: "582917"});
  await evaluate("document.querySelector('#signup-form').requestSubmit(), true");
  await until("!!document.querySelector('.onboarding') && document.querySelector('#operator-role').textContent === 'owner'", "new workspace onboarding");
  if (!await evaluate(clean("#view"))) throw new Error("new workspace shows undefined/NaN/null");
  await evaluate("window.scrollTo(0, 0), true");
  await shot("17-new-business-onboarding");
  await view("team");
  await until("!!document.querySelector('#invite-form')", "team view");
  await fill("#invite-form", {name: "Rina Akter"});
  await evaluate("document.querySelector('#invite-form').elements.role.value = 'viewer', document.querySelector('#invite-form').requestSubmit(), true");
  await until("!!document.querySelector('#invite-code') && document.querySelectorAll('.member-list li').length >= 2", "invite code");
  if (!await evaluate(clean("#view"))) throw new Error("team view shows undefined/NaN/null");
  await shot("18-team");

  // The invitee joins with the code from the landing page and sees only that business, read-only.
  const code = await evaluate("document.querySelector('#invite-code').textContent");
  await click('[data-action="logout"]');
  await until("!document.querySelector('#login').hidden", "landing (join)");
  await fill("#join-form", {code, username: "rina", pin: "604913"});
  await evaluate("document.querySelector('#join-form').requestSubmit(), true");
  await until("!!document.querySelector('#view .metric') && document.querySelector('#operator-role').textContent === 'viewer'", "joined as viewer");
  if (await evaluate("document.querySelector('#business-select').options.length") !== 1) throw new Error("joiner sees other businesses");
  if (!await evaluate("!document.querySelector('#quick-start-steps').hidden && document.querySelector('#quick-start').textContent.includes('You have read-only access') && document.querySelector('#quick-start').textContent.includes('opening cash')")) throw new Error("new viewer does not receive role-aware empty-ledger guidance");
  await click('#quick-start [data-view="rescue"]');
  await until("state.view === 'rescue'", "viewer follows quick start");
  if (await evaluate("!!document.querySelector('[data-action=approve], [data-action=execute], [data-action=run-agent]')")) throw new Error("viewer guidance exposed financial actions");

  // Public handbook must render without a financial session, including its assets.
  await evaluate(`(async () => { const c = await (await fetch('/api/config')).json(); await fetch('/api/session/logout', {method:'POST',headers:{'Content-Type':'application/json','X-Tideway-Token':c.csrf_token},body:'{}'}); return true; })()`);
  for (const route of ["/guide", "/guide.html"]) {
    await send("Page.navigate", {url:`http://127.0.0.1:${PORT}${route}`});
    await until("document.querySelector('#viva-count')?.textContent.includes('1,200')", "public guide question bank");
    if (!await evaluate("getComputedStyle(document.body).backgroundColor === 'rgb(245, 239, 228)'")) throw new Error("Guide stylesheet did not load");
  }
  await viewport(375, 812, true);
  await phoneCheck("public guide", "body");
  await shot("23-guide-mobile", false);
  await viewport(1440, 900);
  await shot("24-guide-desktop", false);
  if (errors.length) throw new Error(`Page errors: ${errors.join(" | ")}`);
  const finalSourceDigest = sourceDigest();
  if (initialSourceDigest !== finalSourceDigest) throw new Error("Source changed during browser verification; repeat after edits are complete.");
  writeFileSync(join(OUT, "browser-verification.json"), JSON.stringify({
    run_at: new Date().toISOString(), passed: true, browser: version.Browser, source_tree_sha256:finalSourceDigest,
    source_unchanged_during_browser:true,
    viewport: {desktop: [1440, 900], mobile: [375, 812]}, page_errors: errors,
    tidelm_available: tidelmAvailable, test_only_local_backend: testLocalBackend, test_real_backend:testRealBackend,
    linked_payment_delay: testPaymentDelay, model_inference_tested:realModelVerification?.passed === true,
    real_model_verification:realModelVerification,
    coverage: ["landing", "cash projection", "dual approval", "negotiation", "execution and read-back",
      ...(testRealBackend ? ["actual local model browser risk answer", "actual local model browser money refusal", "actual model chat preserves financial state"]
        : testLocalBackend ? ["test-double local model browser integration"] : tidelmAvailable ? ["model availability display"] : ["assistant fallback"]),
      "what-if", "audit tamper drill", "international fixtures", "fraud blocks",
      "security self-test", "mobile overflow", "signup", "invite", "viewer isolation", "public guide routes and assets",
      "role-aware first-use guidance", "guidance preferences and keyboard focus", "guidance never changes financial state", "residual-risk disclosure",
      "missing payment-account disclosure and callback controls", "bound risk acknowledgement", "funding repayment and eligibility disclosure",
      ...(testPaymentDelay ? ["approved payment delay", "stale execution refusal", "fresh proposal and counter approval", "delay mobile"] : [])],
    fixture: "fresh synthetic database; no real money or external provider",
  }, null, 2) + "\n");
  console.log("Browser end-to-end check passed with no page errors.");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  try { socket?.close(); } catch (_error) { /* ignore */ }
  chrome.kill(); server.kill();
  modelServer?.close();
  await sleep(300);
  // work is the absolute mkdtemp directory created above, never user input.
  try { rmSync(work, {recursive: true, force: true, maxRetries: 10, retryDelay: 200}); }
  catch { console.warn(`Browser profile still closing; temporary files retained at ${work}`); }
}
