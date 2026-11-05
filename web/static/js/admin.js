import {
  api,
  closeOnBackdrop,
  confirmDialog,
  escapeHtml,
  formatBytes,
  formatDate,
  loadSession,
  session,
  toast,
  toggleTheme,
} from "./common.js";

const $ = (id) => document.getElementById(id);

const VIEWS = {
  overview: { title: "Overview", load: loadOverview },
  upload: { title: "Upload Documents", load: loadUpload },
  knowledge: { title: "Knowledge Base", load: loadDocuments },
  reindex: { title: "Re-index", load: loadReindex },
  settings: { title: "Settings", load: loadSettings },
};

const FILE_TYPES = {
  pdf: ["PDF", "pdf"],
  docx: ["WORD", "word"],
  xlsx: ["EXCEL", "excel"],
  xlsm: ["EXCEL", "excel"],
  png: ["IMAGE", "image"],
  jpg: ["IMAGE", "image"],
  jpeg: ["IMAGE", "image"],
  tif: ["IMAGE", "image"],
  tiff: ["IMAGE", "image"],
  txt: ["TEXT", ""],
  md: ["MARKDOWN", ""],
  json: ["JSON", ""],
};

function fileType(filename) {
  const extension = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  return FILE_TYPES[extension] || [extension.toUpperCase() || "FILE", ""];
}

function typePill(filename) {
  const [label, className] = fileType(filename);
  return `<span class="type-pill ${className}">${escapeHtml(label)}</span>`;
}

const STATUS = {
  indexed: ["pill-success", "Indexed"],
  queued: ["pill-info", "Queued"],
  processing: ["pill-warning pill-processing", "Processing"],
  failed: ["pill-danger", "Failed"],
};

const ICONS = {
  view: '<svg viewBox="0 0 24 24" class="icon"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  retry: '<svg viewBox="0 0 24 24" class="icon"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5"/></svg>',
  download: '<svg viewBox="0 0 24 24" class="icon"><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M4 17v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1"/></svg>',
  trash: '<svg viewBox="0 0 24 24" class="icon"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
};

const state = { view: "overview", limits: { max_upload_mb: 25, max_files_per_upload: 10 }, pollTimer: null };

function statusPill(status) {
  const [className, label] = STATUS[status] || ["", status];
  return `<span class="pill ${className}">${escapeHtml(label)}</span>`;
}

// Navigation

