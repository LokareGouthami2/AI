/**
 * Headless TipTap editor tests (jsdom). Real keyboard/clipboard behaviour is
 * covered in Playwright (e2e/); these verify the schema, commands and
 * converters against the actual ProseMirror model.
 */
import { afterEach, describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { Editor } from '@tiptap/core';
import { editorExtensions } from '../editor/extensions/index.js';
import { fromWdm, toWdm } from '../editor/wdm/convert.js';
import { sanitizePastedHtml } from '../editor/extensions/PasteSanitizer.js';
import { wdmDoc } from './convert.test.js';

let editor;
const make = (doc) => {
  editor = new Editor({ extensions: editorExtensions(), content: fromWdm(doc) });
  return editor;
};
afterEach(() => editor?.destroy());

const P = (id, t) => ({ id, type: 'paragraph', align: 'left', content: t ? [{ type: 'text', text: t, marks: [] }] : [] });
const base = () => ({ schema_version: 1, title: 'T', blocks: [P('b0000000001', 'Machine learning is a branch of AI.'), P('b0000000002', 'It allows computers to learn from data.')] });
const texts = () => toWdm(editor.getJSON()).blocks.map((b) => (b.content || []).map((n) => n.text || '\n').join(''));

describe('editor schema', () => {
  it('accepts every valid WDM document unchanged (schema == WDM)', () => {
    fc.assert(
      fc.property(wdmDoc, (doc) => {
        const e = new Editor({ extensions: editorExtensions(), content: fromWdm(doc) });
        const back = toWdm(e.getJSON(), doc.title);
        e.destroy();
        expect(back).toEqual(doc);
      }),
      { numRuns: 120 },
    );
  });
});

describe('editing commands', () => {
  it('Enter creates a genuine new paragraph with a fresh id', () => {
    make(base());
    editor.commands.setTextSelection(editor.state.doc.child(0).nodeSize - 1); // end of first paragraph
    editor.commands.enter();
    editor.commands.insertContent('New line');
    const w = toWdm(editor.getJSON());
    expect(w.blocks.map((b) => b.type)).toEqual(['paragraph', 'paragraph', 'paragraph']);
    expect(texts()[1]).toBe('New line');
    const ids = w.blocks.map((b) => b.id);
    expect(new Set(ids).size).toBe(3);
  });

  it('Enter twice leaves an empty paragraph', () => {
    make(base());
    editor.commands.setTextSelection(editor.state.doc.child(0).nodeSize - 1);
    editor.commands.enter();
    editor.commands.enter();
    editor.commands.insertContent('After blank line');
    expect(texts()).toEqual(['Machine learning is a branch of AI.', '', 'After blank line', 'It allows computers to learn from data.']);
  });

  it('Shift+Enter inserts a hard break, not a paragraph', () => {
    make(base());
    editor.commands.setTextSelection(8);
    editor.commands.setHardBreak();
    const w = toWdm(editor.getJSON());
    expect(w.blocks).toHaveLength(2);
    expect(w.blocks[0].content.some((n) => n.type === 'hard_break')).toBe(true);
  });

  it('undo and redo restore exact states', () => {
    make(base());
    const before = JSON.stringify(toWdm(editor.getJSON()));
    editor.commands.setTextSelection(1);
    editor.commands.insertContent('XYZ ');
    const after = JSON.stringify(toWdm(editor.getJSON()));
    expect(after).not.toBe(before);
    editor.commands.undo();
    expect(JSON.stringify(toWdm(editor.getJSON()))).toBe(before);
    editor.commands.redo();
    expect(JSON.stringify(toWdm(editor.getJSON()))).toBe(after);
  });

  it('headings, lists and alignment map to WDM', () => {
    make(base());
    editor.commands.setTextSelection(2);
    editor.commands.toggleHeading({ level: 2 });
    editor.commands.setTextSelection(editor.state.doc.child(0).nodeSize + 2);
    editor.commands.toggleOrderedList();
    editor.commands.setTextSelection(2);
    editor.commands.setTextAlign('center');
    const w = toWdm(editor.getJSON());
    expect(w.blocks[0]).toMatchObject({ type: 'heading', level: 2, align: 'center' });
    expect(w.blocks[1].type).toBe('ordered_list');
  });

  it('underline is only applied to the explicit selection', () => {
    make(base());
    expect(JSON.stringify(toWdm(editor.getJSON()))).not.toContain('underline');
    editor.commands.setTextSelection({ from: 1, to: 8 }); // "Machine"
    editor.commands.toggleUnderline();
    const w = toWdm(editor.getJSON());
    const underlined = w.blocks.flatMap((b) => b.content).filter((n) => n.marks?.includes('underline'));
    expect(underlined.map((n) => n.text)).toEqual(['Machine']);
    // typing after the underlined word continues without underline once toggled off
    editor.commands.setTextSelection(editor.state.doc.child(0).nodeSize - 1);
    editor.commands.insertContent(' more');
    const later = toWdm(editor.getJSON()).blocks[0].content.at(-1);
    expect(later.marks).not.toContain('underline');
  });

  it('font size marks map to the WDM enum', () => {
    make(base());
    editor.commands.setTextSelection({ from: 1, to: 8 });
    editor.commands.setFontSize('1.2em');
    expect(toWdm(editor.getJSON()).blocks[0].content[0]).toMatchObject({ text: 'Machine', font_size: 'large' });
  });

  it('moves blocks up and down', () => {
    make(base());
    editor.commands.setTextSelection(editor.state.doc.child(0).nodeSize + 2);
    editor.commands.moveBlockUp();
    expect(texts()).toEqual(['It allows computers to learn from data.', 'Machine learning is a branch of AI.']);
    editor.commands.moveBlockDown();
    expect(texts()).toEqual(['Machine learning is a branch of AI.', 'It allows computers to learn from data.']);
  });

  it('Backspace in an empty paragraph after a list deletes it (no hidden empty list line)', () => {
    editor = new Editor({ extensions: editorExtensions(), content: '<ul><li><p>item one</p></li></ul><p>Example para</p><p>next</p>' });
    let pos = 0;
    editor.state.doc.descendants((n, p) => {
      if (n.isText && n.text === 'Example para') pos = p;
    });
    editor.commands.setTextSelection({ from: pos, to: pos + 12 });
    // Real keydown events (editor.commands.keyboardShortcut replays only doc
    // steps and drops the selection the handler sets).
    const press = () => editor.view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', keyCode: 8, bubbles: true, cancelable: true }));
    press();
    press();
    const w = toWdm(editor.getJSON());
    expect(w.blocks.map((b) => b.type)).toEqual(['bullet_list', 'paragraph']);
    expect(w.blocks[0].items[0].blocks).toHaveLength(1);
    editor.commands.insertContent('!');
    expect(toWdm(editor.getJSON()).blocks[0].items[0].blocks[0].content[0].text).toBe('item one!');
  });

  it('deleting a whole paragraph removes it', () => {
    make(base());
    const size = editor.state.doc.child(0).nodeSize;
    editor.commands.deleteRange({ from: 0, to: size });
    expect(texts()).toEqual(['It allows computers to learn from data.']);
  });

  it('replacing the entire document works', () => {
    make(base());
    editor.commands.selectAll();
    editor.commands.insertContent('<h1>Brand new</h1><p>Everything replaced.</p>');
    const w = toWdm(editor.getJSON());
    expect(w.blocks.map((b) => b.type)).toEqual(['heading', 'paragraph']);
  });

  it('duplicate ids (e.g. from paste) are re-issued', async () => {
    make({ schema_version: 1, title: 'T', blocks: [P('bsame000000', 'a'), P('bsame000000', 'b')] });
    await new Promise((r) => setTimeout(r, 0)); // TipTap emits "create" on the next tick
    const ids = toWdm(editor.getJSON()).blocks.map((b) => b.id);
    expect(new Set(ids).size).toBe(2);
  });

  it('clear formatting removes marks and alignment', () => {
    make(base());
    editor.commands.setTextSelection({ from: 1, to: 8 });
    editor.chain().toggleBold().toggleUnderline().setTextAlign('right').run();
    editor.commands.setTextSelection({ from: 1, to: 8 });
    editor.chain().unsetAllMarks().clearNodes().unsetTextAlign().run();
    const b = toWdm(editor.getJSON()).blocks[0];
    expect(b.align).toBe('left');
    expect(b.content.every((n) => n.marks.length === 0)).toBe(true);
  });
});

describe('paste sanitizer', () => {
  it('strips underline, highlight, colours and sizes from external HTML', () => {
    const html = '<p><u>under</u> <mark>hi</mark> <span style="text-decoration:underline;color:red;font-size:40px">styled</span> <span style="font-weight:700">bold</span></p>';
    const out = sanitizePastedHtml(html);
    expect(out).not.toMatch(/<u>|<mark>|text-decoration|color|font-size/);
    expect(out).toContain('<strong>bold</strong>');
    expect(out).toContain('under');
  });

  it('leaves internal editor clipboard untouched (keeps user formatting)', () => {
    const html = '<p data-pm-slice="1 1 []"><u>mine</u></p>';
    expect(sanitizePastedHtml(html)).toBe(html);
  });
});
