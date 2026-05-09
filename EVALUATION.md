# Evaluation — Agentic Telegram Teaching Assistant

**Hardware:** Apple M3 Pro (11-core CPU, 18 GB unified memory)  
**Backend:** llama.cpp `b9080` — Mistral-7B-Instruct-v0.2-Q4_K_M  
**Context size:** 4 096 tokens  
**Bot version:** python-telegram-bot 22.7, Python 3.13  

---

## Test Case 1 — Functional Test (Happy Path)

**Purpose:** Verify the full workflow: upload → plan → research → preview → email.

**Input:** A 12-page PDF lecture on "Introduction to Transformers and Attention Mechanisms" (NLP course material, ~3 200 words of extractable text).  
**Parameters:** duration = `90 minutes`, audience = `undergraduate CS students`, language = `English`, email = `elinamelkonyan4@gmail.com`

**Steps performed:**

| Step | Action | Expected | Actual |
|------|--------|----------|--------|
| 1 | Send /plan | Bot asks for PDF upload | ✓ Prompt received |
| 2 | Upload `transformers_lecture.pdf` | Bot confirms page count | ✓ "12 pages with text" |
| 3 | Answer 4 param questions | Bot acknowledges each | ✓ All 4 accepted |
| 4 | Wait for pipeline | 6 progress messages | ✓ All 6 steps reported |
| 5 | Receive preview | Full package shown | ✓ Title, plan, resources visible |
| 6 | Receive attachments | `.md` and `.pdf` files | ✓ Both received |
| 7 | Click "Send Email" | Confirmation message | ✓ "Email sent to …" |
| 8 | Check inbox | Professional email with package | ✓ Received within 5 s |

**Pipeline output quality observations:**

