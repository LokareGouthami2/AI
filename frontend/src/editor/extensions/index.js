import StarterKit from '@tiptap/starter-kit';
import TextAlign from '@tiptap/extension-text-align';
import { TextStyle, FontSize } from '@tiptap/extension-text-style';
import { BlockId } from './BlockId.js';
import { PasteSanitizer } from './PasteSanitizer.js';
import { MoveBlock } from './MoveBlock.js';
import { HistoryShortcuts } from './HistoryShortcuts.js';
import { SmartBackspace } from './SmartBackspace.js';
import { DocNavigation } from './DocNavigation.js';

/**
 * The editor schema is deliberately closed: only nodes/marks the handwriting
 * renderer can draw exist, so the editor cannot create anything that would be
 * lost or mis-rendered. Underline is available but never applied by default.
 */
export function editorExtensions() {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      code: false,
      codeBlock: false,
      strike: false,
      horizontalRule: false,
      link: false,
      trailingNode: false,
      undoRedo: { depth: 500, newGroupDelay: 500 },
    }),
    TextAlign.configure({ types: ['heading', 'paragraph'], alignments: ['left', 'center', 'right', 'justify'] }),
    TextStyle,
    FontSize,
    BlockId,
    PasteSanitizer,
    MoveBlock,
    HistoryShortcuts,
    SmartBackspace,
    DocNavigation,
  ];
}
