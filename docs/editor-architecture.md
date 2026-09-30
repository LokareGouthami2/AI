# Editor architecture

The editable document is the heart of WriteAI: nothing is rendered until the
user has had full control over the text.

## Stack

* **TipTap 3 (ProseMirror)** — a schema-enforced document tree, transactional
  undo/redo, and robust clipboard and IME handling. `contenteditable` quirks
  are handled by ProseMirror instead of hand-written code.
* **Closed schema** (`frontend/src/editor/extensions/index.js`): StarterKit
  with code, code block, strike, horizontal rule, link and trailing-node
  **disabled**; headings limited to H1–H3; TextAlign on headings and
  paragraphs; TextStyle + FontSize. The editor can't create anything the
  handwriting renderer can't draw.

| Custom extension | Purpose |
|---|---|
| `BlockId` | Stable `data-block-id` on every block. Re-issues missing or duplicate ids after each change and on load. Handwriting variation is seeded per block, so editing one paragraph doesn't re-randomise the others. |
| `PasteSanitizer` | External HTML loses `<u>`, `<mark>`, `<font>`, colours and sizes (bold and italic are kept). Internal copies (`data-pm-slice`) keep the user's own formatting. |
| `MoveBlock` | Alt+↑ / Alt+↓ (and toolbar buttons) reorder top-level blocks. |
| `HistoryShortcuts` | Ctrl/⌘+Shift+Z and Ctrl/⌘+Y always *consume* the key. ProseMirror otherwise retries an unhandled Shift shortcut without Shift, so "redo with nothing to redo" became **undo**. Found by the Playwright suite. |
| `SmartBackspace` | Backspace in an empty paragraph after a list deletes it and moves the cursor to the list end, as in Docs and Word. ProseMirror's default moved it into the last list item as a hidden blank line. Found by the acceptance test. |

## WDM ⇄ TipTap (`frontend/src/editor/wdm/convert.js`)

Pure functions, mirroring the backend's Pydantic WDM (`backend/editor/wdm.py`):

| WDM | TipTap |
|---|---|
| `paragraph{align, content}` (empty content = blank line) | `paragraph{textAlign, blockId}` |
| `heading{level 1–3}` | `heading{level}` |
| `bullet_list / ordered_list{start}` → `items[].blocks` | `bulletList / orderedList{start}` → `listItem` |
| `blockquote{blocks}` | `blockquote` |
| `text{marks ⊆ bold/italic/underline, font_size}` | `text` + marks `bold/italic/underline/textStyle{fontSize}` |
| `hard_break` (Shift+Enter) | `hardBreak` |

Guarantees, all tested:

* `toWdm(fromWdm(doc)) == doc` for 300 random documents (fast-check).
* Loading any random WDM into a **real TipTap Editor** and reading it back is
  lossless, so the schema accepts exactly WDM.
* The converters never invent underline.

## Keyboard & editing (verified in real Chromium)

Enter (new paragraph), Enter twice (blank line), Shift+Enter (line break),
Backspace/Delete (merge), arrows, Home/End, Ctrl+A, copy/cut/paste,
Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z, toolbar undo/redo, bold/italic/underline,
H1–H3, paragraph, lists, quote, alignment, font size, move block, clear
formatting, and large pastes (40 paragraphs) — see
`frontend/e2e/editor-keyboard.spec.js`.

**Underline policy:** the toolbar button or Ctrl+U on a selection is the
*only* way to underline. Headings are styled by size and weight. AI output
can't carry marks, and pasted web content is stripped of underline.

## Autosave (`frontend/src/editor/autosave.js`)

A framework-free state machine, unit-tested with fake timers:

```text
edit ─► "Unsaved changes" ─► debounce 1.5 s (max wait 10 s) ─► PUT /content {content, base_revision}
     200 ─► "✓ Saved" (revision += 1)
     409 ─► "Edited elsewhere" → [Load their version] [Keep mine (overwrite)]
     network error ─► "Offline — retrying…" (1 s, 2 s, 4 s … max 30 s) + draft in localStorage
flush() ─► save now, resolve with the saved revision (used by Preview / Generate PDF / Save / Ctrl+S)
```

At most one request is in flight. Edits made during a save are saved
afterwards. The e2e test checks that typing a whole sentence produces at
most 2 requests.

## Versions

* `document_contents` is the head (revision + content + hash).
* `document_versions` holds immutable snapshots:
  - `ai_generated` — each generation
  - `manual_save` — the "Save version" button
  - `checkpoint` — at most every 5 minutes of editing
  - `pre_render` — every final PDF
  - `pre_restore` / `restored` — restores
* Restore never destroys anything: the current head is snapshotted first.
  "Compare" shows a block-level diff against the current text.
