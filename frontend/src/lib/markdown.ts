/**
 * Lightweight Markdown-to-HTML parser for rental assistant messages.
 * Supports: bold, italic, headers, lists (ul/ol), links, tables, bare URLs.
 * No code blocks, images, or blockquotes — not needed in rental context.
 */

const BARE_URL = /(?<!\]\()(?<!")(https?:\/\/[^\s<)]+)/g;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Inline formatting: bold, italic, links, bare URLs */
function inlineFormat(raw: string): string {
  let s = escapeHtml(raw);
  // Links [text](url)
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="underline text-[#7dd3fc]">$1</a>');
  // Bold **text**
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic *text* (but not inside <strong>)
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  // Bare URLs (not already inside href="...")
  s = s.replace(BARE_URL, '<a href="$&" target="_blank" rel="noopener noreferrer" class="underline text-[#7dd3fc]">$&</a>');
  return s;
}

export function markdownToHtml(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Table: starts with |
    if (line.trimStart().startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      out.push(renderTable(tableLines));
      continue;
    }

    // Header: ## (map to h4 to keep size reasonable)
    const headerMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headerMatch) {
      const level = Math.min(headerMatch[1].length, 4);
      out.push(`<h${level + 2} class="markdown-heading">${inlineFormat(headerMatch[2])}</h${level + 2}>`);
      i++;
      continue;
    }

    // Unordered list
    if (line.match(/^\s*[-*]\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*[-*]\s+/)) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push("<ul class=\"markdown-list\">" + items.map(it => `<li>${inlineFormat(it)}</li>`).join("") + "</ul>");
      continue;
    }

    // Ordered list
    if (line.match(/^\s*\d+\.\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*\d+\.\s+/)) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      out.push("<ol class=\"markdown-list\">" + items.map(it => `<li>${inlineFormat(it)}</li>`).join("") + "</ol>");
      continue;
    }

    // Blank line → paragraph break
    if (line.trim() === "") {
      out.push("");
      i++;
      continue;
    }

    // Normal paragraph
    out.push(`<p>${inlineFormat(line)}</p>`);
    i++;
  }

  return out.join("\n");
}

function renderTable(lines: string[]): string {
  const rows = lines
    .filter(l => !l.match(/^\s*\|[\s:-]+\|\s*$/))  // skip separator rows
    .map(l =>
      l.split("|")
        .slice(1, -1)  // remove leading/trailing empty from |col|col|
        .map(c => c.trim())
    );

  if (rows.length === 0) return "";

  const [header, ...body] = rows;
  let html = '<table class="markdown-table"><thead><tr>';
  for (const cell of header) {
    html += `<th>${inlineFormat(cell)}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const row of body) {
    html += "<tr>";
    for (const cell of row) {
      html += `<td>${inlineFormat(cell)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}
