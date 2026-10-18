// The actual browser exercises production endpoints on a throwaway synthetic DB.
export async function checkOwnerView({evaluate,click,until,view,viewport,shot,phoneCheck,loginAs,reload}) {
  await loginAs('nadia','2468');await reload();
  await evaluate("api('/api/sandbox/reset',{business_id:'shapla-services'})");
  await evaluate("state.ownerDetailed=false;loadDashboard({businessId:'shapla-services',resetTarget:true})");
  await view('overview');
  const idle = () => until("!state.busy && !document.querySelector('.owner-view button:disabled')",'Owner view calculation',240);
  const input = (name,value) => evaluate(`(()=>{const el=document.querySelector('[data-owner-field=${name}]');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  if (!await evaluate("!!document.querySelector('.owner-view') && !state.ownerDetailed")) throw new Error('Simple Owner view is missing');
  const initial = await evaluate('state.dashboard.snapshot_hash');
  await shot('40-owner-simple');
  await click('[data-action=owner-language]');
  if (!await evaluate("document.querySelector('.owner-view').lang==='bn' && document.querySelector('.owner-head').textContent.includes('সিদ্ধান্ত')")) throw new Error('Bengali Owner view failed');
  await viewport(375,812,true);await phoneCheck('Bengali Owner view','#view');await shot('41-owner-bangla-mobile');
  await click('[data-action=owner-language]');await viewport(1440,900);
  await evaluate("(()=>{window.__ownerFetch=window.fetch;window.__ownerCalls=0;window.fetch=(...args)=>{if(String(args[0]).includes('/api/owner/'))window.__ownerCalls++;return window.__ownerFetch(...args);};})()");
  await input('amount','1000.001');await click('[data-action=owner-expense]');
  if (!await evaluate("window.__ownerCalls===0 && document.querySelector('#toast').textContent.includes('two decimal places')")) throw new Error('Fractional spending was not rejected locally');
  await input('amount','1234.56');await click('[data-action=owner-expense]');await idle();
  if (!await evaluate("document.querySelector('.owner-results').textContent.includes('1,234.56')")) throw new Error('Exact expense preview missing');
  if (!await evaluate(`state.dashboard.snapshot_hash===${JSON.stringify(initial)} && !state.dashboard.plan && !state.dashboard.mandates.length`)) throw new Error('Expense preview changed financial state');
  await evaluate("(()=>{window.fetch=window.__ownerFetch;delete window.__ownerFetch;document.querySelector('.owner-timeline').closest('details').open=true;})()");
  await evaluate("(()=>{const el=document.querySelector('#display-currency');el.value='USD';el.dispatchEvent(new Event('change',{bubbles:true}));})()");
  if (!await evaluate("document.querySelector('.owner-results').textContent.includes('USD') && document.querySelector('[data-owner-field=amount]').value==='1234.56'")) throw new Error('Display FX changed the native expense input or failed to render');
  await evaluate("(()=>{const el=document.querySelector('#display-currency');el.value='';el.dispatchEvent(new Event('change',{bubbles:true}));})()");
  await evaluate("document.querySelector('.owner-timeline').closest('details').open=true");
  const source = await evaluate("document.querySelector('[data-action=owner-source]').dataset.id");
  await click('[data-action=owner-source]');
  if (!await evaluate(`state.view==='records' && state.recordQuery===${JSON.stringify(source)} && document.querySelector('#view').textContent.includes(${JSON.stringify(source)})`)) throw new Error('Source record link failed');
  await view('overview');
  // Hold a real response to exercise the pending state without timing races.
  await evaluate("(()=>{window.__ownerFetch=window.fetch;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/api/owner/coach')){const gate=new Promise(resolve=>{window.__ownerRelease=resolve;});const response=await window.__ownerFetch(...args);await gate;return response;}return window.__ownerFetch(...args);};})()");
  await click('[data-action=owner-coach]');
  if (!await evaluate("[...document.querySelectorAll('[data-owner-field], [data-owner-protect]')].every(el=>el.matches(':disabled'))")) throw new Error('Owner inputs can change while a calculation is pending');
  await evaluate("window.__ownerRelease();window.fetch=window.__ownerFetch;delete window.__ownerFetch");await idle();
  if (!await evaluate("document.querySelectorAll('.owner-option').length===3 && !!document.querySelector('[data-action=owner-propose]')")) throw new Error('Three priority previews missing');
  if (!await evaluate("document.querySelector('.owner-view').textContent.includes('The extra-expense preview above is excluded') && document.querySelector('.owner-results').textContent.includes('Reserve shortfall after this expense') && document.querySelectorAll('.owner-option li strong').length>0 && [...document.querySelectorAll('.owner-option li strong')].every(el=>['Ask for later payment','Offer an early-payment discount'].includes(el.textContent))")) throw new Error('Scenario, saved-ledger and action explanations are missing');
  await shot('42-owner-priorities');
  await viewport(375,812,true);await phoneCheck('Owner recovery options','#view');await shot('43-owner-priorities-mobile');await viewport(1440,900);
  await evaluate("(()=>{window.__ownerFetch=window.fetch;window.fetch=async(...args)=>{const response=await window.__ownerFetch(...args);if(String(args[0]).endsWith('/api/owner/brief'))window.__ownerBrief=await response.clone().json();return response;};})()");
  // An unchecked edit must not silently change the report being exported.
  await input('amount','999.99');
  await click('[data-action=owner-brief]');await idle();
  if (!await evaluate(`window.__ownerBrief?.snapshot_hash===${JSON.stringify(initial)} && window.__ownerBrief.html.includes('Private business figures') && window.__ownerBrief.html.includes('Extra expense tested: BDT 1,234.56') && !window.__ownerBrief.html.includes('<script')`)) throw new Error('Private brief export is not bound to the last checked report');
  await evaluate("window.fetch=window.__ownerFetch;delete window.__ownerFetch");
  await click('[data-action=owner-propose][data-priority=lowest_cost]');
  await until("state.view==='rescue' && !state.busy",'Fresh coach proposal',240);
  if (!await evaluate("state.dashboard.plan?.status==='pending' && !state.dashboard.plan.approvals.length && !state.dashboard.mandates.length")) throw new Error('Coach bypassed the normal approval boundary');
  await loginAs('guest','0000');await reload();
  if (await evaluate('state.ownerDetailed')) await click('[data-action=owner-simple]');
  await click('[data-action=owner-coach]');await idle();
  if (await evaluate("!!document.querySelector('[data-action=owner-propose]')")) throw new Error('Viewer can save a coach proposal');
  if (await evaluate("!!document.querySelector('a[href*=guide],a[href*=personal-prep]')")) throw new Error('Personal prep is reachable from the product');
  await shot('44-owner-viewer');
}
