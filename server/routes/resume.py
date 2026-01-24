from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from pydantic import BaseModel

from server.services.skill_gap_service import analyze_skill_gap
from server.services.ocr_service import ocr_bytes
from server.services.jobs_service import get_job_by_id
from server.services.career_suggest_service import career_suggest
from server.services.critique_service import critique_review
from server.services.resume_optimize_service import optimize_resume

router = APIRouter(prefix="/api/resume", tags=["resume"])

from pydantic import BaseModel
from server.services.course_match_services import recommend_courses_from_missing_skills


class CourseRecRequest(BaseModel):
    missing_skills: list[str]
    top_k: int = 8


@router.post("/course-recommendations")
def course_recommendations(payload: CourseRecRequest):
    return recommend_courses_from_missing_skills(payload.missing_skills, top_k=payload.top_k)

class SkillGapRequest(BaseModel):
    resume_text: str
    job_title: str
    job_description: str


@router.post("/skill-gap")
def skill_gap(req: SkillGapRequest):
    try:
        return analyze_skill_gap(req.resume_text, req.job_title, req.job_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize")
async def resume_optimize(resume: UploadFile = File(...), industry: str = Form(...)):
    file_bytes = await resume.read()
    data = await optimize_resume(
        file_bytes=file_bytes,
        filename=resume.filename,
        industry_key=industry
    )
    return data


@router.post("/ocr-skill-gap")
async def ocr_skill_gap(
    job_id: int = Query(..., description="jobs.id (primary key)"),
    file: UploadFile = File(...)
):
    try:
        job = get_job_by_id(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    data = await file.read()

    # 8 MB limit (same guardrails as before)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 8MB).")

    try:
        resume_text, _pages = ocr_bytes(
            file_bytes=data,
            filename=file.filename or "",
            content_type=file.content_type,
            max_pages=4,
        )
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    try:
        gap = analyze_skill_gap(
            resume_text=resume_text,
            job_title=job["title"],
            job_description=job["description"],
        )

        # 1) semantic course lookup from missing skills
        course_pack = recommend_courses_from_missing_skills(gap.get("missing_skills", []), top_k=10)
        courses = course_pack.get("courses", [])

        # 2) career assistant draft using gap + courses
        draft = career_suggest(
            gap=gap,
            job_title=job["title"],
            job_skills=gap.get("job_skills", []),
            courses=courses,
        )

        # 3) critique verifier (approve or revise)
        critique = critique_review(
            gap=gap,
            job_title=job["title"],
            job_description=job["description"],
            courses=courses,
            draft=draft,
        )

        final_response = critique.get("final_response", draft)
        verdict = critique.get("verdict", "revise")


        return {
            "job_id": job_id,
            "job_title": job["title"],
            "resume_chars": len(resume_text),
            "resume_text_preview": resume_text[:300],
            "gap": gap,
            "courses": courses,
            "career_draft": draft,
            "verdict": verdict,
            "final_recommendation": final_response,
            "issues_found": critique.get("issues_found", []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM failed: {e}")
