"""
Agentic Telegram Teaching Assistant — main bot entry point.

State machine per user (stored in context.user_data):
  IDLE  →  FILE_UPLOAD  →  PARAM_DURATION  →  PARAM_AUDIENCE
        →  PARAM_LANGUAGE  →  PARAM_EMAIL  →  PROCESSING  →  PREVIEW  →  DONE

Run:
  python bot.py
"""

import asyncio
import logging
import os
import tempfile

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents.orchestrator import Orchestrator
from llm_backend import LLMBackend
from tools.benchmark import format_benchmark_results, run_benchmark
from tools.email_sender import send_email
from tools.report_generator import save_markdown, save_pdf
from tools.slides import parse_slides

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ConversationHandler state identifiers ─────────────────────────────────────
FILE_UPLOAD, PARAM_DURATION, PARAM_AUDIENCE, PARAM_LANGUAGE, PARAM_EMAIL = range(5)

# ── Session helpers ───────────────────────────────────────────────────────────

def _init_session(user_data: dict) -> None:
    """Initialise user_data keys that may not exist yet."""
    defaults = {
        "state": "IDLE",
        "file_path": None,
        "file_name": None,
        "duration": None,
        "audience": None,
        "language": "English",
        "recipient_email": None,
        "slide_text": None,
        "report": None,
        "errors": [],
        "logs": [],
    }
    for k, v in defaults.items():
        user_data.setdefault(k, v)


def _reset_session(user_data: dict) -> None:
    """Clear pipeline state but keep contact details if already set."""
    user_data.update(
        state="IDLE",
        file_path=None,
        file_name=None,
        slide_text=None,
        report=None,
        errors=[],
        logs=[],
    )


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _init_session(context.user_data)
    await update.message.reply_text(
        "Welcome to the Agentic Teaching Assistant!\n\n"
        "I turn lecture slides into a complete teaching package:\n"
        "  • Timed lesson plan with objectives\n"
        "  • Concept map and prerequisite list\n"
        "  • Hands-on exercises\n"
        "  • Curated web resources\n"
        "  • Ready-to-send email summary\n\n"
        "Example workflow:\n"
        "  1. /plan  — upload your PDF slides\n"
        "  2. Answer a few questions (duration, audience, language, email)\n"
        "  3. Review the preview, then confirm to send by email\n\n"
        "Type /help for the full command list."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n\n"
        "  /start    — Welcome message\n"
        "  /help     — This message\n"
        "  /plan     — Upload slides and generate a lesson plan\n"
        "  /research — Show web resources for the current topic\n"
        "  /status   — Show session state and recent errors\n"
        "  /send     — Re-send the preview and email confirmation\n"
        "  /cancel    — Cancel the current workflow\n"
        "  /benchmark — Measure LLM latency (chars/s)\n\n"
        "Limitations:\n"
        "  • PDF only (PPTX not supported)\n"
        "  • One active workflow per user\n"
        "  • Requires a running local LLM server (vLLM or llama.cpp)\n"
        "  • Web search requires internet access"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _init_session(context.user_data)
    d = context.user_data
    lines = [
        f"State         : {d['state']}",
        f"File          : {d['file_name'] or 'none'}",
        f"Duration      : {d['duration'] or 'not set'}",
        f"Audience      : {d['audience'] or 'not set'}",
        f"Language      : {d['language']}",
        f"Email         : {d['recipient_email'] or 'not set'}",
        f"Report ready  : {'yes' if d['report'] else 'no'}",
    ]
    if d["errors"]:
        lines.append("\nRecent errors:")
        for e in d["errors"][-3:]:
            lines.append(f"  • {e}")
    if d["logs"]:
        lines.append("\nLast log entries:")
        for log in d["logs"][-5:]:
            lines.append(f"  • {log}")
    await update.message.reply_text("\n".join(lines))


async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _init_session(context.user_data)
    report = context.user_data.get("report")
    if not report:
        await update.message.reply_text(
            "No report available yet. Run /plan first to upload slides."
        )
        return
    resources = report.get("web_resources_text") or "No resources found."
    await update.message.reply_text(f"Web Resources\n\n{resources}")


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _init_session(context.user_data)
    report = context.user_data.get("report")
    if not report:
        await update.message.reply_text("No report available. Run /plan first.")
        return
    await _send_preview(update.message.chat_id, report, context)


# ── /plan ConversationHandler ─────────────────────────────────────────────────

async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _init_session(context.user_data)
    _reset_session(context.user_data)
    context.user_data["state"] = "WAITING_FILE"
    context.user_data["user_id"] = update.effective_user.id  # stored for trace logging
    await update.message.reply_text(
        "Please upload your lecture slides as a PDF file."
    )
    return FILE_UPLOAD


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc = update.message.document
    if not doc:
        await update.message.reply_text("Please send a PDF document file.")
        return FILE_UPLOAD

    if not doc.file_name.lower().endswith(".pdf"):
        context.user_data["errors"].append(f"Rejected non-PDF: {doc.file_name}")
        await update.message.reply_text(
            f"Only PDF files are supported. '{doc.file_name}' was rejected.\n"
            "Please upload a .pdf file."
        )
        return FILE_UPLOAD

    await update.message.reply_text("Downloading your file…")

    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, doc.file_name)
    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(file_path)

    try:
        slide_text = parse_slides(file_path)
    except ValueError as exc:
        context.user_data["errors"].append(f"Slide parse error: {exc}")
        await update.message.reply_text(
            f"Could not read slides: {exc}\n"
            "Please try a different PDF (text must be selectable, not scanned)."
        )
        return FILE_UPLOAD

    context.user_data.update(
        file_path=file_path,
        file_name=doc.file_name,
        slide_text=slide_text,
        state="WAITING_PARAMS",
    )
    context.user_data["logs"].append(f"Uploaded: {doc.file_name}")
    page_count = slide_text.count("[Slide ")

    await update.message.reply_text(
        f"Slides received: {doc.file_name} ({page_count} pages with text).\n\n"
        "How long is the lecture? (e.g. '60 minutes', '1.5 hours')"
    )
    return PARAM_DURATION


