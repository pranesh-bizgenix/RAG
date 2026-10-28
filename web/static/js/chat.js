import {
  ApiError,
  api,
  closeOnBackdrop,
  confirmDialog,
  copyText,
  loadSession,
  session,
  toast,
  toggleTheme,
} from "./common.js";
import { normalizeCitations, renderMarkdown } from "./markdown.js";

const $ = (id) => document.getElementById(id);
const layout = $("layout");
const thread = $("thread");
const messagesEl = $("messages");
const welcome = $("welcome");
const prompt = $("prompt");
const sendBtn = $("send");
const stopBtn = $("stop");
const listEl = $("conversation-list");
const mobile = window.matchMedia("(max-width: 900px)");

const MARK_SVG = '<img src="/static/img/bizgenix-symbol.png" alt="" width="28" height="28" />';
const ICONS = {
  copy: '<svg viewBox="0 0 24 24" class="icon"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  check: '<svg viewBox="0 0 24 24" class="icon"><path d="m5 12 5 5L20 7"/></svg>',
  retry: '<svg viewBox="0 0 24 24" class="icon"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5"/></svg>',
  edit: '<svg viewBox="0 0 24 24" class="icon"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" class="icon"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
};

const state = {
  conversations: [],
  currentId: null,
  controller: null,
};

// Sidebar

function setSidebar(open) {
  if (mobile.matches) {
    layout.classList.toggle("sidebar-open", open);
    $("scrim").hidden = !open;
  } else {
    layout.classList.toggle("sidebar-collapsed", !open);
    try {
      localStorage.setItem("sidebar", open ? "open" : "closed");
    } catch {
      /* ignore */
    }
  }
}

$("open-sidebar").addEventListener("click", () => setSidebar(true));
$("close-sidebar").addEventListener("click", () => setSidebar(false));
$("scrim").addEventListener("click", () => setSidebar(false));
try {
  if (localStorage.getItem("sidebar") === "closed" && !mobile.matches) layout.classList.add("sidebar-collapsed");
} catch {
  /* ignore */
}

function renderConversationList() {
  listEl.replaceChildren();
  $("delete-all").hidden = !state.conversations.length;
  if (!state.conversations.length) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = "Your conversations will appear here.";
    listEl.appendChild(empty);
    return;
  }
  for (const conversation of state.conversations) {
    const row = document.createElement("div");
    row.className = `conversation${conversation.id === state.currentId ? " active" : ""}`;
    const link = document.createElement("button");
    link.type = "button";
    link.className = "conversation-link";
    const linkTitle = document.createElement("span");
    linkTitle.className = "conversation-title";
    linkTitle.textContent = conversation.title;
    link.appendChild(linkTitle);
    link.title = conversation.title;
    if (conversation.id === state.currentId) link.setAttribute("aria-current", "page");
    link.addEventListener("click", () => openConversation(conversation.id));
    const actions = document.createElement("div");
    actions.className = "conversation-actions";
    actions.innerHTML = `
      <button class="icon-btn" type="button" data-action="rename" aria-label="Rename" title="Rename">${ICONS.edit}</button>
      <button class="icon-btn" type="button" data-action="delete" aria-label="Delete" title="Delete">${ICONS.trash}</button>`;
    actions.querySelector('[data-action="rename"]').addEventListener("click", () => renameConversation(conversation));
    actions.querySelector('[data-action="delete"]').addEventListener("click", () => deleteConversation(conversation));
    row.append(link, actions);
    listEl.appendChild(row);
  }
}

async function loadConversations() {
  const data = await api("/api/conversations");
  state.conversations = data.conversations;
  renderConversationList();
}

function touchConversation(id, title) {
  const existing = state.conversations.find((item) => item.id === id);
  const updated = { ...(existing || { id }), title: title || existing?.title || "New conversation" };
  state.conversations = [updated, ...state.conversations.filter((item) => item.id !== id)];
  renderConversationList();
  if (id === state.currentId) setTitle(updated.title);
}

