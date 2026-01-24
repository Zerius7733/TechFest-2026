import json
import os
import inspect
from typing import Any, Dict

from server.services.llm_client import chat_json
from server.services.ocr_service import ocr_bytes

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "resume_optimize.json")

def _load_personas() -> Dict[str, Any]:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _build_system_prompt(industry_key: str, persona_cfg: Dict[str, Any]) -> str:
    title = persona_cfg.get("persona_title", "Hiring Manager")
    checklist = persona_cfg.get("what_they_look_for", [])

    checklist_lines = "\n".join([f"- {x}" for x in checklist])

    return f"""You are a {title}.
You are strict, practical, and specific.

Your job:
1) Explain what you typically look for in this industry.
2) Critique the resume with pinpoint, actionable fixes.
3) Provide an optimized rewrite (same content, better phrasing, stronger impact).
4) Output JSON only in the schema requested.

What you look for in this industry:
{checklist_lines}
"""

def _build_user_prompt(resume_text: str, industry_key: str) -> str:
    # You can optionally ask user for role later. For now: industry-only.
    return f"""Industry selected: {industry_key}

Resume text:
\"\"\"{resume_text}\"\"\"

Return JSON with:
{{
  "summary": {{
    "fit_score": 0-100,
    "clarity": "Low|Medium|High",
    "missing_keywords_count": integer
  }},
  "recruiter_checklist": [string, ...],
  "issues": [
    {{
      "title": string,
      "location": string, 
      "why": string,
      "fix": string,
      "rewrite": string
    }}
  ],
  "optimized_text": string
}}

Rules:
- Be specific. No generic advice.
- Location should reference section names or bullet text snippets.
- optimized_text should be a full improved resume text (plain text).
"""

async def optimize_resume(file_bytes: bytes, filename: str, industry_key: str) -> Dict[str, Any]:
    personas = _load_personas()
    persona_cfg = personas.get(industry_key, personas.get("other"))

    # Extract text from resume file
    ocr_result = ocr_bytes(
        file_bytes=file_bytes,
        filename=filename,
        content_type=None,
        max_pages=4,
    )
    if inspect.iscoroutine(ocr_result):
        original_text, _pages = await ocr_result
    else:
        original_text, _pages = ocr_result


    system_prompt = _build_system_prompt(industry_key, persona_cfg)
    user_prompt = _build_user_prompt(original_text, industry_key)

    # LLM call: must return JSON text
    llm_result = chat_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    if inspect.iscoroutine(llm_result):
        data = await llm_result
    else:
        data = llm_result


    # Attach original text for side-by-side view
    data["original_text"] = original_text
    return data
