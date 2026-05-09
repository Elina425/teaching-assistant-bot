# Agentic Telegram Teaching Assistant

A Telegram bot that turns lecture slides into a complete teaching package using a local LLM, web research, and email delivery.

## Features

- Upload PDF lecture slides via Telegram
- Local LLM (vLLM or llama.cpp) generates summary, concept map, timed teaching plan, exercises
- DuckDuckGo web search finds curated resources (no API key needed)
- Preview before sending — email is only sent after explicit confirmation
- All credentials stored in `.env`, never in code

## Prerequisites

- Python 3.11+
- A running local LLM server (vLLM or llama.cpp) — see below
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Gmail account with an [App Password](https://myaccount.google.com/apppasswords) (or any SMTP server)

## Quick Start

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd agentic-teaching-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN, LLM settings, and SMTP credentials

# 4. Start a local OpenAI-compatible LLM server on port 8000 (pick one)
#
#    A) vLLM — typical setup: Linux + NVIDIA GPU. Install the server first
#       (it is NOT in requirements.txt):
#       pip3 install vllm
#       If you skip that step you get: ModuleNotFoundError: No module named 'vllm'
python3 -m vllm.entrypoints.openai.api_server \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --port 8000
#
#    B) llama.cpp — recommended on macOS and for CPU-only / smaller GPUs (no vLLM install).
#       Build or download llama-server, fetch a GGUF model. With the modern Hub CLI
#       use `hf` (not deprecated huggingface-cli), e.g.:
#       hf download bartowski/Mistral-7B-Instruct-v0.2-GGUF \
#           Mistral-7B-Instruct-v0.2-Q4_K_M.gguf --local-dir ~/models
#       The file on disk may use different casing (e.g. mistral-7b-instruct-v0.2.Q4_K_M.gguf);
#       use:  ls ~/models/*.gguf
#       Then run the OpenAI-compatible server, e.g.:
#       llama-server -m ~/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
#           --port 8000 --ctx-size 4096
#       CPU only (no GPU offload), add:  --n-gpu-layers 0
#       See: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md

# 5. Run the bot
python3 bot.py
```

## Environment Variables

| Variable        | Description                                 | Default                        |
|-----------------|---------------------------------------------|--------------------------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather    | *required*                     |
| `LLM_BASE_URL`  | OpenAI-compatible API base URL             | `http://localhost:8000/v1`     |
| `LLM_MODEL`     | Model name passed to the API               | `mistral-7b-instruct`          |
| `LLM_API_KEY`   | API key (local servers usually ignore this) | `not-needed`                   |
| `SMTP_HOST`     | SMTP server hostname                        | `smtp.gmail.com`               |
| `SMTP_PORT`     | SMTP port (STARTTLS)                        | `587`                          |
| `SMTP_USER`     | Sending email address                       | *required*                     |
| `SMTP_PASSWORD` | SMTP / App Password                         | *required*                     |
| `SMTP_FROM`     | From address (defaults to SMTP_USER)        | same as `SMTP_USER`            |

## Bot Commands

| Command     | Description                                          |
|-------------|------------------------------------------------------|
| `/start`    | Welcome message with workflow overview               |
| `/help`     | List all commands and limitations                    |
| `/plan`     | Start workflow: upload slides → answer questions     |
| `/research` | Show web resources for the current topic             |
| `/status`   | Show session state, file info, and recent errors     |
| `/send`     | Re-display preview and resend confirmation buttons   |
| `/cancel`   | Cancel the active workflow                           |

## Architecture

```
Telegram Bot API
     │
     ▼
  bot.py  (ConversationHandler state machine)
     │
     ▼
agents/orchestrator.py  (6-step pipeline)
     ├── agents/prompts.py          (all LLM prompt templates)
     ├── tools/slides.py            (PDF text extraction via PyMuPDF)
     ├── tools/web_search.py        (DuckDuckGo search)
     └── tools/email_sender.py     (SMTP email via smtplib)
     │
     ▼
llm_backend.py  (AsyncOpenAI client → vLLM / llama.cpp)
```

### Pipeline Steps

| Step | What happens |
|------|-------------|
| 1 — Slide ingestion | PyMuPDF extracts text per page with `[Slide N]` labels |
| 2 — Concept map | LLM lists main concepts, key terms, and prerequisites |
| 3 — Teaching plan | LLM creates a timed plan with objectives, examples, exercises, recap |
| 4 — Web research | LLM generates 3 search queries; DuckDuckGo fetches results |
| 5 — Revision | LLM grounds the plan in slide + web sources, labels each claim |
| 6 — Email draft | LLM writes a professional email body; user confirms before sending |

## Recommended Models

| Hardware | Model | Command |
|----------|-------|---------|
| GPU ≥ 16 GB (Linux + CUDA typical) | Mistral-7B-Instruct-v0.2 (vLLM) | After `pip3 install vllm`: `python3 -m vllm.entrypoints.openai.api_server --model mistralai/Mistral-7B-Instruct-v0.2 --port 8000` |
| macOS / CPU / GPU < 8 GB | Mistral-7B-Instruct Q4_K_M (llama.cpp) | `hf download … --local-dir ~/models` then `llama-server -m ~/models/<your>.gguf --port 8000 --ctx-size 4096` — add `--n-gpu-layers 0` for **CPU only** |

vLLM is not installed with this project; `ModuleNotFoundError: No module named 'vllm'` means you still need `pip3 install vllm` (often impractical on macOS — use llama.cpp instead) or a [source/CPU build](https://docs.vllm.ai/en/latest/getting_started/installation.html). For GGUF files, use the **`hf`** CLI (`pip install -U huggingface_hub`); **`huggingface-cli download` is deprecated** and may refuse to run. If `llama-server` says **No such file or directory** for the model path, the GGUF name often differs from the README (check `ls ~/models/*.gguf`).

Typical latency: ~90 seconds for the full 6-step pipeline on a Q4 GGUF model.

## Troubleshooting

- **`HTTP 409 Conflict` / `terminated by other getUpdates request`** — Telegram allows only **one** client to poll updates per bot. Stop every other copy of this bot: extra Terminal tabs running `python3 bot.py`, a second machine, or an old process. On macOS you can list processes with `pgrep -fl bot.py` and stop them (Ctrl+C in each terminal or `kill <pid>`). If you used **webhooks** before (`setWebhook`), either delete them from your host or use BotFather; this app calls `deleteWebhook` on startup, but another service still polling the same token will cause this until it is stopped.
- **Long noisy tracebacks while polling** — After fixing duplicates, restart a single `python3 bot.py`.

## Security Notes

- Never commit `.env` — it is in `.gitignore`
- Use Gmail App Passwords, not your real password
- The bot only sends email after the user clicks "Send Email" in the inline keyboard
- All SMTP credentials are read from environment variables at runtime

## Limitations

- PDF only (PPTX not supported)
- Scanned/image-based PDFs will be rejected (no OCR)
- One active workflow per user
- Output quality depends heavily on the local LLM model and quantisation level
- Web search may fail if DuckDuckGo rate-limits the request (handled gracefully)
