// Records every storyboard scene as a constant-frame-rate 1920x1080 H.264 clip.
//
// Expects Tideway to be running already (build.py starts it on a fresh database):
//   python run.py --port 8792 --db data/video.sqlite3
// Then:
//   node scripts/pitch_video/record.mjs --work dist/video/work --ffmpeg <path> [--only id1,id2]
//
// Slides are rendered from slide.html (Tideway colours and fonts) and live scenes
// drive the real app. Both are captured with CDP Page.startScreencast; frames are
// resampled to 30 fps in memory and piped straight into ffmpeg, so no frame
// files are written to disk.
import {spawn} from "node:child_process";
import {existsSync, mkdirSync, readFileSync, writeFileSync} from "node:fs";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {launchBrowser, sleep, waitFor} from "./cdp.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const option = (name, fallback) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : fallback; };
const WORK = resolve(option("--work", join(ROOT, "dist", "video", "work")));
const STORYBOARD = resolve(option("--storyboard", join(HERE, "storyboard.json")));
const BASE = option("--base", "http://127.0.0.1:8792");
const FFMPEG = option("--ffmpeg", process.env.FFMPEG || "ffmpeg");
const ONLY = (option("--only", "") || "").split(",").filter(Boolean);
const DEBUG_PORT = Number(option("--debug-port", "9341"));
const board = JSON.parse(readFileSync(STORYBOARD, "utf8"));
const T = {fps: 30, lead: 0.35, tail: 0.55, xfade: 0.5, width: 1280, height: 720, scale: 1.5, ...(board.timing || {})};
const narration = existsSync(join(WORK, "narration.json")) ? JSON.parse(readFileSync(join(WORK, "narration.json"), "utf8")) : {scenes: {}};
mkdirSync(join(WORK, "clips"), {recursive: true});
mkdirSync(join(WORK, "slides"), {recursive: true});
mkdirSync(join(WORK, "debug"), {recursive: true});

const browser = await launchBrowser({debugPort: DEBUG_PORT, width: T.width, height: T.height, scale: T.scale});
const {send, evaluate, until, listeners} = browser;

