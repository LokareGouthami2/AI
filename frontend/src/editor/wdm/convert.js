/**
 * Pure converters between the WriteAI Document Model (WDM — the canonical
 * format stored by the backend and rendered to handwriting) and TipTap /
 * ProseMirror JSON (what the editor holds in memory).
 *
 * The editor schema is restricted to exactly the node/mark set WDM supports,
 * so toWdm(fromWdm(x)) === x for every valid document (property-tested).
 */

export const FONT_SIZES = { small: '0.85em', large: '1.2em', xlarge: '1.4em' };
const CSS_TO_SIZE = Object.fromEntries(Object.entries(FONT_SIZES).map(([k, v]) => [v, k]));
const MARK_ORDER = ['bold', 'italic', 'underline'];
const ALIGNS = new Set(['left', 'center', 'right', 'justify']);

export function newBlockId() {
  const bytes = new Uint8Array(5);
  (globalThis.crypto || window.crypto).getRandomValues(bytes);
  return 'b' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

// ---------------------------------------------------------------- WDM → TipTap

function inlineToTiptap(nodes = []) {
  const out = [];
  for (const n of nodes) {
    if (n.type === 'hard_break') {
      out.push({ type: 'hardBreak' });
      continue;
    }
    if (!n.text) continue;
    const marks = [];
    for (const m of MARK_ORDER) if ((n.marks || []).includes(m)) marks.push({ type: m });
    if (n.font_size && FONT_SIZES[n.font_size]) {
      marks.push({ type: 'textStyle', attrs: { fontSize: FONT_SIZES[n.font_size] } });
    }
    const t = { type: 'text', text: n.text };
    if (marks.length) t.marks = marks;
    out.push(t);
  }
  return out;
}

function blockToTiptap(b) {
  switch (b.type) {
    case 'heading':
    case 'paragraph': {
      const node = {
        type: b.type,
        attrs: { blockId: b.id || null, textAlign: b.align && b.align !== 'left' ? b.align : null },
      };
      if (b.type === 'heading') node.attrs.level = b.level;
      const content = inlineToTiptap(b.content);
      if (content.length) node.content = content;
      return node;
    }
    case 'bullet_list':
    case 'ordered_list': {
      const node = {
        type: b.type === 'bullet_list' ? 'bulletList' : 'orderedList',
        attrs: { blockId: b.id || null },
        content: (b.items || []).map((item) => ({
          type: 'listItem',
          attrs: { blockId: item.id || null },
          content: (item.blocks || []).map(blockToTiptap),
        })),
      };
      if (b.type === 'ordered_list') node.attrs.start = b.start ?? 1;
      return node;
    }
    case 'blockquote':
      return { type: 'blockquote', attrs: { blockId: b.id || null }, content: (b.blocks || []).map(blockToTiptap) };
    default:
      return { type: 'paragraph', attrs: { blockId: b.id || null, textAlign: null } };
  }
}

export function fromWdm(doc) {
  const content = (doc?.blocks || []).map(blockToTiptap);
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph', attrs: { blockId: null, textAlign: null } }] };
}

// ---------------------------------------------------------------- TipTap → WDM

function inlineToWdm(nodes = []) {
  const out = [];
  for (const n of nodes) {
    if (n.type === 'hardBreak') {
      out.push({ type: 'hard_break' });
      continue;
    }
    if (n.type !== 'text' || !n.text) continue;
    const names = new Set((n.marks || []).map((m) => m.type));
    const marks = MARK_ORDER.filter((m) => names.has(m));
    const ts = (n.marks || []).find((m) => m.type === 'textStyle');
    const size = ts && CSS_TO_SIZE[ts.attrs?.fontSize];
    // Newlines never live inside a text node (the backend rejects them).
    const parts = n.text.replace(/\r/g, '').split('\n');
    parts.forEach((part, i) => {
      if (i > 0) out.push({ type: 'hard_break' });
      if (!part) return;
      const t = { type: 'text', text: part, marks };
      if (size) t.font_size = size;
      const prev = out[out.length - 1];
      // Merge adjacent runs with identical formatting (canonical form).
      if (prev && prev.type === 'text' && sameFormat(prev, t)) prev.text += t.text;
      else out.push(t);
    });
  }
  return out;
}

function sameFormat(a, b) {
  return a.marks.join(',') === b.marks.join(',') && (a.font_size || null) === (b.font_size || null);
}

function align(attrs) {
  const a = attrs?.textAlign;
  return ALIGNS.has(a) ? a : 'left';
}

function blockToWdm(n) {
  const id = n.attrs?.blockId || newBlockId();
  switch (n.type) {
    case 'heading':
      return { id, type: 'heading', level: Math.min(3, Math.max(1, n.attrs?.level || 1)), align: align(n.attrs), content: inlineToWdm(n.content) };
    case 'paragraph':
      return { id, type: 'paragraph', align: align(n.attrs), content: inlineToWdm(n.content) };
    case 'bulletList':
    case 'orderedList': {
      const items = (n.content || [])
        .filter((li) => li.type === 'listItem')
        .map((li) => {
          const blocks = (li.content || []).map(blockToWdm);
          return { id: li.attrs?.blockId || newBlockId(), blocks: blocks.length ? blocks : [{ id: newBlockId(), type: 'paragraph', align: 'left', content: [] }] };
        });
      if (!items.length) return { id, type: 'paragraph', align: 'left', content: [] };
      const out = { id, type: n.type === 'bulletList' ? 'bullet_list' : 'ordered_list', items };
      if (n.type === 'orderedList') out.start = Number.isInteger(n.attrs?.start) ? n.attrs.start : 1;
      return out;
    }
    case 'blockquote': {
      const blocks = (n.content || []).map(blockToWdm);
      return { id, type: 'blockquote', blocks: blocks.length ? blocks : [{ id: newBlockId(), type: 'paragraph', align: 'left', content: [] }] };
    }
    default:
      // Defensive: anything unexpected becomes a plain paragraph of its text.
      return { id, type: 'paragraph', align: 'left', content: inlineToWdm(collectText(n)) };
  }
}

function collectText(n) {
  if (n.type === 'text') return [n];
  return (n.content || []).flatMap(collectText);
}

export function toWdm(tiptapJson, title = 'Untitled') {
  const blocks = (tiptapJson?.content || []).map(blockToWdm);
  return { schema_version: 1, title: (title || 'Untitled').slice(0, 300), blocks };
}

/** Plain-text tokens in reading order (mirrors backend wdm.document_tokens). */
export function wdmTokens(doc) {
  const tokens = [];
  const walk = (blocks) => {
    for (const b of blocks || []) {
      if (b.type === 'heading' || b.type === 'paragraph') {
        const text = (b.content || []).map((n) => (n.type === 'hard_break' ? '\n' : n.text)).join('');
        tokens.push(...text.split(/\s+/).filter(Boolean));
      } else if (b.items) b.items.forEach((it) => walk(it.blocks));
      else if (b.blocks) walk(b.blocks);
    }
  };
  walk(doc?.blocks);
  return tokens;
}
