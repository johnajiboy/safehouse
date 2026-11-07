// SafeHome officer dashboard.
// Talks to the FastAPI backend in safehome/api.py and redraws the page from `state`.

const state = {
  view: "today",
  plan: null,
  areas: [],
  selected: null, // a case ref, "new" for the report form, or "cluster:<key>"
  tab: "overview",
  detail: null,
  repairerOptions: null,
  loadingRepairers: false,
  pending: null, // an override waiting for its reason: { type, ref, reason, note }
  processing: null, // { text, step } while a new report is being read
  log: [],
  repairers: [],
  simulation: null,
  coldSnap: false,
};

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 401) {
    location.href = "/login.html"; // the session ended, so sign in again
    throw new Error("Please sign in");
  }
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(problem.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
  );
}

let toastTimer;
function toast(text) {
  const box = document.getElementById("toast");
  box.textContent = text;
  box.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove("show"), 2800);
}

function formatTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function severityClass(item) {
  if (item.level === "Emergency") return "crit";
  if (item.due_soon) return "warn";
  return "calm";
}

const ICONS = {
  today: '<rect x="3" y="4.5" width="14" height="12.5" rx="2.5"/><path d="M3 8.5h14M7 3v3M13 3v3"/>',
  repairers:
    '<path d="M12.6 3.4a3.6 3.6 0 0 0-3.4 4.7l-5.5 5.5a1.6 1.6 0 0 0 2.3 2.3l5.5-5.5a3.6 3.6 0 0 0 4.7-3.4l-2.1 2.1-2-.4-.4-2z"/>',
  results: '<path d="M4 16v-6M10 16V4M16 16V9"/>',
  log: '<path d="M7.5 5H17M7.5 10H17M7.5 15H17"/><circle cx="3.8" cy="5" r=".7"/><circle cx="3.8" cy="10" r=".7"/><circle cx="3.8" cy="15" r=".7"/>',
  sun: '<circle cx="10" cy="10" r="3.4"/><path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M4.7 15.3 6 14M14 6l1.3-1.3"/>',
  moon: '<path d="M16 12.3A6.5 6.5 0 0 1 7.7 4a6.5 6.5 0 1 0 8.3 8.3z"/>',
  signout: '<path d="M8 3.5H4.5v13H8M12.5 6.5 16 10l-3.5 3.5M16 10H7.5"/>',
};

function icon(name) {
  return `<svg viewBox="0 0 20 20" aria-hidden="true">${ICONS[name]}</svg>`;
}

// ---------------------------------------------------------------------------
// Loading data
// ---------------------------------------------------------------------------

async function loadPlan() {
  state.plan = await api("/api/plan");
}

async function loadDetail() {
  state.detail = null;
  state.repairerOptions = null;
  if (!state.selected || state.selected === "new" || state.selected.startsWith("cluster:")) return;
  state.detail = await api(`/api/cases/${state.selected}`);
  if (state.tab === "repairers") await loadRepairerOptions();
}

async function loadRepairerOptions() {
  if (!state.detail || !state.detail.trade_needed) return;
  state.loadingRepairers = true;
  render();
  const started = Date.now();
  state.repairerOptions = await api(`/api/cases/${state.selected}/repairers`);
  // Keep the search visible for a moment so officers can see the agent working.
  const wait = reducedMotion ? 0 : Math.max(0, 700 - (Date.now() - started));
  await new Promise((resolve) => setTimeout(resolve, wait));
  state.loadingRepairers = false;
}

async function refresh() {
  await loadPlan();
  await loadDetail();
  render();
}

// ---------------------------------------------------------------------------
// Rendering: shell
// ---------------------------------------------------------------------------

function render() {
  const before = rowPositions();
  renderNav();
  renderAgents();
  const view = document.getElementById("view");
  if (state.view === "today") view.innerHTML = renderToday();
  if (state.view === "repairers") view.innerHTML = renderRepairersView();
  if (state.view === "results") view.innerHTML = renderResults();
  if (state.view === "log") view.innerHTML = renderLog();
  animateRows(before);
  drawMaps();
}

function renderNav() {
  const counts = { today: state.plan?.counts.open, log: state.log.length || null };
  const items = [
    ["today", "Today"],
    ["repairers", "Repairers"],
    ["results", "Results"],
    ["log", "Log"],
  ];
  document.getElementById("nav").innerHTML = items
    .map(
      ([key, label]) => `
      <button class="navbtn" data-action="view" data-view="${key}" aria-current="${state.view === key}">
        ${icon(key)}<span class="lbl">${label}</span>
        ${counts[key] ? `<span class="badge">${counts[key]}</span>` : ""}
      </button>`,
    )
    .join("");
}

function renderAgents() {
  const plan = state.plan;
  if (!plan) return;
  const bookedTotal = [...plan.today, ...plan.later, ...plan.investigated].filter((c) => c.booked).length;
  const agents = [
    [
      "Intake Agent",
      state.processing
        ? "Reading a new report…"
        : `${plan.counts.open} open cases, ${plan.counts.routine} routine repairs`,
      !!state.processing,
    ],
    [
      "Pattern Agent",
      plan.clusters.length ? `${plan.clusters.length} possible shared cause` : "No patterns found",
      false,
    ],
    [
      "Repair Agent",
      state.loadingRepairers ? "Checking approved repairers…" : `${bookedTotal} repairers booked`,
      state.loadingRepairers,
    ],
  ];
  document.getElementById("agents").innerHTML =
    `<p class="railh">Agents</p>` +
    agents
      .map(
        ([name, status, busy]) => `
        <div class="agent ${busy ? "busy" : ""}">
          <span class="pulse"></span><strong>${name}</strong><span class="sub">${status}</span>
        </div>`,
      )
      .join("");
}

