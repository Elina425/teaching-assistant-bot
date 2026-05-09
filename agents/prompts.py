"""
All LLM prompt templates.

Each function returns a list[dict] (OpenAI chat-format messages).
Keeping prompts here makes them easy to tune and test independently.
"""

SYSTEM_EDUCATOR = (
    "You are an expert educator and curriculum designer. "
    "You create clear, practical, and well-structured teaching materials. "
    "Always be concise and directly useful."
)


def slide_summary_prompt(slide_text: str, language: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                "The following is the full text of lecture slides:\n\n"
                f"{slide_text}\n\n"
                "1. Identify the overall topic.\n"
                "2. Write a concise 3-5 sentence summary of the lecture content.\n"
                "3. Create a short, descriptive title for the lecture.\n\n"
                f"Respond in {language}. Use exactly this format:\n"
                "Title: <lecture title>\n"
                "Summary: <3-5 sentence summary>"
            ),
        },
    ]


def concept_map_prompt(summary: str, slide_text: str, language: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                f"Lecture summary: {summary}\n\n"
                f"Slide content (excerpt):\n{slide_text[:3000]}\n\n"
                "Produce a structured concept map:\n"
                "1. Main Concepts (with [Slide N] references where possible)\n"
                "2. Key Terms and Definitions\n"
                "3. Prerequisite Knowledge students should already have\n\n"
                f"Respond in {language} using bullet-point lists."
            ),
        },
    ]


def teaching_plan_prompt(
    summary: str,
    concept_map: str,
    duration: str,
    audience: str,
    language: str,
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                "Create a detailed timed teaching plan.\n\n"
                f"Lecture summary: {summary}\n"
                f"Concepts: {concept_map}\n"
                f"Total duration: {duration}\n"
                f"Target audience: {audience}\n\n"
                "The plan must include:\n"
                "- 3-5 specific, measurable learning objectives\n"
                "- Timed breakdown (e.g. 0-10 min: Introduction)\n"
                "- At least 2 worked examples with brief descriptions\n"
                "- At least 1 hands-on exercise with clear instructions and expected outcome\n"
                "- A 5-minute recap / Q&A section at the end\n\n"
                f"Respond in {language}."
            ),
        },
    ]


def web_search_queries_prompt(summary: str, concept_map: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                "Based on this lecture:\n"
                f"Summary: {summary}\n"
                f"Concepts: {concept_map}\n\n"
                "Generate exactly 3 web search queries to find high-quality supplementary "
                "resources (tutorials, documentation, research papers, or videos).\n"
                "Return ONLY the 3 queries, one per line, no numbering or extra text."
            ),
        },
    ]


def revision_prompt(
    teaching_plan: str,
    web_resources: str,
    slide_text: str,
    language: str,
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                "Review and revise the following teaching plan.\n\n"
                f"TEACHING PLAN:\n{teaching_plan}\n\n"
                f"AVAILABLE WEB RESOURCES:\n{web_resources}\n\n"
                f"SLIDE CONTENT (excerpt):\n{slide_text[:2000]}\n\n"
                "Produce a final, improved teaching plan that:\n"
                "- Labels each claim as [Slides] or [Web] where it is grounded in a source\n"
                "- Integrates 2-3 of the web resources as 'Further Reading' at the end\n"
                "- Fixes any timing gaps or unrealistic sections\n"
                "- Ensures the exercise instructions are complete and actionable\n\n"
                f"Respond in {language}."
            ),
        },
    ]


def email_body_prompt(
    title: str,
    audience: str,
    duration: str,
    revised_plan: str,
    language: str,
) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_EDUCATOR},
        {
            "role": "user",
            "content": (
                "Write a professional email to accompany a teaching package.\n\n"
                f"Lecture title: {title}\n"
                f"Target audience: {audience}\n"
                f"Duration: {duration}\n\n"
                f"Teaching package (excerpt):\n{revised_plan[:1500]}\n\n"
                "The email should:\n"
                "- Have a professional greeting and sign-off\n"
                "- Briefly describe what the package contains\n"
                "- Highlight 2-3 key features\n"
                "- Be 150-250 words\n\n"
                f"Respond in {language}."
            ),
        },
    ]