async function renameConversation(conversation) {
  const dialog = $("rename-dialog");
  const input = $("rename-input");
  input.value = conversation.title;
  dialog.returnValue = "";
  dialog.showModal();
  input.select();
  dialog.addEventListener(
    "close",
    async () => {
      const title = input.value.trim();
      if (dialog.returnValue !== "save" || !title || title === conversation.title) return;
      try {
        await api(`/api/conversations/${conversation.id}`, { method: "PATCH", json: { title } });
        conversation.title = title;
        renderConversationList();
        if (conversation.id === state.currentId) setTitle(title);
      } catch (error) {
        toast(error.message, "error");
      }
    },
    { once: true }
  );
}

async function deleteConversation(conversation) {
  const ok = await confirmDialog({
    title: "Delete conversation?",
    message: `"${conversation.title}" will be permanently deleted.`,
    confirmLabel: "Delete",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/conversations/${conversation.id}`, { method: "DELETE" });
    state.conversations = state.conversations.filter((item) => item.id !== conversation.id);
    if (conversation.id === state.currentId) newChat();
    else renderConversationList();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteAllConversations() {
  const count = state.conversations.length;
  const ok = await confirmDialog({
    title: "Delete all conversations?",
    message: `All ${count} conversation${count === 1 ? "" : "s"} will be permanently deleted. This cannot be undone.`,
    confirmLabel: "Delete all",
    danger: true,
    countdown: 5,
  });
  if (!ok) return;
  try {
    await api("/api/conversations", { method: "DELETE" });
    state.conversations = [];
    newChat();
    toast("All conversations deleted.");
  } catch (error) {
    toast(error.message, "error");
  }
}

$("delete-all").addEventListener("click", deleteAllConversations);

// Thread

function setTitle(title) {
  const fresh = !title || title === "New chat" || title === "New conversation";
  $("chat-title").textContent = fresh ? "New conversation" : title;
  document.title = fresh ? "BIZGENIX AI · Knowledge Copilot" : `${title} · BIZGENIX AI`;
}

function nearBottom() {
  return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 120;
}

function scrollToBottom(force = false) {
  if (force || nearBottom()) thread.scrollTop = thread.scrollHeight;
}

function showWelcome(show) {
  welcome.hidden = !show;
}

function newChat() {
  if (state.controller) state.controller.abort();
  state.currentId = null;
  messagesEl.replaceChildren();
  showWelcome(true);
  setTitle("");
  history.replaceState(null, "", "/");
  renderConversationList();
  if (mobile.matches) setSidebar(false);
  prompt.focus();
}

async function openConversation(id) {
  if (state.controller) state.controller.abort();
  try {
    const conversation = await api(`/api/conversations/${id}`);
    state.currentId = id;
    messagesEl.replaceChildren();
    showWelcome(false);
    setTitle(conversation.title);
    history.replaceState(null, "", `/#${id}`);
    const assistantIndexes = conversation.messages
      .map((message, index) => (message.role === "assistant" ? index : -1))
      .filter((index) => index >= 0);
    const lastAssistant = assistantIndexes.at(-1);
    conversation.messages.forEach((message, index) => {
      if (message.role === "user") addUserMessage(message.content);
      else {
        const view = addAssistantMessage();
        view.finish(message.content, message.sources, {
          stopped: message.status === "stopped",
          canRegenerate: index === lastAssistant && index === conversation.messages.length - 1,
        });
      }
    });
    // A question without an answer (for example after a failed reply) can be answered again.
    if (conversation.messages.at(-1)?.role === "user") {
      addAssistantMessage().fail("This question hasn't been answered yet.", () => regenerate());
    }
    renderConversationList();
    if (mobile.matches) setSidebar(false);
    scrollToBottom(true);
  } catch (error) {
    if (error.status === 404) {
      toast("That conversation no longer exists.", "error");
      newChat();
    } else {
      toast(error.message, "error");
    }
  }
}

function addUserMessage(text) {
  const article = document.createElement("article");
  article.className = "message user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  article.appendChild(bubble);
  messagesEl.appendChild(article);
  return article;
}

function addAssistantMessage() {
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = `
    <div class="assistant-mark" aria-hidden="true">${MARK_SVG}</div>
    <div class="assistant-body">
      <div class="status-line"><span class="dots" aria-hidden="true"><span></span><span></span><span></span></span><span>Searching the knowledge base…</span></div>
      <div class="markdown" hidden></div>
    </div>`;
  messagesEl.appendChild(article);
  const body = article.querySelector(".assistant-body");
  const statusLine = article.querySelector(".status-line");
  const markdown = article.querySelector(".markdown");
  let sources = [];
  let text = "";
  let frame = 0;

  const paint = () => {
    frame = 0;
    markdown.innerHTML = renderMarkdown(text);
    scrollToBottom();
  };

  const view = {
    element: article,
    setStatus(label) {
      statusLine.lastElementChild.textContent = label;
    },
    setSources(list) {
      sources = list || [];
      view.setStatus(sources.length ? "Writing an answer…" : "Thinking…");
    },
    append(chunk) {
      if (!text) {
        statusLine.hidden = true;
        markdown.hidden = false;
        article.classList.add("streaming");
      }
      text += chunk;
      if (!frame) frame = requestAnimationFrame(paint);
    },
    get text() {
      return text;
    },
    finish(finalText, finalSources, { stopped = false, canRegenerate = true } = {}) {
      if (frame) cancelAnimationFrame(frame);
      article.classList.remove("streaming");
      text = finalText ?? text;
      if (finalSources) sources = finalSources;
      statusLine.hidden = true;
      markdown.hidden = false;
      markdown.innerHTML = renderMarkdown(text);
      const documents = groupByDocument(sources, text);
      article.dataset.sources = JSON.stringify(sources);
      article.dataset.documents = JSON.stringify(documents);
      renderSources(body, documents);
      renderActions(body, text, { stopped, canRegenerate });
    },
    fail(message, retry) {
      if (frame) cancelAnimationFrame(frame);
      article.classList.remove("streaming");
      statusLine.hidden = true;
      const card = document.createElement("div");
      card.className = "error-card";
      card.setAttribute("role", "alert");
      const label = document.createElement("span");
      label.textContent = message;
      card.appendChild(label);
      if (retry) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-sm";
        button.innerHTML = `${ICONS.retry}<span>Try again</span>`;
        button.addEventListener("click", () => {
          article.remove();
          retry();
        });
        card.appendChild(button);
      }
      if (text) {
        markdown.innerHTML = renderMarkdown(text);
        body.appendChild(card);
      } else {
        markdown.remove();
        body.appendChild(card);
      }
    },
  };
  return view;
}

