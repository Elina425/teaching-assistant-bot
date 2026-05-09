# Design Report — Agentic Telegram Teaching Assistant

**Course:** Natural Language Processing — American University of Armenia (AUA)  
**Author:** Elina Melkonyan  
**Date:** May 2026  

---

## 1. System Overview

The Agentic Telegram Teaching Assistant is a complete LLM application that converts lecture slides into a structured teaching package. A user uploads a PDF via Telegram, answers four questions (duration, audience, language, email), and the system autonomously runs a six-step pipeline: it parses the slides, calls a local language model six times for increasingly refined outputs, searches the web for supporting resources, and delivers the final package both as file attachments and by email — but only after the user reviews and explicitly confirms the preview.

The design priority throughout was reliability and clarity over sophistication. A simple finite-state machine handles the conversation; errors at any step produce a user-readable message rather than a crash; no credentials appear in code.

---

## 2. Architecture

```
User (Telegram)
      │  /plan → file → 4 params
      ▼
  bot.py  —  ConversationHandler state machine
  (python-telegram-bot v22, async)
      │
      ▼  asyncio.create_task (non-blocking)
  agents/orchestrator.py  —  6-step pipeline
      │
      ├── tools/slides.py          PyMuPDF — PDF text extraction
      ├── tools/web_search.py      DuckDuckGo (ddgs) — no API key
      ├── tools/email_sender.py    smtplib STARTTLS
      ├── tools/report_generator.py  Markdown + PDF (fpdf2)
      └── tools/benchmark.py       latency measurement
      │
      ▼
  llm_backend.py  —  AsyncOpenAI → llama.cpp / vLLM
  (OpenAI-compatible API at http://localhost:8000/v1)
      │
      ▼
  Local LLM server  (llama.cpp on macOS, vLLM on Linux/GPU)
```

### State machine

Each user has an isolated session in `context.user_data` (PTB built-in). States:

| State | Trigger |
|-------|---------|
| IDLE | Bot starts, /cancel |
| WAITING_FILE | /plan command |
| WAITING_PARAMS | File accepted |
| PROCESSING | All 4 params collected |
| PREVIEW | Pipeline complete — inline keyboard shown |
| DONE | User confirms and email is sent |

The pipeline runs as a background `asyncio.create_task` so the bot remains responsive to other users during generation.

### Trace logging

Every pipeline run appends a JSON record to `traces.json` (step names, per-step elapsed time, total time, status, error if any). A separate Flask dashboard at `http://localhost:5001` reads this file and renders it as an auto-refreshing HTML table.

---

## 3. Local LLM Backend

### Model choice

**Mistral-7B-Instruct-v0.2** (Q4_K_M GGUF quantisation) was selected for the following reasons:

- **Instruction-following quality:** Mistral-7B-Instruct-v0.2 is one of the best open-weight models at its parameter count for following structured prompts (numbered lists, labelled fields, timed plans).
- **Context length:** 32 768 token training context, sufficient for a full lecture PDF plus a detailed plan in a single call.
- **Size:** The Q4_K_M quantisation produces a 4.1 GB file that fits entirely in the 18 GB unified memory of an Apple M3 Pro, with all 33 layers offloaded to the Metal GPU.
- **License:** Apache 2.0 — permissive for academic use.

### Backend: llama.cpp

On macOS, vLLM is not supported (requires Linux + CUDA). `llama-server` from the `llama.cpp` project exposes an OpenAI-compatible REST API (`/v1/chat/completions`) that `llm_backend.py` targets via `openai.AsyncOpenAI`.

Start command used:
```bash
llama-server \
  -m ~/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  --port 8000 \
  --ctx-size 4096
```

The `LLMBackend.generate(messages, temperature, max_tokens)` wrapper is the single point of contact with the server. Swapping to a different model or to vLLM requires only changing `.env` — no code changes.

### Temperature settings per step

| Step | Temperature | Reason |
|------|-------------|--------|
| Summary / title | 0.4 | Factual extraction — low variance desired |
| Concept map | 0.4 | Structured list — consistency matters |
| Teaching plan | 0.6 | Needs creativity for examples and exercises |
| Search queries | 0.3 | Near-deterministic — diverse queries are better |
| Revision | 0.5 | Balance between faithful grounding and improvement |
| Email body | 0.5 | Professional tone but not robotic |

