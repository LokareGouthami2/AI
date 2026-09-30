import { useEditorState } from '@tiptap/react';
import { FONT_SIZES } from './wdm/convert.js';

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

function Btn({ label, title, active, disabled, onClick, children, testId }) {
  return (
    <button
      type="button"
      className="tb-btn"
      aria-label={label}
      title={title || label}
      aria-pressed={active === undefined ? undefined : !!active}
      disabled={disabled}
      data-testid={testId}
      // keep the editor selection when clicking toolbar buttons
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export default function Toolbar({ editor }) {
  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => {
      if (!e) return null;
      const fontSize = e.getAttributes('textStyle').fontSize || '';
      return {
        canUndo: e.can().undo(),
        canRedo: e.can().redo(),
        bold: e.isActive('bold'),
        italic: e.isActive('italic'),
        underline: e.isActive('underline'),
        h1: e.isActive('heading', { level: 1 }),
        h2: e.isActive('heading', { level: 2 }),
        h3: e.isActive('heading', { level: 3 }),
        paragraph: e.isActive('paragraph') && !e.isActive('bulletList') && !e.isActive('orderedList'),
        bullet: e.isActive('bulletList'),
        ordered: e.isActive('orderedList'),
        quote: e.isActive('blockquote'),
        left: e.isActive({ textAlign: 'left' }) || (!e.isActive({ textAlign: 'center' }) && !e.isActive({ textAlign: 'right' }) && !e.isActive({ textAlign: 'justify' })),
        center: e.isActive({ textAlign: 'center' }),
        right: e.isActive({ textAlign: 'right' }),
        justify: e.isActive({ textAlign: 'justify' }),
        fontSize,
      };
    },
  });
  if (!editor || !s) return null;
  const chain = () => editor.chain().focus();

  return (
    <div className="toolbar" role="toolbar" aria-label="Formatting">
      <Btn label="Undo" title={`Undo (${MOD}+Z)`} disabled={!s.canUndo} onClick={() => chain().undo().run()} testId="tb-undo">↶</Btn>
      <Btn label="Redo" title={`Redo (${MOD}+Y)`} disabled={!s.canRedo} onClick={() => chain().redo().run()} testId="tb-redo">↷</Btn>
      <span className="sep" />
      <Btn label="Bold" title={`Bold (${MOD}+B)`} active={s.bold} onClick={() => chain().toggleBold().run()} testId="tb-bold"><b>B</b></Btn>
      <Btn label="Italic" title={`Italic (${MOD}+I)`} active={s.italic} onClick={() => chain().toggleItalic().run()} testId="tb-italic"><i>I</i></Btn>
      <Btn label="Underline" title={`Underline (${MOD}+U) — only applied when you choose it`} active={s.underline} onClick={() => chain().toggleUnderline().run()} testId="tb-underline"><u>U</u></Btn>
      <select
        className="tb-select"
        aria-label="Font size"
        value={Object.entries(FONT_SIZES).find(([, v]) => v === s.fontSize)?.[0] || 'normal'}
        onChange={(e) => {
          const v = e.target.value;
          if (v === 'normal') chain().unsetFontSize().run();
          else chain().setFontSize(FONT_SIZES[v]).run();
        }}
      >
        <option value="small">Small</option>
        <option value="normal">Normal</option>
        <option value="large">Large</option>
        <option value="xlarge">Extra large</option>
      </select>
      <span className="sep" />
      <Btn label="Heading 1" active={s.h1} onClick={() => chain().toggleHeading({ level: 1 }).run()} testId="tb-h1">H1</Btn>
      <Btn label="Heading 2" active={s.h2} onClick={() => chain().toggleHeading({ level: 2 }).run()} testId="tb-h2">H2</Btn>
      <Btn label="Heading 3" active={s.h3} onClick={() => chain().toggleHeading({ level: 3 }).run()} testId="tb-h3">H3</Btn>
      <Btn label="Normal text" active={s.paragraph && !s.h1 && !s.h2 && !s.h3} onClick={() => chain().setParagraph().run()} testId="tb-paragraph">¶</Btn>
      <span className="sep" />
      <Btn label="Bullet list" active={s.bullet} onClick={() => chain().toggleBulletList().run()} testId="tb-bullet">•</Btn>
      <Btn label="Numbered list" active={s.ordered} onClick={() => chain().toggleOrderedList().run()} testId="tb-ordered">1.</Btn>
      <Btn label="Block quote" active={s.quote} onClick={() => chain().toggleBlockquote().run()} testId="tb-quote">❝</Btn>
      <span className="sep" />
      <Btn label="Align left" active={s.left} onClick={() => chain().setTextAlign('left').run()} testId="tb-left">⯇</Btn>
      <Btn label="Align center" active={s.center} onClick={() => chain().setTextAlign('center').run()} testId="tb-center">≡</Btn>
      <Btn label="Align right" active={s.right} onClick={() => chain().setTextAlign('right').run()} testId="tb-right">⯈</Btn>
      <Btn label="Justify" active={s.justify} onClick={() => chain().setTextAlign('justify').run()} testId="tb-justify">☰</Btn>
      <span className="sep" />
      <Btn label="Move block up" title="Move block up (Alt+↑)" onClick={() => chain().moveBlockUp().run()} testId="tb-up">↑</Btn>
      <Btn label="Move block down" title="Move block down (Alt+↓)" onClick={() => chain().moveBlockDown().run()} testId="tb-down">↓</Btn>
      <Btn
        label="Clear formatting"
        title="Clear formatting"
        onClick={() => chain().unsetAllMarks().clearNodes().unsetTextAlign().run()}
        testId="tb-clear"
      >
        ⌫
      </Btn>
    </div>
  );
}
