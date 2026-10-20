// Minimal Chrome DevTools Protocol helpers for the pitch-video recorder.
// Same approach as scripts/capture_screens.mjs: headless Chrome, Node 22+
// built-in WebSocket, no npm packages.
import {spawn} from "node:child_process";
import {existsSync, mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const CHROME = process.env.CHROME || [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find(existsSync) || "google-chrome";

export async function waitFor(url, tries = 120) {
  for (let i = 0; i < tries; i += 1) {
    try { const response = await fetch(url); if (response.ok) return response; } catch (_error) { /* not up yet */ }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

export async function launchBrowser({debugPort = 9341, width = 1280, height = 720, scale = 1.5} = {}) {
  const profile = mkdtempSync(join(tmpdir(), "tideway-video-"));
  const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "--mute-audio", "--force-color-profile=srgb",
    "--font-render-hinting=none", `--window-size=${Math.round(width * scale)},${Math.round(height * scale)}`, "about:blank"],
    {stdio: "ignore", windowsHide: true});
  const errors = [];
  chrome.on("error", (error) => errors.push(`Browser launch: ${error.message}`));
  const version = await (await waitFor(`http://127.0.0.1:${debugPort}/json/version`)).json();
  const target = await (await fetch(`http://127.0.0.1:${debugPort}/json/new?about:blank`, {method: "PUT"})).json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  const listeners = new Set();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const {resolve, reject, method} = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") {
      errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    }
    for (const listener of listeners) listener(message);
  };
  const send = (method, params = {}) => {
    const id = ++nextId;
    socket.send(JSON.stringify({id, method, params}));
    return new Promise((resolve, reject) => pending.set(id, {resolve, reject, method}));
  };
  const evaluate = async (expression) => {
    const result = await send("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(`Page script failed: ${result.exceptionDetails.exception?.description || result.exceptionDetails.text}`);
    return result.result.value;
  };
  const until = async (expression, label, timeoutMs = 20000) => {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) { if (await evaluate(expression)) return; await sleep(120); }
    throw new Error(`Timed out: ${label}`);
  };
  const viewport = (w, h, s) => send("Emulation.setDeviceMetricsOverride", {width: w, height: h, deviceScaleFactor: s, mobile: false});
  await send("Page.enable"); await send("Runtime.enable");
  await viewport(width, height, scale);
  const close = async () => {
    try { socket.close(); } catch (_error) { /* ignore */ }
    chrome.kill();
    await sleep(400);
    try { rmSync(profile, {recursive: true, force: true, maxRetries: 10, retryDelay: 200}); } catch (_error) { /* profile still closing */ }
  };
  return {send, evaluate, until, viewport, listeners, errors, version, close};
}