// ---------------------------------------------------------------------------
// Today view
// ---------------------------------------------------------------------------

function renderToday() {
  const plan = state.plan;
  if (!plan) return `<p class="empty">Loading today's plan…</p>`;

  const atRisk = plan.later.filter((c) => plan.at_risk.includes(c.ref));
  const date = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  const status = atRisk.length
    ? `<button class="status" data-action="select" data-ref="${atRisk[0].ref}"><span class="d"></span>
         ${atRisk.length === 1 ? `${escapeHtml(atRisk[0].address)} may miss its deadline` : `${atRisk.length} cases may miss their deadlines`}
       </button>`
    : `<span class="status good"><span class="d"></span>Every urgent case fits today</span>`;

  return `
    <header class="pagehead">
      <div>
        <p class="eyebrow">${date} · Middlesbrough</p>
        <h1>${plan.counts.today} of ${plan.counts.open} open cases fit today</h1>
        ${status}
      </div>
      <button class="btn primary big" data-action="new-report">+ Add report</button>
    </header>

    <section class="panel kpis" aria-label="Summary">
      ${kpi(
        "Open cases",
        plan.counts.open,
        `Waiting for investigation${plan.counts.routine ? ` · plus ${plan.counts.routine} routine repairs` : ""}`,
      )}
      ${kpi("Possible emergencies", plan.counts.emergencies, "Investigate within 24 hours", plan.counts.emergencies > 0)}
      ${visitsRing(plan)}
      ${kpi("May miss a deadline", atRisk.length, atRisk.length ? "Add an inspector or move a case" : "On track", atRisk.length > 0)}
      ${kpi("Repairers booked", `${plan.counts.booked_today}<small> / ${plan.today.length}</small>`, "For today's cases")}
    </section>

    <div class="board">
      <section class="panel queue" aria-label="Inspection plan">
        <div class="qhead">
          <h2>Inspection plan</h2>
          <div class="step">
            <span>Inspectors</span>
            <button data-action="inspectors" data-change="-1" aria-label="Remove an inspector" ${plan.inspectors <= 1 ? "disabled" : ""}>−</button>
            <b>${plan.inspectors}</b>
            <button data-action="inspectors" data-change="1" aria-label="Add an inspector" ${plan.inspectors >= 20 ? "disabled" : ""}>+</button>
          </div>
        </div>
        ${plan.clusters.map(clusterSignal).join("")}
        ${group("Today", `${plan.today.length} cases · ${plan.visits_used} visits`, plan.today)}
        <div class="capline">Inspector capacity reached</div>
        ${group("Later", `${plan.later.length} cases`, plan.later) || ""}
        ${plan.later.length ? "" : `<p class="empty">Nothing waiting.</p>`}
        ${plan.investigated.length ? group("Investigated · next legal steps", `${plan.investigated.length}`, plan.investigated) : ""}
        ${plan.routine.length ? group("Routine repairs · no Awaab's Law deadline", `${plan.routine.length}`, plan.routine) : ""}
      </section>
      <aside class="panel detail" id="detail">${renderDetail()}</aside>
    </div>`;
}

function kpi(label, value, note, critical = false) {
  return `
    <div class="kpi ${critical ? "crit" : ""}">
      <span class="k">${label}</span><b>${value}</b><span class="s">${note}</span>
    </div>`;
}

function visitsRing(plan) {
  const share = plan.capacity ? plan.visits_used / plan.capacity : 0;
  return `
    <div class="kpi ringk">
      <svg class="ring" viewBox="0 0 40 40" aria-hidden="true">
        <circle class="rbg" cx="20" cy="20" r="16" pathLength="100"/>
        <circle class="rfg" cx="20" cy="20" r="16" pathLength="100" style="stroke-dashoffset:${100 - 100 * share}"/>
      </svg>
      <div><span class="k">Visits used</span><b>${plan.visits_used}<small> / ${plan.capacity}</small></b></div>
    </div>`;
}

function clusterSignal(cluster) {
  const selected = state.selected === `cluster:${cluster.key}`;
  return `
    <button class="signal ${selected ? "sel" : ""}" data-action="select" data-ref="cluster:${cluster.key}">
      <span class="ic">≈</span>
      <span>
        <strong>${cluster.grouped ? "Grouped survey" : "Possible shared cause"} at ${escapeHtml(cluster.building)}</strong>
        <span class="sub">Pattern Agent linked ${cluster.refs.length} reports</span>
      </span>
      <span class="go">Review</span>
    </button>`;
}

function group(title, count, cases) {
  if (!cases.length) return "";
  return `<div class="glabel"><span>${title}</span><span>${count}</span></div>${cases.map(caseRow).join("")}`;
}

function caseRow(item) {
  const tags = [...item.vulnerability, ...(item.repeat ? ["Reported before"] : [])];
  const chips = [
    item.visit_confirmed ? `<span class="chip acc">Visit confirmed</span>` : "",
    item.booked ? `<span class="chip ok">Repairer booked</span>` : "",
    item.suggested
      ? `<span class="chip agent">Suggested: ${escapeHtml(item.suggested.name)} · ${item.suggested.match}%</span>`
      : "",
    item.overridden ? `<span class="chip warn">Overridden</span>` : "",
    item.needs_review ? `<span class="chip crit">Check report</span>` : "",
  ].join("");
  return `
    <button class="case ${state.selected === item.ref ? "sel" : ""}" data-action="select" data-ref="${item.ref}" data-flip="${item.ref}">
      <span class="sev ${severityClass(item)}"></span>
      <span>
        <strong>${escapeHtml(item.address)}</strong>
        <span class="sub">${escapeHtml(item.hazard)}${tags.length ? " · " + escapeHtml(tags.join(", ")) : ""}${chips}</span>
      </span>
      <span class="due ${item.due_soon && item.stage === 0 ? "hot" : ""}">
        <span>${escapeHtml(item.due_text)}</span>
        <span class="track"><i class="${severityClass(item)}" style="transform:scaleX(${item.urgency})"></i></span>
      </span>
    </button>`;
}

