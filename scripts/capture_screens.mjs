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
import {fileURLToPath} from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "evidence", "screens");
const PORT = 8799, DEBUG_PORT = 9333;
const chromeArg = process.argv.indexOf("--chrome");
const CHROME = chromeArg > 0 ? process.argv[chromeArg + 1] : process.platform === "darwin"
  ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : "google-chrome";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const errors = [];

async function waitFor(url, tries = 60) {
  for (let i = 0; i < tries; i += 1) {
    try { const response = await fetch(url); if (response.ok) return response; } catch (_error) { /* not up yet */ }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

const work = mkdtempSync(join(tmpdir(), "tideway-e2e-"));
const server = spawn("python3", [join(ROOT, "run.py"), "--db", join(work, "e2e.sqlite3"), "--port", String(PORT)], {stdio: "ignore"});
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${DEBUG_PORT}`, `--user-data-dir=${join(work, "profile")}`,
  "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"], {stdio: "ignore"});

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
  console.log(`saved evidence/screens/${name}.png`);
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
  await shot("00-sign-in", false);

  // Accountant runs the agent and gives the first of two approvals.
  await loginAs("imran", "1357"); await reload();
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
  await view("assistant");
  await click('[data-prompt="Can I pay payroll on time?"]');
  await until("document.querySelectorAll('.chat-log .msg').length >= 3", "assistant answer");
  await click('[data-prompt="Approve the plan and pay the supplier"]');
  await until("document.querySelectorAll('.chat-log .msg').length >= 5", "refusal answer");
  await shot("07-assistant");
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
  await evaluate(`(() => { const select = document.querySelector('#business-select'); select.value = 'meghna-traders'; select.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  await until("document.querySelector('#eyebrow').textContent.includes('Meghna')", "Meghna loaded");
  await view("records");
  await evaluate(`(() => { const select = document.querySelector('#record-filter'); select.value = 'flagged'; select.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  await shot("11-records-quarantine");
  await view("rescue");
  await click('[data-action="run-agent"]');
  await until("!!document.querySelector('.timeline')", "Meghna agent run");
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

  if (errors.length) throw new Error(`Page errors: ${errors.join(" | ")}`);
  console.log("Browser end-to-end check passed with no page errors.");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  try { socket?.close(); } catch (_error) { /* ignore */ }
  chrome.kill(); server.kill();
  await sleep(300);
  rmSync(work, {recursive: true, force: true});
}