// The ids of passages the answer cites inline, e.g. "[1]" or "[1, 3]".
function citedIds(text) {
  const ids = new Set();
  for (const match of normalizeCitations(text).matchAll(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g)) {
    match[1].split(",").forEach((n) => ids.add(n.trim()));
  }
  return ids;
}

// One entry per document the answer drew on. Passages that were retrieved but never cited are
// left out; if the answer cites nothing (e.g. retrieval-only mode), every retrieved passage counts.
function groupByDocument(sources, text) {
  const cited = citedIds(text);
  const used = sources.filter((source) => cited.has(String(source.id)));
  const groups = new Map();
  for (const source of used.length ? used : sources) {
    if (!groups.has(source.document)) groups.set(source.document, { document: source.document, passages: [] });
    groups.get(source.document).passages.push(source);
  }
  return [...groups.values()];
}

function describeLocations(passages) {
  const locations = [...new Set(passages.map((passage) => passage.location).filter(Boolean))];
  const pages = locations.map((location) => location.match(/^Page (\d+)$/)?.[1]);
  if (pages.length > 1 && pages.every(Boolean)) return `Pages ${pages.join(", ")}`;
  return locations.join("; ");
}

function renderSources(body, groups) {
  body.querySelector(".sources")?.remove();
  if (!groups.length) return;
  const wrap = document.createElement("div");
  wrap.className = "sources";
  const heading = document.createElement("div");
  heading.className = "sources-title";
  heading.textContent = "Sources";
  wrap.appendChild(heading);
  groups.forEach((group, index) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "source-chip";
    chip.dataset.document = group.document;
    const number = document.createElement("span");
    number.className = "num";
    number.textContent = index + 1;
    const label = document.createElement("span");
    label.className = "label";
    const locations = describeLocations(group.passages);
    label.textContent = locations ? `${group.document} · ${locations}` : group.document;
    chip.title = label.textContent;
    chip.append(number, label);
    wrap.appendChild(chip);
  });
  body.appendChild(wrap);
}

