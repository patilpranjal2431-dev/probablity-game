"use strict";

let activeSocket = null;
let currentState = null;

function showLobbyError(msg) {
  const el = document.getElementById("lobby-error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearLobbyError() {
  const el = document.getElementById("lobby-error");
  el.textContent = "";
  el.classList.add("hidden");
}

function appendLog(text) {
  const list = document.getElementById("event-log");
  const li = document.createElement("li");
  li.textContent = text;
  list.prepend(li);
}

async function fetchLobbies() {
  const res = await fetch("/api/lobbies", { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.replace("/");
    return;
  }
  if (!res.ok) {
    showLobbyError("Failed to fetch lobbies.");
    return;
  }
  const tables = await res.json();
  const tbody = document.getElementById("lobbies-tbody");
  tbody.textContent = "";

  if (tables.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "empty-state";
    td.textContent = "No tables yet. Create one above.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const t of tables) {
    const tr = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.className = "mono";
    idCell.textContent = `#${t.table_id}`;

    const gameCell = document.createElement("td");
    gameCell.textContent = t.game_type;

    const modeCell = document.createElement("td");
    modeCell.textContent = t.opponent_type === "bot" ? `vs ${t.bot_strategy}` : "PvP";

    const seatsCell = document.createElement("td");
    seatsCell.textContent = t.seats.map((s) => s.username || "open").join(" vs ");

    const statusCell = document.createElement("td");
    statusCell.className = "mono";
    statusCell.textContent = t.status;

    const actionCell = document.createElement("td");
    actionCell.className = "text-right";
    const joinBtn = document.createElement("button");
    joinBtn.type = "button";
    joinBtn.className = "btn btn-secondary";
    joinBtn.textContent = "Join";
    joinBtn.addEventListener("click", () => connectToTable(t.table_id));
    actionCell.appendChild(joinBtn);

    tr.append(idCell, gameCell, modeCell, seatsCell, statusCell, actionCell);
    tbody.appendChild(tr);
  }
}

function renderTableState(state) {
  currentState = state;
  document.getElementById("active-table-panel").classList.remove("hidden");
  document.getElementById("table-heading").textContent =
    `Table #${state.table_id} (${state.game_type}) — Hand #${state.hand_number}`;

  const privVal = document.getElementById("private-card-val");
  const privEq = document.getElementById("private-equity-val");
  if (state.your_private) {
    privVal.textContent = state.your_private.label;
    privEq.textContent = `Showdown Equity: ${(state.your_private.equity * 100).toFixed(1)}%`;
  } else {
    privVal.textContent = "--";
    privEq.textContent = "Waiting for hand";
  }

  document.getElementById("pot-val").textContent = `${state.pot} coins`;
  const turnText =
    state.current_turn_seat === null
      ? `Status: ${state.status}`
      : state.current_turn_seat === state.your_seat
        ? `Your turn (${state.turn_timeout_seconds}s timeout)`
        : "Waiting for opponent...";
  document.getElementById("turn-status-val").textContent = turnText;

  const seatsTbody = document.getElementById("seats-tbody");
  seatsTbody.textContent = "";
  for (const p of state.players) {
    const tr = document.createElement("tr");

    const seatCell = document.createElement("td");
    seatCell.className = "mono";
    seatCell.textContent = p.seat === state.your_seat ? `Seat ${p.seat} (You)` : `Seat ${p.seat}`;

    const userCell = document.createElement("td");
    userCell.textContent = p.username || "Waiting...";

    const stackCell = document.createElement("td");
    stackCell.className = "mono text-right";
    stackCell.textContent = `${p.stack.toLocaleString()} coins`;

    const contribCell = document.createElement("td");
    contribCell.className = "mono text-right";
    contribCell.textContent = `${p.contribution}`;

    const connCell = document.createElement("td");
    connCell.className = "mono text-right";
    connCell.textContent = p.is_bot ? "bot" : p.connected ? "online" : "offline";

    tr.append(seatCell, userCell, stackCell, contribCell, connCell);
    seatsTbody.appendChild(tr);
  }

  const legal = new Set(state.legal_actions || []);
  document.getElementById("btn-check").disabled = !legal.has("check");
  const callBtn = document.getElementById("btn-call");
  callBtn.disabled = !legal.has("call");
  callBtn.textContent = state.to_call > 0 ? `Call ${state.to_call}` : "Call";

  const betInput = document.getElementById("bet-amount-input");
  betInput.min = String(state.min_bet);
  betInput.max = String(state.effective_max_bet);
  if (Number(betInput.value) < state.min_bet) {
    betInput.value = String(state.min_bet);
  }
  document.getElementById("btn-bet").disabled = !legal.has("bet");
  document.getElementById("btn-fold").disabled = !legal.has("fold");
  document.getElementById("btn-next-hand").disabled = state.current_turn_seat !== null;
}

function connectToTable(tableId) {
  clearLobbyError();
  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }

  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/ws/lobbies/${tableId}`;
  const ws = new WebSocket(wsUrl);
  activeSocket = ws;

  document.getElementById("event-log").textContent = "";
  appendLog(`Connecting to Table #${tableId}...`);

  ws.addEventListener("open", () => {
    appendLog(`Connected to Table #${tableId}.`);
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "table:state") {
      renderTableState(msg);
      return;
    }
    if (msg.type === "hand:action") {
      const amtText = msg.amount > 0 ? ` (${msg.amount})` : "";
      appendLog(`${msg.username}: ${msg.action}${amtText}`);
      return;
    }
    if (msg.type === "hand:timeout") {
      appendLog(`TIMEOUT: ${msg.username} auto-${msg.auto_action}`);
      return;
    }
    if (msg.type === "hand:resolved") {
      const reveal = msg.revealed_hands
        ? ` | Hands: ${msg.revealed_hands.map((h) => `${h.label}`).join(" vs ")}`
        : " | Hidden hands kept private";
      const winner = msg.winner_username ? `${msg.winner_username} won ${msg.pot}` : "Split pot";
      appendLog(`Hand #${msg.hand_number} (${msg.reason}): ${winner}${reveal}`);
      if (Array.isArray(msg.decision_grades)) {
        for (const g of msg.decision_grades) {
          const taken = g.taken_amount > 0 ? `${g.taken_action} ${g.taken_amount}` : g.taken_action;
          const best = g.best_amount > 0 ? `${g.best_action} ${g.best_amount}` : g.best_action;
          appendLog(
            `  EV Grade [${g.username} / ${g.private_label}]: ${taken} (EV ${Number(g.taken_ev).toFixed(2)}), best ${best} (EV ${Number(g.best_ev).toFixed(2)}), regret ${Number(g.regret).toFixed(2)}`
          );
        }
      }
      fetchLobbies();
      return;
    }
    if (msg.type === "error") {
      showLobbyError(`${msg.code}: ${msg.detail}`);
      appendLog(`ERROR (${msg.code}): ${msg.detail}`);
    }
  });

  ws.addEventListener("close", (event) => {
    appendLog(`Disconnected (code ${event.code}).`);
    if (activeSocket === ws) {
      activeSocket = null;
    }
  });
}

