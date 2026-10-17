import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';import {tmpdir} from 'node:os';
const ROOT=process.env.TIDEWAY_REPO||process.cwd(),PY=process.env.PYTHON||'python3';
const OUT=join(ROOT,'evidence/remediation-v7/browser-risk');mkdirSync(OUT,{recursive:true});
const work=mkdtempSync(join(tmpdir(),'tideway-h11-browser-'));
const digest=()=>spawnSync(PY,['-B','-c','from scripts.verify_submission import source_digest;print(source_digest()[0])'],{cwd:ROOT,encoding:'utf8'}).stdout.trim();
const before=digest();
const code=`import sys,json\nsys.path.insert(0,${JSON.stringify(ROOT)})\nfrom tideway.service import Tideway\nfrom tideway.server import make_handler,Application\nfrom http.server import ThreadingHTTPServer\nfrom scripts.evaluate_upgrade_scenarios import load_spec,new_business\na=Application(${JSON.stringify(join(work,'h11.sqlite3'))},seed=False)\ns=load_spec();new_business(a.tideway,next(c for c in s['scenarios'] if c['id']=='H11'),s['defaults'])\nh=ThreadingHTTPServer(('127.0.0.1',0),make_handler(a))\nprint(json.dumps({'port':h.server_port}),flush=True)\nh.serve_forever()\n`;
const server=spawn(PY,['-B','-c',code],{cwd:ROOT,stdio:['ignore','pipe','ignore'],env:{...process.env,OPENAI_API_KEY:'',TIDEWAY_LOCAL_MODEL_URL:'',TIDEWAY_LOCAL_TEXT_MODEL:'',TIDEWAY_SEMANTIC_SCREENING:'0'}});
let buf='';const port=await new Promise((resolve,reject)=>{server.stdout.on('data',x=>{buf+=x;if(buf.includes('\n'))resolve(JSON.parse(buf.split('\n')[0]).port);});server.on('exit',c=>reject(new Error('H11 server exited '+c)));});
const chrome=spawn(process.env.CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--remote-debugging-port=9366',`--user-data-dir=${join(work,'chrome')}`,'--no-first-run','--no-default-browser-check','about:blank'],{stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let socket,id=0;const pending=new Map();const errors=[];
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function ev(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function until(expression,label){for(let i=0;i<200;i++){if(await ev(expression))return;await sleep(150);}throw new Error('Timed out '+label);}
const click=selector=>ev(`document.querySelector(${JSON.stringify(selector)}).click(),true`);
async function shot(name){const r=await send('Page.captureScreenshot',{format:'png'});writeFileSync(join(OUT,name+'.png'),Buffer.from(r.data,'base64'));}
async function login(who,pin){await ev(`(async()=>{const c=await(await fetch('/api/config')).json();const h={'Content-Type':'application/json','X-Tideway-Token':c.csrf_token};await fetch('/api/session/logout',{method:'POST',headers:h,body:'{}'});const r=await fetch('/api/session/login',{method:'POST',headers:h,body:JSON.stringify({operator_id:${JSON.stringify(who)},pin:${JSON.stringify(pin)}})});if(!r.ok)throw Error('login failed');return true;})()`);await send('Page.reload');await until('!!state.dashboard && !state.busy','dashboard');await click('[data-view="rescue"]');}
try{
 let tabs;for(let i=0;i<100;i++){try{tabs=await(await fetch('http://127.0.0.1:9366/json')).json();break;}catch{await sleep(100);}}
 socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r,{once:true}));
 socket.addEventListener('message',event=>{const r=JSON.parse(event.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(r.error.message)):p.resolve(r.result);}else if(r.method==='Runtime.exceptionThrown')errors.push(r.params.exceptionDetails.text);});
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:`http://127.0.0.1:${port}/`});await until("document.readyState==='complete' && typeof state!=='undefined'",'page');
 await login('eval-accountant','374296');await click('[data-action="run-agent"]');await until('!!state.dashboard.plan && !state.busy','H11 plan');
 const plan=await ev('state.dashboard.plan');const b=plan.bundles[0];if(!b.feasible||b.probability_breach_after<=plan.risk_target)throw Error('Expected feasible above-target H11');
 if(!await ev("document.querySelector('.residual-risk').textContent.includes('Target not met')"))throw Error('Missing risk notice');
 const approvals=[];
 for(const [who,pin] of [['eval-accountant','374296'],['eval-owner','893741']]){
  if(who==='eval-owner')await login(who,pin);
  await click('[data-action="approve"]');await until("document.querySelector('#approve-dialog').open",'approval dialog');
  if(!await ev("!document.querySelector('#approve-risk-label').hidden && document.querySelector('#approve-risk-ack').required && !document.querySelector('#approve-risk-ack').checked"))throw Error('Consent missing or prechecked');
  await ev(`document.querySelector('#confirm-amount').value=money(state.dashboard.plan.bundles[0].exposure_minor);document.querySelector('#approve-pin').value=${JSON.stringify(pin)};true`);
  await ev("document.querySelector('#approve-form').requestSubmit(),true");await sleep(200);
  if(!await ev("document.querySelector('#approve-dialog').open && !document.querySelector('#approve-risk-ack').checked"))throw Error('Unchecked risk consent accepted');
  await shot(who+'-unchecked-risk');await click('#approve-risk-ack');await sleep(3300);await ev("document.querySelector('#approve-form').requestSubmit(),true");await until("!document.querySelector('#approve-dialog').open && !state.busy",'approval saved');approvals.push(who);
  if(await ev('state.dashboard.mandates.length>0'))break;
 }
 const mandates=await ev('state.dashboard.mandates');const mandate=mandates.find(m=>m.mandate.plan_id===plan.plan_id)?.mandate;
 if(!mandate)throw Error('No H11 mandate');
 for(const a of mandate.approvals){const x=a.risk_acknowledgement;if(!x?.acknowledged||x.plan_id!==plan.plan_id||x.plan_hash!==plan.plan_hash||x.bundle_id!==b.bundle_id||x.probability_breach_after!==b.probability_breach_after||x.risk_target!==plan.risk_target)throw Error('Incorrect exact consent binding');}
 await shot('signed-exact-risk');
 const after=digest();if(before!==after)throw Error('Source changed');if(errors.length)throw Error(errors.join(';'));
 writeFileSync(join(OUT,'browser-verification.json'),JSON.stringify({passed:true,scope:'Actual H11 proposal and approval dialogs on disposable synthetic ledger; scripted test operators, not real consent.',source_tree_sha256:before,source_unchanged:true,probability_breach_after:b.probability_breach_after,risk_target:plan.risk_target,unchecked_consent_blocked:true,fresh_unchecked_control_for_every_approver:true,exact_acknowledgement_in_each_signed_approval:true,approvers:approvals,mandate_approvals:mandate.approvals.length,page_errors:errors,executed:false},null,2)+'\n');
 console.log('H11 browser consent passed',b.probability_breach_after,approvals);
}finally{socket?.close();chrome.kill();server.kill();await sleep(400);rmSync(work,{recursive:true,force:true});}
