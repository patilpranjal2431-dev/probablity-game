"use strict";

function showLbError(msg) {
  const el = document.getElementById("lb-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearLbError() {
  const el = document.getElementById("lb-error");
  el.textContent = "";
  el.classList.add("hidden");
}

function fmtEv(val) {
  const num = Number(val);
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}`;
}

function fmtActionLabel(action, amount) {
  if (action === "bet" && amount > 0) {
    return `bet ${amount}`;
  }
  return action;
}

function renderSkillLeaderboard(entries) {
  const tbody = document.getElementById("skill-lb-tbody");
  tbody.textContent = "";
  if (entries.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "empty-state";
    td.textContent = "No players found yet.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const row of entries) {
    const tr = document.createElement("tr");

    const rankCell = document.createElement("td");
    rankCell.className = "mono";
    rankCell.textContent = `#${row.rank}`;

    const nameCell = document.createElement("td");
    nameCell.textContent = row.is_bot ? `${row.username} [BOT]` : row.username;

    const evCell = document.createElement("td");
    evCell.className = `mono text-right ${row.cumulative_ev >= 0 ? "amount-pos" : "amount-neg"}`;
    evCell.textContent = fmtEv(row.cumulative_ev);

    const regretCell = document.createElement("td");
    regretCell.className = `mono text-right ${row.total_regret > 0.01 ? "amount-neg" : ""}`;
    regretCell.textContent = Number(row.total_regret).toFixed(2);

    const optCell = document.createElement("td");
    optCell.className = "mono text-right";
    optCell.textContent =
      row.decisions_count > 0 ? `${(row.optimal_rate * 100).toFixed(1)}%` : "--";

    const countCell = document.createElement("td");
    countCell.className = "mono text-right";
    countCell.textContent = `${row.decisions_count} (${row.hands_played})`;

    const coinsCell = document.createElement("td");
    coinsCell.className = "mono text-right";
    coinsCell.textContent = Number(row.coin_balance).toLocaleString();

    tr.append(rankCell, nameCell, evCell, regretCell, optCell, countCell, coinsCell);
    tbody.appendChild(tr);
  }
}

function renderCoinsLeaderboard(entries) {
  const tbody = document.getElementById("coins-lb-tbody");
  tbody.textContent = "";
  if (entries.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "empty-state";
    td.textContent = "No players found yet.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const row of entries) {
    const tr = document.createElement("tr");

    const rankCell = document.createElement("td");
    rankCell.className = "mono";
    rankCell.textContent = `#${row.rank}`;

    const nameCell = document.createElement("td");
    nameCell.textContent = row.is_bot ? `${row.username} [BOT]` : row.username;

    const balanceCell = document.createElement("td");
    balanceCell.className = "mono text-right";
    balanceCell.textContent = `${Number(row.coin_balance).toLocaleString()} coins`;

    const profitCell = document.createElement("td");
    profitCell.className = `mono text-right ${row.net_coin_profit >= 0 ? "amount-pos" : "amount-neg"}`;
    const sign = row.net_coin_profit > 0 ? "+" : "";
    profitCell.textContent = `${sign}${Number(row.net_coin_profit).toLocaleString()}`;

    const evCell = document.createElement("td");
    evCell.className = `mono text-right ${row.cumulative_ev >= 0 ? "amount-pos" : "amount-neg"}`;
    evCell.textContent = fmtEv(row.cumulative_ev);

    const regretCell = document.createElement("td");
    regretCell.className = "mono text-right";
    regretCell.textContent = Number(row.total_regret).toFixed(2);

    const handsCell = document.createElement("td");
    handsCell.className = "mono text-right";
    handsCell.textContent = String(row.hands_played);

    tr.append(rankCell, nameCell, balanceCell, profitCell, evCell, regretCell, handsCell);
    tbody.appendChild(tr);
  }
}

async function fetchLeaderboards() {
  clearLbError();
  const includeBots = document.getElementById("include-bots-toggle").checked;
  const res = await fetch(`/api/leaderboards?include_bots=${includeBots}`, {
    credentials: "same-origin",
  });
  if (!res.ok) {
    showLbError("Could not load leaderboards.");
    return;
  }
  const data = await res.json();
  renderSkillLeaderboard(data.skill_leaderboard || []);
  renderCoinsLeaderboard(data.coins_leaderboard || []);
}

async function fetchMyDecisions() {
  const res = await fetch("/api/decisions/me?limit=30", { credentials: "same-origin" });
  if (!res.ok) {
    return;
  }
  const data = await res.json();
  const section = document.getElementById("my-grades-section");
  section.classList.remove("hidden");

  document.getElementById("my-cum-ev").textContent = `${fmtEv(data.cumulative_ev)} EV`;
  document.getElementById("my-total-regret").textContent = Number(data.total_regret).toFixed(2);
  document.getElementById("my-optimal-rate").textContent =
    data.decisions_count > 0 ? `${(data.optimal_rate * 100).toFixed(1)}%` : "--";

  const tbody = document.getElementById("my-grades-tbody");
  tbody.textContent = "";
  const list = data.decisions || [];
  if (list.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "empty-state";
    td.textContent = "Play a hand in Live Lobby to see your EV grades.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const g of list) {
    const tr = document.createElement("tr");

    const handCell = document.createElement("td");
    handCell.className = "mono";
    handCell.textContent = `#${g.hand_id}.${g.decision_index}`;

    const gameCell = document.createElement("td");
    gameCell.textContent = g.game_type;

    const privCell = document.createElement("td");
    privCell.className = "mono";
    privCell.textContent = g.private_label;

    const eqCell = document.createElement("td");
    eqCell.className = "mono text-right";
    eqCell.textContent = `${(g.equity * 100).toFixed(1)}%`;

    const takenCell = document.createElement("td");
    takenCell.className = "mono";
    const autoTag = g.is_auto ? " [auto]" : "";
    takenCell.textContent = `${fmtActionLabel(g.taken_action, g.taken_amount)} (${fmtEv(g.taken_ev)})${autoTag}`;

    const bestCell = document.createElement("td");
    bestCell.className = "mono";
    bestCell.textContent = `${fmtActionLabel(g.best_action, g.best_amount)} (${fmtEv(g.best_ev)})`;

    const regretCell = document.createElement("td");
    regretCell.className = `mono text-right ${g.regret > 0.01 ? "amount-neg" : "amount-pos"}`;
    regretCell.textContent = Number(g.regret).toFixed(2);

    tr.append(handCell, gameCell, privCell, eqCell, takenCell, bestCell, regretCell);
    tbody.appendChild(tr);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("include-bots-toggle").addEventListener("change", fetchLeaderboards);
  document.getElementById("refresh-lb-btn").addEventListener("click", () => {
    fetchLeaderboards();
    fetchMyDecisions();
  });
  fetchLeaderboards();
  fetchMyDecisions();
});