// ---------------------------------------------------------------- screencast
let frames = null, castStart = 0;
listeners.add((message) => {
  if (message.method !== "Page.screencastFrame") return;
  const {data, metadata, sessionId} = message.params;
  send("Page.screencastFrameAck", {sessionId}).catch(() => {});
  if (!frames) return;
  const t = (metadata?.timestamp ? metadata.timestamp * 1000 : Date.now()) - castStart;
  frames.push({t: Math.max(0, t) / 1000, data: Buffer.from(data, "base64")});
});
async function startCast() {
  frames = []; castStart = Date.now();
  await send("Page.startScreencast", {format: "jpeg", quality: 92, maxWidth: Math.round(T.width * T.scale), maxHeight: Math.round(T.height * T.scale), everyNthFrame: 1});
  // Force at least one fresh frame even on a completely static page.
  await evaluate("(()=>{const d=document.createElement('div');d.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;opacity:.01;pointer-events:none';document.body.appendChild(d);requestAnimationFrame(()=>requestAnimationFrame(()=>d.remove()));return true;})()");
}
async function stopCast() {
  await send("Page.stopScreencast");
  const captured = frames; frames = null;
  return captured;
}
async function encodeClip(captured, seconds, outFile) {
  if (!captured.length) {
    const {data} = await send("Page.captureScreenshot", {format: "jpeg", quality: 92});
    captured = [{t: 0, data: Buffer.from(data, "base64")}];
  }
  captured.sort((a, b) => a.t - b.t);
  const total = Math.round(seconds * T.fps);
  const W = Math.round(T.width * T.scale), H = Math.round(T.height * T.scale);
  const ff = spawn(FFMPEG, ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(T.fps), "-c:v", "mjpeg", "-i", "-",
    "-vf", `scale=${W}:${H}:flags=lanczos,setsar=1,format=yuv420p`, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
    "-r", String(T.fps), "-g", String(T.fps * 2), outFile], {stdio: ["pipe", "ignore", "pipe"], windowsHide: true});
  let stderr = "";
  ff.stderr.on("data", (chunk) => { stderr += chunk; });
  const done = new Promise((resolveDone, reject) => ff.on("close", (code) => code === 0 ? resolveDone() : reject(new Error(`ffmpeg clip ${outFile}: ${stderr}`))));
  let index = 0;
  for (let k = 0; k < total; k += 1) {
    const time = k / T.fps;
    while (index + 1 < captured.length && captured[index + 1].t <= time) index += 1;
    if (!ff.stdin.write(captured[index].data)) await new Promise((r) => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  await done;
}

// ------------------------------------------------------------------ helpers
const js = (value) => JSON.stringify(value);
const highlightCss = `.pv-ring{outline:5px solid #d6337f!important;outline-offset:5px!important;box-shadow:0 0 0 14px rgba(214,51,127,.22)!important;border-radius:14px;transition:outline-offset .25s}`;
async function ensureStyle() {
  await evaluate(`(()=>{if(!document.querySelector('#pv-style')){const s=document.createElement('style');s.id='pv-style';s.textContent=${js(highlightCss)};document.head.appendChild(s);}return true;})()`);
}
async function exists(selector) { return evaluate(`!!document.querySelector(${js(selector)})`); }
async function smoothScroll(selector, block = "start", offset = 0) {
  await evaluate(`(async()=>{const el=document.querySelector(${js(selector)});if(!el)throw new Error('missing ${String(selector).replaceAll("'", "\\'")}');
    const r=el.getBoundingClientRect();const target=${js(block)}==='center'?window.scrollY+r.top-(innerHeight-r.height)/2:window.scrollY+r.top-${Number(offset) || 16};
    const start=window.scrollY,end=Math.max(0,Math.min(target,document.documentElement.scrollHeight-innerHeight)),dur=900;const t0=performance.now();
    await new Promise(done=>{const step=now=>{const p=Math.min(1,(now-t0)/dur);const e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;window.scrollTo(0,start+(end-start)*e);p<1?requestAnimationFrame(step):done();};requestAnimationFrame(step);});return true;})()`);
}
async function scrollBy(dy) {
  await evaluate(`(async()=>{const start=window.scrollY,end=Math.max(0,Math.min(start+${Number(dy)},document.documentElement.scrollHeight-innerHeight)),dur=900,t0=performance.now();
    await new Promise(done=>{const step=now=>{const p=Math.min(1,(now-t0)/dur);const e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;window.scrollTo(0,start+(end-start)*e);p<1?requestAnimationFrame(step):done();};requestAnimationFrame(step);});return true;})()`);
}
async function highlight(selector, ms = 900) {
  await ensureStyle();
  await evaluate(`(()=>{const el=document.querySelector(${js(selector)});if(!el)throw new Error('missing ${String(selector).replaceAll("'", "\\'")}');el.classList.add('pv-ring');return true;})()`);
  await sleep(ms);
  await evaluate(`(()=>{document.querySelectorAll('.pv-ring').forEach(e=>e.classList.remove('pv-ring'));return true;})()`);
}
async function apiLogin(id, pin) {
  await evaluate(`(async()=>{const c=await(await fetch('/api/config')).json();
    await fetch('/api/session/logout',{method:'POST',headers:{'Content-Type':'application/json','X-Tideway-Token':c.csrf_token},body:'{}'});
    const r=await fetch('/api/session/login',{method:'POST',headers:{'Content-Type':'application/json','X-Tideway-Token':c.csrf_token},body:JSON.stringify({operator_id:${js(id)},pin:${js(pin)}})});
    if(!r.ok)throw new Error((await r.json()).error||'sign-in failed');return true;})()`);
}
async function reloadPage() {
  const previous = await evaluate("performance.timeOrigin");
  await send("Page.reload");
  await until(`performance.timeOrigin!==${previous} && document.readyState==='complete' && !!document.querySelector('#view .metric, #view .owner-view, #login:not([hidden])')`, "page ready", 30000);
  await sleep(400);
}
async function typeInto(selector, text, cps = 22) {
  await evaluate(`(()=>{const el=document.querySelector(${js(selector)});el.focus();el.value='';el.dispatchEvent(new Event('input',{bubbles:true}));return true;})()`);
  const chars = [...text];
  const chunk = Math.max(1, Math.round(cps / 15));
  for (let i = 0; i < chars.length; i += chunk) {
    const part = chars.slice(i, i + chunk).join("");
    await evaluate(`(()=>{const el=document.querySelector(${js(selector)});el.value+=${js(part)};el.dispatchEvent(new Event('input',{bubbles:true}));return true;})()`);
    await sleep(1000 * chunk / cps);
  }
}

// Each step: {do: ..., at?: fraction of narration when the step should start}
async function runStep(step, ctx) {
  const op = step.do;
  switch (op) {
    case "navigate": await send("Page.navigate", {url: new URL(step.url || "/", BASE).href});
      await until("document.readyState==='complete'", "navigation", 30000); if (step.ready) await until(step.ready, `ready ${step.ready}`, 30000); break;
    case "login": await apiLogin(step.id, step.pin); await reloadPage(); break;
    case "reload": await reloadPage(); break;
    case "view": await evaluate(`(()=>{const el=document.querySelector('[data-view=${step.name}]');if(!el)throw new Error('missing view ${step.name}');el.click();return true;})()`);
      await until(`state.view===${js(step.name)} && !state.busy`, `view ${step.name}`, 30000); await evaluate("window.scrollTo(0,0),true"); break;
    case "click": if (step.optional && !await exists(step.selector)) break;
      if (step.highlight !== false) await highlight(step.selector, step.highlight_ms ?? 700);
      await evaluate(`(()=>{const el=document.querySelector(${js(step.selector)});if(!el)throw new Error('missing ${String(step.selector).replaceAll("'", "\\'")}');el.click();return true;})()`); break;
    case "highlight": await highlight(step.selector, step.ms ?? 1200); break;
    case "type": await typeInto(step.selector, step.text, step.cps ?? 22); break;
    case "set": await evaluate(`(()=>{const el=document.querySelector(${js(step.selector)});el.value=${js(step.value)};el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true;})()`); break;
    case "submit": await evaluate(`(()=>{document.querySelector(${js(step.selector)}).requestSubmit();return true;})()`); break;
    case "wait": await until(step.for, step.label || step.for, step.timeout ?? 30000); break;
    case "pause": await sleep(step.ms ?? 1000); break;
    case "scroll": if (step.selector) await smoothScroll(step.selector, step.block, step.offset); else if (step.by) await scrollBy(step.by); else await evaluate(`window.scrollTo({top:${Number(step.y) || 0},behavior:'smooth'}),true`); break;
    case "eval": await evaluate(step.js); break;
    case "storage": await evaluate(`(()=>{localStorage.setItem(${js(step.key)},${js(step.value)});return true;})()`); break;
    case "hover": {
      const box = await evaluate(`(()=>{const el=document.querySelector(${js(step.selector)});if(!el)throw new Error('missing hover target');el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
      await send("Input.dispatchMouseEvent", {type: "mouseMoved", x: box.x, y: box.y});
      if (step.click) {
        await send("Input.dispatchMouseEvent", {type: "mousePressed", x: box.x, y: box.y, button: "left", clickCount: 1});
        await send("Input.dispatchMouseEvent", {type: "mouseReleased", x: box.x, y: box.y, button: "left", clickCount: 1});
      }
      break;
    }
    case "slide-play": await evaluate("document.body.classList.add('play'),true"); break;
    default: throw new Error(`Unknown step '${op}' in scene ${ctx.id}`);
  }
}

// ------------------------------------------------------------------- slides
const template = readFileSync(join(HERE, "slide.html"), "utf8");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function slideHtml(slide) {
  const fonts = pathToFileURL(join(ROOT, "web", "fonts")).href;
  const items = (slide.items || []).map((item, i) => `<li class="item" style="--i:${i}">${item.tag ? `<span class="tag">${esc(item.tag)}</span>` : ""}<h3>${esc(item.h)}</h3>${item.p ? `<p>${esc(item.p)}</p>` : ""}</li>`).join("");
  const stats = (slide.stats || []).map((s, i) => `<li class="stat" style="--i:${i}"><span class="label">${esc(s.label)}</span><strong>${esc(s.value)}</strong><span class="note">${esc(s.note)}</span></li>`).join("");
  const chips = (slide.chips || []).map((c, i) => `<span class="chip" style="--i:${i}">${esc(c)}</span>`).join("");
  const people = (slide.people || []).map((p, i) => `<li style="--i:${i}">${esc(p)}</li>`).join("");
  return template.replaceAll("{{FONTS}}", fonts).replace("{{LAYOUT}}", esc(slide.layout || "cards"))
    .replace("{{KICKER}}", esc(slide.kicker)).replace("{{TITLE}}", (slide.title || "").split("|").map((part) => esc(part).replace(/\*(.+?)\*/g, "<em>$1</em>")).join("<br>"))
    .replace("{{SUB}}", esc(slide.subtitle)).replace("{{ITEMS}}", items).replace("{{STATS}}", stats)
    .replace("{{CHIPS}}", chips).replace("{{PEOPLE}}", people).replace("{{FOOT}}", esc(slide.footnote));
}

// -------------------------------------------------------------------- scenes
function sceneLength(scene) {
  const audio = narration.scenes[scene.id];
  const spoken = audio ? audio.duration : 0;
  return Math.max(scene.min_seconds || 0, T.lead + spoken + T.tail + T.xfade + (scene.extra_seconds || 0));
}
async function requirementMet(scene) {
  if (scene.enabled === false) return "disabled in storyboard";
  if (!scene.requires) return null;
  const ok = await evaluate(`(()=>{try{return !!document.querySelector(${js(scene.requires)});}catch(e){return false;}})()`);
  return ok ? null : `requires ${scene.requires}, not present in this build`;
}

const manifest = {started_at: new Date().toISOString(), browser: browser.version.Browser, base: BASE, timing: T, scenes: []};
let appReady = false;
try {
  await waitFor(`${BASE}/api/config`);
  for (const scene of board.scenes) {
    if (ONLY.length && !ONLY.includes(scene.id)) continue;
    const entry = {id: scene.id, kind: scene.kind};
    try {
      if (scene.kind === "app" && !appReady) {
        await send("Page.navigate", {url: `${BASE}/`});
        await until("document.readyState==='complete' && !!document.querySelector('#login')", "landing", 30000);
        appReady = true;
      }
      const reason = scene.enabled === false ? "disabled in storyboard" : (scene.kind === "app" ? await requirementMet(scene) : null);
      if (reason) {
        if (!scene.optional && scene.enabled !== false) throw new Error(reason);
        entry.skipped = reason; manifest.scenes.push(entry); console.log(`skip ${scene.id}: ${reason}`); continue;
      }
      for (const step of scene.setup || []) await runStep(step, scene);
      if (scene.kind === "slide") {
        const file = join(WORK, "slides", `${scene.id}.html`);
        writeFileSync(file, slideHtml(scene.slide));
        await send("Page.navigate", {url: pathToFileURL(file).href});
        await until("document.readyState==='complete' && document.fonts.status==='loaded'", "slide fonts", 15000);
        await sleep(300);
        appReady = false;
      }
      const target = sceneLength(scene);
      await startCast();
      const t0 = Date.now();
      if (scene.kind === "slide") await runStep({do: "slide-play"}, scene);
      for (const step of scene.steps || []) {
        if (typeof step.at === "number") { const due = t0 + step.at * (target - T.xfade) * 1000; const wait = due - Date.now(); if (wait > 0) await sleep(wait); }
        await runStep(step, scene);
      }
      const elapsed = (Date.now() - t0) / 1000;
      const holdUntil = Math.max(target, elapsed + (scene.hold_after || 0.8) + T.xfade);
      const remaining = holdUntil - (Date.now() - t0) / 1000;
      if (remaining > 0) await sleep(remaining * 1000);
      const captured = await stopCast();
      const length = Math.round(holdUntil * T.fps) / T.fps;
      await encodeClip(captured, length, join(WORK, "clips", `${scene.id}.mp4`));
      Object.assign(entry, {length, target, actions_seconds: +elapsed.toFixed(2), frames_captured: captured.length, clip: `clips/${scene.id}.mp4`});
      manifest.scenes.push(entry);
      console.log(`recorded ${scene.id}: ${length.toFixed(2)} s (narration target ${target.toFixed(2)} s, actions ${elapsed.toFixed(1)} s, ${captured.length} frames)`);
    } catch (error) {
      try { await stopCast(); } catch (_e) { /* not casting */ }
      try { const {data} = await send("Page.captureScreenshot", {format: "jpeg", quality: 80}); writeFileSync(join(WORK, "debug", `${scene.id}-failure.jpg`), Buffer.from(data, "base64")); } catch (_e) { /* ignore */ }
      if (scene.optional) { entry.skipped = `failed: ${error.message}`; manifest.scenes.push(entry); console.warn(`optional scene ${scene.id} skipped after failure: ${error.message}`); appReady = false; continue; }
      throw new Error(`Scene ${scene.id} failed: ${error.message}`);
    }
  }
  if (browser.errors.length) manifest.page_errors = browser.errors;
  manifest.finished_at = new Date().toISOString();
  writeFileSync(join(WORK, ONLY.length ? "record-partial.json" : "record.json"), JSON.stringify(manifest, null, 2));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
