// End-to-end browser check and screenshot capture for Tideway.
//
// Starts its own server on a throwaway database, drives headless Chrome over the
// DevTools protocol (Node 22+ built-in WebSocket, no npm packages), walks the
// full demo story, fails on any page error, and writes PNGs to evidence/screens/.
//
//   node scripts/capture_screens.mjs [--chrome "/path/to/chrome"]
import {spawn} from "node:child_process";
import {mkdtempSync, mkdirSync, writeFileSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, dirname} from "node:path";
import {existsSync} from "node:fs";
import {createServer} from "node:http";
import {fileURLToPath} from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
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
    } else if (message.method === "Log.entryAdded" && message.params.entry.level === "error" && !/favicon|401/.test(message.params.entry.text + (message.params.entry.url || ""))) {
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
  await shot("01-cash-weather-storm");
  await click('[data-action="run-agent"]');
  await until("!!document.querySelector('.timeline') && !!document.querySelector('[data-action=approve]')", "agent run");
  await sleep(1300);
  await shot("02-rescue-agent-and-plan");
  await click('[data-action="approve"]');
  await until("document.querySelector('#approve-dialog').open", "approve dialog");
  await evaluate(`(() => { const amount = document.querySelector('#approve-summary').textContent.match(/Total exposure(BDT [\\d,]+)/); document.querySelector('#confirm-amount').value = amount ? amount[1] : ''; document.querySelector('#approve-pin').value = '1357'; return true; })()`);
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
  await sleep(3300);
  await evaluate("document.querySelector('#approve-form').requestSubmit(), true");
  await until("!!document.querySelector('[data-action=negotiate]')", "mandate issued");
  await click('[data-action="negotiate"]');
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

  if (errors.length) throw new Error(`Page errors: ${errors.join(" | ")}`);
  writeFileSync(join(OUT, "browser-verification.json"), JSON.stringify({
    run_at: new Date().toISOString(), passed: true, browser: version.Browser,
    viewport: {desktop: [1440, 900], mobile: [375, 812]}, page_errors: errors,
    tidelm_available: tidelmAvailable, test_only_local_backend: testLocalBackend, model_inference_tested: false,
    coverage: ["landing", "cash projection", "dual approval", "negotiation", "execution and read-back",
      "assistant fallback", "what-if", "audit tamper drill", "international fixtures", "fraud blocks",
      "security self-test", "mobile overflow", "signup", "invite", "viewer isolation"],
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
