import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

/**
 * External clipboard HTML (web pages, Word, Google Docs) often carries
 * underline, highlight, colours and arbitrary font sizes. WriteAI never adds
 * underline or highlighting automatically, so pasted content is stripped of
 * them. Content copied from *inside* the editor (ProseMirror marks the HTML
 * with data-pm-slice) keeps the formatting the user applied.
 */
export function sanitizePastedHtml(html) {
  if (!html || html.includes('data-pm-slice')) return html;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('u, ins, mark, font, style, script, meta, link').forEach((el) => {
    if (['STYLE', 'SCRIPT', 'META', 'LINK'].includes(el.tagName)) el.remove();
    else el.replaceWith(...el.childNodes);
  });
  doc.querySelectorAll('[style]').forEach((el) => {
    // Keep only bold/italic intent expressed through inline styles.
    const s = el.style;
    const bold = /^(bold|[6-9]00)$/.test(s.fontWeight);
    const italic = s.fontStyle === 'italic';
    el.removeAttribute('style');
    if (bold || italic) {
      let inner = el.innerHTML;
      if (italic) inner = `<em>${inner}</em>`;
      if (bold) inner = `<strong>${inner}</strong>`;
      el.innerHTML = inner;
    }
  });
  doc.querySelectorAll('[class]').forEach((el) => el.removeAttribute('class'));
  return doc.body.innerHTML;
}

export const PasteSanitizer = Extension.create({
  name: 'pasteSanitizer',
  addProseMirrorPlugins() {
    return [new Plugin({ key: new PluginKey('pasteSanitizer'), props: { transformPastedHTML: sanitizePastedHtml } })];
  },
});
