import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { fromWdm, toWdm, wdmTokens } from '../editor/wdm/convert.js';

// ---------------------------------------------------------------- arbitraries
let counter = 0;
const id = () => fc.constant(null).map(() => 'b' + (counter++).toString(16).padStart(10, '0'));
const word = fc.stringMatching(/^[A-Za-z0-9éüß,.;:!?'()-]{1,12}$/);
const text = fc.array(word, { minLength: 1, maxLength: 6 }).map((ws) => ws.join(' '));
const marks = fc.subarray(['bold', 'italic', 'underline']);
const size = fc.constantFrom(undefined, 'small', 'large', 'xlarge');

const inline = fc
  .array(fc.oneof({ weight: 5, arbitrary: fc.record({ text, marks, size }) }, { weight: 1, arbitrary: fc.constant('BR') }), { maxLength: 6 })
  .map((items) => {
    // Build canonical runs: merge adjacent equal-format runs, drop empty.
    const out = [];
    for (const it of items) {
      if (it === 'BR') {
        out.push({ type: 'hard_break' });
        continue;
      }
      const t = { type: 'text', text: it.text, marks: it.marks };
      if (it.size) t.font_size = it.size;
      const prev = out[out.length - 1];
      if (prev && prev.type === 'text' && prev.marks.join() === t.marks.join() && (prev.font_size || null) === (t.font_size || null)) prev.text += t.text;
      else out.push(t);
    }
    return out;
  });
const align = fc.constantFrom('left', 'center', 'right', 'justify');

const leaf = fc.oneof(
  fc.record({ id: id(), type: fc.constant('paragraph'), align, content: inline }),
  fc.record({ id: id(), type: fc.constant('heading'), level: fc.integer({ min: 1, max: 3 }), align, content: inline }),
);

const { block } = fc.letrec((tie) => ({
  block: fc.oneof(
    { depthSize: 'small', withCrossShrink: true },
    leaf,
    leaf,
    fc.record({ id: id(), type: fc.constant('bullet_list'), items: fc.array(fc.record({ id: id(), blocks: fc.array(tie('block'), { minLength: 1, maxLength: 2 }) }), { minLength: 1, maxLength: 3 }) }),
    fc.record({ id: id(), type: fc.constant('ordered_list'), start: fc.integer({ min: 1, max: 20 }), items: fc.array(fc.record({ id: id(), blocks: fc.array(tie('block'), { minLength: 1, maxLength: 2 }) }), { minLength: 1, maxLength: 3 }) }),
    fc.record({ id: id(), type: fc.constant('blockquote'), blocks: fc.array(tie('block'), { minLength: 1, maxLength: 2 }) }),
  ),
}));

export const wdmDoc = fc.record({
  schema_version: fc.constant(1),
  title: fc.constantFrom('Notes', 'Machine Learning', 'Untitled'),
  blocks: fc.array(block, { minLength: 1, maxLength: 8 }),
});

// -------------------------------------------------------------------- tests
describe('WDM ⇄ TipTap converters', () => {
  it('round-trips random documents exactly', () => {
    fc.assert(
      fc.property(wdmDoc, (doc) => {
        expect(toWdm(fromWdm(doc), doc.title)).toEqual(doc);
      }),
      { numRuns: 300 },
    );
  });

  it('keeps empty paragraphs (Enter pressed twice)', () => {
    const doc = { schema_version: 1, title: 'T', blocks: [
      { id: 'b1', type: 'paragraph', align: 'left', content: [{ type: 'text', text: 'A', marks: [] }] },
      { id: 'b2', type: 'paragraph', align: 'left', content: [] },
      { id: 'b3', type: 'paragraph', align: 'left', content: [{ type: 'text', text: 'B', marks: [] }] },
    ] };
    const tt = fromWdm(doc);
    expect(tt.content[1]).toEqual({ type: 'paragraph', attrs: { blockId: 'b2', textAlign: null } });
    expect(toWdm(tt, 'T')).toEqual(doc);
  });

  it('turns newlines inside text into hard breaks and orders marks canonically', () => {
    const tt = { type: 'doc', content: [{ type: 'paragraph', attrs: { blockId: 'x' }, content: [
      { type: 'text', text: 'one\ntwo', marks: [{ type: 'underline' }, { type: 'bold' }] },
    ] }] };
    const w = toWdm(tt);
    expect(w.blocks[0].content).toEqual([
      { type: 'text', text: 'one', marks: ['bold', 'underline'] },
      { type: 'hard_break' },
      { type: 'text', text: 'two', marks: ['bold', 'underline'] },
    ]);
  });

  it('never invents underline', () => {
    fc.assert(
      fc.property(wdmDoc, (doc) => {
        const strip = JSON.parse(JSON.stringify(doc).replaceAll('"underline"', '"bold"').replaceAll('"bold","bold"', '"bold"'));
        const back = toWdm(fromWdm(strip), strip.title);
        expect(JSON.stringify(back).includes('underline')).toBe(false);
      }),
      { numRuns: 100 },
    );
  });

  it('assigns ids to id-less blocks and maps unknown nodes to paragraphs', () => {
    const w = toWdm({ type: 'doc', content: [{ type: 'horizontalRule' }, { type: 'codeBlock', content: [{ type: 'text', text: 'x = 1' }] }] });
    expect(w.blocks.every((b) => b.type === 'paragraph' && /^b[0-9a-f]{10}$/.test(b.id))).toBe(true);
    expect(w.blocks[1].content[0].text).toBe('x = 1');
  });

  it('tokenises like the backend', () => {
    const doc = { blocks: [{ type: 'heading', content: [{ type: 'text', text: 'Hello world' }] }, { type: 'bullet_list', items: [{ blocks: [{ type: 'paragraph', content: [{ type: 'text', text: 'a' }, { type: 'hard_break' }, { type: 'text', text: 'b' }] }] }] }] };
    expect(wdmTokens(doc)).toEqual(['Hello', 'world', 'a', 'b']);
  });
});
