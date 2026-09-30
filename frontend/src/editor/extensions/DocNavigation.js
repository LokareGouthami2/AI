import { Extension } from '@tiptap/core';
import { Selection, TextSelection } from '@tiptap/pm/state';

/**
 * Ctrl/⌘+Home / Ctrl/⌘+End (and Shift variants) handled by the editor itself.
 * Chromium's native handling looks for the end of the *page*; in the
 * Edit + Preview layout that is the non-editable preview pane, so the caret
 * did not move at all (found by running the app).
 */
function jump(editor, toEnd, extend) {
  const { state, view } = editor;
  const target = toEnd ? Selection.atEnd(state.doc) : Selection.atStart(state.doc);
  const sel = extend ? TextSelection.create(state.doc, state.selection.anchor, target.head) : target;
  view.dispatch(state.tr.setSelection(sel).scrollIntoView());
  return true;
}

export const DocNavigation = Extension.create({
  name: 'docNavigation',
  priority: 1000,
  addKeyboardShortcuts() {
    return {
      'Mod-End': () => jump(this.editor, true, false),
      'Mod-Home': () => jump(this.editor, false, false),
      'Shift-Mod-End': () => jump(this.editor, true, true),
      'Shift-Mod-Home': () => jump(this.editor, false, true),
    };
  },
});
