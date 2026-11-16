"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
let activeSessionId = null;

function elSvg(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function showObError(msg) {
  const el = document.getElementById("ob-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearObError() {
  const el = document.getElementById("ob-error");
  el.textContent = "";
  el.classList.add("hidden");
}

function fmtSigned(val) {
  const num = Number(val);
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}`;
}

function renderQuotesChart(svg, rounds) {
  svg.textContent = "";
  if (!rounds || rounds.length === 0) {
    return;
  }

  const width = 820;
  const height = 300;
  const pad = { top: 20, right: 24, bottom: 42, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const allPrices = [];
  for (const r of rounds) {
    allPrices.push(r.fair_value, r.bid_price, r.ask_price);
  }
  const minP = Math.min(...allPrices) - 1.0;
  const maxP = Math.max(...allPrices) + 1.0;
  const spanP = Math.max(1.0, maxP - minP);

  const xScale = (idx) =>
    rounds.length === 1
      ? pad.left + plotW / 2
      : pad.left + (idx / (rounds.length - 1)) * plotW;
  const yScale = (price) => pad.top + plotH - ((price - minP) / spanP) * plotH;

  for (let i = 0; i <= 4; i += 1) {
    const val = minP + (i / 4) * spanP;
    const y = yScale(val);
    svg.appendChild(
      elSvg("line", {
        x1: pad.left,
        y1: y,
        x2: width - pad.right,
        y2: y,
        stroke: "#243042",
        "stroke-width": 1,
      })
    );
    const lbl = elSvg("text", {
      x: pad.left - 8,
      y: y + 4,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "end",
    });
    lbl.textContent = val.toFixed(1);
    svg.appendChild(lbl);
  }

  const lines = [
    { key: "ask_price", color: "#fbbf24", dash: "5,4", width: 2 },
    { key: "bid_price", color: "#38bdf8", dash: "5,4", width: 2 },
    { key: "fair_value", color: "#34d399", dash: "", width: 2.5 },
  ];
  for (const cfg of lines) {
    const pts = rounds.map(
      (r, idx) => `${xScale(idx).toFixed(1)},${yScale(r[cfg.key]).toFixed(1)}`
    );
    const attrs = {
      fill: "none",
      stroke: cfg.color,
      "stroke-width": cfg.width,
      points: pts.join(" "),
    };
    if (cfg.dash) {
      attrs["stroke-dasharray"] = cfg.dash;
    }
    svg.appendChild(elSvg("polyline", attrs));
  }

  rounds.forEach((r, idx) => {
    const lbl = elSvg("text", {
      x: xScale(idx).toFixed(1),
      y: pad.top + plotH + 18,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "middle",
    });
    lbl.textContent = `R${r.round_number}`;
    svg.appendChild(lbl);
  });

  svg.appendChild(
    elSvg("rect", {
      x: pad.left,
      y: pad.top,
      width: plotW,
      height: plotH,
      fill: "none",
      stroke: "#334155",
      "stroke-width": 1.2,
    })
  );
}

function renderPnlChart(svg, rounds) {
  svg.textContent = "";
  if (!rounds || rounds.length === 0) {
    return;
  }

  const width = 820;
  const height = 260;
  const pad = { top: 20, right: 24, bottom: 42, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const vals = rounds.map((r) => r.mtm_pnl_after);
  const minY = Math.min(0, ...vals) - 2.0;
  const maxY = Math.max(0, ...vals) + 2.0;
  const spanY = Math.max(1.0, maxY - minY);

  const xScale = (idx) =>
    rounds.length === 1
      ? pad.left + plotW / 2
      : pad.left + (idx / (rounds.length - 1)) * plotW;
  const yScale = (v) => pad.top + plotH - ((v - minY) / spanY) * plotH;

  const y0 = yScale(0);
  svg.appendChild(
    elSvg("line", {
      x1: pad.left,
      y1: y0,
      x2: width - pad.right,
      y2: y0,
      stroke: "#475569",
      "stroke-dasharray": "4,4",
      "stroke-width": 1.2,
    })
  );

  const pts = rounds.map((r, idx) => `${xScale(idx).toFixed(1)},${yScale(r.mtm_pnl_after).toFixed(1)}`);
  svg.appendChild(
    elSvg("polyline", {
      fill: "none",
      stroke: "#38bdf8",
      "stroke-width": 2.5,
      points: pts.join(" "),
    })
  );

  rounds.forEach((r, idx) => {
    const dot = elSvg("circle", {
      cx: xScale(idx).toFixed(1),
      cy: yScale(r.mtm_pnl_after).toFixed(1),
      r: 4,
      fill: r.mtm_pnl_after >= 0 ? "#34d399" : "#fb7185",
      stroke: "#0b1018",
      "stroke-width": 1.5,
    });
    const tip = elSvg("title");
    tip.textContent = `R${r.round_number}: P&L=${fmtSigned(r.mtm_pnl_after)}, Inv=${r.inventory_after}`;
    dot.appendChild(tip);
    svg.appendChild(dot);
  });

  svg.appendChild(
    elSvg("rect", {
      x: pad.left,
      y: pad.top,
      width: plotW,
      height: plotH,
      fill: "none",
      stroke: "#334155",
      "stroke-width": 1.2,
    })
  );
}

function renderSession(session) {
  activeSessionId = session.id;
  document.getElementById("ob-desk-panel").classList.remove("hidden");
  document.getElementById("ob-session-heading").textContent =
    `Order Book Session #${session.id}`;
  document.getElementById("ob-round-val").textContent =
    `${session.current_round} / ${session.num_rounds} (${session.status})`;
  document.getElementById("ob-signal-val").textContent = session.latest_public_signal.toFixed(2);
  document.getElementById("ob-cash-val").textContent = session.cash.toFixed(2);
  document.getElementById("ob-inv-val").textContent =
    `${session.inventory} (max \u00B1${session.max_inventory})`;

  const isCompleted = session.status === "completed";
  document.getElementById("ob-quote-btn").disabled = isCompleted;
  document.getElementById("ob-finish-btn").disabled = isCompleted;

  // Suggest centered default quotes if inputs are empty
  const bidInput = document.getElementById("ob-bid-input");
  const askInput = document.getElementById("ob-ask-input");
  if (!bidInput.value || !askInput.value || session.current_round === 0) {
    bidInput.value = Math.max(1, session.latest_public_signal - 1.5).toFixed(1);
    askInput.value = (session.latest_public_signal + 1.5).toFixed(1);
  }

  // Order book ladder
  const ladderTbody = document.getElementById("ob-ladder-tbody");
  ladderTbody.textContent = "";
  for (const lvl of session.book_levels) {
    const tr = document.createElement("tr");
    const sideCell = document.createElement("td");
    sideCell.className = `mono ${lvl.side === "ask" ? "amount-neg" : "amount-pos"}`;
    sideCell.textContent = lvl.side.toUpperCase();

    const priceCell = document.createElement("td");
    priceCell.className = "mono text-right";
    priceCell.textContent = lvl.price.toFixed(2);

    const qtyCell = document.createElement("td");
    qtyCell.className = "mono text-right";
    qtyCell.textContent = String(lvl.quantity);

    const ownerCell = document.createElement("td");
    ownerCell.className = "mono text-right";
    ownerCell.textContent = lvl.owner === "you" ? "YOU" : "market";

    tr.append(sideCell, priceCell, qtyCell, ownerCell);
    ladderTbody.appendChild(tr);
  }

  // Observable fills tape
  const tapeTbody = document.getElementById("ob-tape-tbody");
  tapeTbody.textContent = "";
  const allPublicFills = [];
  for (const r of session.rounds) {
    for (const f of r.fills) {
      allPublicFills.push(f);
    }
  }
  if (allPublicFills.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "empty-state";
    td.textContent = "No fills yet.";
    tr.appendChild(td);
    tapeTbody.appendChild(tr);
  } else {
    for (const f of allPublicFills.slice().reverse()) {
      const tr = document.createElement("tr");
      const rCell = document.createElement("td");
      rCell.className = "mono";
      rCell.textContent = `R${f.round_number}`;
      const sideCell = document.createElement("td");
      sideCell.className = `mono ${f.side === "buy" ? "amount-pos" : "amount-neg"}`;
      sideCell.textContent = f.side.toUpperCase();
      const pCell = document.createElement("td");
      pCell.className = "mono text-right";
      pCell.textContent = f.price.toFixed(2);
      const qCell = document.createElement("td");
      qCell.className = "mono text-right";
      qCell.textContent = String(f.quantity);
      tr.append(rCell, sideCell, pCell, qCell);
      tapeTbody.appendChild(tr);
    }
  }

  // Post-game analysis panel
  const analysisPanel = document.getElementById("ob-analysis-panel");
  if (!session.analysis) {
    analysisPanel.classList.add("hidden");
    return;
  }

  analysisPanel.classList.remove("hidden");
  const an = session.analysis;
  document.getElementById("ob-identity-note").textContent =
    `Exact Identity: Total P&L (${fmtSigned(an.total_pnl)}) = Spread Captured (${fmtSigned(an.spread_captured)}) - Adverse Selection (${an.adverse_selection_cost.toFixed(2)}) + Inventory Drift (${fmtSigned(an.inventory_drift_pnl)})`;

  const totalEl = document.getElementById("an-total-pnl");
  totalEl.textContent = fmtSigned(an.total_pnl);
  totalEl.className = `stat-value mono ${an.total_pnl >= 0 ? "amount-pos" : "amount-neg"}`;
  document.getElementById("an-fair-range").textContent =
    `Fair Value: ${an.initial_fair_value.toFixed(2)} -> ${an.terminal_fair_value.toFixed(2)}`;

  document.getElementById("an-spread-cap").textContent = fmtSigned(an.spread_captured);
  document.getElementById("an-avg-spread").textContent =
    `Avg Quoted Spread: ${an.avg_quoted_spread.toFixed(2)} across ${an.rounds.length} rounds`;

  document.getElementById("an-adv-sel").textContent = an.adverse_selection_cost.toFixed(2);
  document.getElementById("an-informed-share").textContent =
    `Informed Volume: ${(an.informed_volume_share * 100).toFixed(1)}% (${an.informed_fills}/${an.total_fills} fills)`;

  const driftEl = document.getElementById("an-inv-drift");
  driftEl.textContent = fmtSigned(an.inventory_drift_pnl);
  driftEl.className = `stat-value mono ${an.inventory_drift_pnl >= 0 ? "amount-pos" : "amount-neg"}`;
  document.getElementById("an-max-inv").textContent =
    `Final Inv: ${an.final_inventory} | Peak |Inv|: ${an.max_abs_inventory}`;

  renderQuotesChart(document.getElementById("ob-quotes-chart"), an.rounds);
  renderPnlChart(document.getElementById("ob-pnl-chart"), an.rounds);

  const auditTbody = document.getElementById("ob-audit-tbody");
  auditTbody.textContent = "";
  const auditFills = an.rounds.flatMap((r) => r.fills);
  if (auditFills.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.className = "empty-state";
    td.textContent = "No executions occurred during this session.";
    tr.appendChild(td);
    auditTbody.appendChild(tr);
  } else {
    for (const f of auditFills) {
      const tr = document.createElement("tr");
      const rCell = document.createElement("td");
      rCell.className = "mono";
      rCell.textContent = `R${f.round_number}`;
      const sideCell = document.createElement("td");
      sideCell.className = "mono";
      sideCell.textContent = f.side.toUpperCase();
      const botCell = document.createElement("td");
      botCell.className = `mono ${f.bot_kind === "informed_arb" ? "amount-neg" : ""}`;
      botCell.textContent = f.bot_kind;
      const pCell = document.createElement("td");
      pCell.className = "mono text-right";
      pCell.textContent = f.price.toFixed(2);
      const fvCell = document.createElement("td");
      fvCell.className = "mono text-right";
      fvCell.textContent = f.fair_value.toFixed(2);
      const qCell = document.createElement("td");
      qCell.className = "mono text-right";
      qCell.textContent = String(f.quantity);
      const spCell = document.createElement("td");
      spCell.className = "mono text-right amount-pos";
      spCell.textContent = fmtSigned(f.spread_captured);
      const asCell = document.createElement("td");
      asCell.className = `mono text-right ${f.adverse_selection > 0 ? "amount-neg" : ""}`;
      asCell.textContent = f.adverse_selection.toFixed(2);
      const edgeCell = document.createElement("td");
      edgeCell.className = `mono text-right ${f.net_edge >= 0 ? "amount-pos" : "amount-neg"}`;
      edgeCell.textContent = fmtSigned(f.net_edge);

      tr.append(rCell, sideCell, botCell, pCell, fvCell, qCell, spCell, asCell, edgeCell);
      auditTbody.appendChild(tr);
    }
  }
}

async function fetchSessions() {
  const res = await fetch("/api/orderbook/sessions", { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.replace("/");
    return;
  }
  if (!res.ok) {
    return;
  }
  const list = await res.json();
  const tbody = document.getElementById("ob-sessions-tbody");
  tbody.textContent = "";
  if (list.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.className = "empty-state";
    td.textContent = "No order book sessions yet. Start one above.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const s of list) {
    const tr = document.createElement("tr");
    const idCell = document.createElement("td");
    idCell.className = "mono";
    idCell.textContent = `#${s.id}`;
    const stCell = document.createElement("td");
    stCell.className = "mono";
    stCell.textContent = s.status;
    const progCell = document.createElement("td");
    progCell.className = "mono text-right";
    progCell.textContent = `${s.current_round}/${s.num_rounds}`;
    const invCell = document.createElement("td");
    invCell.className = "mono text-right";
    invCell.textContent = String(s.inventory);
    const pnlCell = document.createElement("td");
    pnlCell.className = "mono text-right";
    pnlCell.textContent = s.total_pnl !== null ? fmtSigned(s.total_pnl) : "hidden";
    const spCell = document.createElement("td");
    spCell.className = "mono text-right";
    spCell.textContent = s.spread_captured !== null ? fmtSigned(s.spread_captured) : "--";
    const asCell = document.createElement("td");
    asCell.className = "mono text-right";
    asCell.textContent = s.adverse_selection_cost !== null ? s.adverse_selection_cost.toFixed(2) : "--";

    const actCell = document.createElement("td");
    actCell.className = "text-right";
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "btn btn-secondary";
    openBtn.textContent = "Open";
    openBtn.addEventListener("click", () => loadSession(s.id));
    actCell.appendChild(openBtn);

    tr.append(idCell, stCell, progCell, invCell, pnlCell, spCell, asCell, actCell);
    tbody.appendChild(tr);
  }
}

async function loadSession(sessionId) {
  clearObError();
  const res = await fetch(`/api/orderbook/sessions/${sessionId}`, { credentials: "same-origin" });
  if (!res.ok) {
    showObError("Could not load session.");
    return;
  }
  const data = await res.json();
  renderSession(data);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("ob-create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearObError();
    const fd = new FormData(e.target);
    const res = await fetch("/api/orderbook/sessions", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        num_rounds: Number(fd.get("num_rounds")),
        max_inventory: Number(fd.get("max_inventory")),
        fundamental_volatility: Number(fd.get("fundamental_volatility")),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showObError(data.detail || "Failed to start order book session.");
      return;
    }
    document.getElementById("ob-bid-input").value = "";
    document.getElementById("ob-ask-input").value = "";
    renderSession(data);
    fetchSessions();
  });

  document.getElementById("ob-quote-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearObError();
    if (!activeSessionId) {
      showObError("Start a session first.");
      return;
    }
    const fd = new FormData(e.target);
    const res = await fetch(`/api/orderbook/sessions/${activeSessionId}/quote`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bid_price: Number(fd.get("bid_price")),
        ask_price: Number(fd.get("ask_price")),
        quote_size: Number(fd.get("quote_size")),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      const msg =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail) && data.detail[0]
            ? data.detail[0].msg
            : "Quote rejected.";
      showObError(msg);
      return;
    }
    renderSession(data);
    fetchSessions();
  });

  document.getElementById("ob-finish-btn").addEventListener("click", async () => {
    if (!activeSessionId) {
      return;
    }
    const res = await fetch(`/api/orderbook/sessions/${activeSessionId}/finish`, {
      method: "POST",
      credentials: "same-origin",
    });
    if (res.ok) {
      renderSession(await res.json());
      fetchSessions();
    }
  });

  fetchSessions();
});
