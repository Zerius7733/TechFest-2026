import json
from pathlib import Path
from typing import Any, Dict

from server.services.llm_client import chat_json

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _render(template: str, **kwargs: str) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def career_suggest(
    gap: Dict[str, Any],
    job_title: str,
    job_skills: list[str],
    courses: list[dict],
) -> Dict[str, Any]:
    prompt_obj = json.loads((PROMPTS_DIR / "career_suggest.json").read_text(encoding="utf-8"))

    user_prompt = _render(
        prompt_obj["user_template"],
        RESUME_SKILLS=json.dumps(gap.get("resume_skills", []), ensure_ascii=False),
        JOB_TITLE=job_title,
        JOB_SKILLS=json.dumps(job_skills or gap.get("job_skills", []), ensure_ascii=False),
        MISSING_SKILLS=json.dumps(gap.get("missing_skills", []), ensure_ascii=False),
        EXTRA_SKILLS=json.dumps(gap.get("extra_skills", []), ensure_ascii=False),
        COURSES_JSON=json.dumps(courses or [], ensure_ascii=False),
    )

    result = chat_json(prompt_obj["system"], user_prompt)

    # minimal enforcement
    for key in ["skills_to_focus", "action_plan", "recommended_courses", "warnings"]:
        if key not in result or not isinstance(result[key], list):
            result[key] = []
    if "summary" not in result or not isinstance(result["summary"], str):
        result["summary"] = ""

    return result
