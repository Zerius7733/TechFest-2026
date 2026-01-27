from __future__ import annotations

from typing import List, Dict, Any

from server.services.course_index import query_courses


def _base_ref(course_ref: str) -> str:
    # Remove the "#n" suffix we added to avoid duplicate IDs in Chroma
    return str(course_ref or "").split("#", 1)[0].strip()


def _dedupe_courses(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in courses or []:
        base = _base_ref(c.get("coursereferencenumber", ""))
        if not base or base in seen:
            continue
        seen.add(base)

        # normalize to base ref for cleaner UI
        c2 = dict(c)
        c2["coursereferencenumber"] = base
        out.append(c2)
    return out


def recommend_courses_from_missing_skills(
    missing_skills: List[str],
    top_k: int = 8,
    job_title: str | None = None,
) -> Dict[str, Any]:
    skills = [str(s).strip() for s in (missing_skills or []) if str(s).strip()]

    # Query 1: focus on missing skills
    query = "Courses to learn and upskill: " + ", ".join(skills) if skills else "Courses for career upskilling"
    try:
        courses_1 = query_courses(query_text=query, top_k=top_k)
    except Exception as e:
        return {
            "query": query,
            "fallback_query": None,
            "missing_skills": skills,
            "top_k": top_k,
            "strong_threshold": 0.72,
            "courses": [],
            "strong_matches": [],
            "error": str(e),
        }

    # Dedupe (handles TGS-xxxx and TGS-xxxx#1)
    courses_1 = _dedupe_courses(courses_1)

    # Strong match threshold (tune later if needed)
    STRONG_THRESH = 0.72
    strong_1 = [c for c in courses_1 if float(c.get("distance", 1.0)) <= STRONG_THRESH]

    # If no strong matches, deterministic "double-check" with broader query
    courses_2: List[Dict[str, Any]] = []
    fallback_query: str | None = None

    if not strong_1 and skills:
        fallback_query = f"Courses to prepare for {job_title or 'this role'}. Missing skills: {', '.join(skills)}"
        courses_2 = query_courses(query_text=fallback_query, top_k=top_k)
        courses_2 = _dedupe_courses(courses_2)

    # Merge (keep order: query1 then query2) + final dedupe
    merged = _dedupe_courses((courses_1 or []) + (courses_2 or []))
    strong_merged = [c for c in merged if float(c.get("distance", 1.0)) <= STRONG_THRESH]

    return {
        "query": query,
        "fallback_query": fallback_query,
        "missing_skills": skills,
        "top_k": top_k,
        "strong_threshold": STRONG_THRESH,
        "courses": merged,
        "strong_matches": strong_merged,
    }
