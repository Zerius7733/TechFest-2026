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


def critique_review(
    gap: Dict[str, Any],
    job_title: str,
    job_description: str,
    courses: list[dict],
    draft: Dict[str, Any],
) -> Dict[str, Any]:
    prompt_obj = json.loads((PROMPTS_DIR / "critique.json").read_text(encoding="utf-8"))

    user_prompt = _render(
        prompt_obj["user_template"],
        JOB_TITLE=job_title,
        JOB_DESCRIPTION=job_description,
        GAP_JSON=json.dumps(gap, ensure_ascii=False),
        COURSES_JSON=json.dumps(courses or [], ensure_ascii=False),
        DRAFT_JSON=json.dumps(draft, ensure_ascii=False),
    )

    result = chat_json(prompt_obj["system"], user_prompt)

    if result.get("verdict") not in ("approve", "revise"):
        result["verdict"] = "revise"
    if "final_response" not in result or not isinstance(result["final_response"], dict):
        result["final_response"] = draft
    if "issues_found" not in result or not isinstance(result["issues_found"], list):
        result["issues_found"] = []

    return result
