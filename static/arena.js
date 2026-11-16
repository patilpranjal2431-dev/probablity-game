"use strict";

function formatEv(value) {
  const num = Number(value);
  const sign = num >= 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}`;
}

function renderLeaderboard(tbody, rows) {
  tbody.textContent = "";
  for (const row of rows) {
    const tr = document.createElement("tr");

    const nameCell = document.createElement("td");
    nameCell.textContent = row.name;

    const handsCell = document.createElement("td");
    handsCell.className = "mono text-right";
    handsCell.textContent = row.hands_played.toLocaleString();

    const wltCell = document.createElement("td");
    wltCell.className = "mono text-right";
    wltCell.textContent = `${row.wins}-${row.losses}-${row.ties}`;

    const wrCell = document.createElement("td");
    wrCell.className = "mono text-right";
    wrCell.textContent = `${(row.win_rate * 100).toFixed(1)}% [${(row.win_rate_ci_lower * 100).toFixed(1)}%, ${(row.win_rate_ci_upper * 100).toFixed(1)}%]`;

    const evCell = document.createElement("td");
    evCell.className = `mono text-right ${row.ev_per_game >= 0 ? "amount-pos" : "amount-neg"}`;
    evCell.textContent = `${formatEv(row.ev_per_game)} [${formatEv(row.ev_ci_lower)}, ${formatEv(row.ev_ci_upper)}]`;

    tr.append(nameCell, handsCell, wltCell, wrCell, evCell);
    tbody.appendChild(tr);
  }
}

function renderMatchups(tbody, matchups) {
  tbody.textContent = "";
  for (const m of matchups) {
    const tr = document.createElement("tr");

    const pairCell = document.createElement("td");
    pairCell.textContent = `${m.bot_a_name} vs ${m.bot_b_name}`;

    const wltCell = document.createElement("td");
    wltCell.className = "mono text-right";
    wltCell.textContent = `${m.wins}-${m.losses}-${m.ties}`;

    const wrCell = document.createElement("td");
    wrCell.className = "mono text-right";
    wrCell.textContent = `${(m.win_rate * 100).toFixed(1)}% [${(m.win_rate_ci_lower * 100).toFixed(1)}%, ${(m.win_rate_ci_upper * 100).toFixed(1)}%]`;

    const evCell = document.createElement("td");
    evCell.className = `mono text-right ${m.ev_per_game >= 0 ? "amount-pos" : "amount-neg"}`;
    evCell.textContent = `${formatEv(m.ev_per_game)} [${formatEv(m.ev_ci_lower)}, ${formatEv(m.ev_ci_upper)}]`;

    tr.append(pairCell, wltCell, wrCell, evCell);
    tbody.appendChild(tr);
  }
}

async function runTournament() {
  const errorBanner = document.getElementById("arena-error");
  errorBanner.textContent = "";
  errorBanner.classList.add("hidden");

  const gameType = document.getElementById("game-select").value;
  const handsPerMatchup = Number(document.getElementById("hands-input").value || 500);
  const seed = Number(document.getElementById("arena-seed-input").value || 42);

  const res = await fetch("/api/games/tournament", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      game_type: gameType,
      hands_per_matchup: handsPerMatchup,
      seed,
    }),
  });

  const payload = await res.json();
  if (!res.ok) {
    errorBanner.textContent = payload.detail || "Tournament execution failed.";
    errorBanner.classList.remove("hidden");
    return;
  }

  renderLeaderboard(document.getElementById("leaderboard-tbody"), payload.leaderboard);
  renderMatchups(document.getElementById("matchups-tbody"), payload.matchups);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("tournament-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runTournament();
  });
  runTournament();
});