// ---------------------------------------------------------------------------
// Case file (right-hand panel)
// ---------------------------------------------------------------------------

function renderDetail() {
  if (state.processing) return renderProcessing();
  if (state.selected === "new") return renderReportForm();
  if (state.selected?.startsWith("cluster:")) return renderCluster();
  if (!state.detail) return `<p class="empty">Select a case to see its details.</p>`;

  const c = state.detail;
  const tabs = [
    ["overview", "Overview"],
    ["legal", "Legal steps"],
    ["repairers", "Repairers"],
    ["messages", "Messages"],
  ];
  const drafts = c.messages.filter((m) => m.status === "draft").length;
  return `
    <div class="dtabs" role="tablist">
      ${tabs
        .map(
          ([key, label]) => `
          <button class="dtab" role="tab" data-action="tab" data-tab="${key}" aria-selected="${state.tab === key}">
            ${label}${key === "messages" && drafts ? ` (${drafts})` : ""}
          </button>`,
        )
        .join("")}
    </div>
    <div class="dinner">
      <div>
        <p class="dref"><span class="mono">${c.ref}</span> · ${escapeHtml(c.area)} · reported ${formatTime(c.reported_at)}</p>
        <h2>${escapeHtml(c.address)}</h2>
      </div>
      ${safetyBanner(c)}
      ${state.tab === "overview" ? renderOverview(c) : ""}
      ${state.tab === "legal" ? renderLegal(c) : ""}
      ${state.tab === "repairers" ? renderRepairerTab(c) : ""}
      ${state.tab === "messages" ? renderMessages(c) : ""}
    </div>`;
}

function safetyBanner(c) {
  if (c.level !== "Emergency") return "";
  const sent = c.messages.find((m) => m.kind === "Safety advice");
  return `
    <div class="alertbox">
      <strong>Possible emergency.</strong> Investigate and make safe within 24 hours.
      ${sent ? ` Safety advice was sent to the tenant automatically at ${formatTime(sent.sent_at)}.` : ""}
    </div>`;
}

function highlight(text, evidence) {
  const spans = [...evidence].sort((a, b) => a.start - b.start || b.end - a.end);
  const kindClass = { hazard: "hz", emergency: "hz", household: "vu", repeat: "rp" };
  let html = "";
  let position = 0;
  for (const span of spans) {
    if (span.start < position) continue; // skip overlapping quotes
    html += escapeHtml(text.slice(position, span.start));
    html += `<mark class="ev ${kindClass[span.kind]}">${escapeHtml(text.slice(span.start, span.end))}</mark>`;
    position = span.end;
  }
  return html + escapeHtml(text.slice(position));
}