function showView(name) {
  if (!VIEWS[name]) name = "overview";
  state.view = name;
  document.querySelectorAll(".view").forEach((section) => (section.hidden = section.dataset.view !== name));
  document.querySelectorAll(".nav-links .nav-link").forEach((link) => {
    const active = link.dataset.view === name;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("crumb").textContent = VIEWS[name].title;
  document.title = `${VIEWS[name].title} · Admin · Knowledge Copilot`;
  $("layout").classList.remove("nav-open");
  $("scrim").hidden = true;
  refresh();
}

async function refresh() {
  clearTimeout(state.pollTimer);
  try {
    const busy = await VIEWS[state.view].load();
    // Poll while documents are being processed so status changes appear without reloading.
    if (busy) state.pollTimer = setTimeout(refresh, 2500);
  } catch (error) {
    toast(error.message, "error");
  }
}

$("refresh").addEventListener("click", async () => {
  const button = $("refresh");
  button.classList.add("spinning");
  await refresh();
  button.classList.remove("spinning");
});

window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
$("open-nav").addEventListener("click", () => {
  $("layout").classList.add("nav-open");
  $("scrim").hidden = false;
});
$("scrim").addEventListener("click", () => {
  $("layout").classList.remove("nav-open");
  $("scrim").hidden = true;
});

function updateThemeLabel() {
  $("theme-toggle").setAttribute(
    "aria-label",
    document.documentElement.getAttribute("data-theme") === "dark" ? "Switch to light theme" : "Switch to dark theme"
  );
}
$("theme-toggle").addEventListener("click", () => {
  toggleTheme();
  updateThemeLabel();
});

function setReindexBanner(needed) {
  $("reindex-banner").hidden = !needed;
}

// Overview

async function loadOverview() {
  const [overview, health, data] = await Promise.all([
    api("/api/admin/overview"),
    api("/api/admin/health"),
    api("/api/admin/documents?status=indexed"),
  ]);
  const indexed = data.documents;
  $("stat-chunks").textContent = overview.chunks.toLocaleString();
  $("stat-indexed").textContent = overview.documents.indexed.toLocaleString();
  $("stat-types").textContent = new Set(indexed.map((doc) => fileType(doc.filename)[0])).size;
  setReindexBanner(overview.index.needs_reindex);

  const hours = Math.floor(health.uptime_seconds / 3600);
  const minutes = Math.floor((health.uptime_seconds % 3600) / 60);
  $("uptime").textContent = `Up ${hours ? `${hours} h ` : ""}${minutes} min · ${health.environment}`;
  const checks = [
    { name: "API Backend", ok: true, detail: "Online" },
    { name: "Vector Store", ok: !overview.index.needs_reindex, detail: `${overview.chunks.toLocaleString()} vectors` },
    ...health.checks.filter((check) => check.name !== "Embeddings"),
  ];
  $("health-list").innerHTML = checks
    .map(
      (check) => `<li>
        <span class="status-dot${check.ok ? "" : " bad"}" aria-label="${check.ok ? "Healthy" : "Needs attention"}"></span>
        <span class="status-name">${escapeHtml(check.name)}</span>
        <span class="status-detail">${escapeHtml(check.detail)}</span>
      </li>`
    )
    .join("");

  const recent = [...indexed]
    .sort((a, b) => String(b.indexed_at || b.created_at).localeCompare(String(a.indexed_at || a.created_at)))
    .slice(0, 5);
  $("recent-empty").hidden = recent.length > 0;
  $("recent-body").innerHTML = recent
    .map(
      (doc) => `<tr data-id="${escapeHtml(doc.id)}">
        <td><div class="doc-name"><button type="button" data-action="open">${escapeHtml(doc.filename)}</button></div></td>
        <td>${typePill(doc.filename)}</td>
        <td class="chunks">${escapeHtml(doc.chunk_count ?? "—")}</td>
      </tr>`
    )
    .join("");
  return overview.documents.processing > 0;
}

$("recent-body").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action='open']");
  if (button) openViewer(button.closest("tr").dataset.id);
});

// Documents

let searchTimer = null;
$("doc-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});
$("doc-status").addEventListener("change", refresh);

async function loadDocuments() {
  const params = new URLSearchParams();
  if ($("doc-search").value.trim()) params.set("q", $("doc-search").value.trim());
  if ($("doc-status").value) params.set("status", $("doc-status").value);
  const [data, kb] = await Promise.all([api(`/api/admin/documents?${params}`), api("/api/admin/knowledge-base")]);
  state.limits = kb.limits;
  setReindexBanner(kb.index.needs_reindex);
  const body = $("documents-body");
  const empty = $("documents-empty");
  const filtered = params.toString() !== "";

  if (!data.documents.length) {
    body.innerHTML = "";
    empty.hidden = false;
    empty.innerHTML = filtered
      ? "<strong>No matching documents</strong><span>Try a different search or status filter.</span>"
      : "<strong>No documents yet</strong><span>Upload files above to build the knowledge base.</span>";
  } else {
    empty.hidden = true;
    body.innerHTML = data.documents.map(documentRow).join("");
  }
  return data.documents.some((doc) => doc.status === "queued" || doc.status === "processing");
}

function documentRow(doc) {
  const busy = doc.status === "queued" || doc.status === "processing";
  const error =
    doc.status === "failed" && doc.error
      ? `<span class="doc-error">${escapeHtml(doc.error)}${
          doc.chunk_count ? ` · previous version (${doc.chunk_count} chunks) is still searchable` : ""
        }</span>`
      : "";
  const sub = doc.has_original ? escapeHtml(doc.content_type || "") : "Imported from earlier index";
  return `<tr data-id="${escapeHtml(doc.id)}">
    <td><div class="doc-name"><button type="button" data-action="open" title="Open file">${escapeHtml(doc.filename)}</button>
      <span class="doc-sub">${sub}</span>${error}</div></td>
    <td>${typePill(doc.filename)}</td>
    <td>${statusPill(doc.status)}</td>
    <td class="num">${doc.chunk_count || "—"}</td>
    <td class="num">${formatBytes(doc.size_bytes)}</td>
    <td class="when" title="${escapeHtml(doc.uploaded_by || "")}">${escapeHtml(formatDate(doc.created_at))}</td>
    <td><div class="row-actions">
      <button class="icon-btn" type="button" data-action="view" aria-label="View details" title="View details">${ICONS.view}</button>
      ${
        doc.has_original
          ? `<a class="icon-btn" href="${fileUrl(doc.id, true)}" download aria-label="Download" title="Download">${ICONS.download}</a>`
          : ""
      }
      <button class="icon-btn" type="button" data-action="reindex" aria-label="Reindex" title="Reindex" ${busy ? "disabled" : ""}>${ICONS.retry}</button>
      <button class="icon-btn danger" type="button" data-action="delete" aria-label="Delete" title="Delete" ${
        doc.status === "processing" ? "disabled" : ""
      }>${ICONS.trash}</button>
    </div></td>
  </tr>`;
}

$("documents-body").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const row = button.closest("tr");
  const id = row.dataset.id;
  const name = row.querySelector(".doc-name button").textContent;
  if (button.dataset.action === "open") return openViewer(id);
  if (button.dataset.action === "view") return openDocument(id);
  if (button.dataset.action === "reindex") {
    try {
      await api(`/api/admin/documents/${id}/reindex`, { method: "POST" });
      toast(`"${name}" queued for reindexing.`);
      refresh();
    } catch (error) {
      toast(error.message, "error");
    }
  }
  if (button.dataset.action === "delete") {
    const ok = await confirmDialog({
      title: "Delete document?",
      message: `"${name}" and all of its indexed chunks will be removed. Customers will no longer get answers from it. You can undo this for a short time afterwards.`,
      confirmLabel: "Delete document",
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api(`/api/admin/documents/${id}`, { method: "DELETE" });
      toast(`Deleted "${name}" (${result.removed_chunks} chunks removed).`, "info", {
        action: { label: "Undo", onClick: () => restoreDocument(id, name) },
        duration: Math.min(result.undo_seconds || 15, 15) * 1000,
      });
      refresh();
    } catch (error) {
      toast(error.message, "error");
    }
  }
});

