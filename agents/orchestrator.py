"""
Agent orchestrator — runs the full 6-step teaching-package pipeline.

Steps:
  1. Slide summary + title
  2. Concept map
  3. Teaching plan
  4. Web research (LLM generates queries, DuckDuckGo executes them)
  5. Revision (grounds plan in slide + web sources)
  6. Email body draft

Each pipeline run is timed per step and appended to traces.json so the
dashboard can inspect agent behaviour.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from agents.prompts import (
    concept_map_prompt,
    email_body_prompt,
    revision_prompt,
    slide_summary_prompt,
    teaching_plan_prompt,
    web_search_queries_prompt,
)
from tools.web_search import search_web

logger = logging.getLogger(__name__)

SLIDE_CONTEXT_LIMIT = 8000
TRACES_FILE = Path(__file__).parent.parent / "traces.json"


class Orchestrator:
    def __init__(self, llm) -> None:
        self.llm = llm

    async def run(
        self,
        session: dict,
        progress_cb: Callable[[str], Awaitable] | None = None,
    ) -> dict:
        """
        Execute the full pipeline and return a report dict.

        Appends a trace entry to traces.json on completion (success or error).
        """
        trace: dict = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": session.get("user_id", 0),
            "file_name": session.get("file_name", ""),
            "params": {
                "duration": session.get("duration", ""),
                "audience": session.get("audience", ""),
                "language": session.get("language", "English"),
            },
            "steps": [],
            "total_elapsed_s": 0.0,
            "status": "error",
            "error": None,
        }
        pipeline_start = time.perf_counter()

        async def notify(msg: str) -> None:
            logger.info("[pipeline] %s", msg)
            session["logs"].append(msg)
            if progress_cb:
                try:
                    await progress_cb(msg)
                except Exception:
                    pass

        async def timed_step(name: str, coro):
            """Await *coro*, record elapsed time in the trace, return the result."""
            await notify(name)
            t0 = time.perf_counter()
            result = await coro
            elapsed = round(time.perf_counter() - t0, 2)
            trace["steps"].append({"name": name, "elapsed_s": elapsed})
            return result

        slide_text: str = session["slide_text"]
        duration: str = session["duration"]
        audience: str = session["audience"]
        language: str = session["language"]
        slide_excerpt = slide_text[:SLIDE_CONTEXT_LIMIT]

        try:
            # ── Step 1: Summary + title ───────────────────────────────────────
            raw_summary = await timed_step(
                "Step 1/6 — Summarising slides…",
                self.llm.generate(
                    slide_summary_prompt(slide_excerpt, language),
                    temperature=0.4, max_tokens=512,
                ),
            )
            title = _extract_field(raw_summary, "Title") or "Lecture"
            summary = _extract_field(raw_summary, "Summary") or raw_summary

            # ── Step 2: Concept map ───────────────────────────────────────────
            concept_map = await timed_step(
                "Step 2/6 — Building concept map…",
                self.llm.generate(
                    concept_map_prompt(summary, slide_text, language),
                    temperature=0.4, max_tokens=600,
                ),
            )

            # ── Step 3: Teaching plan ─────────────────────────────────────────
            teaching_plan = await timed_step(
                "Step 3/6 — Creating teaching plan…",
                self.llm.generate(
                    teaching_plan_prompt(summary, concept_map, duration, audience, language),
                    temperature=0.6, max_tokens=1600,
                ),
            )

            # ── Step 4: Web research ──────────────────────────────────────────
            queries_raw = await timed_step(
                "Step 4/6 — Searching the web for resources…",
                self.llm.generate(
                    web_search_queries_prompt(summary, concept_map),
                    temperature=0.3, max_tokens=128,
                ),
            )
            queries = [q.strip() for q in queries_raw.splitlines() if q.strip()][:3]
            raw_results: list[dict] = []
            for q in queries:
                raw_results.extend(search_web(q, max_results=3))

            seen_urls: set[str] = set()
            web_resources: list[dict] = []
            for r in raw_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    web_resources.append(r)
                if len(web_resources) >= 6:
                    break
            web_resources_text = _format_resources(web_resources)

            # ── Step 5: Revision ──────────────────────────────────────────────
            revised_plan = await timed_step(
                "Step 5/6 — Revising and grounding the plan…",
                self.llm.generate(
                    revision_prompt(teaching_plan, web_resources_text, slide_text, language),
                    temperature=0.5, max_tokens=1800,
                ),
            )

            # ── Step 6: Email body ────────────────────────────────────────────
            email_body = await timed_step(
                "Step 6/6 — Drafting email body…",
                self.llm.generate(
                    email_body_prompt(title, audience, duration, revised_plan, language),
                    temperature=0.5, max_tokens=512,
                ),
            )

            trace["status"] = "success"
            report = {
                "title": title,
                "summary": summary,
                "audience": audience,
                "duration": duration,
                "language": language,
                "concept_map": concept_map,
                "teaching_plan": teaching_plan,
                "web_resources": web_resources,
                "web_resources_text": web_resources_text,
                "revised_plan": revised_plan,
                "email_body": email_body,
            }
            return report

        except Exception as exc:
            trace["error"] = str(exc)
            raise
        finally:
            trace["total_elapsed_s"] = round(time.perf_counter() - pipeline_start, 2)
            _append_trace(trace)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_field(text: str, field: str) -> str:
    prefix = field.lower() + ":"
    for line in text.splitlines():
        if line.lower().startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _format_resources(results: list[dict]) -> str:
    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        title = r.get("title") or "Resource"
        url = r.get("url") or ""
        snippet = (r.get("snippet") or "")[:150]
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   {snippet}…")
    return "\n".join(lines)


def _append_trace(trace: dict) -> None:
    try:
        existing: list[dict] = []
        if TRACES_FILE.exists():
            existing = json.loads(TRACES_FILE.read_text(encoding="utf-8"))
        existing.append(trace)
        TRACES_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not write trace: %s", exc)
