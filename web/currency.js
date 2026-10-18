"use strict";

// Exact, shared presentation/input conversion. Ledger values remain integer minor units.
globalThis.TidewayMoney = (() => {
  let rates = {};
  const MAX = 100000000000000;
  function decimal(raw, signed=false) {
    const text = String(raw ?? '').trim();
    if(text.length>40)throw new Error('Amount exceeds the allowed limit.');
    const pattern = signed ? /^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$/ : /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$/;
    if (!pattern.test(text)) throw new Error('Enter a nonnegative amount with at most two decimal places and valid comma grouping.');
    const negative=text.startsWith('-'), clean=text.replace(/[,+-]/g,''), [whole,fraction='']=clean.split('.');
    const value=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));
    return negative?-value:value;
  }
  function checked(value, limit=Number.MAX_SAFE_INTEGER) {
    if(value>BigInt(limit)||value<BigInt(-limit))throw new Error('Amount exceeds the allowed limit.');
    return Number(value);
  }
  function parseInput(raw,code) {
    if(!valid(code))throw new Error('Choose a supported input currency.');
    return decimal(String(raw??'').trim().replace(new RegExp('^'+code+'\\s*','i'),''));
  }
  function configure(table) {
    const next={};
    for(const [code,value] of Object.entries(table)) {
      const amount=decimal(value);
      if(!/^[A-Z]{3}$/.test(code)||amount<=0n)throw new Error('Invalid illustrative currency rate.');
      next[code]=amount;
    }
    rates=next;
  }
  function valid(code){return Object.hasOwn(rates,code);}
  function bigConvert(minor,from,to,round='nearest') {
    if((typeof minor!=='bigint'&&!Number.isSafeInteger(minor))||!valid(from)||!valid(to))throw new Error('A supported currency and exact amount are required.');
    const n=BigInt(minor), negative=n<0n, numerator=(negative?-n:n)*rates[to], denominator=rates[from];
    let q=numerator/denominator, r=numerator%denominator;
    if(round==='nearest'&&r*2n>=denominator||round==='up'&&r)q++;
    return negative?-q:q;
  }
  function convert(minor,from,to,round='nearest'){return checked(bigConvert(minor,from,to,round));}
  function units(minor) {
    if(typeof minor!=='bigint'&&!Number.isSafeInteger(minor))throw new Error('Amount is not an exact integer.');
    const value=BigInt(minor), n=value<0n?-value:value;
    return `${value<0n?'-':''}${n/100n}.${String(n%100n).padStart(2,'0')}`;
  }
  function format(minor,from,to=from,{decimals,native=false}={}) {
    if(typeof minor!=='number'||!Number.isSafeInteger(minor))return '—';
    const changed=!native&&from!==to, n=changed?bigConvert(minor,from,to):BigInt(minor);
    if(changed&&minor!==0&&n===0n)return `≈ ${minor<0?'−':''}${to} < 0.01`;
    const [whole,fraction]=units(n<0n?-n:n).split('.');
    const number=whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+((decimals===2||fraction!=='00')?`.${fraction}`:'');
    return `${changed?'≈ ':''}${n<0?'−':''}${native?from:to} ${number}`;
  }
  function capture(raw,code,base,initialText,initialMinor) {
    if(String(raw)===String(initialText)&&Number.isSafeInteger(initialMinor))return {raw:String(raw),code,base,minor:initialMinor};
    try {
      if(String(raw).trim()==='')return {raw:'',code,base,minor:0,empty:true};
      const entered=parseInput(raw,code);
      const minor=convert(entered,code,base);
      if(entered>0&&minor===0)throw new Error('Amount is below one ledger minor unit; enter a larger amount.');
      if(minor>MAX)throw new Error('Amount exceeds the ledger limit.');
      return {raw:String(raw),code,base,minor};
    }catch(error){return {raw:String(raw),code,base,error:error.message};}
  }
  function value(model,fallback,base,show) {
    if(model&&model.code===show)return model.raw;
    if(model?.error)throw new Error('Fix the invalid amount before changing currency.');
    if(model?.empty)return '';
    return fallback===null&&!model?'':units(bigConvert(model?.minor??fallback,base,show));
  }
  function read(model,fallback=0) {
    if(model?.error)throw new Error(model.error);
    const n=model?.minor??fallback;
    if(!Number.isSafeInteger(n)||n<0||n>MAX)throw new Error('Amount exceeds the ledger limit.');
    return n;
  }
  function text(value,to,protectedNames=[]) {
    const source=String(value??'');
    if(!valid(to))return source;
    // Most nodes contain no foreign monetary token; avoid scanning every identity for each table cell.
    const expression=/(?<![\w≈])([−-]?)([A-Z]{3})\s+([−-]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?(?!(?:\w|,\d|\.\d))/g;
    if(![...source.matchAll(expression)].some(m=>valid(m[2])&&m[2]!==to))return source;
    const protectedRanges=[];
    for(const name of protectedNames) {
      if(!name)continue;
      let i=source.indexOf(name);
      while(i>=0){protectedRanges.push([i,i+name.length]);i=source.indexOf(name,i+Math.max(1,name.length));}
    }
    // Require a currency code and whitespace: dates, IDs, percentages and account numbers are not amounts.
    return source.replace(expression,(match,prefix,code,inner,whole,fraction,offset)=>{
      if(!valid(code)||code===to||protectedRanges.some(([a,b])=>offset<b&&offset+match.length>a))return match;
      try{return format(checked(decimal(`${prefix||inner?'-':''}${whole}${fraction||''}`,true)),code,to);}catch(_){return match;}
    });
  }
  return {configure,valid,convert,bigConvert,units,format,capture,value,read,text,parse:(raw,signed=false)=>checked(decimal(raw,signed)),parseBig:decimal,parseInput,MAX};
})();