async function restoreDocument(id, name) {
  try {
    await api(`/api/admin/documents/${id}/restore`, { method: "POST" });
    toast(`Restored "${name}".`);
    refresh();
  } catch (error) {
    toast(error.message, "error");
  }
}

const documentDialog = $("document-dialog");
closeOnBackdrop(documentDialog);
documentDialog.querySelector("[data-close]").addEventListener("click", () => documentDialog.close());

async function openDocument(id) {
  try {
    const doc = await api(`/api/admin/documents/${id}`);
    $("document-title").textContent = doc.filename;
    const fields = [
      ["Status", statusPill(doc.status)],
      ["Chunks", escapeHtml(doc.chunk_count)],
      ["Size", escapeHtml(formatBytes(doc.size_bytes))],
      ["Type", escapeHtml(doc.content_type || "—")],
      ["Uploaded", escapeHtml(formatDate(doc.created_at, { relative: false }))],
      ["Uploaded by", escapeHtml(doc.uploaded_by || "—")],
      ["Last indexed", escapeHtml(formatDate(doc.indexed_at, { relative: false }))],
      ["Embedding", escapeHtml(doc.embedding_backend || "—")],
      ["SHA-256", doc.sha256 ? `<span class="mono" title="${escapeHtml(doc.sha256)}">${escapeHtml(doc.sha256.slice(0, 16))}…</span>` : "—"],
    ];
    const error = doc.error ? `<p class="form-error">${escapeHtml(doc.error)}</p>` : "";
    const chunks = doc.chunks.length
      ? `<ul class="chunk-list">${doc.chunks
          .map(
            (chunk) =>
              `<li><span class="chunk-location">${escapeHtml(chunk.location || "Chunk")}</span>${escapeHtml(chunk.text)}</li>`
          )
          .join("")}</ul>${doc.chunk_count > doc.chunks.length ? `<p class="hint">Showing ${doc.chunks.length} of ${doc.chunk_count} chunks.</p>` : ""}`
      : '<p class="hint">No indexed chunks.</p>';
    const events = doc.events.length
      ? `<ul class="event-list">${doc.events
          .map(
            (item) =>
              `<li><span class="when">${escapeHtml(formatDate(item.created_at, { relative: false }))}</span><span>${escapeHtml(item.message)}</span></li>`
          )
          .join("")}</ul>`
      : '<p class="hint">No events.</p>';
    $("document-body").innerHTML = `
      ${error}
      <dl class="detail-grid">${fields.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("")}</dl>
      <div class="detail-section">Processing log</div>${events}
      <div class="detail-section">Indexed content preview</div>${chunks}`;
    documentDialog.showModal();
  } catch (error) {
    toast(error.message, "error");
  }
}