---

## 4. Prompt Design

All prompts live in `agents/prompts.py` as functions returning OpenAI chat-format `list[dict]`. This keeps them independent of the orchestrator and easy to tune.

### Design principles applied

**Explicit output format.** Every prompt specifies the exact format expected (e.g. `Title: <text>\nSummary: <text>`). Without this, Mistral-7B often adds preamble ("Sure, here is a summary…") that breaks the `_extract_field` parser.

**Language injection.** Every prompt ends with `Respond in {language}`. This single line enables English, Armenian, Russian, and bilingual output without separate prompt variants.

**Source grounding instruction.** The revision prompt explicitly asks the model to label each claim as `[Slides]` or `[Web]`, which satisfies the grounding requirement and makes the output more trustworthy.

**Context limiting.** Slide text is truncated to 8 000 characters before being sent to avoid overflowing the 4 096-token context window set for the server. The full text is still available for the revision step (which receives a 2 000-character excerpt) via the session.

### Example: Teaching Plan prompt (abbreviated)

```
System: You are an expert educator and curriculum designer…
User:   Create a detailed timed teaching plan.
        Lecture summary: {summary}
        Concepts: {concept_map}
        Total duration: {duration}
        Target audience: {audience}

        The plan must include:
        - 3-5 specific, measurable learning objectives
        - Timed breakdown (e.g. 0-10 min: Introduction)
        - At least 2 worked examples with brief descriptions
        - At least 1 hands-on exercise with clear instructions
        - A 5-minute recap / Q&A section at the end

        Respond in {language}.
```

---

## 5. Tools

### Slide parser (`tools/slides.py`)
Uses **PyMuPDF** (`fitz`) to extract selectable text page by page. Each page is prefixed with `[Slide N]` so the LLM can reference specific slides. Image-only PDFs raise a `ValueError` with a user-friendly message; the bot forwards this to the user and stays in the `FILE_UPLOAD` state.

### Web search (`tools/web_search.py`)
Uses **DuckDuckGo** via the `ddgs` library — no API key or account required. The LLM first generates three search queries tuned to the lecture topic; the tool executes each and returns up to 6 deduplicated results. Failures return an error entry instead of raising, so the pipeline always completes even without internet access.

### Email sender (`tools/email_sender.py`)
Uses Python's `smtplib` with STARTTLS on port 587. Credentials come from environment variables only. A preview is always shown and the email is sent only on explicit inline-keyboard confirmation — the bot cannot send email autonomously.

### Report generator (`tools/report_generator.py`)
Generates a `.md` file (full Unicode, works for Armenian) and a `.pdf` file using **fpdf2**. The PDF uses **Arial Unicode.ttf** (present on macOS) for full Armenian and multilingual support. If no Unicode font is found, PDF generation is silently skipped and only Markdown is sent.

### Benchmark (`tools/benchmark.py`)
Sends a fixed test prompt to the configured backend(s) and measures wall-clock latency and characters/second. Supports comparing a primary and a secondary backend (configured via `LLM_BASE_URL_2` / `LLM_MODEL_2` in `.env`).

---

## 6. Limitations

| Limitation | Impact | Possible fix |
|------------|--------|--------------|
| PDF only — no PPTX | Users with PowerPoint slides must export to PDF first | Add `python-pptx` extraction |
| Scanned / image PDFs rejected | OCR not implemented | Add `pytesseract` fallback |
| Single active workflow per user | Starting /plan again resets current session | Persist sessions to SQLite |
| Context window (4 096 tokens) | Very long slide decks are truncated at 8 000 chars | Increase `--ctx-size` or use chunked RAG |
| LLM quality depends on quantisation | Q4_K_M may hallucinate exercises or timings | Use Q8 or full-precision model |
| Web search rate limits | DuckDuckGo may throttle repeated searches | Add exponential backoff or a paid API |
| One LLM server assumed | Bot crashes if server is down | Add health-check with user-facing error |
| No persistent storage | Sessions lost on bot restart | Add Redis or SQLite session store |
| Armenian in PDF requires Arial Unicode | Font not guaranteed on non-macOS systems | Bundle a free Unicode font (Noto Sans) |
