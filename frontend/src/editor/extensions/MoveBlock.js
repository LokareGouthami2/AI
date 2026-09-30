import { Extension } from '@tiptap/core';
import { TextSelection } from '@tiptap/pm/state';

/**
 * Move the top-level block containing the cursor up or down (Alt+↑ / Alt+↓),
 * a reliable way to reorder paragraphs besides drag-and-drop or cut/paste.
 */
function moveBlock(direction) {
  return ({ state, dispatch }) => {
    const { $from } = state.selection;
    if ($from.depth < 1) return false;
    const index = $from.index(0);
    const doc = state.doc;
    const target = direction === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= doc.childCount) return false;
    if (!dispatch) return true;
    const node = doc.child(index);
    let start = 0;
    for (let i = 0; i < index; i++) start += doc.child(i).nodeSize;
    const end = start + node.nodeSize;
    const tr = state.tr.delete(start, end);
    let insertAt = 0;
    for (let i = 0; i < target; i++) insertAt += tr.doc.child(i).nodeSize;
    tr.insert(insertAt, node);
    const offset = $from.pos - start;
    tr.setSelection(TextSelection.near(tr.doc.resolve(Math.min(insertAt + offset, tr.doc.content.size))));
    dispatch(tr.scrollIntoView());
    return true;
  };
}

export const MoveBlock = Extension.create({
  name: 'moveBlock',
  addCommands() {
    return {
      moveBlockUp: () => moveBlock('up'),
      moveBlockDown: () => moveBlock('down'),
    };
  },
  addKeyboardShortcuts() {
    return {
      'Alt-ArrowUp': () => this.editor.commands.moveBlockUp(),
      'Alt-ArrowDown': () => this.editor.commands.moveBlockDown(),
    };
  },
});