// File viewer

const viewer = $("viewer-dialog");
const viewerState = { doc: null, mode: "", preview: null, sheet: 0 };
const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "tif", "tiff"];
const FRAME_EXTENSIONS = ["pdf", "txt", "md", "json"];
const OFFICE_EXTENSIONS = ["docx", "xlsx", "xlsm"];

function fileUrl(id, download = false) {
  return `/api/admin/documents/${encodeURIComponent(id)}/file${download ? "?download=1" : ""}`;
}

function extensionOf(filename) {
  return filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
}

closeOnBackdrop(viewer);
viewer.querySelector("[data-close]").addEventListener("click", () => viewer.close());
viewer.addEventListener("close", () => {
  $("viewer-body").replaceChildren();
  viewerState.doc = null;
});
$("viewer-details").addEventListener("click", () => {
  const id = viewerState.doc?.id;
  viewer.close();
  if (id) openDocument(id);
});
$("viewer-tabs").addEventListener("click", (event) => {
  const tab = event.target.closest("[data-sheet]");
  if (!tab) return;
  viewerState.sheet = Number(tab.dataset.sheet);
  renderOfficePreview();
});

async function openViewer(id) {
  let doc;
  try {
    doc = await api(`/api/admin/documents/${encodeURIComponent(id)}`);
  } catch (error) {
    toast(error.message, "error");
    return;
  }
  const extension = extensionOf(doc.filename);
  Object.assign(viewerState, { doc, preview: null, sheet: 0 });
  viewerState.mode = !doc.has_original
    ? "chunks"
    : FRAME_EXTENSIONS.includes(extension)
      ? "frame"
      : IMAGE_EXTENSIONS.includes(extension)
        ? "image"
        : OFFICE_EXTENSIONS.includes(extension)
          ? "office"
          : "none";

  $("viewer-type").innerHTML = typePill(doc.filename);
  $("viewer-title").textContent = doc.filename;
  $("viewer-meta").textContent = [
    formatBytes(doc.size_bytes),
    doc.chunk_count ? `${doc.chunk_count} chunks` : "",
    formatDate(doc.created_at),
  ]
    .filter(Boolean)
    .join(" · ");
  $("viewer-download").hidden = !doc.has_original;
  $("viewer-download").href = fileUrl(doc.id, true);
  $("viewer-print").disabled = viewerState.mode === "none";
  $("viewer-tabs").hidden = true;

  const body = $("viewer-body");
  body.className = `viewer-body mode-${viewerState.mode}`;
  if (viewerState.mode === "frame") {
    body.innerHTML = `<iframe id="viewer-frame" title="${escapeHtml(doc.filename)}" src="${fileUrl(doc.id)}"></iframe>`;
  } else if (viewerState.mode === "image") {
    body.innerHTML = `<img src="${fileUrl(doc.id)}" alt="${escapeHtml(doc.filename)}" />`;
  } else if (viewerState.mode === "office") {
    body.innerHTML = '<div class="viewer-loading"><span class="spinner"></span>Loading preview…</div>';
  } else if (viewerState.mode === "chunks") {
    const text = doc.chunks.map((chunk) => `<p>${escapeHtml(chunk.text)}</p>`).join("");
    body.innerHTML = `<div class="viewer-page"><p class="viewer-notice">The original file isn't stored for this document (it was imported from an earlier index), so this shows its indexed text.</p>${
      text || '<p class="hint">No indexed content.</p>'
    }</div>`;
  } else {
    body.innerHTML = noPreview("This file type can't be shown in the browser.");
  }
  if (!viewer.open) viewer.showModal();

  if (viewerState.mode === "office") {
    try {
      viewerState.preview = await api(`/api/admin/documents/${encodeURIComponent(doc.id)}/preview`);
      if (viewerState.doc?.id === doc.id) renderOfficePreview();
    } catch (error) {
      viewerState.mode = "none";
      $("viewer-print").disabled = true;
      body.innerHTML = noPreview(error.message);
    }
  }
}

