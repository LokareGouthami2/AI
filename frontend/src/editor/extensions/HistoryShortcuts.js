import { Extension } from '@tiptap/core';

/**
 * Redo shortcuts that always consume the key press.
 *
 * ProseMirror retries an unhandled Shift+letter shortcut *without* Shift. When
 * there is nothing to redo, Ctrl+Shift+Z (reported with key "z" by some
 * layouts and by automation tools) would therefore fall through to Ctrl+Z and
 * UNDO. Found by the Playwright suite; a redo key must never undo.
 */
export const HistoryShortcuts = Extension.create({
  name: 'historyShortcuts',
  priority: 1000,
  addKeyboardShortcuts() {
    const redo = () => {
      this.editor.commands.redo();
      return true;
    };
    return { 'Shift-Mod-z': redo, 'Shift-Mod-Z': redo, 'Mod-y': redo };
  },
});