function renderActions(body, text, { stopped, canRegenerate }) {
  body.querySelector(".message-actions")?.remove();
  messagesEl.querySelectorAll('[data-action="regenerate"]').forEach((button) => button.remove());
  const actions = document.createElement("div");
  actions.className = "message-actions";
  actions.innerHTML = `<button class="icon-btn" type="button" data-action="copy" aria-label="Copy response" title="Copy">${ICONS.copy}</button>`;
  if (canRegenerate) {
    actions.insertAdjacentHTML(
      "beforeend",
      `<button class="icon-btn" type="button" data-action="regenerate" aria-label="Regenerate response" title="Regenerate">${ICONS.retry}</button>`
    );
  }
  if (stopped) actions.insertAdjacentHTML("beforeend", '<span class="message-note">Stopped</span>');
  actions.querySelector('[data-action="copy"]').addEventListener("click", async (event) => {
    const button = event.currentTarget;
    if (await copyText(text)) {
      button.innerHTML = ICONS.check;
      setTimeout(() => (button.innerHTML = ICONS.copy), 1500);
    }
  });
  actions.querySelector('[data-action="regenerate"]')?.addEventListener("click", () => {
    body.closest(".message").remove();
    regenerate();
  });
  body.appendChild(actions);
}

// Sources dialog: opened from chips and inline [n] citations.

const sourceDialog = $("source-dialog");
closeOnBackdrop(sourceDialog);
sourceDialog.querySelector("[data-close]").addEventListener("click", () => sourceDialog.close());

function showSourceDialog(passages) {
  $("source-title").textContent = passages[0].document;
  $("source-location").textContent = describeLocations(passages) || "—";
  const list = $("source-passages");
  list.replaceChildren();
  for (const passage of passages) {
    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = `[${passage.id}] ${passage.location || "Passage"}`;
    const snippet = document.createElement("blockquote");
    snippet.className = "source-snippet";
    snippet.textContent = passage.snippet;
    list.append(label, snippet);
  }
  sourceDialog.showModal();
}

messagesEl.addEventListener("click", async (event) => {
  const trigger = event.target.closest(".cite, .source-chip");
  if (trigger) {
    const article = trigger.closest(".message");
    const passages = trigger.classList.contains("source-chip")
      ? JSON.parse(article.dataset.documents || "[]").find((item) => item.document === trigger.dataset.document)?.passages
      : JSON.parse(article.dataset.sources || "[]").filter((item) => String(item.id) === trigger.dataset.source);
    if (!passages?.length) return;
    showSourceDialog(passages);
    return;
  }
  const copy = event.target.closest(".code-copy");
  if (copy && (await copyText(copy.closest(".code-block").querySelector("code").textContent))) {
    copy.textContent = "Copied";
    setTimeout(() => (copy.textContent = "Copy"), 1500);
  }
});

// Streaming

function setStreaming(active) {
  sendBtn.hidden = active;
  stopBtn.hidden = !active;
  updateSendState();
}

