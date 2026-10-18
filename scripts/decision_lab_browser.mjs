// Optional extension to the real-browser regression driver. No provider calls.
export async function checkDecisionLab({evaluate, click, until, view, viewport, shot, phoneCheck, loginAs, reload}) {
  await loginAs("nadia", "2468");
  await evaluate("api('/api/sandbox/reset',{business_id:'shapla-services'})");
  await reload();
  await viewport(1440,900);
  await evaluate("state.businessId='shapla-services';loadDashboard({resetTarget:true})");
  await view("lab");
  const idle = () => until("!document.querySelector('.lab-tabs button:disabled')", "decision lab calculation", 200);
  const tab = async id => {await click(`[data-action=lab-tab][data-tab=${id}]`);await idle();};
  await click('[data-action=lab-reverse]');await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('one-day-less')")) throw new Error("Reverse-stress witness missing");
  await shot('30-lab-reverse');
  await tab('promises');await click('[data-action=lab-promises]');await idle();
  if (!await evaluate("document.querySelector('.lab-panel table')?.textContent.includes('25%')")) throw new Error("Agreement stress missing assumed cases");
  await shot('31-lab-promises');
  await tab('frontier');await click('[data-action=lab-frontier]');await idle();
  if (!await evaluate("document.querySelector('.lab-panel table')?.textContent.includes('no-action')")) throw new Error("Recovery comparison missing baseline");
  await shot('32-lab-frontier');
  await tab('privacy');await click('[data-action=lab-privacy]');await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('Network calls: 0')")) throw new Error("Privacy preview did not render");
  await shot('33-lab-privacy');
  await click('[data-action=lab-return-chat]');
  if (!await evaluate("state.view==='assistant' && document.querySelector('#chat-input').value.includes('Explain')")) throw new Error("Privacy preview did not return unsent question to chat");
  await view('lab');await tab('replay');
  await click('[data-action=lab-challenge-delay]');await idle();
  await click('[data-action=lab-challenge-block]');await idle();
  await click('[data-action=lab-challenge-instruction]');await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('forbidden_execution_tool_blocked')")) throw new Error("Judge challenge guard result missing");
  await evaluate(`(async()=>{const capsule=await api('/api/lab/capsule',{business_id:state.businessId,target_date:state.targetDate});const file=new File([JSON.stringify(capsule)],'private-replay.json',{type:'application/json'});const dt=new DataTransfer();dt.items.add(file);document.querySelector('#lab-capsule-file').files=dt.files;})()`);
  await click('[data-action=lab-replay]');
  await until("document.querySelector('.lab-panel')?.textContent.includes('Replay matched')", "capsule file read and replay result",200);
  await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('Replay matched')")) throw new Error("Downloaded capsule could not be replayed in browser");
  await shot('34-lab-replay');
  await tab('bilateral');
  // A three-decimal money input must be refused before any request, not rounded.
  await evaluate(`(()=>{window.__labFetch=window.fetch;window.__labRequests=0;window.fetch=(...args)=>{if(String(args[0]).includes('/api/lab/bilateral'))window.__labRequests++;return window.__labFetch(...args);};const f=document.querySelector('[data-lab-field=supplierCash]');f.value='1000.001';f.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click('[data-action=lab-bilateral]');
  if (!await evaluate("window.__labRequests===0 && document.body.textContent.includes('at most two decimal places')")) throw new Error("Invalid fractional money reached a financial calculation");
  await evaluate(`(()=>{window.fetch=window.__labFetch;delete window.__labFetch;const f=document.querySelector('[data-lab-field=supplierCash]');f.value='60000';f.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click('[data-action=lab-bilateral]');await idle();
  if (!await evaluate("!!document.querySelector('[data-action=lab-bilateral-propose]')")) throw new Error("Jointly feasible bilateral quotes missing");
  await shot('35-lab-bilateral');
  await click('[data-action=lab-bilateral-propose]');await until("state.view==='rescue' && !state.busy", "bilateral saved proposal",200);
  if (!await evaluate("document.querySelector('#view').textContent.includes('Two-sided synthetic liquidity terms') && !state.dashboard.plan.approvals.length")) throw new Error("Saved proposal omitted supplier assumptions or inherited approval");
  await view('lab');await tab('events');
  await click('[data-action=lab-watch-toggle]');
  await until("document.querySelector('#pin-dialog').open", "monitor PIN");
  await evaluate("document.querySelector('#pin-input').value='2468';document.querySelector('#pin-form').requestSubmit()");
  await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('Monitor armed')")) throw new Error("Monitor did not arm");
  await evaluate(`(()=>{const field=document.querySelector('[data-lab-field=eventType]');field.value='unexpected_expense';field.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await click('[data-action=lab-event]');await until("document.querySelector('#pin-dialog').open", "event PIN");
  await evaluate("document.querySelector('#pin-input').value='2468';document.querySelector('#pin-form').requestSubmit()");
  await idle();
  if (!await evaluate("document.querySelector('.lab-panel').textContent.includes('proposal waiting for human approval') && !state.dashboard.plan.approvals.length")) throw new Error("Event failed to create a fresh unapproved proposal");
  await shot('36-lab-events');
  await viewport(375,812,true);
  for (const id of ['reverse','promises','frontier','events','replay','privacy','bilateral']) {
    await tab(id);await phoneCheck(`decision lab ${id}`,'#view');
  }
  await shot('37-lab-mobile',false);
  await loginAs('guest','0000');await reload();await view('lab');await tab('events');
  if (!await evaluate("!document.querySelector('[data-action=lab-event],[data-action=lab-watch-toggle]')")) throw new Error("Viewer received owner event controls");
  await tab('bilateral');await click('[data-action=lab-bilateral]');await idle();
  if (!await evaluate("!document.querySelector('[data-action=lab-bilateral-propose]')")) throw new Error("Viewer received proposal control");
  await loginAs('nadia','2468');await reload();await viewport(1440,900);
}
