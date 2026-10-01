# Security

## Uploads

| Control | Where |
|---|---|
| Extension allow-list (`.pdf .docx .txt`) **and** magic-byte sniffing (`%PDF-`; ZIP containing `[Content_Types].xml` and `word/document.xml`; no NUL bytes and a detectable encoding for TXT) | `documents/validation.py` |
| Size limit (20 MB default). The API reads at most limit + 1 bytes. nginx `client_max_body_size 25m`. | `api/routes.py`, `docker/nginx.conf` |
| Page limit (300); encrypted PDFs rejected; corrupt files rejected | `validation.py` |
| DOCX zip-bomb guard: total uncompressed size (100 MB) and entry count (2,000) | `validation.py` |
| Stored under a random UUID name, mode `0600`, in a `0700` directory outside any static route; the original filename is sanitised and display-only | `documents/storage.py` |
| Path containment checks before every read or delete; render directories derived from a validated UUID | `storage.py` |
| Temporary work in private temp dirs that are always removed | `storage.secure_tempdir` |
| Delete removes rows (cascade), the uploaded file, renders and vectors | `services/documents.delete_document` |

## Secrets

* `ANTHROPIC_API_KEY` is read only by the backend (`pydantic` `SecretStr`),
  never logged, and never returned by any endpoint. The frontend bundle
  contains no secrets; the browser talks only to our API.
* `.env` is git-ignored; `.env.example` lists every variable with no values.
* `/api/health` reports provider *names* only (tested: no key material).

## API hardening

* Pydantic validation on every request body. WDM documents are closed schemas
  (`extra="forbid"`) with limits: 5,000 blocks, nesting depth 4, 20,000
  characters per text node, 5 MB per document.
* Render settings are range-checked (font size, margins, spacing …). Header
  text fields are limited to 80 characters and normalised to one printable
  line.
* One error envelope; unhandled errors return a generic 500 with no stack
  trace.
* Security headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, and a restrictive CSP (API and nginx).
* CORS limited to the configured frontend origins.
* Per-client sliding-window rate limits on upload, generate, render and ask.
* Optional shared API token (`WRITEAI_API_TOKEN`, checked with a
  constant-time comparison) for public demos.
* Optimistic concurrency (`base_revision`) prevents silent overwrites between
  tabs.

## Prompt injection

Uploaded documents are untrusted input. Defences in depth:

1. Document text is wrapped in `<document>…</document>`, and the system prompt
   states it is untrusted **data** whose instructions must never be followed.
2. The LLM has **no tools** and no side effects. It can only return JSON.
3. Output must match a strict schema of plain strings and is semantically
   validated. Invalid output is repaired once, then replaced by the offline
   engine.
4. Page numbers and citations are resolved **server-side** from retrieved
   chunk ids; invented ids and pages are dropped.
5. AI output reaches the editor only through `from_llm.py`, which strips
   markdown and HTML and emits no marks.
6. Suspicious spans ("ignore previous instructions", "system prompt" …) are
   flagged in the Analysis tab.

## Output safety (XSS)

* AI and pasted content become ProseMirror text nodes, never `innerHTML`.
* The paste sanitiser removes scripts, styles and meta tags, and the closed
  schema drops unknown nodes.
* Preview images are served from our own origin as `image/png`.

## Container

* Runs as a non-root user (uid 10001). Data is on a volume. There's a
  healthcheck.
* Dependencies are pinned by version floor. Run `pip-audit` and `npm audit`
  in CI (recommended).

## Ethics

An optional "Generated with WriteAI" footer (off by default) is available, and
the UI states the intended use (personal study notes). Submitting
computer-generated handwriting as one's own work may breach academic-integrity
rules.
