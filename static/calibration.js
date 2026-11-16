"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
let activePromptId = null;

function elSvg(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function showCalError(msg) {
  const el = document.getElementById("cal-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearCalError() {
  const el = document.getElementById("cal-error");
  el.textContent = "";
  el.classList.add("hidden");
}

function renderBrierChart(svg, points) {
  svg.textContent = "";
  if (!points || points.length === 0) {
    const empty = elSvg("text", {
      x: 410,
      y: 150,
      fill: "#8b9bb4",
      "font-size": 14,
      "text-anchor": "middle",
    });
    empty.textContent = "Answer calibration rounds to track your Brier score over time.";
    svg.appendChild(empty);
    return;
  }

  const width = 820;
  const height = 300;
  const pad = { top: 20, right: 24, bottom: 42, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const maxRound = Math.max(points.length, 2);
  const maxY = Math.max(0.35, ...points.map((p) => p.brier_score));

  const xScale = (r) =>
    points.length === 1
      ? pad.left + plotW / 2
      : pad.left + ((r - 1) / (maxRound - 1)) * plotW;
  const yScale = (val) => pad.top + plotH - (val / maxY) * plotH;

  for (let i = 0; i <= 4; i += 1) {
    const val = (i / 4) * maxY;
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
    lbl.textContent = val.toFixed(2);
    svg.appendChild(lbl);
  }

  // 0.25 uninformative baseline
  const yBase = yScale(0.25);
  svg.appendChild(
    elSvg("line", {
      x1: pad.left,
      y1: yBase,
      x2: width - pad.right,
      y2: yBase,
      stroke: "#fbbf24",
      "stroke-dasharray": "6,4",
      "stroke-width": 1.6,
    })
  );

  // Per-round dots
  for (const pt of points) {
    const dot = elSvg("circle", {
      cx: xScale(pt.round_number).toFixed(1),
      cy: yScale(pt.brier_score).toFixed(1),
      r: 3.5,
      fill: "#94a3b8",
      opacity: 0.75,
    });
    const tip = elSvg("title");
    tip.textContent = `Round ${pt.round_number}: p_hat=${pt.estimated_prob.toFixed(2)}, y=${pt.actual_outcome ? 1 : 0}, Brier=${pt.brier_score.toFixed(4)}`;
    dot.appendChild(tip);
    svg.appendChild(dot);
  }

  // Cumulative mean Brier polyline
  const meanPts = points.map(
    (p) => `${xScale(p.round_number).toFixed(1)},${yScale(p.cumulative_mean_brier).toFixed(1)}`
  );
  svg.appendChild(
    elSvg("polyline", {
      fill: "none",
      stroke: "#38bdf8",
      "stroke-width": 2.5,
      points: meanPts.join(" "),
    })
  );

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

function renderReliabilityCurve(svg, bins) {
  svg.textContent = "";
  const width = 820;
  const height = 300;
  const pad = { top: 20, right: 24, bottom: 42, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const xScale = (p) => pad.left + p * plotW;
  const yScale = (p) => pad.top + plotH - p * plotH;

  for (let i = 0; i <= 4; i += 1) {
    const p = i * 0.25;
    const y = yScale(p);
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
    lbl.textContent = `${(p * 100).toFixed(0)}%`;
    svg.appendChild(lbl);

    const xl = elSvg("text", {
      x: xScale(p),
      y: pad.top + plotH + 18,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "middle",
    });
    xl.textContent = `${(p * 100).toFixed(0)}%`;
    svg.appendChild(xl);
  }

  // Ideal diagonal y = x
  svg.appendChild(
    elSvg("line", {
      x1: xScale(0),
      y1: yScale(0),
      x2: xScale(1),
      y2: yScale(1),
      stroke: "#475569",
      "stroke-dasharray": "5,4",
      "stroke-width": 1.5,
    })
  );

  if (bins && bins.length > 0) {
    const pts = bins.map(
      (b) => `${xScale(b.mean_predicted).toFixed(1)},${yScale(b.empirical_rate).toFixed(1)}`
    );
    svg.appendChild(
      elSvg("polyline", {
        fill: "none",
        stroke: "#34d399",
        "stroke-width": 2.5,
        points: pts.join(" "),
      })
    );

    for (const b of bins) {
      const circle = elSvg("circle", {
        cx: xScale(b.mean_predicted).toFixed(1),
        cy: yScale(b.empirical_rate).toFixed(1),
        r: 5,
        fill: "#34d399",
        stroke: "#0b1018",
        "stroke-width": 1.5,
      });
      const tip = elSvg("title");
      tip.textContent = `${b.bin_label} (n=${b.count}): predicted ${(b.mean_predicted * 100).toFixed(1)}%, observed ${(b.empirical_rate * 100).toFixed(1)}%`;
      circle.appendChild(tip);
      svg.appendChild(circle);
    }
  }

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

function renderHistoryTable(rounds) {
  const tbody = document.getElementById("cal-history-tbody");
  tbody.textContent = "";
  if (!rounds || rounds.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty-state";
    td.textContent = "No calibration guesses submitted yet.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const r of rounds) {
    const tr = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.className = "mono";
    idCell.textContent = `#${r.id}`;

    const catCell = document.createElement("td");
    catCell.textContent = r.category;

    const estCell = document.createElement("td");
    estCell.className = "mono text-right";
    estCell.textContent = `${(r.estimated_prob * 100).toFixed(1)}%`;

    const trueCell = document.createElement("td");
    trueCell.className = "mono text-right";
    trueCell.textContent = `${(r.true_probability * 100).toFixed(1)}%`;

    const outCell = document.createElement("td");
    outCell.className = `mono ${r.actual_outcome ? "amount-pos" : "amount-neg"}`;
    outCell.textContent = r.actual_outcome ? "YES (1)" : "NO (0)";

    const brierCell = document.createElement("td");
    brierCell.className = `mono text-right ${r.brier_score <= 0.15 ? "amount-pos" : ""}`;
    brierCell.textContent = Number(r.brier_score).toFixed(4);

    tr.append(idCell, catCell, estCell, trueCell, outCell, brierCell);
    tbody.appendChild(tr);
  }
}

async function ensurePrompt() {
  const res = await fetch("/api/calibration/prompts", {
    method: "POST",
    credentials: "same-origin",
  });
  if (res.status === 401) {
    window.location.replace("/");
    return;
  }
  if (!res.ok) {
    showCalError("Could not load calibration question.");
    return;
  }
  const prompt = await res.json();
  activePromptId = prompt.id;
  document.getElementById("cal-prompt-category").textContent = `Question #${prompt.id} (${prompt.category})`;
  document.getElementById("cal-question-text").textContent = prompt.question_text;
  document.getElementById("cal-submit-btn").disabled = false;
}

async function loadHistory() {
  clearCalError();
  const res = await fetch("/api/calibration/history", { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.replace("/");
    return;
  }
  if (!res.ok) {
    showCalError("Failed to fetch calibration history.");
    return;
  }
  const data = await res.json();
  document.getElementById("cal-mean-brier").textContent =
    data.rounds_answered > 0 ? Number(data.mean_brier_score).toFixed(4) : "--";
  document.getElementById("cal-rounds-count").textContent = String(data.rounds_answered);
  document.getElementById("cal-prob-err").textContent =
    data.rounds_answered > 0 ? `${(data.mean_abs_prob_error * 100).toFixed(1)}%` : "--";

  renderBrierChart(document.getElementById("brier-time-chart"), data.points);
  renderReliabilityCurve(document.getElementById("calibration-curve-chart"), data.bins);
  renderHistoryTable(data.recent_rounds);

  if (data.pending_prompt) {
    activePromptId = data.pending_prompt.id;
    document.getElementById("cal-prompt-category").textContent =
      `Question #${data.pending_prompt.id} (${data.pending_prompt.category})`;
    document.getElementById("cal-question-text").textContent = data.pending_prompt.question_text;
    document.getElementById("cal-submit-btn").disabled = false;
  } else {
    await ensurePrompt();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const slider = document.getElementById("cal-prob-slider");
  const numInput = document.getElementById("cal-prob-input");
  const pctLabel = document.getElementById("cal-prob-pct");

  slider.addEventListener("input", () => {
    const pct = Number(slider.value);
    pctLabel.textContent = `${pct}%`;
    numInput.value = (pct / 100).toFixed(2);
  });

  numInput.addEventListener("input", () => {
    const val = Math.max(0, Math.min(1, Number(numInput.value || 0)));
    const pct = Math.round(val * 100);
    slider.value = String(pct);
    pctLabel.textContent = `${pct}%`;
  });

  document.getElementById("cal-next-btn").addEventListener("click", ensurePrompt);

  document.getElementById("cal-guess-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearCalError();
    if (!activePromptId) {
      await ensurePrompt();
      return;
    }

    const est = Number(numInput.value);
    const res = await fetch(`/api/calibration/prompts/${activePromptId}/guess`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ estimated_prob: est }),
    });
    const result = await res.json();
    if (!res.ok) {
      showCalError(result.detail || "Could not submit forecast.");
      return;
    }

    const feedback = document.getElementById("cal-feedback");
    feedback.classList.remove("hidden");
    const outcomeLabel = result.actual_outcome ? "HIT (1)" : "MISS (0)";
    document.getElementById("cal-feedback-title").textContent =
      `${outcomeLabel} — Brier Score: ${Number(result.brier_score).toFixed(4)}`;
    document.getElementById("cal-feedback-detail").textContent =
      `Your forecast: ${(result.estimated_prob * 100).toFixed(1)}% | Exact: ${(result.true_probability * 100).toFixed(1)}% — ${result.explanation}`;

    activePromptId = null;
    await loadHistory();
  });

  loadHistory();
});
