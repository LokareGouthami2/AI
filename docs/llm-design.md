# LLM design

## Where an LLM is used — and where it is not

| Task | Engine |
|---|---|
| Extraction, cleaning, classification, layout, validation | Deterministic code and classical ML (no LLM) |
| Preserve mode | Deterministic tree → WDM (no LLM) |
| Clean / Smart / Assignment / Exam / Simple notes, flashcards, quiz, RAG answers | LLM (Claude) with structured output, **or** the offline extractive engine |

## Providers (`backend/llm/provider.py`)

* **`AnthropicProvider`** uses the official `anthropic` SDK with
  `messages.parse(output_format=<Pydantic model>)`, so responses are
  constrained to the task's JSON schema. Settings:
  - default model `claude-opus-5-5` (`WRITEAI_ANTHROPIC_MODEL`)
  - effort via `output_config` (`WRITEAI_ANTHROPIC_EFFORT`, default `medium`)
  - server-side refusal fallbacks (`fallbacks="default"`, beta,
    `WRITEAI_ANTHROPIC_FALLBACKS`)
  - `stop_reason == "refusal"` is handled explicitly
  - SDK errors are mapped to user-safe messages (rate limit, auth,
    connection, status)
* **`ExtractiveProvider`** is an offline, deterministic engine
  (`backend/llm/extractive.py`). It produces the *same* output schemas from
  the section tree using sentence scoring (content-word frequency),
  pattern-based definition parsing, step splitting, definition-based and
  cloze quiz questions with distractors, and IDF-weighted extractive QA. It
  only reuses sentences from the document, so it cannot hallucinate. It's
  used when no API key is configured, in all tests, and as the fallback.

`WRITEAI_LLM_PROVIDER=auto` chooses Anthropic when `ANTHROPIC_API_KEY` is set.

## Output schemas (`backend/llm/schemas.py`)

`NotesOutput`, `AssignmentOutput`, `ExamOutput`, `FlashcardsOutput`,
`QuizOutput` and `RagAnswer` are strict Pydantic models (`extra="forbid"`)
containing **plain strings only**. There is no markdown, HTML or formatting
field, so the AI has no way to express underline or highlight.

## Validation → repair → fallback (`backend/llm/service.py`)

```text
LLM output ─► schema parse ─► semantic checks ─► ok
                   │ fail            │ fail
                   ▼                 ▼
            one repair call (errors + previous output sent back)
                   │ still failing / LLM error / refusal
                   ▼
            offline extractive engine (status = "fallback", shown in the UI)
```

Semantic checks include:

* quiz questions have exactly 4 distinct non-empty options and
  `correct_index` in 0–3;
* flashcards are non-empty and de-duplicated;
* notes sections are non-empty;
* page numbers outside `1..page_count` are removed (the LLM can't invent
  pages).

Every generation is logged in the `generations` table (provider, model,
prompt version, tokens, validated JSON, status).

## Converting to the editor (`backend/editor/from_llm.py`)

The only path from AI output into the editor. It strips any stray markdown
or HTML the model emitted anyway (`**`, `__`, `<u>`, `<mark>`, `#`) while
preserving legitimate text such as quiz blanks `_____`. It maps block types
to WDM nodes (definitions become "Term: definition", formulas are centred,
examples get an "Example:" prefix) and emits **no marks**. A parametrised
test asserts that all six modes produce WDM with zero marks.

## Long documents

The outline is split at top-level headings into parts of at most 60k
characters. Notes modes run per part (map), and their sections are
concatenated deterministically (reduce).

## Prompt-injection defence

See [security.md](security.md#prompt-injection). In short: document text is
wrapped in `<document>` tags and declared untrusted data, the model has no
tools, output is schema-constrained and validated, citations and pages are
resolved server-side, and suspicious spans are flagged in the UI.

## Not verified in this environment

No `ANTHROPIC_API_KEY` was available where this was built. The Claude
provider is implemented against the current SDK (structured outputs,
fallbacks, refusal handling) and its repair/fallback logic is unit-tested with
a scripted provider, but **no live Claude call was made**. All end-to-end
tests use the offline engine.