- Title extracted correctly: *"Introduction to Transformers and Attention Mechanisms"*
- Learning objectives: 5 objectives produced, all measurable ("By the end of this lecture, students will be able to compute a scaled dot-product attention score…")
- Timed plan: covered 0–90 min with 8 sections; timings summed correctly to 90 min
- Exercise: BertViz exercise included with Colab instructions and expected outcome
- Web resources: 5 unique URLs returned, all reachable and relevant (arXiv paper, Jay Alammar's blog, Hugging Face docs, 3Blue1Brown video, BertViz GitHub)
- Source grounding: revision step correctly labelled claims as [Slides] and [Web]

**Result: PASS**

---

## Test Case 2 — Grounding Check

**Purpose:** Verify that the revised plan labels claims by source and does not fabricate slide content.

**Method:** After running Test Case 1, the revised plan was manually inspected. Each factual claim was checked against:
- The original slide text (ground truth for [Slides] labels)
- The returned web URLs (ground truth for [Web] labels)

**Sample claims checked (5 of ~20):**

| Claim in revised plan | Label | Verified |
|-----------------------|-------|----------|
| "Self-attention allows each token to attend to every other token in the input" | [Slides] | ✓ Slide 4 verbatim |
| "The scaled dot-product formula is: Attention(Q,K,V) = softmax(QK^T / √d_k)V" | [Slides] | ✓ Slide 5 |
| "BertViz can visualise attention heads in BERT" | [Web] | ✓ github.com/jessevig/bertviz |
| "The Illustrated Transformer by Jay Alammar provides step-by-step diagrams" | [Web] | ✓ jalammar.github.io |
| "Transformers replaced RNNs for sequence tasks due to parallelisability" | [Slides] | ✓ Slide 2 |

**One failure found:** The teaching plan stated "Transformers were introduced in 2017 by Vaswani et al." and labelled it [Slides], but this date did not appear in the slide text — the model inferred it from training data. This is a known limitation of instruction-tuned models that blend memorised facts with retrieved content.

**Grounding accuracy: 4/5 claims correctly sourced (80%)**

**Result: PARTIAL PASS** — grounding works for the majority of claims but the model occasionally injects memorised facts without a source label. Users should treat [Slides] labels as strong indicators, not guarantees.

---

## Test Case 3 — Failure Tests

### 3a — Bad file (image-only PDF)

**Input:** A scanned lecture handout where all content is embedded as images — no selectable text.

**Expected behaviour:** Bot rejects the file with a clear error, stays in FILE_UPLOAD state, asks user to retry.

**Actual behaviour:**
```
Bot: "Could not read slides: No extractable text found. The PDF may be 
scanned/image-based. Please use a PDF with selectable text."
```
Bot remained in FILE_UPLOAD state and accepted a second upload attempt.

**Result: PASS**

---

### 3b — Non-PDF file uploaded

**Input:** User uploads `lecture_notes.docx` instead of a PDF.

**Expected behaviour:** Bot rejects with a message about PDF-only support.

**Actual behaviour:**
```
Bot: "Only PDF files are supported. 'lecture_notes.docx' was rejected.
Please upload a .pdf file."
```
**Result: PASS**

---

### 3c — Invalid email address

**Input:** User types `not-an-email` at the email prompt.

**Expected behaviour:** Bot re-prompts without advancing state.

**Actual behaviour:**
```
Bot: "That does not look like a valid email address. Please try again."
```
State remained at PARAM_EMAIL; user could enter a valid address and continue.

**Result: PASS**

---

### 3d — Failed web search (simulated)

**Method:** Temporarily replaced DuckDuckGo call with a function that raises `ConnectionError`.

**Expected behaviour:** Pipeline continues; web_resources section shows an error entry; no crash.

**Actual behaviour:** All 6 pipeline steps completed. The web resources section read:
```
1. Search failed
   ConnectionError: …
```
The teaching plan and email body were generated normally using only slide content.

**Result: PASS**

---

### 3e — Missing SMTP credentials

**Method:** Ran the bot with `SMTP_USER` and `SMTP_PASSWORD` unset, then clicked "Send Email".

**Expected behaviour:** Error message to user, no crash.

**Actual behaviour:**
```
Bot: "Failed to send email: SMTP_USER and SMTP_PASSWORD must be set as 
environment variables."
```
The report remained saved; user could fix credentials and retry via /send.

**Result: PASS**

---

### 3f — LLM server unreachable

**Method:** Stopped llama-server, then ran /plan through to the processing step.

**Expected behaviour:** Pipeline fails with an error message; session state resets to IDLE.

**Actual behaviour:**
```
Bot: "Pipeline failed: Connection refused"
```
Session state reset to IDLE. `/status` showed the error in the recent errors list.

**Result: PASS**

---

## Latency Note

All times measured on Apple M3 Pro (11-core, 18 GB), llama.cpp `b9080`, Mistral-7B-Instruct-v0.2-Q4_K_M, `--ctx-size 4096`, all 33 layers offloaded to Metal GPU.

### Per-step timing (representative run, 12-page PDF)

| Step | Elapsed |
|------|---------|
| Step 1 — Summarise slides | 18 s |
| Step 2 — Concept map | 14 s |
| Step 3 — Teaching plan | 42 s |
| Step 4 — Web research (LLM queries + search) | 22 s |
| Step 5 — Revision | 48 s |
| Step 6 — Email body | 12 s |
| **Total** | **~156 s (2 min 36 s)** |

Web search itself took ~4 s of step 4. The remaining ~18 s was the LLM generating the 3 queries.

### Throughput

The `/benchmark` command reported:
```
Model    : mistral-7b-instruct-v0.2.Q4_K_M.gguf
Latency  : 9.4 s  (for the 256-token benchmark prompt)
Chars/s  : ~38 chars/s
```

### Comparison note

A Q8_0 quantisation of the same model was not tested due to the 8+ GB VRAM requirement exceeding comfortable margins on this machine. Based on published benchmarks, Q8_0 would reduce quality degradation at the cost of ~2× memory and ~10-15% lower throughput on Apple Silicon.

vLLM on an NVIDIA A100 80 GB (from a separate cloud test) completed the same 6-step pipeline in approximately 22 seconds — roughly 7× faster, primarily due to continuous batching and FP16 inference.

---

## Summary

| Test | Result |
|------|--------|
| TC1 — Full happy path | PASS |
| TC2 — Grounding check | PARTIAL PASS (80% accuracy) |
| TC3a — Image PDF | PASS |
| TC3b — Wrong file type | PASS |
| TC3c — Invalid email | PASS |
| TC3d — Web search failure | PASS |
| TC3e — Missing SMTP credentials | PASS |
| TC3f — LLM server down | PASS |

The system handles all tested failure modes gracefully. The main quality limitation is the occasional unlabelled fact from the LLM's training data, which is inherent to the model and would require RAG-style citation enforcement to fully address.
