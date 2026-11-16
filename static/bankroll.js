"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
let lastSim = null;

function elSvg(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function showBankrollError(msg) {
  const el = document.getElementById("bankroll-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearBankrollError() {
  const el = document.getElementById("bankroll-error");
  el.textContent = "";
  el.classList.add("hidden");
}

function renderHistogram(svg, bins, initialBankroll) {
  svg.textContent = "";
  if (!bins || bins.length === 0) {
    return;
  }

  const width = 820;
  const height = 320;
  const pad = { top: 20, right: 24, bottom: 52, left: 60 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const maxFreq = Math.max(...bins.map((b) => b.frequency), 0.05);
  const barGap = 4;
  const barW = Math.max(6, plotW / bins.length - barGap);

  for (let i = 0; i <= 4; i += 1) {
    const frac = i / 4;
    const y = pad.top + plotH - frac * plotH;
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
    lbl.textContent = `${(frac * maxFreq * 100).toFixed(0)}%`;
    svg.appendChild(lbl);
  }

  bins.forEach((b, idx) => {
    const x = pad.left + idx * (plotW / bins.length) + barGap / 2;
    const h = (b.frequency / maxFreq) * plotH;
    const y = pad.top + plotH - h;
    const isLoss = b.bin_end <= initialBankroll;
    const rect = elSvg("rect", {
      x: x.toFixed(1),
      y: y.toFixed(1),
      width: barW.toFixed(1),
      height: Math.max(1, h).toFixed(1),
      fill: isLoss ? "#fb7185" : "#38bdf8",
      opacity: 0.85,
      rx: 2,
    });
    const tip = elSvg("title");
    tip.textContent = `[${b.bin_start.toFixed(0)}, ${b.bin_end.toFixed(0)}]: ${b.count} paths (${(b.frequency * 100).toFixed(1)}%)`;
    rect.appendChild(tip);
    svg.appendChild(rect);

    if (idx % 2 === 0 || idx === bins.length - 1) {
      const xl = elSvg("text", {
        x: (x + barW / 2).toFixed(1),
        y: pad.top + plotH + 18,
        fill: "#8b9bb4",
        "font-size": 10,
        "font-family": "monospace",
        "text-anchor": "middle",
      });
      xl.textContent = Math.round(b.bin_start).toLocaleString();
      svg.appendChild(xl);
    }
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

function renderTrajectories(svg, points, initialBankroll) {
  svg.textContent = "";
  if (!points || points.length === 0) {
    return;
  }

  const width = 820;
  const height = 320;
  const pad = { top: 20, right: 24, bottom: 44, left: 72 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const maxStep = Math.max(...points.map((p) => p.step), 1);
  const maxY = Math.max(...points.map((p) => p.p90), initialBankroll * 1.2);
  const minY = 0;

  const xScale = (step) => pad.left + (step / maxStep) * plotW;
  const yScale = (val) => pad.top + plotH - ((val - minY) / Math.max(1, maxY - minY)) * plotH;

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
    lbl.textContent = Math.round(val).toLocaleString();
    svg.appendChild(lbl);
  }

  // Initial bankroll horizontal reference
  const yInit = yScale(initialBankroll);
  svg.appendChild(
    elSvg("line", {
      x1: pad.left,
      y1: yInit,
      x2: width - pad.right,
      y2: yInit,
      stroke: "#475569",
      "stroke-dasharray": "4,4",
      "stroke-width": 1.2,
    })
  );

  const series = [
    { key: "p90", color: "#34d399" },
    { key: "median", color: "#38bdf8" },
    { key: "p10", color: "#fb7185" },
  ];
  for (const s of series) {
    const pts = points.map((p) => `${xScale(p.step).toFixed(1)},${yScale(p[s.key]).toFixed(1)}`);
    svg.appendChild(
      elSvg("polyline", {
        fill: "none",
        stroke: s.color,
        "stroke-width": s.key === "median" ? 2.5 : 2,
        points: pts.join(" "),
      })
    );
  }

  for (const idx of [0, Math.floor(points.length / 2), points.length - 1]) {
    const p = points[idx];
    const lbl = elSvg("text", {
      x: xScale(p.step).toFixed(1),
      y: pad.top + plotH + 18,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "middle",
    });
    lbl.textContent = `Bet ${p.step}`;
    svg.appendChild(lbl);
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

function renderKellyCurve(svg, curve, fullKelly, chosenFraction) {
  svg.textContent = "";
  if (!curve || curve.length === 0) {
    return;
  }

  const width = 820;
  const height = 300;
  const pad = { top: 20, right: 24, bottom: 44, left: 72 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const minX = 0;
  const maxX = Math.max(...curve.map((c) => c.fraction), chosenFraction, 0.2);
  const gVals = curve.map((c) => c.log_growth);
  const minY = Math.min(...gVals, -0.005);
  const maxY = Math.max(...gVals, 0.005);
  const spanY = Math.max(1e-5, maxY - minY);

  const xScale = (f) => pad.left + ((f - minX) / (maxX - minX)) * plotW;
  const yScale = (g) => pad.top + plotH - ((g - minY) / spanY) * plotH;

  // Zero growth horizontal line
  if (minY <= 0 && maxY >= 0) {
    const y0 = yScale(0);
    svg.appendChild(
      elSvg("line", {
        x1: pad.left,
        y1: y0,
        x2: width - pad.right,
        y2: y0,
        stroke: "#475569",
        "stroke-width": 1.2,
      })
    );
  }

  const pts = curve.map((c) => `${xScale(c.fraction).toFixed(1)},${yScale(c.log_growth).toFixed(1)}`);
  svg.appendChild(
    elSvg("polyline", {
      fill: "none",
      stroke: "#38bdf8",
      "stroke-width": 2.5,
      points: pts.join(" "),
    })
  );

  // Full Kelly vertical marker
  if (fullKelly > 0 && fullKelly <= maxX) {
    const xk = xScale(fullKelly);
    svg.appendChild(
      elSvg("line", {
        x1: xk,
        y1: pad.top,
        x2: xk,
        y2: pad.top + plotH,
        stroke: "#34d399",
        "stroke-dasharray": "5,4",
        "stroke-width": 1.8,
      })
    );
  }

  // Chosen fraction vertical marker
  const xc = xScale(chosenFraction);
  svg.appendChild(
    elSvg("line", {
      x1: xc,
      y1: pad.top,
      x2: xc,
      y2: pad.top + plotH,
      stroke: "#fbbf24",
      "stroke-dasharray": "5,4",
      "stroke-width": 1.8,
    })
  );

  for (let i = 0; i <= 4; i += 1) {
    const f = (i / 4) * maxX;
    const lbl = elSvg("text", {
      x: xScale(f).toFixed(1),
      y: pad.top + plotH + 18,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "middle",
    });
    lbl.textContent = `${(f * 100).toFixed(0)}%`;
    svg.appendChild(lbl);
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

async function runBankrollSim() {
  clearBankrollError();
  const form = document.getElementById("bankroll-form");
  const fd = new FormData(form);
  const rawRuin = String(fd.get("ruin_threshold") || "").trim();

  const body = {
    initial_bankroll: Number(fd.get("initial_bankroll")),
    win_prob: Number(fd.get("win_prob")),
    payout_odds: Number(fd.get("payout_odds")),
    bet_fraction: Number(fd.get("bet_fraction")),
    sizing_mode: String(fd.get("sizing_mode")),
    num_bets: Number(fd.get("num_bets")),
    num_paths: Number(fd.get("num_paths")),
    ruin_threshold: rawRuin === "" ? null : Number(rawRuin),
    seed: Number(fd.get("seed")),
  };

  const res = await fetch("/api/quant/bankroll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    const msg =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail) && data.detail[0]
          ? data.detail[0].msg
          : "Simulation failed.";
    showBankrollError(msg);
    return;
  }

  lastSim = data;
  document.getElementById("stat-kelly").textContent = `${(data.full_kelly_fraction * 100).toFixed(2)}%`;
  document.getElementById("stat-half-kelly").textContent =
    `Half Kelly: ${(data.half_kelly_fraction * 100).toFixed(2)}% | Edge/unit: ${(data.expected_edge_per_unit * 100).toFixed(2)}%`;

  document.getElementById("stat-ror").textContent = `${(data.empirical_risk_of_ruin * 100).toFixed(2)}%`;
  const analyticalNote =
    data.analytical_risk_of_ruin !== null
      ? ` | Exact RoR: ${(data.analytical_risk_of_ruin * 100).toFixed(2)}%`
      : "";
  document.getElementById("stat-ror-sub").textContent =
    `95% CI [${(data.ruin_ci_lower * 100).toFixed(1)}%, ${(data.ruin_ci_upper * 100).toFixed(1)}%]${analyticalNote}`;

  const gEl = document.getElementById("stat-growth");
  gEl.textContent = `${(data.chosen_log_growth * 100).toFixed(3)}% / bet`;
  gEl.className = `stat-value mono ${data.chosen_log_growth >= 0 ? "amount-pos" : "amount-neg"}`;
  document.getElementById("stat-growth-sub").textContent =
    `Optimal g(f*): ${(data.optimal_log_growth * 100).toFixed(3)}% / bet`;

  document.getElementById("stat-median").textContent = Number(data.median_terminal).toLocaleString();
  document.getElementById("stat-median-sub").textContent =
    `P(profit): ${(data.profit_probability * 100).toFixed(1)}% | p05-p95: ${Number(data.p05_terminal).toLocaleString()}..${Number(data.p95_terminal).toLocaleString()}`;

  renderHistogram(document.getElementById("histogram-chart"), data.histogram, data.initial_bankroll);
  renderTrajectories(document.getElementById("trajectory-chart"), data.trajectories, data.initial_bankroll);
  renderKellyCurve(
    document.getElementById("kelly-chart"),
    data.kelly_curve,
    data.full_kelly_fraction,
    data.bet_fraction
  );
}

function setFractionMultiplier(mult) {
  const p = Number(document.getElementById("br-prob").value);
  const b = Number(document.getElementById("br-odds").value);
  const fk = Math.max(0.01, (b * p - (1 - p)) / b);
  const chosen = Math.min(0.9, Math.max(0.005, fk * mult));
  document.getElementById("br-frac").value = chosen.toFixed(3);
  runBankrollSim();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("bankroll-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runBankrollSim();
  });
  document.getElementById("btn-half-kelly").addEventListener("click", () => setFractionMultiplier(0.5));
  document.getElementById("btn-full-kelly").addEventListener("click", () => setFractionMultiplier(1.0));
  document.getElementById("btn-overbet-kelly").addEventListener("click", () => setFractionMultiplier(2.2));
  runBankrollSim();
});
