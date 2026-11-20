import { api } from "./common.js";

const $ = (id) => document.getElementById(id);

function showError(id, message) {
  const element = $(id);
  element.textContent = message;
  element.hidden = !message;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.textContent = busy ? "Please wait…" : label;
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("login-error", "");
  setBusy($("login-submit"), true, "Sign in");
  try {
    const result = await api("/api/auth/login", { method: "POST", json: { email: $("email").value, password: $("password").value } });
    location.replace(result.user.role === "admin" ? "/admin" : "/");
  } catch (error) {
    showError("login-error", error.message);
    setBusy($("login-submit"), false, "Sign in");
  }
});

