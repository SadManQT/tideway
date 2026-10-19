// Assertions on financial explanations, missing data and malicious display text.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

let currency = 'BDT';
const esc = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const context={window:{},esc,day:x=>x,isNum:Number.isFinite,money:x=>`${currency} ${(x/100).toFixed(2)}`};
vm.runInNewContext(readFileSync(new URL('../web/decision-review.js',import.meta.url),'utf8'),context);
const ui=context.window.TidewayReview;
const original={payroll:{next_date:'2026-10-31'},customer_receipts:[{customer:'A',settled_invoices:10,late_settlements:7,limited_history:false,open_amount_minor:50000,expected_by_payroll_minor:0,next_receipt:{id:'a',date:'2026-11-02',amount_minor:50000,after_payroll:true}}]};
let html=ui.customers(original);
assert.match(html,/7 \/ 10 settled invoices were paid late/);
assert.match(html,/Expected after payroll/);
assert.match(html,/2026-10-31/);
assert.match(html,/data-customer="A"/);
const sameDay=structuredClone(original);sameDay.customer_receipts[0].next_receipt.date='2026-10-31';
assert.match(ui.customers(sameDay),/Same day: check payment timing/);
const missing=structuredClone(original);missing.payroll.next_date=null;missing.customer_receipts[0].next_receipt=null;missing.customer_receipts[0].settled_invoices=0;
assert.match(ui.customers(missing),/No settled payment history/);
assert.match(ui.customers(missing),/Receipt date needs review/);
const hostile=structuredClone(original);hostile.customer_receipts[0].customer='"><img src=x onerror=alert(1)>';
assert.doesNotMatch(ui.customers(hostile),/<img/);
assert.match(ui.customers(original,'bn'),/গ্রাহকের টাকা/);
const plan={risk_target:0.1}, option={economic_cost_minor:1500,probability_breach_after:0.12,after:{minimum_cash_minor:33500,reserve_floor_minor:30000}};
for (const code of ['BDT','USD','CNY']) {
  currency=code;html=ui.bundle(plan,option);
  assert.ok(html.includes(`${code} 15.00`) && html.includes(`${code} 335.00`) && html.includes(`${code} 300.00`));
  assert.match(html,/12% · target 10%/);assert.match(html,/Risk target exceeded/);
  assert.match(html,/Exposure is the amount affected/);
  assert.ok(ui.customers(original).includes(`${code} 500.00`));
}
assert.match(ui.bundle(plan,{...option,probability_breach_after:0.10000000000000002}),/10\.000000000000002%/);
assert.match(ui.bundle(plan,{...option,probability_breach_after:0.1}),/Within the simulated risk target/);
assert.match(ui.bundle(plan,{}),/Not available/);
assert.match(ui.bundle(plan,{}),/Risk estimate needs review/);
assert.doesNotMatch(ui.bundle({},{}),/Within the simulated risk target/);
assert.match(ui.bundle(plan,{...option,feasible:false}),/cannot be approved/);
assert.doesNotMatch(ui.bundle(plan,{...option,feasible:false}),/Understand this option before approving/);
assert.equal(original.customer_receipts[0].next_receipt.date,'2026-11-02');
console.log('Decision-review checks passed: history, dates, missing data, risk precision, currency labels and escaping.');