async function streamAnswer(url, body, view, onRequestError) {
  const controller = new AbortController();
  state.controller = controller;
  setStreaming(true);
  let sources = [];
  let finished = false;
  try {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      let message = "Something went wrong. Please try again.";
      try {
        message = (await response.json()).error || message;
      } catch {
        /* not JSON */
      }
      throw new ApiError(message, response.status);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = /^event: (.+)$/m.exec(block)?.[1];
        const dataLine = /^data: (.+)$/m.exec(block)?.[1];
        if (!event || !dataLine) continue;
        const data = JSON.parse(dataLine);
        if (event === "start") touchConversation(data.conversation.id, data.conversation.title);
        else if (event === "sources") {
          sources = data.sources;
          view.setSources(sources);
        } else if (event === "delta") view.append(data.text);
        else if (event === "error") {
          view.fail(data.message, () => regenerate());
          finished = true;
        } else if (event === "done") {
          view.finish(null, sources);
          finished = true;
        }
      }
    }
    if (!finished) {
      if (view.text) view.finish(null, sources, { stopped: true });
      else view.fail("The connection was interrupted before an answer arrived.", () => regenerate());
    }
  } catch (error) {
    if (error.name === "AbortError") {
      if (view.text) view.finish(null, sources, { stopped: true });
      else view.fail("Stopped before an answer was written.", () => regenerate());
    } else if (onRequestError) {
      onRequestError(error);
    } else {
      view.fail(error.message, () => regenerate());
    }
  } finally {
    if (state.controller === controller) state.controller = null;
    setStreaming(false);
    scrollToBottom();
  }
}

async function send(text) {
  if (state.controller || !text.trim()) return;
  prompt.value = "";
  autosize();
  showWelcome(false);
  try {
    if (!state.currentId) {
      const conversation = await api("/api/conversations", { method: "POST" });
      state.currentId = conversation.id;
      history.replaceState(null, "", `/#${conversation.id}`);
      touchConversation(conversation.id, conversation.title);
    }
  } catch (error) {
    toast(error.message, "error");
    prompt.value = text;
    autosize();
    if (!messagesEl.children.length) showWelcome(true);
    return;
  }
  const userEl = addUserMessage(text);
  const view = addAssistantMessage();
  scrollToBottom(true);
  await streamAnswer(`/api/conversations/${state.currentId}/messages`, { content: text }, view, (error) => {
    // The request was rejected before the question was saved (rate limit, busy, validation).
    view.fail(error.message, () => {
      userEl.remove();
      send(text);
    });
  });
}

async function regenerate() {
  if (state.controller || !state.currentId) return;
  const view = addAssistantMessage();
  scrollToBottom(true);
  await streamAnswer(`/api/conversations/${state.currentId}/regenerate`, null, view);
}

// Composer

function autosize() {
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 220)}px`;
  updateSendState();
}

function updateSendState() {
  sendBtn.disabled = Boolean(state.controller) || !prompt.value.trim();
}

prompt.addEventListener("input", autosize);
prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    send(prompt.value);
  }
});
$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  send(prompt.value);
});
stopBtn.addEventListener("click", () => state.controller?.abort());
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.controller && !document.querySelector("dialog[open]")) state.controller.abort();
});
$("new-chat").addEventListener("click", newChat);
$("clear-chat").addEventListener("click", newChat);

// Theme

$("theme-toggle").addEventListener("click", toggleTheme);

// About dialog

const aboutDialog = $("about-dialog");
closeOnBackdrop(aboutDialog);
aboutDialog.querySelector("[data-close]").addEventListener("click", () => aboutDialog.close());
$("about-button").addEventListener("click", () => aboutDialog.showModal());

// Startup

async function loadSuggestions() {
  const container = $("suggestions");
  try {
    const data = await api("/api/suggestions");
    if (!data.has_documents) {
      $("welcome-text").textContent =
        "The knowledge base is empty right now. Once an administrator adds documents, you can ask questions about them here.";
    }
    container.replaceChildren(
      ...data.suggestions.map((item) => {
        // Older servers send plain strings; newer ones send { category, text }.
        const { category, text } = typeof item === "string" ? { category: "Suggested", text: item } : item;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "suggestion";
        button.title = text;
        const label = document.createElement("span");
        label.className = "suggestion-category";
        label.textContent = category;
        const question = document.createElement("span");
        question.className = "suggestion-text";
        question.textContent = text;
        button.append(label, question);
        button.addEventListener("click", () => send(text));
        return button;
      })
    );
  } catch {
    container.replaceChildren();
  }
}

async function init() {
  await loadSession();
  autosize();
  await Promise.all([loadConversations(), loadSuggestions()]);
  const id = location.hash.slice(1);
  if (/^[0-9a-f]{32}$/.test(id)) await openConversation(id);
  else prompt.focus();
}

init().catch((error) => toast(error.message || "Failed to load the app.", "error"));
