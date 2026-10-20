"use strict";

// Plain-language help layer. It only adds explanations and navigation shortcuts;
// it never calls the API, approves, executes or changes records. Any failure here
// is contained so the financial UI keeps working without help.
window.TidewayHelp = (() => {
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* preference is optional */ } },
  };

  // ---- What each page is for, in everyday words ----------------------------
  const PAGES = {
    overview: {
      what: "Will the business have enough cash on the day it matters (for example payroll day)? This page answers that and shows how likely a shortfall is.",
      who: "Everyone",
      steps: ["Read the weather: clear means fine, unsettled means watch out, storm means cash is likely to run short.",
        "Find the lowest-cash day and compare it with your safety cushion (reserve floor).",
        "Thinking about a purchase? Use “test an expense” first. Switch to Detailed view for charts."],
      safe: "Read-only. Nothing on this page moves money.",
    },
    rescue: {
      what: "When a cash gap is coming, Tideway suggests ways to close it: pay a supplier later, offer a customer a small discount to pay sooner, or send reminders. People decide.",
      who: "Owners and accountants approve; viewers can read",
      steps: ["Ask the agent for options, then compare cost, remaining risk and who has to agree.",
        "Approve with your own PIN. Large amounts need a second person.",
        "Execution is a separate, final step and only happens in the practice sandbox."],
      safe: "The AI can propose but can never approve or execute. Every approval needs a person and a PIN.",
    },
    assistant: {
      what: "Ask questions in plain words, in your own language, and get answers built from Tideway's own calculations.",
      who: "Everyone",
      steps: ["Type “hi” for a quick briefing on today's cash position.",
        "Ask something like “What if Nila Traders pays 20 days late?”",
        "Open the plan under an answer to see exactly which tools were used."],
      safe: "The assistant can read and explain. It cannot move money or change records.",
    },
    inbox: {
      what: "Paste a bank SMS, payment alert or chat message. Tideway turns it into draft records so nobody has to type them in.",
      who: "Owners and accountants save; everyone can try",
      steps: ["Paste the message and press extract.",
        "Check every drafted field: amount, date, customer or supplier.",
        "Confirm to save. Suspicious instructions inside messages are flagged."],
      safe: "Nothing is saved until a person confirms. Text inside a message never gets authority.",
    },
    whatif: {
      what: "Try “what if” questions: a customer pays late, an unexpected bill arrives, sales drop. See the effect on cash instantly.",
      who: "Everyone",
      steps: ["Move a slider or enter an amount.", "Watch the lowest cash and the shortfall risk change.", "Nothing you try here is saved."],
      safe: "Exploration only. Your records are not changed.",
    },
    lab: {
      what: "Stress-test a plan before you trust it: how late can a customer be before the plan breaks, and which recovery option is cheapest for the risk?",
      who: "Analysts, owners and accountants",
      steps: ["Find the breaking point for each customer.", "Compare recovery options side by side.",
        "Preview exactly what an optional cloud AI would see before you ever send anything."],
      safe: "Analysis only. Any change it suggests still needs the normal approvals.",
    },
    treasury: {
      what: "Bank-grade reports in one place: a 13-week cash plan, a working-capital health score, a scan for duplicate or unusual payments, and a signed credit passport you can share with a lender.",
      who: "Finance teams, owners, and lenders reviewing the business",
      steps: ["Read the week-by-week table and look for weeks below the reserve.",
        "Check the health score and the suggestions that would raise it most.",
        "Run the payment-integrity scan; issue and verify a credit passport."],
      safe: "Reports are read-only. Issuing a passport is recorded in the audit trail; no money moves.",
    },
    portfolio: {
      what: "For banks and lenders: an early-warning radar across many small-business clients, ranking who is likely to run short of cash and why.",
      who: "Relationship managers and credit-risk teams",
      steps: ["Start with the red and amber counts.", "Sort the table by risk and read each client's main driver.",
        "Apply an economic shock to see who would move into danger, then check the backtest card."],
      safe: "Runs on a synthetic portfolio only. It never reads other workspaces and its suggestions are advice, not credit decisions.",
    },
    records: {
      what: "The ledger behind every number: invoices you are owed, bills you owe, and past transactions.",
      who: "Everyone",
      steps: ["Filter by type or search for a customer or supplier.", "Red flags mark changed bank details or suspicious text.",
        "Export to a spreadsheet from the Evidence page."],
      safe: "Viewing records changes nothing. Suspicious text is quarantined and shown as plain data.",
    },
    team: {
      what: "Who can see and act for this business. Invite colleagues with a one-time code and the right role.",
      who: "Owners manage the team",
      steps: ["Owner: full control, including policy and resuming the agent.", "Accountant: can propose and approve plans.",
        "Viewer: read-only, cannot approve anything."],
      safe: "Every request is checked against membership, so businesses never see each other's data.",
    },
    security: {
      what: "The safety controls: who may do what, spending limits, an emergency stop for the AI, payee verification and a one-click attack self-test.",
      who: "Owners; everyone can run the self-test",
      steps: ["Run the self-test and watch every simulated attack get blocked.",
        "The kill switch pauses the AI instantly; only the owner can resume it.",
        "Verify a flagged payee by calling back a number already on file."],
      safe: "Controls here protect money; they cannot be changed by the AI or by message text.",
    },
    evidence: {
      what: "Proof of what happened: a tamper-evident audit trail, signed approvals, receipts and exports for your accountant or bank.",
      who: "Everyone, auditors and reviewers",
      steps: ["Run the tamper drill: change one record and watch the chain detect it.",
        "Open a receipt to see before and after fingerprints of the ledger.",
        "Export evidence, records or the draft bank payment file."],
      safe: "Exports are read-only copies. The draft bank file is never sent.",
    },
  };

  // ---- Jargon, explained once per page -------------------------------------
  const TERMS = [
    [["reserve floor", "reserve"], "Reserve floor", "The minimum cash you want to keep in the bank at all times: your safety cushion."],
    [["shortfall", "cash gap"], "Shortfall", "How much cash would be missing on a given day compared with what you need."],
    [["target date"], "Target date", "The day you care about, such as payroll day. Tideway also looks 14 days beyond it so problems can't hide just after."],
    [["Monte Carlo"], "Monte Carlo", "Replaying the coming weeks many times with realistic random payment delays to estimate the chance of running short."],
    [["breach risk", "breach probability", "breach"], "Breach", "Cash falling below your reserve floor. The risk is the share of simulated futures where that happens."],
    [["likely scenario", "likely path", "likely forecast"], "Likely scenario", "A forecast based on how each customer actually tends to pay, predicted by TidePay."],
    [["stress scenario", "stress path", "stress test"], "Stress scenario", "A cautious forecast in which slow payers are slower still."],
    [["mandate"], "Mandate", "A digitally signed permission slip listing exactly what people approved, for how much, and until when."],
    [["maker-checker"], "Maker-checker", "One person proposes and a different person approves: the standard bank control against mistakes and fraud."],
    [["deferral", "defer"], "Deferral", "Agreeing with a supplier to pay a bill later than planned."],
    [["early-payment discount", "early payment"], "Early-payment discount", "A small discount offered to a customer for paying sooner, bringing cash in earlier."],
    [["APR"], "APR", "The yearly cost of a discount or loan, so different options can be compared fairly."],
    [["kill switch"], "Kill switch", "An emergency stop that pauses the AI agent at once. Only the owner can resume it."],
    [["circuit breaker"], "Circuit breaker", "An automatic pause after repeated blocked attempts, like a fuse that trips."],
    [["audit trail", "audit log", "audit"], "Audit trail", "A permanent record of who did what and when. Each entry is chained to the previous one."],
    [["hash"], "Hash", "A digital fingerprint of data. If anything changes, even one digit, the fingerprint changes."],
    [["injection"], "Injection", "Hidden instructions inside a message that try to trick an AI. Tideway flags them and never obeys them."],
    [["TidePay"], "TidePay", "Tideway's own model that predicts how late each invoice is likely to be paid."],
    [["TideLM"], "TideLM", "Tideway's own language model that understands questions and pasted messages in several languages."],
    [["DSO"], "DSO", "Days Sales Outstanding: on average, how many days customers take to pay you."],
    [["DPO"], "DPO", "Days Payable Outstanding: on average, how many days you take to pay suppliers."],
    [["HHI", "concentration"], "Concentration", "How dependent you are on a few customers. High concentration means one late payer can hurt a lot."],
    [["13-week", "TWCF"], "13-week cash flow", "A week-by-week cash plan for the next quarter: the format banks and lenders ask for."],
    [["credit passport", "passport"], "Credit passport", "A signed summary of the business's cash health to share with a lender. Any edit breaks the signature."],
    [["HMAC"], "HMAC signature", "A secret-key signature that reveals tampering. Here only the issuing Tideway can verify it."],
    [["counter-offer", "counter offer"], "Counter-offer", "The other side proposes different terms. It becomes a new proposal that needs fresh approval."],
    [["step-up"], "Step-up", "Entering your PIN again for a sensitive action."],
    [["separation of duties"], "Separation of duties", "Whoever verified a payee cannot be the only person approving payments to them."],
    [["pseudonym", "pseudonymised", "pseudonymized"], "Pseudonym", "A stand-in name, so the real name is not shared with an outside service."],
    [["sandbox"], "Sandbox", "A safe practice environment with fictional businesses. No real money or bank is connected."],
    [["pain.001", "ISO 20022"], "ISO 20022 pain.001", "The international bank file format for payment instructions. Tideway only drafts it; it is never sent."],
    [["runway"], "Runway", "How many days your cash lasts at the current spending rate."],
    [["witness"], "Witness checkpoint", "A separate copy of the latest audit position that proves the log was not cut short."],
    [["exposure"], "Exposure", "The total amount of money affected by an approval."],
    [["read-back"], "Read-back", "After executing, Tideway reads the ledger again to confirm the change really happened."],
    [["quarantine", "quarantined"], "Quarantine", "Suspicious text is set aside and shown only as data, never treated as an instruction."],
    [["backtest"], "Backtest", "Checking a warning system against simulated outcomes it did not see when it made its call."],
    [["AUC"], "AUC", "How well a score ranks risky clients above safe ones: 0.5 is a coin flip, 1.0 is perfect."],
    [["Brier"], "Brier score", "The accuracy of probability forecasts. Lower is better."],
  ];
  const lookup = new Map();
  for (const [aliases, title, text] of TERMS) for (const alias of aliases) lookup.set(alias.toLowerCase(), {title, text, key: title});
  const pattern = new RegExp(`(?<![\\w-])(${[...lookup.keys()].sort((a, b) => b.length - a.length)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![\\w-])`, "i");
  const SKIP = "input,textarea,select,option,button,a,pre,code,script,style,svg,dialog,.tw-term,.tw-page-help,.msg.user,[data-currency-original],.nav-item,.pill,th";

  const enabled = () => store.get("tideway.help.v1", "on") !== "off";
  const currentView = () => { try { return typeof state !== "undefined" ? state.view : ""; } catch { return ""; } };
  const currentRole = () => { try { return typeof role === "function" ? role() : ""; } catch { return ""; } };

  function decorate(root) {
    if (!enabled() || !root) return;
    const seen = new Set();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => !node.nodeValue.trim() || node.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const nodes = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node);
    for (const node of nodes) {
      const match = pattern.exec(node.nodeValue);
      if (!match) continue;
      const entry = lookup.get(match[1].toLowerCase());
      if (!entry || seen.has(entry.key)) continue;
      seen.add(entry.key);
      const after = node.splitText(match.index);
      after.nodeValue = after.nodeValue.slice(match[1].length);
      const term = document.createElement("span");
      term.className = "tw-term";
      term.tabIndex = 0;
      term.setAttribute("role", "button");
      term.dataset.term = entry.key;
      term.setAttribute("aria-label", `${match[1]}: explain`);
      term.textContent = match[1];
      node.parentNode.insertBefore(term, after);
    }
  }

  // ---- Page explainer card -------------------------------------------------
  function pageCard() {
    const view = currentView();
    let host = document.getElementById("tw-page-help");
    const anchor = document.getElementById("view");
    if (!anchor) return;
    if (!host) {
      host = document.createElement("section");
      host.id = "tw-page-help";
      host.className = "tw-page-help";
      host.setAttribute("aria-label", "About this page");
      anchor.parentNode.insertBefore(host, anchor);
    }
    const page = PAGES[view];
    if (!enabled() || !page) { host.hidden = true; host.dataset.view = ""; return; }
    const folded = store.get(`tideway.help.fold.${view}`, "open") === "folded";
    const key = `${view}|${folded}|${currentRole()}`;
    if (host.dataset.key === key && !host.hidden) return;
    host.dataset.key = key;
    host.hidden = false;
    const r = currentRole();
    host.innerHTML = `<div class="tw-help-head"><span class="tw-help-badge" aria-hidden="true">?</span>
      <div class="tw-help-lead"><strong>What is this page?</strong> <span>${escape(page.what)}</span></div>
      <button type="button" class="button small ghost" data-help-fold="${escape(view)}" aria-expanded="${!folded}">${folded ? "Show how to use it" : "Hide"}</button></div>
      ${folded ? "" : `<div class="tw-help-body"><ol>${page.steps.map((s) => `<li>${escape(s)}</li>`).join("")}</ol>
      <div class="tw-help-meta"><span class="tw-chip">For: ${escape(page.who)}</span>${r ? `<span class="tw-chip">You are signed in as: ${escape(r)}</span>` : ""}<span class="tw-chip tw-safe">${escape(page.safe)}</span></div></div>`}`;
  }

  // ---- Glossary popover ----------------------------------------------------
  let pop = null, popFor = null;
  function showTerm(el) {
    const entry = [...lookup.values()].find((e) => e.key === el.dataset.term);
    if (!entry) return;
    if (!pop) {
      pop = document.createElement("div");
      pop.id = "tw-pop";
      pop.className = "tw-pop";
      pop.setAttribute("role", "tooltip");
      document.body.appendChild(pop);
    }
    pop.innerHTML = `<strong>${escape(entry.title)}</strong><span>${escape(entry.text)}</span>`;
    pop.hidden = false;
    popFor = el;
    el.setAttribute("aria-describedby", "tw-pop");
    const box = el.getBoundingClientRect(), width = Math.min(300, window.innerWidth - 24);
    pop.style.width = `${width}px`;
    const left = Math.max(12, Math.min(window.innerWidth - width - 12, box.left + box.width / 2 - width / 2));
    pop.style.left = `${left + window.scrollX}px`;
    const below = box.bottom + 8 + pop.offsetHeight < window.innerHeight;
    pop.style.top = `${(below ? box.bottom + 8 : box.top - 8 - pop.offsetHeight) + window.scrollY}px`;
  }
  function hideTerm() {
    if (pop) pop.hidden = true;
    popFor?.removeAttribute("aria-describedby");
    popFor = null;
  }

  // ---- Guided tour of the navigation --------------------------------------
  const TOUR = [
    ["overview", "Cash weather", "Start here every morning: will cash last until the day that matters?"],
    ["rescue", "Rescue plan", "If a gap is coming, Tideway proposes fixes. People approve with a PIN."],
    ["assistant", "Ask Tideway", "Ask anything in plain words and your own language."],
    ["inbox", "Inbox", "Paste payment alerts and messages; Tideway drafts the records for you."],
    ["whatif", "What-if", "Try scenarios safely. Nothing is saved."],
    ["lab", "Decision lab", "Stress-test a plan before trusting it."],
    ["treasury", "Treasury", "13-week cash plan, health score, duplicate-payment scan and a signed credit passport."],
    ["portfolio", "Portfolio radar", "For lenders: early warning across many small-business clients."],
    ["records", "Records", "Every invoice, bill and transaction behind the numbers."],
    ["team", "Team", "Invite colleagues with the right role."],
    ["security", "Security centre", "Emergency stop, limits, payee checks and an attack self-test."],
    ["evidence", "Evidence", "Tamper-evident proof of everything that happened."],
  ];
  let tourIndex = -1, tourSteps = [];
  function tourShow() {
    document.querySelectorAll(".tw-tour-target").forEach((el) => el.classList.remove("tw-tour-target"));
    let card = document.getElementById("tw-tour");
    if (tourIndex < 0 || tourIndex >= tourSteps.length) { card?.remove(); tourIndex = -1; return; }
    const [view, title, text] = tourSteps[tourIndex];
    const target = document.querySelector(`.sidebar .nav-item[data-view="${view}"]`);
    target?.classList.add("tw-tour-target");
    target?.scrollIntoView({block: "nearest"});
    if (!card) {
      card = document.createElement("div");
      card.id = "tw-tour";
      card.className = "tw-tour";
      card.setAttribute("role", "dialog");
      card.setAttribute("aria-label", "Guided tour");
      document.body.appendChild(card);
    }
    card.innerHTML = `<span class="eyebrow">Tour · ${tourIndex + 1} of ${tourSteps.length}</span><h3>${escape(title)}</h3><p>${escape(text)}</p>
      <div class="tw-tour-actions"><button type="button" class="button small ghost" data-tour="end">Close</button>
      <span>${tourIndex > 0 ? '<button type="button" class="button small ghost" data-tour="back">Back</button>' : ""}
      <button type="button" class="button small ghost" data-view="${escape(view)}" data-tour="open">Open page</button>
      <button type="button" class="button small primary" data-tour="next">${tourIndex === tourSteps.length - 1 ? "Finish" : "Next"}</button></span></div>`;
    const box = target?.getBoundingClientRect();
    card.style.top = `${Math.max(12, Math.min(window.innerHeight - 220, box ? box.top - 10 : 80))}px`;
    card.style.left = `${box ? Math.min(window.innerWidth - 340, box.right + 14) : 24}px`;
    card.querySelector('[data-tour="next"]')?.focus({preventScroll: true});
  }
  function startTour() {
    tourSteps = TOUR.filter(([view]) => document.querySelector(`.sidebar .nav-item[data-view="${view}"]`));
    tourIndex = 0;
    tourShow();
  }

  // ---- Toolbar controls ----------------------------------------------------
  function toolbar() {
    const controls = document.querySelector(".topbar-controls");
    if (!controls || document.getElementById("tw-help-tools")) return;
    const tools = document.createElement("div");
    tools.id = "tw-help-tools";
    tools.className = "tw-help-tools";
    tools.innerHTML = `<button type="button" class="button ghost small" data-help-tool="tour" title="A one-minute tour of every page">Tour</button>
      <button type="button" class="button ghost small" data-help-tool="toggle" aria-pressed="${enabled()}" title="Show plain-language help on every page">Help ${enabled() ? "on" : "off"}</button>
      <button type="button" class="button ghost small" data-help-tool="text" aria-pressed="${document.documentElement.classList.contains("tw-large")}" title="Larger text">A+</button>`;
    controls.prepend(tools);
  }
  function syncToolbar() {
    const toggle = document.querySelector('[data-help-tool="toggle"]');
    if (toggle) { toggle.textContent = `Help ${enabled() ? "on" : "off"}`; toggle.setAttribute("aria-pressed", String(enabled())); }
    const text = document.querySelector('[data-help-tool="text"]');
    text?.setAttribute("aria-pressed", String(document.documentElement.classList.contains("tw-large")));
  }

  function refresh() {
    try {
      observer.disconnect();
      toolbar();
      pageCard();
      decorate(document.getElementById("view"));
      decorate(document.getElementById("quick-start"));
    } catch (error) {
      console.warn("Tideway help layer skipped:", error);
    } finally {
      const view = document.getElementById("view");
      if (view) observer.observe(view, {childList: true, subtree: true});
    }
  }
  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; refresh(); });
  });

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const term = target.closest(".tw-term");
    if (term) { popFor === term ? hideTerm() : showTerm(term); return; }
    if (!target.closest(".tw-pop")) hideTerm();
    const fold = target.closest("[data-help-fold]");
    if (fold) {
      const key = `tideway.help.fold.${fold.dataset.helpFold}`;
      store.set(key, store.get(key, "open") === "folded" ? "open" : "folded");
      pageCard();
      document.querySelector("[data-help-fold]")?.focus({preventScroll: true});
      return;
    }
    const tool = target.closest("[data-help-tool]");
    if (tool) {
      if (tool.dataset.helpTool === "tour") startTour();
      if (tool.dataset.helpTool === "toggle") {
        store.set("tideway.help.v1", enabled() ? "off" : "on");
        if (!enabled()) document.querySelectorAll(".tw-term").forEach((el) => el.replaceWith(document.createTextNode(el.textContent)));
        pageCard(); refresh(); syncToolbar();
      }
      if (tool.dataset.helpTool === "text") {
        document.documentElement.classList.toggle("tw-large");
        store.set("tideway.help.large", document.documentElement.classList.contains("tw-large") ? "on" : "off");
        syncToolbar();
      }
      return;
    }
    const tour = target.closest("[data-tour]");
    if (tour) {
      const step = tour.dataset.tour;
      if (step === "next") tourIndex = tourIndex === tourSteps.length - 1 ? -1 : tourIndex + 1;
      else if (step === "back") tourIndex = Math.max(0, tourIndex - 1);
      else if (step === "end") tourIndex = -1;
      if (step !== "open") tourShow();
    }
  });
  document.addEventListener("mouseover", (event) => {
    const term = event.target instanceof Element ? event.target.closest(".tw-term") : null;
    if (term && term !== popFor) showTerm(term);
  });
  document.addEventListener("mouseout", (event) => {
    const term = event.target instanceof Element ? event.target.closest(".tw-term") : null;
    const next = event.relatedTarget instanceof Element ? event.relatedTarget.closest(".tw-term") : null;
    if (term && term === popFor && next !== term && document.activeElement !== term) hideTerm();
  });
  document.addEventListener("focusin", (event) => {
    const term = event.target instanceof Element ? event.target.closest(".tw-term") : null;
    if (term) showTerm(term);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { hideTerm(); if (tourIndex >= 0) { tourIndex = -1; tourShow(); } }
    const term = event.target instanceof Element ? event.target.closest(".tw-term") : null;
    if (term && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); popFor === term ? hideTerm() : showTerm(term); }
  });
  window.addEventListener("scroll", hideTerm, {passive: true});

  if (store.get("tideway.help.large", "off") === "on") document.documentElement.classList.add("tw-large");
  document.addEventListener("DOMContentLoaded", refresh);
  return Object.freeze({refresh, startTour, pages: Object.keys(PAGES), terms: TERMS.length});
})();