function noPreview(message) {
  return `<div class="empty-state viewer-empty"><strong>Preview not available</strong><span>${escapeHtml(message)} Use Download to open it.</span></div>`;
}

function tableHtml(rows, { header = false } = {}) {
  if (!rows.length) return '<p class="hint">Empty.</p>';
  const width = Math.max(...rows.map((row) => row.length));
  const cells = (row, tag) =>
    Array.from({ length: width }, (_, i) => `<${tag}>${escapeHtml(row[i] ?? "")}</${tag}>`).join("");
  const [first, ...rest] = rows;
  const head = header ? `<thead><tr>${cells(first, "th")}</tr></thead>` : "";
  return `<table class="preview-table">${head}<tbody>${(header ? rest : rows)
    .map((row) => `<tr>${cells(row, "td")}</tr>`)
    .join("")}</tbody></table>`;
}

function officeHtml() {
  const preview = viewerState.preview;
  if (preview.kind === "spreadsheet") {
    const sheet = preview.sheets[viewerState.sheet];
    const note = preview.truncated
      ? '<p class="hint">Large sheet: showing the first 500 rows and 50 columns. Download for the full file.</p>'
      : "";
    return `<div class="sheet-scroll">${sheet ? tableHtml(sheet.rows, { header: true }) : ""}</div>${note}`;
  }
  const blocks = preview.blocks
    .map((block) => {
      if (block.type === "table") return tableHtml(block.rows);
      if (block.type === "heading") return `<h${block.level + 1}>${escapeHtml(block.text)}</h${block.level + 1}>`;
      return block.text ? `<p>${escapeHtml(block.text)}</p>` : "";
    })
    .join("");
  return `<div class="viewer-page">${blocks || '<p class="hint">This document has no text.</p>'}</div>`;
}

function renderOfficePreview() {
  const preview = viewerState.preview;
  if (preview.kind === "spreadsheet" && preview.sheets.length > 1) {
    $("viewer-tabs").hidden = false;
    $("viewer-tabs").innerHTML = preview.sheets
      .map(
        (sheet, i) =>
          `<button type="button" class="viewer-tab${i === viewerState.sheet ? " active" : ""}" data-sheet="${i}">${escapeHtml(sheet.name)}</button>`
      )
      .join("");
  }
  $("viewer-body").innerHTML = officeHtml();
}

// Prints only the document: framed files (PDF, text) print their own frame; everything
// else is copied into a hidden same-origin frame that uses the print stylesheet.
$("viewer-print").addEventListener("click", () => {
  const { mode, doc } = viewerState;
  if (!doc) return;
  if (mode === "frame") {
    try {
      $("viewer-frame").contentWindow.focus();
      $("viewer-frame").contentWindow.print();
    } catch {
      window.open(fileUrl(doc.id), "_blank", "noopener");
    }
    return;
  }
  let content;
  if (mode === "image") {
    content = `<img src="${fileUrl(doc.id)}" alt="" />`;
  } else if (mode === "office" && viewerState.preview?.kind === "spreadsheet") {
    // Print every sheet, each starting on a new page.
    content = viewerState.preview.sheets
      .map((sheet) => `<section class="sheet"><h2>${escapeHtml(sheet.name)}</h2>${tableHtml(sheet.rows, { header: true })}</section>`)
      .join("");
  } else {
    content = $("viewer-body").innerHTML;
  }
  printHtml(doc.filename, content);
});

