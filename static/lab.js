"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

function createSvgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function renderLogLogChart(svg, points) {
  svg.textContent = "";
  if (!points || points.length === 0) {
    return;
  }

  const width = 820;
  const height = 380;
  const pad = { top: 24, right: 28, bottom: 48, left: 74 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const minLogX = Math.log10(points[0].n);
  const maxLogX = Math.log10(points[points.length - 1].n);

  const errorFloor = 1e-5;
  const yValues = [];
  for (const pt of points) {
    yValues.push(Math.max(pt.abs_error, errorFloor));
    yValues.push(pt.inv_sqrt_n);
    yValues.push(Math.max(pt.se_reference, errorFloor));
  }
  const minLogY = Math.floor(Math.log10(Math.min(...yValues)));
  const maxLogY = Math.ceil(Math.log10(Math.max(...yValues)));

  const xScale = (n) => {
    const lx = Math.log10(n);
    const ratio = maxLogX === minLogX ? 0.5 : (lx - minLogX) / (maxLogX - minLogX);
    return pad.left + ratio * plotW;
  };
  const yScale = (val) => {
    const ly = Math.log10(Math.max(val, errorFloor));
    const ratio = maxLogY === minLogY ? 0.5 : (ly - minLogY) / (maxLogY - minLogY);
    return pad.top + plotH - ratio * plotH;
  };

  // Horizontal log gridlines (powers of 10)
  for (let exp = minLogY; exp <= maxLogY; exp += 1) {
    const yVal = 10 ** exp;
    const y = yScale(yVal);
    svg.appendChild(
      createSvgEl("line", {
        x1: pad.left,
        y1: y,
        x2: width - pad.right,
        y2: y,
        stroke: "#243042",
        "stroke-width": 1,
      })
    );
    const label = createSvgEl("text", {
      x: pad.left - 10,
      y: y + 4,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "end",
    });
    label.textContent = `1e${exp}`;
    svg.appendChild(label);
  }

  // Vertical gridlines at each sample size n
  for (const pt of points) {
    const x = xScale(pt.n);
    svg.appendChild(
      createSvgEl("line", {
        x1: x,
        y1: pad.top,
        x2: x,
        y2: pad.top + plotH,
        stroke: "#1d2736",
        "stroke-width": 1,
      })
    );
    const label = createSvgEl("text", {
      x,
      y: pad.top + plotH + 18,
      fill: "#8b9bb4",
      "font-size": 11,
      "font-family": "monospace",
      "text-anchor": "middle",
    });
    label.textContent = String(pt.n);
    svg.appendChild(label);
  }

  // Axes
  svg.appendChild(
    createSvgEl("rect", {
      x: pad.left,
      y: pad.top,
      width: plotW,
      height: plotH,
      fill: "none",
      stroke: "#334155",
      "stroke-width": 1.2,
    })
  );

  const xAxisTitle = createSvgEl("text", {
    x: pad.left + plotW / 2,
    y: height - 8,
    fill: "#8b9bb4",
    "font-size": 12,
    "text-anchor": "middle",
  });
  xAxisTitle.textContent = "Sample size n (log scale)";
  svg.appendChild(xAxisTitle);

  // 1/sqrt(n) reference line
  const invPts = points.map((p) => `${xScale(p.n).toFixed(1)},${yScale(p.inv_sqrt_n).toFixed(1)}`);
  svg.appendChild(
    createSvgEl("polyline", {
      fill: "none",
      stroke: "#fbbf24",
      "stroke-width": 2,
      "stroke-dasharray": "6,4",
      points: invPts.join(" "),
    })
  );

  // Theoretical SE sqrt(p(1-p)/n) reference line
  const sePts = points.map((p) => `${xScale(p.n).toFixed(1)},${yScale(p.se_reference).toFixed(1)}`);
  svg.appendChild(
    createSvgEl("polyline", {
      fill: "none",
      stroke: "#34d399",
      "stroke-width": 2,
      "stroke-dasharray": "2,4",
      points: sePts.join(" "),
    })
  );

  // Empirical |estimate - exact| polyline + markers
  const errPts = points.map((p) => `${xScale(p.n).toFixed(1)},${yScale(p.abs_error).toFixed(1)}`);
  svg.appendChild(
    createSvgEl("polyline", {
      fill: "none",
      stroke: "#38bdf8",
      "stroke-width": 2.5,
      points: errPts.join(" "),
    })
  );

  for (const p of points) {
    const cx = xScale(p.n);
    const cy = yScale(p.abs_error);
    const circle = createSvgEl("circle", {
      cx: cx.toFixed(1),
      cy: cy.toFixed(1),
      r: 4,
      fill: "#38bdf8",
      stroke: "#0b1018",
      "stroke-width": 1.5,
    });
    const title = createSvgEl("title");
    title.textContent = `n=${p.n}, |error|=${p.abs_error.toExponential(3)}`;
    circle.appendChild(title);
    svg.appendChild(circle);
  }
}

function renderConvergenceTable(tbody, points) {
  tbody.textContent = "";
  for (const p of points) {
    const row = document.createElement("tr");

    const nCell = document.createElement("td");
    nCell.className = "mono text-right";
    nCell.textContent = p.n.toLocaleString();

    const estCell = document.createElement("td");
    estCell.className = "mono text-right";
    estCell.textContent = p.estimate.toFixed(6);

    const ciCell = document.createElement("td");
    ciCell.className = "mono text-right";
    ciCell.textContent = `[${p.ci_lower.toFixed(5)}, ${p.ci_upper.toFixed(5)}]`;

    const errCell = document.createElement("td");
    errCell.className = "mono text-right";
    errCell.textContent = p.abs_error.toFixed(6);

    const refCell = document.createElement("td");
    refCell.className = "mono text-right";
    refCell.textContent = p.inv_sqrt_n.toFixed(6);

    row.append(nCell, estCell, ciCell, errCell, refCell);
    tbody.appendChild(row);
  }
}

async function loadPokerTable() {
  const pokerTbody = document.getElementById("poker-tbody");
  const res = await fetch("/api/quant/exact/poker");
  if (!res.ok) {
    return;
  }
  const data = await res.json();
  pokerTbody.textContent = "";
  for (const hand of data.hands) {
    const row = document.createElement("tr");

    const rankCell = document.createElement("td");
    rankCell.className = "mono";
    rankCell.textContent = hand.rank;

    const countCell = document.createElement("td");
    countCell.className = "mono text-right";
    countCell.textContent = hand.count.toLocaleString();

    const probCell = document.createElement("td");
    probCell.className = "mono text-right";
    probCell.textContent = `${(hand.probability * 100).toFixed(5)}%`;

    row.append(rankCell, countCell, probCell);
    pokerTbody.appendChild(row);
  }
}

async function runConvergence() {
  const errorBanner = document.getElementById("lab-error");
  errorBanner.textContent = "";
  errorBanner.classList.add("hidden");

  const problem = document.getElementById("problem-select").value;
  const seed = Number(document.getElementById("seed-input").value || 42);

  const res = await fetch("/api/quant/convergence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ problem, seed }),
  });

  const payload = await res.json();
  if (!res.ok) {
    errorBanner.textContent = payload.detail || "Failed to run convergence analysis.";
    errorBanner.classList.remove("hidden");
    return;
  }

  document.getElementById("exact-prob-val").textContent = payload.exact_probability.toFixed(6);
  document.getElementById("exact-prob-label").textContent = payload.label;
  document.getElementById("slope-val").textContent =
    payload.log_log_slope === null ? "N/A" : payload.log_log_slope.toFixed(3);

  const cov = payload.coverage;
  document.getElementById("coverage-val").textContent = `${(cov.empirical_coverage * 100).toFixed(1)}%`;
  document.getElementById("coverage-sub").textContent =
    `${cov.covered_count}/${cov.num_experiments} Wilson 95% CIs covered exact p (avg width ${cov.mean_ci_width.toFixed(4)})`;

  renderLogLogChart(document.getElementById("convergence-chart"), payload.points);
  renderConvergenceTable(document.getElementById("convergence-tbody"), payload.points);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("convergence-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runConvergence();
  });
  loadPokerTable();
  runConvergence();
});