async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["duration"] = update.message.text.strip()
    await update.message.reply_text(
        "Who is the target audience?\n"
        "(e.g. 'undergraduate CS students', 'high-school grade 10')"
    )
    return PARAM_AUDIENCE


async def receive_audience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["audience"] = update.message.text.strip()
    await update.message.reply_text(
        "What language should the output be in?\n\n"
        "Examples:\n"
        "  English\n"
        "  Armenian\n"
        "  bilingual Armenian/English\n"
        "  Russian\n\n"
        "Type 'skip' for English."
    )
    return PARAM_LANGUAGE


async def receive_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = update.message.text.strip()
    if lang.lower() == "skip":
        lang = "English"
    # Normalise common bilingual shorthand
    lang = lang.replace("armenian/english", "bilingual Armenian and English")
    lang = lang.replace("english/armenian", "bilingual Armenian and English")
    context.user_data["language"] = lang
    await update.message.reply_text("What is the recipient email address?")
    return PARAM_EMAIL


async def receive_email_addr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email_addr = update.message.text.strip()
    if "@" not in email_addr or "." not in email_addr.split("@")[-1]:
        await update.message.reply_text(
            "That does not look like a valid email address. Please try again."
        )
        return PARAM_EMAIL

    context.user_data["recipient_email"] = email_addr
    context.user_data["state"] = "PROCESSING"
    context.user_data["logs"].append("Pipeline started.")

    await update.message.reply_text(
        "All set! Starting the pipeline now.\n"
        "I will send progress updates and show a preview when done.\n"
        "(This may take 1-2 minutes depending on your LLM.)"
    )

    # Run the pipeline in the background so the handler returns immediately.
    asyncio.create_task(
        _run_pipeline(update.effective_chat.id, context)
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _reset_session(context.user_data)
    await update.message.reply_text("Workflow cancelled. Type /plan to start over.")
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /cancel handler for when no conversation is active."""
    _init_session(context.user_data)
    if context.user_data.get("state", "IDLE") == "IDLE":
        await update.message.reply_text("Nothing to cancel. Type /plan to start.")
    else:
        _reset_session(context.user_data)
        await update.message.reply_text("Session reset. Type /plan to start over.")


# ── Pipeline runner ───────────────────────────────────────────────────────────

async def _run_pipeline(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background task: run the orchestrator and send the preview on completion."""
    user_data = context.user_data
    llm = LLMBackend()
    orchestrator = Orchestrator(llm)

    async def progress_cb(msg: str) -> None:
        try:
            await context.bot.send_message(chat_id, f"[pipeline] {msg}")
        except Exception:
            pass

    try:
        report = await orchestrator.run(user_data, progress_cb=progress_cb)
        user_data["report"] = report
        user_data["state"] = "PREVIEW"
        user_data["logs"].append("Pipeline complete.")

        # Send Markdown and PDF attachments
        await _send_attachments(chat_id, report, context)

        await _send_preview(chat_id, report, context)
    except Exception as exc:
        user_data["state"] = "IDLE"
        user_data["errors"].append(str(exc))
        logger.exception("Pipeline error for chat %s", chat_id)
        await context.bot.send_message(
            chat_id,
            f"Pipeline failed: {exc}\n\nCheck /status for details.",
        )


# ── Preview & confirm ─────────────────────────────────────────────────────────

async def _send_preview(
    chat_id: int, report: dict, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Send the teaching-package preview with confirm/cancel buttons."""
    preview = _format_preview(report)
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Send Email", callback_data="confirm_send"),
            InlineKeyboardButton("Cancel",     callback_data="cancel_send"),
        ]]
    )
    chunks = _split_text(preview, max_len=4000)
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await context.bot.send_message(chat_id, chunk, reply_markup=keyboard)
        else:
            await context.bot.send_message(chat_id, chunk)


async def confirm_send_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the inline-keyboard confirm/cancel buttons."""
    query = update.callback_query
    await query.answer()
    _init_session(context.user_data)

    if query.data == "confirm_send":
        report = context.user_data.get("report")
        if not report:
            await query.edit_message_text("No report to send. Run /plan first.")
            return
        email_addr = context.user_data.get("recipient_email")
        if not email_addr:
            await query.edit_message_text("No recipient email set. Run /plan again.")
            return

        await query.edit_message_text("Sending email…")
        try:
            send_email(
                to_addr=email_addr,
                subject=f"Teaching Package: {report.get('title', 'Lecture')}",
                body=_build_email_body(report),
            )
            context.user_data["state"] = "DONE"
            context.user_data["logs"].append(f"Email sent to {email_addr}")
            await context.bot.send_message(
                query.message.chat_id,
                f"Email sent successfully to {email_addr}.",
            )
        except Exception as exc:
            context.user_data["errors"].append(f"Email error: {exc}")
            await context.bot.send_message(
                query.message.chat_id,
                f"Failed to send email: {exc}",
            )
    else:
        context.user_data["state"] = "IDLE"
        await query.edit_message_text(
            "Email cancelled. Your report is saved. "
            "Use /send to show the preview again."
        )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_preview(report: dict) -> str:
    sep = "-" * 40
    sections = [
        "===== TEACHING PACKAGE PREVIEW =====",
        f"Title    : {report.get('title', 'N/A')}",
        f"Audience : {report.get('audience', 'N/A')}",
        f"Duration : {report.get('duration', 'N/A')}",
        f"Language : {report.get('language', 'N/A')}",
        sep,
        "SUMMARY",
        report.get("summary", ""),
        sep,
        "CONCEPT MAP",
        report.get("concept_map", ""),
        sep,
        "REVISED TEACHING PLAN",
        report.get("revised_plan", ""),
        sep,
        "WEB RESOURCES",
        report.get("web_resources_text", ""),
        sep,
        "EMAIL BODY PREVIEW",
        report.get("email_body", ""),
    ]
    return "\n\n".join(sections)


def _build_email_body(report: dict) -> str:
    body_parts = [
        report.get("email_body", ""),
        "",
        "--- Teaching Package ---",
        "",
        f"Title    : {report.get('title', 'N/A')}",
        f"Audience : {report.get('audience', 'N/A')}",
        f"Duration : {report.get('duration', 'N/A')}",
        "",
        report.get("revised_plan", ""),
        "",
        "--- Web Resources ---",
        report.get("web_resources_text", ""),
    ]
    return "\n".join(body_parts)


async def _send_attachments(
    chat_id: int, report: dict, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send Markdown and PDF files as Telegram documents."""
    try:
        md_path = save_markdown(report)
        with open(md_path, "rb") as f:
            await context.bot.send_document(
                chat_id, document=f, filename=f"{report.get('title', 'report')}.md",
                caption="Teaching package (Markdown)"
            )
    except Exception as exc:
        logger.warning("Could not send Markdown attachment: %s", exc)

    try:
        pdf_path = save_pdf(report)
        if pdf_path:
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id, document=f, filename=f"{report.get('title', 'report')}.pdf",
                    caption="Teaching package (PDF)"
                )
    except Exception as exc:
        logger.warning("Could not send PDF attachment: %s", exc)


async def cmd_benchmark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Running benchmark — sending a test prompt to the configured LLM(s).\n"
        "This may take 30-60 seconds…"
    )
    try:
        results = await run_benchmark()
        text = format_benchmark_results(results)
        for chunk in _split_text(text, 4000):
            await update.message.reply_text(chunk)
    except Exception as exc:
        await update.message.reply_text(f"Benchmark failed: {exc}")


def _split_text(text: str, max_len: int = 4000) -> list[str]:
    """Split a long string at newline boundaries, respecting max_len."""
    chunks: list[str] = []
    while len(text) > max_len:
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _require_telegram_token() -> str:
    """Return a stripped token or raise with an actionable message."""
    raw = os.getenv("TELEGRAM_BOT_TOKEN")
    if not raw or not raw.strip():
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Copy .env.example to .env and set TELEGRAM_BOT_TOKEN to the token from @BotFather."
        )
    token = raw.strip()
    lower = token.lower()
    if lower in _INVALID_TOKEN_MARKERS or lower.startswith("your_telegram"):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is still a placeholder (e.g. from .env.example). "
            "Open Telegram → @BotFather → /newbot or your bot → copy the token into .env."
        )
    # BotFather tokens are "<numeric_bot_id>:<secret>"
    if ":" not in token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN does not look like a Telegram bot token "
            "(expected something like 123456789:AAH...)."
        )
    bot_id, _, secret = token.partition(":")
    if not bot_id.isdigit() or not secret:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN does not look like a Telegram bot token "
            "(expected leading digits before ':')."
        )

    return token


# ── Application setup ─────────────────────────────────────────────────────────

def main() -> None:
    token = _require_telegram_token()

    app = Application.builder().token(token).build()

    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("plan", plan_start)],
        states={
            FILE_UPLOAD:    [MessageHandler(filters.Document.ALL, receive_file)],
            PARAM_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_duration)],
            PARAM_AUDIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_audience)],
            PARAM_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_language)],
            PARAM_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email_addr)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ConversationHandler must be registered first so its states
    # take priority over standalone command handlers for active conversations.
    app.add_handler(plan_conv)
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("research",  cmd_research))
    app.add_handler(CommandHandler("send",      cmd_send))
    app.add_handler(CommandHandler("benchmark", cmd_benchmark))
    app.add_handler(CommandHandler("cancel",    cmd_cancel))
    app.add_handler(
        CallbackQueryHandler(
            confirm_send_callback,
            pattern=r"^(confirm|cancel)_send$",
        )
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