function sendAction(action, amount = 0) {
  clearLobbyError();
  if (!activeSocket || activeSocket.readyState !== WebSocket.OPEN) {
    showLobbyError("Not connected to a table.");
    return;
  }
  activeSocket.send(JSON.stringify({ type: "action", action, amount }));
}

document.addEventListener("DOMContentLoaded", () => {
  const oppSelect = document.getElementById("lobby-opponent-type");
  const botField = document.getElementById("bot-strategy-field");
  oppSelect.addEventListener("change", () => {
    botField.classList.toggle("hidden", oppSelect.value !== "bot");
  });

  document.getElementById("create-table-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    clearLobbyError();
    const formData = new FormData(e.target);
    const opponentType = String(formData.get("opponent_type"));
    const body = {
      game_type: String(formData.get("game_type")),
      opponent_type: opponentType,
      ante: Number(formData.get("ante")),
    };
    if (opponentType === "bot") {
      body.bot_strategy = String(formData.get("bot_strategy"));
    }

    const res = await fetch("/api/lobbies", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      showLobbyError(payload.detail || "Could not create table.");
      return;
    }
    await fetchLobbies();
    connectToTable(payload.table_id);
  });

  document.getElementById("refresh-lobbies-btn").addEventListener("click", fetchLobbies);
  document.getElementById("leave-table-btn").addEventListener("click", () => {
    if (activeSocket) {
      activeSocket.close();
      activeSocket = null;
    }
    document.getElementById("active-table-panel").classList.add("hidden");
  });

  document.getElementById("btn-check").addEventListener("click", () => sendAction("check", 0));
  document.getElementById("btn-call").addEventListener("click", () => sendAction("call", 0));
  document.getElementById("btn-fold").addEventListener("click", () => sendAction("fold", 0));
  document.getElementById("btn-bet").addEventListener("click", () => {
    const amount = Number(document.getElementById("bet-amount-input").value || 0);
    sendAction("bet", amount);
  });
  document.getElementById("btn-next-hand").addEventListener("click", () => {
    clearLobbyError();
    if (activeSocket && activeSocket.readyState === WebSocket.OPEN) {
      activeSocket.send(JSON.stringify({ type: "next_hand" }));
    }
  });

  fetchLobbies();
});
