// Shared helpers: API calls, formatting, toasts, dialogs, theme.

export const session = { csrf: "" };

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export async function api(path, { method = "GET", json, body, signal } = {}) {
  const init = { method, credentials: "same-origin", headers: {}, signal };
  if (method !== "GET") init.headers["X-CSRF-Token"] = session.csrf;
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.body = body;
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (response.status === 401 && location.pathname !== "/login") {
    location.replace("/login");
    throw new ApiError("Your session expired. Sign in again.", 401, data);
  }
  if (!response.ok) {
    throw new ApiError((data && data.error) || `Request failed (${response.status}).`, response.status, data);
  }
  return data;
}

// Formatting

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatBytes(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso, { relative = true } = {}) {
  if (!iso) return "—";
  const date = new Date(iso);
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (relative && seconds < 60) return "just now";
  if (relative && seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (relative && seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// Theme

export function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("theme", next);
  } catch {
    /* storage unavailable */
  }
  return next;
}

// Toasts

function toastHost() {
  let host = document.querySelector(".toasts");
  if (!host) {
    host = document.createElement("div");
    host.className = "toasts";
    host.setAttribute("role", "status");
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
  }
  return host;
}

// With ``action`` ({ label, onClick }), the toast gets a button and stays up for ``duration`` ms.
export function toast(message, type = "info", { action, duration } = {}) {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  const text = document.createElement("span");
  text.textContent = message;
  element.appendChild(text);
  if (action) {
    element.classList.add("has-action");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      element.remove();
      action.onClick();
    });
    element.appendChild(button);
  }
  toastHost().appendChild(element);
  setTimeout(() => element.remove(), duration ?? (action ? 10000 : type === "error" ? 6000 : 3500));
}

// Dialogs

// With ``countdown`` (seconds), the confirm button stays dimmed and disabled until it reaches zero.
export function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false, countdown = 0 }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal";
    dialog.innerHTML = `
      <div class="modal-header"><h2></h2></div>
      <div class="modal-body"><p></p></div>
      <div class="modal-actions">
        <button type="button" class="btn" value="cancel">Cancel</button>
        <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"}" value="confirm"></button>
      </div>`;
    dialog.querySelector("h2").textContent = title;
    dialog.querySelector("p").textContent = message;
    const confirmButton = dialog.querySelector('[value="confirm"]');
    confirmButton.textContent = confirmLabel;
    let timer = 0;
    if (countdown > 0) {
      let remaining = countdown;
      confirmButton.disabled = true;
      confirmButton.textContent = `${confirmLabel} (${remaining})`;
      timer = setInterval(() => {
        remaining -= 1;
        if (remaining > 0) {
          confirmButton.textContent = `${confirmLabel} (${remaining})`;
          return;
        }
        clearInterval(timer);
        confirmButton.disabled = false;
        confirmButton.textContent = confirmLabel;
      }, 1000);
    }
    let result = false;
    dialog.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (button?.disabled) return;
      if (button) {
        result = button.value === "confirm";
        dialog.close();
      } else if (event.target === dialog) {
        dialog.close();
      }
    });
    dialog.addEventListener("close", () => {
      clearInterval(timer);
      dialog.remove();
      resolve(result);
    });
    document.body.appendChild(dialog);
    dialog.showModal();
    dialog.querySelector('[value="cancel"]').focus();
  });
}

export function closeOnBackdrop(dialog) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.className = "sr-only";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}
