"use strict";

function extractErrorMessage(payload, fallback) {
  if (!payload) {
    return fallback;
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    const first = payload.detail[0];
    if (first && typeof first.msg === "string") {
      return first.msg;
    }
  }
  return fallback;
}

function showBanner(element, message) {
  element.textContent = message;
  element.classList.remove("hidden");
}

function hideBanner(element) {
  element.textContent = "";
  element.classList.add("hidden");
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  return { response, payload };
}

function initAuthPage() {
  const tabLogin = document.getElementById("tab-login");
  const tabRegister = document.getElementById("tab-register");
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const errorBanner = document.getElementById("auth-error");

  // Redirect straight to profile if the user already has a valid session.
  apiJson("/api/profile").then(({ response }) => {
    if (response.ok) {
      window.location.replace("/profile");
    }
  });

  function setActiveTab(mode) {
    hideBanner(errorBanner);
    const isLogin = mode === "login";
    tabLogin.classList.toggle("active", isLogin);
    tabRegister.classList.toggle("active", !isLogin);
    tabLogin.setAttribute("aria-selected", String(isLogin));
    tabRegister.setAttribute("aria-selected", String(!isLogin));
    loginForm.classList.toggle("hidden", !isLogin);
    registerForm.classList.toggle("hidden", isLogin);
  }

  tabLogin.addEventListener("click", () => setActiveTab("login"));
  tabRegister.addEventListener("click", () => setActiveTab("register"));

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideBanner(errorBanner);

    const formData = new FormData(loginForm);
    const { response, payload } = await apiJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: String(formData.get("username") || ""),
        password: String(formData.get("password") || ""),
      }),
    });

    if (!response.ok) {
      showBanner(errorBanner, extractErrorMessage(payload, "Sign in failed."));
      return;
    }

    window.location.assign("/profile");
  });

  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideBanner(errorBanner);

    const formData = new FormData(registerForm);
    const { response, payload } = await apiJson("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: String(formData.get("username") || ""),
        email: String(formData.get("email") || ""),
        password: String(formData.get("password") || ""),
      }),
    });

    if (!response.ok) {
      showBanner(errorBanner, extractErrorMessage(payload, "Registration failed."));
      return;
    }

    window.location.assign("/profile");
  });
}

function formatCoins(value) {
  return `${Number(value).toLocaleString()} coins`;
}

function formatSignedAmount(amount) {
  const num = Number(amount);
  const formatted = Math.abs(num).toLocaleString();
  return num > 0 ? `+${formatted}` : `-${formatted}`;
}

function formatUtcTimestamp(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toISOString().replace("T", " ").slice(0, 19);
}

async function initProfilePage() {
  const navUsername = document.getElementById("nav-username");
  const logoutBtn = document.getElementById("logout-btn");
  const errorBanner = document.getElementById("profile-error");
  const walletBalance = document.getElementById("wallet-balance");
  const profileUsername = document.getElementById("profile-username");
  const profileEmail = document.getElementById("profile-email");
  const txEmpty = document.getElementById("tx-empty");
  const txTbody = document.getElementById("tx-tbody");

  logoutBtn.addEventListener("click", async () => {
    await apiJson("/api/auth/logout", { method: "POST" });
    window.location.assign("/");
  });

  const { response, payload } = await apiJson("/api/profile");
  if (response.status === 401) {
    window.location.replace("/");
    return;
  }
  if (!response.ok || !payload) {
    showBanner(errorBanner, extractErrorMessage(payload, "Could not load profile."));
    return;
  }

  navUsername.textContent = `@${payload.user.username}`;
  profileUsername.textContent = payload.user.username;
  profileEmail.textContent = payload.user.email;
  walletBalance.textContent = formatCoins(payload.balance);

  txTbody.textContent = "";
  const transactions = Array.isArray(payload.transactions) ? payload.transactions : [];
  if (transactions.length === 0) {
    txEmpty.classList.remove("hidden");
    return;
  }

  txEmpty.classList.add("hidden");
  for (const tx of transactions) {
    const row = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.className = "mono";
    idCell.textContent = `#${tx.id}`;

    const typeCell = document.createElement("td");
    typeCell.className = "mono";
    typeCell.textContent = tx.tx_type;

    const descCell = document.createElement("td");
    descCell.textContent = tx.description || "-";

    const amountCell = document.createElement("td");
    amountCell.className = `mono text-right ${tx.amount >= 0 ? "amount-pos" : "amount-neg"}`;
    amountCell.textContent = formatSignedAmount(tx.amount);

    const balanceCell = document.createElement("td");
    balanceCell.className = "mono text-right";
    balanceCell.textContent = Number(tx.balance_after).toLocaleString();

    const timeCell = document.createElement("td");
    timeCell.className = "mono text-right";
    timeCell.textContent = formatUtcTimestamp(tx.created_at);

    row.append(idCell, typeCell, descCell, amountCell, balanceCell, timeCell);
    txTbody.appendChild(row);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "auth") {
    initAuthPage();
  } else if (page === "profile") {
    initProfilePage();
  }
});
