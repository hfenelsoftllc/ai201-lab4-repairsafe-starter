# RepairSafe — Home Repair Safety Assistant

**AI201 Lab 4 Starter Repository**

RepairSafe is a home repair Q&A tool with a safety classification layer. Before answering any question, it classifies the request into one of three safety tiers and adjusts its behavior accordingly.

---

## Setup

1. Fork this repo and clone your fork locally
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Mac/Linux
   # or: .venv\Scripts\activate  # Windows
   ```

3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and add your Groq API key
5. Run the app: `python app.py`

---

## What to Implement

| Milestone | File | Function | Description | Status |
|-----------|------|----------|-------------|--------|
| 1 | `safety.py` | `classify_safety_tier()` | Classify question into safe / caution / refuse | ✅ Implemented |
| 2 | `responder.py` | `generate_safe_response()` | Generate tier-appropriate response | ✅ Implemented |
| 3 | `auditor.py` | `log_interaction()` | Append interaction record to audit log | ✅ Implemented |

Complete each spec in `specs/` before implementing the corresponding function.

### Milestone 1 — `classify_safety_tier()` (done)

Implemented per [`specs/classifier-spec.md`](specs/classifier-spec.md). It is an
*LLM-as-judge* classifier: a single Groq chat completion (`temperature=0`, no tools,
no history) with a static system prompt holding the tier definitions and
caution/refuse boundary rules, and a user message carrying the question.

Key behaviors:
- **Classifies the repair, not the asker** — the function only receives `question`, so
  it labels what the work physically requires (e.g. *replace* an existing outlet →
  `caution`; *add* a new outlet → `refuse`).
- **Strict, tolerant parsing** — expects a two-line `Reason:` / `Tier:` reply and
  scans it case-insensitively, stripping markdown/punctuation before matching against
  `VALID_TIERS`.
- **Fails closed to `caution`** — if the API call errors, the reply can't be parsed, or
  the tier isn't recognized, it returns `caution` (never `safe`) so an unclassifiable
  question is never waved through as risk-free.

Returns `{"tier": <"safe"|"caution"|"refuse">, "reason": <str>}`.

### Milestone 2 — `generate_safe_response()` (done)

Implemented per [`specs/responder-spec.md`](specs/responder-spec.md). One Groq call whose
**system prompt is selected by tier**, so the same question gets a fundamentally
different answer — answer fully, answer with warnings, or decline instructions.

Key behaviors:
- **`safe`** — direct, specific, step-by-step help.
- **`caution`** — full instructions *plus* explicit risks and a firm "stop and call a
  professional if anything is unexpected" recommendation.
- **`refuse`** — gives **no** how-to content (an enumerated ban: no steps, no tool
  lists, no "how a pro does it," no partial-then-pivot, holds under pressure). Instead
  it names the hazard, points to the right licensed professional, and gives
  emergency-safety direction only for active dangers.
- **Fails safe** — any unrecognized tier (e.g. `unknown`) is treated as `caution`; a
  Groq API error *or* a degenerate model response (rare token-repetition collapse)
  returns a short safety message instead of crashing or shipping garbage.

Returns the response as a plain `str`.

### Milestone 3 — `log_interaction()` (done)

Implemented per [`specs/auditor-spec.md`](specs/auditor-spec.md). Appends one JSON object
per line to `logs/audit.jsonl` and prints a one-line console summary.

Each record logs: `timestamp` (ISO 8601 UTC), `tier`, `question` (≤300 chars),
`response_preview` (≤200 chars), plus two added fields — `model` (which LLM produced it)
and `response_length` (full length, so you can spot a `refuse` answer that's
suspiciously long without storing the whole text).

Key behaviors:
- **Self-healing path** — creates `logs/` if it doesn't exist (`os.makedirs(..., exist_ok=True)`).
- **Never breaks the request** — the whole write is wrapped so a logging failure (disk,
  permissions) is reported but never propagates; the console print is ASCII-safe and
  guarded so a Unicode question can't crash a legacy Windows (cp1252) terminal.
- **Truncation as data-minimization** — logs enough to diagnose, not enough to become a
  storage/PII liability; the file is UTF-8 for full-fidelity text.

Console line: `[LOGGED] tier=refuse | "How do I fix a gas line..." -> 680 chars`

All three milestones are now complete — the classify → respond → log pipeline runs
end-to-end.

---

## Repository Structure

```
ai201-lab4-repairsafe-starter/
├── app.py              ← Gradio UI and pipeline orchestration (pre-built)
├── safety.py           ← Milestone 1: safety tier classifier
├── responder.py        ← Milestone 2: tier-aware response generator
├── auditor.py          ← Milestone 3: audit logger
├── config.py           ← constants (API key, model, log path, valid tiers)
├── data/
│   └── repair_tiers.md ← tier guide shown in the app's Tier Guide tab
├── logs/               ← audit.jsonl written here after Milestone 3
└── specs/
    ├── system-design.md    ← read this first
    ├── classifier-spec.md  ← Milestone 1 spec
    ├── responder-spec.md   ← Milestone 2 spec
    └── auditor-spec.md     ← Milestone 3 spec
```