function printHtml(title, content) {
  document.getElementById("print-frame")?.remove();
  const frame = document.createElement("iframe");
  frame.id = "print-frame";
  frame.className = "print-frame";
  frame.setAttribute("aria-hidden", "true");
  frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>
    <link rel="stylesheet" href="/static/css/print.css"></head><body><h1 class="print-title">${escapeHtml(title)}</h1>${content}</body></html>`;
  frame.addEventListener("load", async () => {
    const images = [...frame.contentDocument.images];
    await Promise.all(
      images.map((img) => (img.complete ? null : new Promise((done) => (img.onload = img.onerror = done))))
    );
    frame.contentWindow.focus();
    frame.contentWindow.print();
  });
  document.body.appendChild(frame);
}

// Uploads

const dropzone = $("dropzone");
const fileInput = $("file-input");
const ALLOWED = [".pdf", ".docx", ".xlsx", ".xlsm", ".txt", ".md", ".json", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => {
  queueFiles([...fileInput.files]);
  fileInput.value = "";
});
["dragenter", "dragover"].forEach((type) =>
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  })
);
["dragleave", "drop"].forEach((type) =>
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  })
);
dropzone.addEventListener("drop", (event) => queueFiles([...event.dataTransfer.files]));

// Files wait here until "Save & Index" is clicked; rejected ones carry an error and are never sent.
const queue = [];

function queueFiles(files) {
  const maxBytes = state.limits.max_upload_mb * 1024 * 1024;
  for (const file of files) {
    if (queue.some((item) => item.file.name === file.name && item.file.size === file.size)) continue;
    const extension = file.name.includes(".") ? `.${file.name.split(".").pop().toLowerCase()}` : "";
    let error = "";
    if (!ALLOWED.includes(extension)) error = "Unsupported file type.";
    else if (file.size > maxBytes) error = `Larger than ${state.limits.max_upload_mb} MB.`;
    else if (file.size === 0) error = "The file is empty.";
    queue.push({ file, error });
  }
  renderQueue();
}

function renderQueue() {
  const valid = queue.filter((item) => !item.error);
  $("queue").hidden = queue.length === 0;
  $("queue-count").textContent = `${valid.length} file${valid.length === 1 ? "" : "s"} ready to index`;
  $("queue-size").textContent = formatBytes(valid.reduce((total, item) => total + item.file.size, 0));
  $("queue-list").innerHTML = queue
    .map(
      (item, index) => `<li class="${item.error ? "invalid" : ""}">
        ${typePill(item.file.name)}
        <span class="queue-name">${escapeHtml(item.file.name)}</span>
        <span class="${item.error ? "queue-error" : "hint"}">${escapeHtml(item.error || formatBytes(item.file.size))}</span>
        <button class="icon-btn" type="button" data-index="${index}" aria-label="Remove ${escapeHtml(item.file.name)}" title="Remove">
          <svg viewBox="0 0 24 24" class="icon"><path d="M6 6l12 12M18 6 6 18"/></svg>
        </button>
      </li>`
    )
    .join("");
  $("save-index").disabled = valid.length === 0;
  $("clear-queue").disabled = queue.length === 0;
}

$("queue-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-index]");
  if (!button) return;
  queue.splice(Number(button.dataset.index), 1);
  renderQueue();
});

$("clear-queue").addEventListener("click", () => {
  queue.length = 0;
  renderQueue();
});

$("save-index").addEventListener("click", () => {
  const files = queue.filter((item) => !item.error).map((item) => item.file);
  if (files.length > state.limits.max_files_per_upload) {
    toast(`Upload at most ${state.limits.max_files_per_upload} files at a time.`, "error");
    return;
  }
  queue.length = 0;
  renderQueue();
  uploadFiles(files);
});

function renderUploadResults(results) {
  $("upload-results").innerHTML = results
    .map(
      (result) => `<li>
        ${result.ok ? '<span class="pill pill-success">Uploaded</span>' : '<span class="pill pill-danger">Rejected</span>'}
        <span class="name">${escapeHtml(result.filename)}</span>
        <span class="${result.ok ? "detail" : "error"}">${escapeHtml(result.ok ? "Indexing in the background; track its status in the Knowledge Base." : result.error)}</span>
      </li>`
    )
    .join("");
}

function uploadFiles(accepted) {
  if (!accepted.length) return;
  $("upload-panel").hidden = false;
  $("view-kb").hidden = true;
  renderUploadResults([]);
  $("save-index").classList.add("busy");

  const form = new FormData();
  accepted.forEach((file) => form.append("files", file, file.name));
  const request = new XMLHttpRequest();
  request.open("POST", "/api/admin/documents");
  request.setRequestHeader("X-CSRF-Token", session.csrf);
  $("upload-label").textContent = `Uploading ${accepted.length} file${accepted.length === 1 ? "" : "s"}…`;
  $("upload-bar").style.width = "0";
  request.upload.addEventListener("progress", (event) => {
    if (event.lengthComputable) $("upload-bar").style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
  });
  request.addEventListener("load", () => {
    $("upload-bar").style.width = "100%";
    let data = null;
    try {
      data = JSON.parse(request.responseText);
    } catch {
      data = null;
    }
    if (data && data.results) {
      const ok = data.results.filter((result) => result.ok).length;
      $("upload-label").textContent = ok
        ? `Uploaded ${ok} of ${accepted.length}. Indexing runs in the background.`
        : "None of the files could be uploaded.";
      renderUploadResults(data.results);
      $("view-kb").hidden = ok === 0;
    } else {
      $("upload-label").textContent = (data && data.error) || `Upload failed (${request.status}).`;
    }
    $("save-index").classList.remove("busy");
  });
  request.addEventListener("error", () => {
    $("upload-label").textContent = "Upload failed. Check your connection and try again.";
    $("save-index").classList.remove("busy");
  });
  request.send(form);
}

async function loadUpload() {
  const kb = await api("/api/admin/knowledge-base");
  state.limits = kb.limits;
  setReindexBanner(kb.index.needs_reindex);
  $("dropzone-hint").textContent =
    `Supports PDF, Excel, Word, and image files · up to ${kb.limits.max_upload_mb} MB each, ${kb.limits.max_files_per_upload} files at a time`;
  return false;
}

// Settings

async function loadSettings() {
  const [kb, overview] = await Promise.all([api("/api/admin/knowledge-base"), api("/api/admin/overview")]);
  state.limits = kb.limits;
  const index = kb.index;
  setReindexBanner(index.needs_reindex);
  const describeEmbedding = (backend, model) =>
    backend === "api" ? `API · ${model || "unknown model"}` : backend === "local-hash" ? "Local hashing (offline)" : "—";
  const rows = [
    ["Indexed chunks", index.chunks.toLocaleString()],
    ["Documents", `${overview.documents.indexed} indexed of ${overview.documents.total}`],
    ["Index embedding", index.embedding_backend ? describeEmbedding(index.embedding_backend, index.embedding_model) : "Empty index"],
    ["Configured embedding", describeEmbedding(index.configured_backend, index.configured_model)],
    ["Vector dimension", index.dimension ?? "—"],
    ["Index status", index.needs_reindex ? "Reindex required" : "Up to date"],
    ["Chunk size", `${index.chunk_size} words (${index.chunk_overlap} overlap)`],
    ["Retrieved per question", kb.retrieval.top_k],
    ["Minimum similarity", kb.retrieval.min_vector_score],
    ["Language model", kb.llm ? `${kb.llm.provider} · ${kb.llm.model}` : "Not configured (retrieval only)"],
    ["Upload limit", `${kb.limits.max_upload_mb} MB per file, ${kb.limits.max_files_per_upload} files per upload`],
  ];
  $("kb-config").innerHTML = rows
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
  return false;
}

// Re-index

async function loadReindex() {
  const level = $("event-level").value;
  const [overview, data] = await Promise.all([
    api("/api/admin/overview"),
    api(`/api/admin/events?limit=200${level ? `&level=${level}` : ""}`),
  ]);
  setReindexBanner(overview.index.needs_reindex);
  $("reindex-all").disabled = overview.documents.processing > 0 || overview.documents.total === 0;
  renderEvents(data.events);
  return overview.documents.processing > 0;
}

$("reindex-all").addEventListener("click", async () => {
  const ok = await confirmDialog({
    title: "Reindex all documents?",
    message:
      "Every document will be re-embedded with the current configuration. The existing index keeps serving answers until the new one is ready. With an embedding API this may incur usage costs.",
    confirmLabel: "Reindex all",
  });
  if (!ok) return;
  try {
    const result = await api("/api/admin/reindex", { method: "POST" });
    toast(`Reindexing ${result.queued} documents in the background.`);
    refresh();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("event-level").addEventListener("change", refresh);

function renderEvents(events) {
  $("events-empty").hidden = events.length > 0;
  $("events-body").innerHTML = events
    .map(
      (item) => `<tr>
        <td class="when">${escapeHtml(formatDate(item.created_at, { relative: false }))}</td>
        <td>${
          item.level === "error"
            ? '<span class="pill pill-danger">Error</span>'
            : item.level === "warning"
              ? '<span class="pill pill-warning">Warning</span>'
              : '<span class="pill pill-info">Info</span>'
        }</td>
        <td>${escapeHtml(item.document_name)}</td>
        <td>${escapeHtml(item.message)}</td>
      </tr>`
    )
    .join("");
}

// Startup

async function init() {
  await loadSession();
  updateThemeLabel();
  showView(location.hash.slice(1) || "overview");
}

init().catch((error) => toast(error.message || "Failed to load the dashboard.", "error"));
