// Render-safety normalization for LLM-generated markdown.
// Mirrors backend/app/services/export.py::normalize_markdown so the web view,
// PDF and DOCX all repair the same malformations:
//  1. inline "- a - b" bullet runs inside a paragraph -> real list blocks
//  2. tables glued to the preceding paragraph ("**Comparison:**\n| H |...")
//     -> blank line inserted so remark-gfm opens a real <table>

function isListItem(line) {
  const t = line.trim();
  return (/^[-*]\s+\S/.test(t) || /^\d+[.)]\s+\S/.test(t));
}

function isTableSep(line) {
  const s = (line || '').trim();
  return s.startsWith('|') && s.includes('-') && /^[|: \-]+$/.test(s);
}

export function normalizeBullets(mdText) {
  const out = [];
  let prevWasList = true; // start-of-doc needs no blank line
  for (const line of (mdText || '').split('\n')) {
    const st = line.trim();
    if (isListItem(line)) {
      // markdown needs a blank line before a list or '- ' merges into the paragraph above
      if (!prevWasList) out.push('');
      out.push(line);
      prevWasList = true;
      continue;
    }
    prevWasList = !st;
    if (!st || st.startsWith('>') || st.startsWith('#') || st.startsWith('|') || st.startsWith('```')) {
      out.push(line);
      continue;
    }
    if (!line.includes(' - ')) {
      out.push(line);
      continue;
    }
    const parts = line.split(/\s+-\s+(?=[A-Z0-9"'])/);
    if (parts.length < 2) {
      out.push(line);
      continue;
    }
    const firstEndsListIntro = /[:;]$/.test(parts[0].trim());
    if (!firstEndsListIntro && parts.length < 3) {
      out.push(line);
      continue;
    }
    out.push(parts[0].trimEnd());
    out.push(''); // blank line so the parser opens a real list
    for (const p of parts.slice(1)) out.push('- ' + p.trim());
  }
  return out.join('\n');
}

export function normalizeTables(mdText) {
  const lines = (mdText || '').split('\n');
  const out = [];
  let prevBlankOrTable = true;
  for (let i = 0; i < lines.length; i++) {
    const st = lines[i].trim();
    const isPipe = st.startsWith('|');
    if (isPipe && !prevBlankOrTable) {
      const nxt = (i + 1 < lines.length ? lines[i + 1].trim() : '');
      if (isTableSep(nxt)) out.push('');
    }
    out.push(lines[i]);
    prevBlankOrTable = !st || isPipe;
  }
  return out.join('\n');
}

export function normalizeMarkdown(mdText) {
  return normalizeTables(normalizeBullets(mdText || ''));
}