function renderOverview(c) {
  const lowConfidence = c.findings.some((f) => f.confidence === "Low") || c.needs_review;
  const findingRows = c.findings
    .map((f) => {
      const proof = f.evidence.length
        ? [...new Set(f.evidence.map((e) => e.toLowerCase()))].map((e) => `“${escapeHtml(e)}”`).join(", ")
        : escapeHtml(f.note);
      return `
        <div class="frow">
          <span class="fk">${f.field}</span>
          <span class="fv">${escapeHtml(f.value)}<span class="fe">${proof}</span></span>
          <span class="conf ${f.confidence.replace(/\s+/g, "-")}">${f.confidence}</span>
        </div>`;
    })
    .join("");

  const total = c.score.reduce((sum, part) => sum + part.points, 0);
  const scoreRows = c.score
    .map((part) => `<li><span>${escapeHtml(part.reason)}</span><b>+${part.points}</b></li>`)
    .join("");

  return `
    ${lowConfidence ? `<div class="reviewbox"><strong>Check before acting.</strong> The Intake Agent isn't confident about part of this report.</div>` : ""}
    <div>
      <p class="quote">${highlight(c.text, c.evidence)}</p>
      <div class="evkey"><span><i></i>Hazard evidence</span><span><i class="vu"></i>Household</span><span><i class="rp"></i>Repeat report</span></div>
    </div>
    <div class="sect">
      <h3>What the Intake Agent found <span class="muted">· read with ${c.source === "claude" ? "Claude" : "keyword matching"}</span></h3>
      <div class="found">${findingRows}</div>
    </div>
    <div class="sect">
      <h3>Legal level</h3>
      <ul class="dots">${c.level_reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
    </div>
    <div class="sect">
      <h3>Why it ranks here · ${total} points</h3>
      <ul class="score">${scoreRows || "<li><span>No priority points</span><b>0</b></li>"}</ul>
    </div>
    ${
      c.questions.length
        ? `
      <div class="sect">
        <h3>Ask the tenant</h3>
        <ul class="dots agentq">${c.questions.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul>
      </div>`
        : ""
    }
    ${repairSuggestion(c)}
    ${c.override_reason ? `<div class="tip"><strong>Override reason:</strong> ${escapeHtml(c.override_reason)}</div>` : ""}
    ${["today", "later"].includes(state.pending?.type) ? reasonBox(c) : overviewActions(c)}`;
}

function repairSuggestion(c) {
  if (c.booking) {
    return `<div class="tip"><strong>Booked:</strong> ${escapeHtml(c.booking.repairer_name)}, approved by an officer.</div>`;
  }
  const r = c.recommendation;
  if (!r) return "";
  return `
    <div class="sect">
      <h3>Repair Agent suggests</h3>
      <div class="rep best">
        <div class="reptop">
          <div><strong>Suggested: ${escapeHtml(r.repairer_name)} · ${r.match}%</strong></div>
          <div class="match"><b>${r.match}%</b><span>match</span></div>
        </div>
        <ul class="dots">${r.reasons.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
        <div class="acts">
          <button class="btn primary" data-action="book" data-repairer="${r.repairer_id}">Approve and book</button>
          <button class="btn" data-action="tab" data-tab="repairers">Choose another</button>
        </div>
      </div>
      <p class="note">Nothing is booked until an officer approves it.</p>
    </div>`;
}

function overviewActions(c) {
  if (c.stage >= 1) {
    return `<div class="acts"><button class="btn big" data-action="tab" data-tab="legal">Investigated · see legal steps</button></div>`;
  }
  if (c.level === "Routine") {
    return `<div class="tip">Routine repair. It goes to the normal repairs queue, not the inspection plan.</div>`;
  }
  if (c.in_today) {
    return `
      <div class="acts">
        <button class="btn primary big" data-action="confirm-visit" ${c.visit_confirmed ? "disabled" : ""}>
          ${c.visit_confirmed ? "Visit confirmed" : "Confirm visit"}
        </button>
        <button class="btn big" data-action="start-override" data-type="later">Move later</button>
      </div>`;
  }
  return `<div class="acts"><button class="btn primary big" data-action="start-override" data-type="today">Do today</button></div>`;
}

const REASONS = {
  later: [
    "Tenant not available today",
    "Duplicate of another report",
    "Lower risk after a call with the tenant",
    "Officer judgement",
  ],
  today: ["New information from the tenant", "Higher risk than reported", "Officer judgement"],
  cancel: ["Repairer unavailable", "Wrong trade", "Tenant asked to rearrange", "Officer judgement"],
  book: [
    "Suggested repairer can't attend in time",
    "Tenant asked for this repairer",
    "Knows this property or a linked job",
    "Officer judgement",
  ],
};
const REASON_QUESTIONS = {
  later: "Why move this case to later?",
  today: "Why move this case to today?",
  cancel: "Why cancel this booking?",
  book: "Why choose this repairer instead of the suggested one?",
};

function reasonBox(c) {
  const p = state.pending;
  return `
    <form class="reasonbox" data-form="override">
      <strong>${REASON_QUESTIONS[p.type]}</strong>
      ${
        p.type === "later" && c.level === "Emergency"
          ? `<div class="alertbox"><strong>Possible emergency.</strong> Moving it could breach the 24-hour deadline.</div>`
          : ""
      }
      ${p.type === "book" ? `<p>Booking <strong>${escapeHtml(p.name)}</strong>. The Repair Agent suggested ${escapeHtml(c.recommendation?.repairer_name || "another repairer")}.</p>` : ""}
      ${p.error ? `<div class="alertbox" role="alert"><strong>${p.type === "book" ? "Can't book this repairer." : "Can't move this case."}</strong> ${escapeHtml(p.error)}</div>` : ""}
      <div class="reasons" role="radiogroup" aria-label="Reason">
        ${REASONS[p.type]
          .map(
            (r, i) => `
            <label><input type="radio" name="reason" id="reason-${i}" value="${escapeHtml(r)}" ${p.reason === r ? "checked" : ""}>
            <span>${escapeHtml(r)}</span></label>`,
          )
          .join("")}
      </div>
      <input type="text" name="note" placeholder="Add a note (optional)" value="${escapeHtml(p.note || "")}" aria-label="Note">
      <div class="acts">
        <button class="btn primary" type="submit" ${p.reason ? "" : "disabled"}>Confirm</button>
        <button class="btn" type="button" data-action="cancel-override">Cancel</button>
      </div>
      <p class="note">The reason is saved in the decision log.</p>
    </form>`;
}

function renderLegal(c) {
  const next = c.stages.find((s) => s.status === "next");
  return `
    <div class="sect">
      <h3>Awaab's Law steps</h3>
      <ol class="stages">
        ${c.stages
          .map(
            (s, i) => `
            <li class="${s.status === "done" ? "done" : s.status === "next" ? "next" : ""}">
              <span class="sn">${s.status === "done" ? "✓" : i + 1}</span>
              <div>
                <strong>${s.name}</strong>
                <span class="sd">${s.done_at ? `Done ${formatTime(s.done_at)}` : `${escapeHtml(s.rule)}${s.due_at ? ` · due ${formatTime(s.due_at)}` : ""}`}</span>
              </div>
            </li>`,
          )
          .join("")}
      </ol>
    </div>
    ${
      next
        ? `<div class="acts"><button class="btn primary big" data-action="record-stage">Record “${next.name.toLowerCase()}”</button></div>
         ${c.stage === 0 ? `<p class="note">Recording the investigation moves the case out of the inspection plan and drafts the written summary.</p>` : ""}`
        : `<div class="tip"><strong>All steps recorded.</strong> Keep monitoring until the works are finished.</div>`
    }`;
}

function renderRepairerTab(c) {
  if (!c.trade_needed) {
    return `<div class="tip">The Repair Agent needs an officer to confirm the hazard before it can search.</div>`;
  }
  if (state.loadingRepairers || !state.repairerOptions) {
    return `
      <div class="search">
        <p><strong>Repair Agent is searching.</strong> <span class="muted">Checking approved repairers in Middlesbrough.</span></p>
        <div class="scan"></div><div class="ghost"></div><div class="ghost" style="opacity:.6"></div>
      </div>`;
  }
  const booking = c.booking;
  const cards = state.repairerOptions
    .map((option, i) => {
      const r = option.repairer;
      const isBooked = booking && booking.repairer_id === r.id;
      const isSuggested = c.recommendation?.repairer_id === r.id;
      // Booking anyone but the Repair Agent's suggestion asks for a reason first.
      const bookAction = isSuggested || !c.recommendation
        ? `data-action="book" data-repairer="${r.id}"`
        : `data-action="start-book-other" data-repairer="${r.id}" data-name="${escapeHtml(r.name)}"`;
      const slot =
        option.next_slot_hours < 24
          ? `${option.next_slot_hours} hours`
          : `${Math.round(option.next_slot_hours / 24)} day${Math.round(option.next_slot_hours / 24) === 1 ? "" : "s"}`;
      return `
        <article class="rep ${isBooked ? "booked" : isSuggested && !booking ? "best" : ""} rise" style="animation-delay:${i * 90}ms">
          <div class="reptop">
            <div><strong>${escapeHtml(r.name)}</strong><span class="sub">${escapeHtml(r.certification)} · ${option.trade}</span></div>
            <div class="match"><b>${option.match}%</b><span>match</span></div>
          </div>
          <div class="mbar"><i style="transform:scaleX(${option.match / 100})"></i></div>
          <div class="facts">
            ${isSuggested ? `<span class="chip agent">Suggested</span>` : ""}
            <span class="chip ${option.in_time ? "ok" : "warn"}">${option.in_time ? "Within deadline" : "After deadline"} · ${slot}</span>
            ${option.distance_km !== null ? `<span class="chip">${option.distance_km} km away</span>` : ""}
            <span class="chip">${r.first_time_fix}% fixed first time</span>
          </div>
          <div class="acts">
            ${
              isBooked
                ? `<button class="btn" data-action="start-override" data-type="cancel">Cancel booking</button>`
                : `<button class="btn ${isSuggested ? "primary" : ""}" ${bookAction} ${booking ? "disabled" : ""}>Approve and book</button>`
            }
          </div>
        </article>`;
    })
    .join("");

  return `
    ${booking ? `<div class="tip"><strong>Booked:</strong> ${escapeHtml(booking.repairer_name)}, approved by the officer.</div>` : ""}
    ${["cancel", "book"].includes(state.pending?.type) ? reasonBox(c) : ""}
    <div class="mapwrap"><div class="leafmap small" id="case-map"></div></div>
    <div class="reps">${cards || `<p class="empty">No approved repairer covers this trade.</p>`}</div>
    <p class="note">The agent suggests. An officer approves every booking.</p>`;
}

function renderMessages(c) {
  if (!c.messages.length) return `<p class="empty">No messages yet. Drafts appear here for approval.</p>`;
  return c.messages
    .map(
      (m) => `
      <div class="msg ${m.status}">
        <div class="msghead"><strong>${escapeHtml(m.kind)}</strong>
          <span class="chip ${m.status === "sent" ? "ok" : "warn"}">${m.status === "sent" ? `Sent ${formatTime(m.sent_at)}` : "Draft · needs approval"}</span>
        </div>
        ${
          m.status === "draft"
            ? `<textarea id="msg-${m.id}" aria-label="Message text">${escapeHtml(m.body)}</textarea>
             <div class="acts"><button class="btn primary" data-action="approve-message" data-id="${m.id}">Approve and send</button></div>`
            : `<p class="msgbody">${escapeHtml(m.body).replace(/\n/g, "<br>")}</p>`
        }
      </div>`,
    )
    .join("");
}

function renderReportForm() {
  const options = state.areas.map((a) => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join("");
  return `
    <form class="dinner" data-form="report">
      <div><p class="dref">Intake Agent</p><h2>Add a tenant report</h2></div>
      <label class="field"><span>What the tenant said</span>
        <textarea name="text" required minlength="5" placeholder="For example: There's a strong smell of gas in the kitchen and my baby is at home."></textarea>
      </label>
      <label class="field"><span>Address</span><input name="address" required placeholder="Flat 4, Ash Court"></label>
      <label class="field"><span>Area</span><select name="area">${options}</select></label>
      <label class="field"><span>Contact (optional)</span><input name="contact" placeholder="Phone or email"></label>
      <div class="acts"><button class="btn primary big" type="submit">Read report</button>
        <button class="btn big" type="button" data-action="close-form">Cancel</button></div>
    </form>`;
}

function renderProcessing() {
  const steps = [
    "Reading the report",
    "Applying Awaab's Law rules",
    "Ranking against today's cases",
    "Checking for linked reports",
  ];
  return `
    <div class="dinner">
      <div><p class="dref">Intake Agent</p><h2>Reading a new report</h2></div>
      <p class="quote">${escapeHtml(state.processing.text)}</p>
      <ol class="steps">
        ${steps.map((s, i) => `<li class="${i < state.processing.step ? "done" : i === state.processing.step ? "now" : ""}"><span class="si"></span>${s}</li>`).join("")}
      </ol>
    </div>`;
}

function renderCluster() {
  const key = state.selected.replace("cluster:", "");
  const cluster = state.plan.clusters.find((c) => c.key === key);
  if (!cluster) return `<p class="empty">This pattern is no longer active.</p>`;
  const all = [...state.plan.today, ...state.plan.later, ...state.plan.investigated];
  const items = cluster.refs.map((ref) => all.find((c) => c.ref === ref)).filter(Boolean);
  return `
    <div class="dinner">
      <div><p class="dref">Pattern Agent</p><h2>Possible shared cause at ${escapeHtml(cluster.building)}</h2></div>
      <p class="quote">${escapeHtml(cluster.explanation)}</p>
      <div class="sect"><h3>Linked reports</h3>
        <ul class="dots agentq">${items.map((c) => `<li>${escapeHtml(c.address)}: ${escapeHtml(c.hazard.toLowerCase())}</li>`).join("")}</ul>
      </div>
      <div class="acts"><button class="btn primary big" data-action="toggle-survey" data-key="${cluster.key}">
        ${cluster.grouped ? "Undo grouped survey" : "Group into one survey"}</button></div>
      <p class="note">A grouped survey uses one inspection visit. A surveyor must confirm the cause, and each tenant's legal deadline still applies.</p>
    </div>`;
}

// ---------------------------------------------------------------------------
// Other views
// ---------------------------------------------------------------------------

function renderRepairersView() {
  const rows = state.repairers
    .map(
      (r, i) => `
      <tr>
        <td><span class="num">${i + 1}</span></td>
        <td><strong>${escapeHtml(r.name)}</strong><br><span class="muted small">${escapeHtml(r.certification)}</span></td>
        <td class="nowrap">${r.next_slot_hours < 24 ? `${r.next_slot_hours} hours` : `${Math.round(r.next_slot_hours / 24)} days`}</td>
        <td>${r.jobs.length ? `<span class="chip ok">${r.jobs.length} job${r.jobs.length > 1 ? "s" : ""}</span>` : `<span class="muted">None</span>`}</td>
      </tr>`,
    )
    .join("");
  return `
    <header class="pagehead">
      <div>
        <p class="eyebrow">Repair Agent · Middlesbrough</p>
        <h1>Approved repairers</h1>
        <p class="lede">Matched by trade, certification, availability, distance and first-time fix rate. An officer approves every booking.</p>
      </div>
    </header>
    <div class="board repboard">
      <section class="panel" style="padding:14px">
        <div class="leafmap" id="overview-map"></div>
        <div class="legend"><span><i class="crit"></i>Emergency</span><span><i class="warn"></i>Due within a day</span><span><i></i>Other case</span><span><i class="sq"></i>Repairer</span></div>
      </section>
      <section class="panel"><div class="tablewrap"><table>
        <thead><tr><th>#</th><th>Repairer</th><th>Next slot</th><th>Booked</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div></section>
    </div>`;
}

function renderResults() {
  const rows = state.simulation;
  if (!rows) return `<p class="empty">Running the simulation…</p>`;
  const measures = [
    ["deadlines_missed", "Deadlines missed"],
    ["emergencies_missed", "Emergencies missed"],
    ["high_risk_wait_days", "High-risk wait (days)"],
  ];
  const cell = (row, key) => {
    const values = rows.map((r) => r[key]);
    const max = Math.max(0.1, ...values);
    const best = Math.min(...values) !== Math.max(...values) && row[key] === Math.min(...values);
    return `<td><div class="cellbar"><span class="${best ? "best" : ""}">${row[key].toFixed(1)}</span>
      <i><b class="${row.method === "SafeHome plan" ? "plan" : ""}" style="transform:scaleX(${row[key] / max})"></b></i></div></td>`;
  };
  return `
    <header class="pagehead">
      <div>
        <p class="eyebrow">Evaluation · simulated workload</p>
        <h1>Does the plan beat simpler methods?</h1>
        <p class="lede">The same simulated reports over 20 working days, averaged across 100 runs. Lower is better.</p>
      </div>
    </header>
    <section class="panel">
      <div class="resctrl">
        <div class="step"><span>Inspectors</span>
          <button data-action="inspectors" data-change="-1" ${state.plan.inspectors <= 1 ? "disabled" : ""}>−</button>
          <b>${state.plan.inspectors}</b>
          <button data-action="inspectors" data-change="1">+</button>
        </div>
        <label class="switch"><input type="checkbox" id="cold-snap" ${state.coldSnap ? "checked" : ""}>Cold snap</label>
      </div>
      <div class="tablewrap"><table>
        <thead><tr><th>Method</th>${measures.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr><td><strong>${r.method}</strong></td>${measures.map(([key]) => cell(r, key)).join("")}</tr>`).join("")}</tbody>
      </table></div>
    </section>
    <p class="note" style="margin-top:14px">
      Assumes 5–7 reports a day, 12% emergencies, 30% vulnerable households and 3 visits per inspector.
      These results show how the method behaves, not real-world performance.
      Report-reading accuracy is measured separately with <span class="mono">evaluation/evaluate.py</span>.
    </p>`;
}

function renderLog() {
  if (!state.log.length) return `<p class="empty">No decisions recorded yet.</p>`;
  const kind = (entry) =>
    entry.actor === "Officer" ? (entry.action.startsWith("Override") ? "override" : "ok") : "agent";
  return `
    <header class="pagehead"><div><p class="eyebrow">Audit trail</p><h1>Decision log</h1>
      <p class="lede">Every agent action and officer decision, newest first.</p></div></header>
    <section class="panel"><ol class="timeline">
      ${state.log
        .map(
          (e) => `
          <li><span class="t">${formatTime(e.at)}</span><span class="d ${kind(e)}"></span>
          <span><strong>${escapeHtml(e.actor)}</strong>${e.case_ref ? ` · <span class="mono">${e.case_ref}</span>` : ""} · ${escapeHtml(e.action)}</span></li>`,
        )
        .join("")}
    </ol></section>`;
}

// ---------------------------------------------------------------------------
// Maps (Leaflet with OpenStreetMap tiles)
// ---------------------------------------------------------------------------

let maps = [];

function drawMaps() {
  maps.forEach((m) => m.remove());
  maps = [];
  if (!window.L) return;

  const overview = document.getElementById("overview-map");
  if (overview) maps.push(buildMap(overview, allCases(), state.repairers, null));

  const caseMap = document.getElementById("case-map");
  if (caseMap && state.detail && state.repairerOptions) {
    maps.push(
      buildMap(
        caseMap,
        [state.detail],
        state.repairerOptions.map((o) => o.repairer),
        state.detail,
      ),
    );
  }
}

function allCases() {
  const plan = state.plan;
  return plan ? [...plan.today, ...plan.later, ...plan.investigated, ...plan.routine] : [];
}

function buildMap(element, cases, repairers, focus) {
  const map = L.map(element, { scrollWheelZoom: false }).setView([54.552, -1.23], 12);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const colours = { crit: "#d23e2a", warn: "#b87305", calm: "#5f6688" };
  const points = [];
  cases
    .filter((c) => c.lat)
    .forEach((c) => {
      L.circleMarker([c.lat, c.lng], {
        radius: focus ? 9 : 7,
        color: "#fff",
        weight: 2,
        fillColor: colours[severityClass(c)],
        fillOpacity: 0.95,
      })
        .bindTooltip(`${c.address} · ${c.hazard}`)
        .addTo(map);
      points.push([c.lat, c.lng]);
    });

  repairers.forEach((r, i) => {
    const marker = L.divIcon({
      className: "repairer-pin",
      html: `<span>${focus ? i + 1 : state.repairers.indexOf(r) + 1}</span>`,
      iconSize: [22, 22],
    });
    L.marker([r.lat, r.lng], { icon: marker }).bindTooltip(r.name).addTo(map);
    points.push([r.lat, r.lng]);
    if (focus && focus.lat) {
      L.polyline(
        [
          [focus.lat, focus.lng],
          [r.lat, r.lng],
        ],
        { color: "#0e7c74", weight: i === 0 ? 3 : 1.5, dashArray: "6 6", opacity: i === 0 ? 0.9 : 0.5 },
      ).addTo(map);
    }
    (r.jobs || []).forEach((job) => {
      if (job.lat)
        L.polyline(
          [
            [job.lat, job.lng],
            [r.lat, r.lng],
          ],
          { color: "#3d8516", weight: 2 },
        ).addTo(map);
    });
  });

  if (points.length > 1) map.fitBounds(points, { padding: [24, 24] });
  return map;
}

// ---------------------------------------------------------------------------
// Animation: rows glide to their new position when the plan changes
// ---------------------------------------------------------------------------

function rowPositions() {
  const positions = {};
  document.querySelectorAll("[data-flip]").forEach((row) => {
    positions[row.dataset.flip] = row.getBoundingClientRect().top;
  });
  return positions;
}

function animateRows(before) {
  if (reducedMotion) return;
  document.querySelectorAll("[data-flip]").forEach((row) => {
    const previous = before[row.dataset.flip];
    if (previous === undefined) {
      row.classList.add("rise");
      return;
    }
    const shift = previous - row.getBoundingClientRect().top;
    if (Math.abs(shift) > 1) {
      row.animate([{ transform: `translateY(${shift}px)` }, { transform: "none" }], {
        duration: 450,
        easing: "cubic-bezier(.2,.8,.2,1)",
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function openView(view) {
  state.view = view;
  if (view === "repairers") state.repairers = await api("/api/repairers");
  if (view === "log") state.log = await api("/api/log");
  if (view === "results") {
    state.simulation = null;
    render();
    state.simulation = await api(`/api/simulation?inspectors=${state.plan.inspectors}&cold_snap=${state.coldSnap}`);
  }
  render();
  window.scrollTo(0, 0);
}

async function selectCase(ref) {
  state.selected = ref;
  state.pending = null;
  await loadDetail();
  render();
  if (window.innerWidth <= 1100) document.getElementById("detail")?.scrollIntoView({ block: "start" });
}

async function submitReport(form) {
  const data = Object.fromEntries(new FormData(form));
  state.processing = { text: data.text, step: 0 };
  render();
  const ticker = setInterval(
    () => {
      if (state.processing && state.processing.step < 3) {
        state.processing.step += 1;
        render();
      }
    },
    reducedMotion ? 100 : 600,
  );
  try {
    const created = await api("/api/reports", { method: "POST", body: data });
    clearInterval(ticker);
    state.processing = null;
    state.selected = created.ref;
    state.tab = "overview";
    toast(`${created.ref} read and ranked`);
    await refresh();
  } catch (error) {
    clearInterval(ticker);
    state.processing = null;
    render();
    toast(error.message);
  }
}

async function submitOverride(form) {
  const reason = new FormData(form).get("reason");
  const note = new FormData(form).get("note") || "";
  const ref = state.pending.ref;
  const type = state.pending.type;
  let booked = null;
  try {
    if (type === "cancel") {
      await api(`/api/cases/${ref}/cancel-booking`, { method: "POST", body: { reason, note } });
    } else if (type === "book") {
      const body = { repairer_id: state.pending.repairer, reason, note };
      booked = (await api(`/api/cases/${ref}/book`, { method: "POST", body })).booked;
    } else {
      await api(`/api/cases/${ref}/move`, { method: "POST", body: { to: type, reason, note } });
    }
  } catch (error) {
    // Keep the form open so the officer can read why it was refused.
    Object.assign(state.pending, { reason, note, error: error.message });
    render();
    return;
  }
  state.pending = null;
  toast(booked ? `Booked ${booked}, with your reason logged` : "Override saved with its reason");
  await refresh();
}

const actions = {
  view: (el) => openView(el.dataset.view),
  select: (el) => selectCase(el.dataset.ref),
  tab: async (el) => {
    state.tab = el.dataset.tab;
    state.pending = null;
    render();
    if (state.tab === "repairers" && !state.repairerOptions) {
      await loadRepairerOptions();
      render();
    }
  },
  "new-report": async () => {
    state.selected = "new";
    state.detail = null;
    if (!state.areas.length) state.areas = await api("/api/areas");
    render();
    document.querySelector('[data-form="report"] textarea')?.focus();
  },
  "close-form": () => {
    state.selected = null;
    render();
  },
  inspectors: async (el) => {
    await api("/api/settings/inspectors", {
      method: "POST",
      body: { inspectors: state.plan.inspectors + Number(el.dataset.change) },
    });
    await loadPlan();
    if (state.view === "results") return openView("results");
    await loadDetail();
    render();
  },
  "confirm-visit": async () => {
    await api(`/api/cases/${state.selected}/confirm-visit`, { method: "POST" });
    toast("Visit confirmed. A message to the tenant is waiting for approval.");
    await refresh();
  },
  "start-book-other": (el) => {
    state.pending = { type: "book", ref: state.selected, repairer: el.dataset.repairer, name: el.dataset.name, reason: "", note: "" };
    render();
  },
  "start-override": (el) => {
    state.pending = { type: el.dataset.type, ref: state.selected, reason: "", note: "" };
    render();
  },
  "cancel-override": () => {
    state.pending = null;
    render();
  },
  "record-stage": async () => {
    const result = await api(`/api/cases/${state.selected}/stage`, { method: "POST" });
    toast(`Recorded: ${result.recorded.toLowerCase()}`);
    await refresh();
  },
  book: async (el) => {
    const result = await api(`/api/cases/${state.selected}/book`, {
      method: "POST",
      body: { repairer_id: el.dataset.repairer },
    });
    toast(`Booked ${result.booked}`);
    await refresh();
  },
  "approve-message": async (el) => {
    const body = document.getElementById(`msg-${el.dataset.id}`).value;
    await api(`/api/messages/${el.dataset.id}/approve`, { method: "POST", body: { body } });
    toast("Message approved and sent");
    await refresh();
  },
  "toggle-survey": async (el) => {
    const result = await api(`/api/clusters/${el.dataset.key}/survey`, { method: "POST" });
    toast(result.grouped ? "Reports grouped into one survey" : "Grouped survey undone");
    await refresh();
  },
  "reset-demo": async () => {
    toast("Reloading sample data…");
    await api("/api/demo/reset", { method: "POST" });
    state.selected = null;
    state.detail = null;
    await refresh();
    toast("Sample data reloaded");
  },
};

document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-action]");
  if (!el || el.disabled) return;
  const action = actions[el.dataset.action];
  if (action) {
    Promise.resolve(action(el)).catch((error) => toast(error.message));
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  event.preventDefault();
  const handler =
    form.dataset.form === "report" ? submitReport : form.dataset.form === "override" ? submitOverride : null;
  if (handler) handler(form).catch((error) => toast(error.message));
});

document.addEventListener("change", async (event) => {
  if (event.target.name === "reason" && state.pending) {
    state.pending.reason = event.target.value;
    const confirm = event.target.form.querySelector('[type="submit"]');
    if (confirm) confirm.disabled = false;
  }
  if (event.target.id === "cold-snap") {
    state.coldSnap = event.target.checked;
    openView("results");
  }
});

document.addEventListener("input", (event) => {
  if (event.target.name === "note" && state.pending) state.pending.note = event.target.value;
});

// ---------------------------------------------------------------------------
// Light and dark mode
// ---------------------------------------------------------------------------

function setupThemeToggle() {
  const root = document.documentElement;
  const button = document.getElementById("theme-toggle");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const current = () => root.dataset.theme || (systemDark.matches ? "dark" : "light");
  const paint = () => {
    const dark = current() === "dark";
    button.innerHTML = `${icon(dark ? "sun" : "moon")}<span class="lbl">${dark ? "Light mode" : "Dark mode"}</span>`;
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  };
  try {
    const saved = localStorage.getItem("safehome-theme");
    if (saved) root.dataset.theme = saved;
  } catch {
    // Storage can be blocked; the system theme is used instead.
  }
  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try {
      localStorage.setItem("safehome-theme", next);
    } catch {}
    paint();
    drawMaps();
  });
  paint();
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function setupSignOut() {
  const button = document.getElementById("sign-out");
  const { officer, demo } = await api("/api/me");
  if (demo) {
    document.querySelector(".rail .logo").insertAdjacentHTML("afterend", `<span class="demotag">Demo mode</span>`);
  }
  button.innerHTML = `${icon("signout")}<span class="lbl">Sign out ${escapeHtml(officer)}</span>`;
  button.setAttribute("aria-label", `Sign out ${officer}`);
  button.addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    location.href = "/login.html";
  });
}

async function start() {
  setupThemeToggle();
  setupSignOut().catch(() => {});
  try {
    await loadPlan();
    const first = state.plan.today[0];
    if (first) {
      state.selected = first.ref;
      await loadDetail();
    }
    render();
  } catch (error) {
    document.getElementById("view").innerHTML =
      `<p class="empty">Couldn't reach the SafeHome server. Is it running? (${escapeHtml(error.message)})</p>`;
  }
}

start();
