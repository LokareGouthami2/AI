import { Extension } from '@tiptap/core';
import { TextSelection } from '@tiptap/pm/state';

/**
 * Backspace in an EMPTY paragraph that directly follows a list removes the
 * paragraph and puts the cursor at the end of the list — as in Google Docs
 * and Word. ProseMirror's default instead moves the empty paragraph into the
 * last list item, leaving an invisible empty line inside the list (found by
 * the browser acceptance test).
 */
export const SmartBackspace = Extension.create({
  name: 'smartBackspace',
  priority: 1000,
  addKeyboardShortcuts() {
    return {
      Backspace: () => {
        const { state, view } = this.editor;
        const { selection } = state;
        const { $from } = selection;
        if (!selection.empty || $from.parent.type.name !== 'paragraph' || $from.parent.content.size !== 0) return false;
        const depth = $from.depth;
        const index = $from.index(depth - 1);
        if (index === 0) return false;
        const before = $from.node(depth - 1).child(index - 1);
        if (!['bulletList', 'orderedList'].includes(before.type.name)) return false;
        const start = $from.before(depth);
        const tr = state.tr.delete(start, start + $from.parent.nodeSize);
        // end of the list = just before the deleted paragraph's old position
        tr.setSelection(TextSelection.near(tr.doc.resolve(start - 1), -1));
        view.dispatch(tr.scrollIntoView());
        return true;
      },
    };
  },
});
