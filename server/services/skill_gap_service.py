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


def analyze_skill_gap(resume_text: str, job_title: str, job_description: str) -> Dict[str, Any]:
    prompt_path = PROMPTS_DIR / "skill_gap.json"
    prompt_obj = json.loads(prompt_path.read_text(encoding="utf-8"))

    system_prompt = prompt_obj["system"]
    user_template = prompt_obj["user_template"]

    user_prompt = _render(
        user_template,
        RESUME_TEXT=resume_text.strip(),
        JOB_TITLE=job_title.strip(),
        JOB_DESCRIPTION=job_description.strip(),
    )

    result = chat_json(system_prompt, user_prompt)

    # minimal shape enforcement
    for key in ["resume_skills", "job_skills", "matched_skills", "missing_skills", "extra_skills"]:
        if key not in result or not isinstance(result[key], list):
            result[key] = []
    if "notes" not in result or not isinstance(result["notes"], str):
        result["notes"] = ""

    return result
