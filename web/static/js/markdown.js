// Minimal, safe Markdown renderer for model output.
// Everything is HTML-escaped first; only whitelisted constructs are turned back into markup.

import { escapeHtml } from "./common.js";

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

// Some models cite as 【4†L21-L22】 or 【4】 instead of [4]; rewrite those to the standard form.
export function normalizeCitations(text) {
  return String(text ?? "").replace(/【\s*(\d{1,2})(?:†[^】]*)?\s*】/g, "[$1]");
}

function inline(text) {
  const codeSpans = [];
  let html = escapeHtml(text).replace(/`([^`\n]+)`/g, (_, code) => {
    codeSpans.push(`<code>${code}</code>`);
    return `\u0000${codeSpans.length - 1}\u0000`;
  });

  html = html
    .replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
      const decoded = url.replace(/&amp;/g, "&");
      if (!SAFE_URL.test(decoded)) return label;
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    })
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>")
    // Citation markers like [1] or [1, 2] become buttons that open the source.
    .replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g, (_, numbers) =>
      numbers
        .split(",")
        .map((n) => `<button type="button" class="cite" data-source="${n.trim()}">${n.trim()}</button>`)
        .join("")
    );

  return html.replace(/\u0000(\d+)\u0000/g, (_, index) => codeSpans[Number(index)]);
}

function splitRow(line) {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderTable(lines) {
  const header = splitRow(lines[0]);
  const aligns = splitRow(lines[1]).map((cell) =>
    cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : ""
  );
  const cell = (tag, value, index) =>
    `<${tag}${aligns[index] ? ` class="align-${aligns[index]}"` : ""}>${inline(value)}</${tag}>`;
  const head = `<tr>${header.map((value, index) => cell("th", value, index)).join("")}</tr>`;
  const body = lines
    .slice(2)
    .map((line) => `<tr>${splitRow(line).map((value, index) => cell("td", value, index)).join("")}</tr>`)
    .join("");
  return `<div class="table-wrap"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

function renderList(lines) {
  // Builds nested lists from indentation.
  const root = { children: [], ordered: false };
  const stack = [{ indent: -1, node: root }];
  for (const line of lines) {
    const match = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (!match) {
      const last = stack[stack.length - 1].node.children.at(-1);
      if (last) last.text += ` ${line.trim()}`;
      continue;
    }
    const indent = match[1].replace(/\t/g, "  ").length;
    const ordered = /\d/.test(match[2]);
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const parent = stack[stack.length - 1].node;
    const item = { text: match[3], children: [], ordered: false };
    if (parent.children.length === 0) parent.ordered = ordered;
    parent.children.push(item);
    stack.push({ indent, node: item });
  }
  const render = (node) => {
    if (!node.children.length) return "";
    const tag = node.ordered ? "ol" : "ul";
    return `<${tag}>${node.children.map((item) => `<li>${inline(item.text)}${render(item)}</li>`).join("")}</${tag}>`;
  };
  return render(root);
}

export function renderMarkdown(source) {
  const lines = normalizeCitations(source).replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let index = 0;

  const isTableStart = (i) =>
    lines[i]?.includes("|") && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1] || "");
  const isListItem = (line) => /^\s*([-*+]|\d+[.)])\s+/.test(line);
  const isBlockStart = (i) =>
    /^(```|#{1,6}\s|>\s?|\s*([-*_])\s*\2\s*\2[\s\-*_]*$)/.test(lines[i]) || isListItem(lines[i]) || isTableStart(i);

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```\s*([\w+-]*)/);
    if (fence) {
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) code.push(lines[index++]);
      index += 1;
      const language = fence[1] ? `<span class="code-lang">${escapeHtml(fence[1])}</span>` : "<span></span>";
      out.push(
        `<div class="code-block"><div class="code-head">${language}<button type="button" class="code-copy">Copy</button></div>` +
          `<pre><code>${escapeHtml(code.join("\n"))}</code></pre></div>`
      );
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6); // h1 inside a message would be too loud
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      out.push("<hr>");
      index += 1;
      continue;
    }

    if (isTableStart(index)) {
      const table = [lines[index], lines[index + 1]];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) table.push(lines[index++]);
      out.push(renderTable(table));
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${renderMarkdown(quote.join("\n"))}</blockquote>`);
      continue;
    }

    if (isListItem(line)) {
      const items = [];
      const ordered = /^\s*\d/.test(line);
      const topLevelOfOtherKind = (candidate) => /^\S/.test(candidate) && /^\d/.test(candidate) !== ordered;
      while (
        index < lines.length &&
        (isListItem(lines[index]) || (/^\s{2,}\S/.test(lines[index]) && items.length)) &&
        !(items.length && topLevelOfOtherKind(lines[index]))
      ) {
        items.push(lines[index++]);
      }
      out.push(renderList(items));
      continue;
    }

    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !(paragraph.length && isBlockStart(index))) {
      paragraph.push(lines[index++]);
    }
    out.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
  }

  return out.join("");
}
