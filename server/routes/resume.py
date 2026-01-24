from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from server.services.skill_gap_service import analyze_skill_gap
from server.services.ocr_service import ocr_bytes
from server.services.jobs_service import get_job_by_id

router = APIRouter(prefix="/api/resume", tags=["resume"])


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

        return {
            "job_id": job_id,
            "job_title": job["title"],
            "resume_chars": len(resume_text),
            "resume_text_preview": resume_text[:300],
            "gap": gap,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM failed: {e}")
