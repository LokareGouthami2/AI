import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { newBlockId } from '../wdm/convert.js';

const TYPES = ['paragraph', 'heading', 'bulletList', 'orderedList', 'listItem', 'blockquote'];

/** Transaction assigning fresh ids to blocks whose id is missing or duplicated. */
function fixIds(state) {
  const seen = new Set();
  let tr = null;
  state.doc.descendants((node, pos) => {
    if (!TYPES.includes(node.type.name)) return;
    const id = node.attrs.blockId;
    if (!id || seen.has(id)) {
      tr = tr || state.tr;
      const fresh = newBlockId();
      tr.setNodeMarkup(pos, undefined, { ...node.attrs, blockId: fresh });
      seen.add(fresh);
    } else {
      seen.add(id);
    }
  });
  if (tr) tr.setMeta('addToHistory', false);
  return tr;
}

/**
 * Stable block ids (WDM `id`). Handwriting variation is seeded per block, so
 * ids must survive edits: splitting a paragraph (Enter) creates a node without
 * an id (keepOnSplit: false) and pasting can duplicate ids, so ids are
 * re-issued for missing and duplicate values after every change and on load.
 */
export const BlockId = Extension.create({
  name: 'blockId',

  addGlobalAttributes() {
    return [
      {
        types: TYPES,
        attributes: {
          blockId: {
            default: null,
            keepOnSplit: false,
            parseHTML: (el) => el.getAttribute('data-block-id'),
            renderHTML: (attrs) => (attrs.blockId ? { 'data-block-id': attrs.blockId } : {}),
          },
        },
      },
    ];
  },

  onCreate() {
    const tr = fixIds(this.editor.state);
    if (tr) this.editor.view.dispatch(tr);
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('blockId'),
        appendTransaction: (transactions, _old, state) => (transactions.some((t) => t.docChanged) ? fixIds(state) : null),
      }),
    ];
  },
});
