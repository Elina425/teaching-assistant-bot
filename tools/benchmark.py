"""
LLM benchmark tool.

Sends a fixed test prompt to one or two OpenAI-compatible backends and
measures wall-clock latency and approximate tokens/s.

Used by the /benchmark bot command.
Configure a second backend for comparison via .env:
  LLM_BASE_URL_2=http://localhost:9000/v1
  LLM_MODEL_2=llama-3-8b-instruct
"""

import os
import time

from openai import AsyncOpenAI

TEST_PROMPT = (
    "Explain the concept of gradient descent in machine learning "
    "in 3 concise sentences suitable for a first-year university student."
)


async def benchmark_single(
    base_url: str,
    model: str,
    api_key: str = "not-needed",
    label: str = "Backend",
) -> dict:
    """
    Run the test prompt and return a result dict:
      label, model, latency_s, char_count, chars_per_s, output (first 200 chars), error
    """
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    t0 = time.perf_counter()
    error = None
    output = ""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful educator."},
                {"role": "user", "content": TEST_PROMPT},
            ],
            temperature=0.3,
            max_tokens=256,
        )
        output = resp.choices[0].message.content or ""
    except Exception as exc:
        error = str(exc)
    elapsed = time.perf_counter() - t0
    chars = len(output)
    return {
        "label": label,
        "model": model,
        "base_url": base_url,
        "latency_s": round(elapsed, 2),
        "char_count": chars,
        "chars_per_s": round(chars / elapsed, 1) if elapsed > 0 and chars > 0 else 0,
        "output": output[:300],
        "error": error,
    }


async def run_benchmark() -> list[dict]:
    """
    Benchmark the primary backend (from env), and optionally a second one.
    Returns a list of result dicts (1 or 2 entries).
    """
    results = []

    primary = await benchmark_single(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:8000/v1"),
        model=os.getenv("LLM_MODEL", "mistral-7b-instruct"),
        api_key=os.getenv("LLM_API_KEY", "not-needed"),
        label="Primary (llama.cpp / vLLM)",
    )
    results.append(primary)

    url2 = os.getenv("LLM_BASE_URL_2", "")
    model2 = os.getenv("LLM_MODEL_2", "")
    if url2 and model2:
        secondary = await benchmark_single(
            base_url=url2,
            model=model2,
            api_key=os.getenv("LLM_API_KEY_2", "not-needed"),
            label="Secondary",
        )
        results.append(secondary)

    return results


def format_benchmark_results(results: list[dict]) -> str:
    lines = ["Benchmark Results", "=" * 36, f"Prompt: {TEST_PROMPT[:80]}…", ""]
    for r in results:
        lines.append(f"--- {r['label']} ---")
        lines.append(f"Model      : {r['model']}")
        lines.append(f"URL        : {r['base_url']}")
        if r["error"]:
            lines.append(f"ERROR      : {r['error']}")
        else:
            lines.append(f"Latency    : {r['latency_s']} s")
            lines.append(f"Chars      : {r['char_count']}")
            lines.append(f"Chars/s    : {r['chars_per_s']}")
            lines.append(f"Output     : {r['output'][:200]}…")
        lines.append("")
    if len(results) == 2 and not results[0]["error"] and not results[1]["error"]:
        diff = results[0]["latency_s"] - results[1]["latency_s"]
        faster = results[0]["label"] if diff < 0 else results[1]["label"]
        lines.append(f"Faster: {faster} by {abs(diff):.2f} s")
    return "\n".join(lines)
