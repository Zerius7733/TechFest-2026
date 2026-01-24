from __future__ import annotations

from typing import List, Dict, Any

from server.services.course_index import query_courses


def recommend_courses_from_missing_skills(
    missing_skills: List[str],
    top_k: int = 8,
) -> Dict[str, Any]:
    skills = [s.strip() for s in (missing_skills or []) if str(s).strip()]
    query = "Courses to learn and upskill: " + ", ".join(skills) if skills else "Courses for career upskilling"

    courses = query_courses(query_text=query, top_k=top_k)

    return {
        "query": query,
        "missing_skills": skills,
        "top_k": top_k,
        "courses": courses,
    }
