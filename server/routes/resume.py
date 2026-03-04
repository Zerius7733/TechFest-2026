from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form, Header
from pydantic import BaseModel
from datetime import datetime
import os

from server.services.skill_gap_service import analyze_skill_gap
from server.services.ocr_service import ocr_bytes
from server.services.jobs_service import get_job_by_id
from server.services.career_suggest_service import career_suggest
from server.services.critique_service import critique_review
from server.services.resume_optimize_service import optimize_resume
from server.csv_store import load_csv, write_csv, safe_int
from server.routes.auth import require_user_id
import mimetypes

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
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None)
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

    resume_saved = False
    resume_file_url = None
    resume_filename = None
    if authorization:
        user_id = require_user_id(authorization)
        original_name = os.path.basename(file.filename or "resume.pdf")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "resumes"))
        os.makedirs(upload_dir, exist_ok=True)
        stored_name = f"{user_id}_{ts}_{original_name}"
        #stored_name = f"{user_id}_{original_name}"
        file_path = os.path.join(upload_dir, stored_name)
        with open(file_path, "wb") as f:
            f.write(data)

        profiles = load_csv("student_profiles")
        target = None
        for p in profiles:
            if safe_int(p.get("user_id")) == safe_int(user_id):
                target = p
                break

        if target is not None:
            target["resume_path"] = os.path.join("resumes", stored_name)
            target["resume_name"] = original_name
            target["resume_uploaded_at"] = datetime.utcnow().isoformat()
            fieldnames = list(profiles[0].keys())
            for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
                if extra not in fieldnames:
                    fieldnames.append(extra)
            write_csv("student_profiles", profiles, fieldnames=fieldnames)
            resume_saved = True
            resume_filename = original_name
            resume_file_url = f"/uploads/resumes/{stored_name}"

    return _process_resume_for_job(
        job=job,
        job_id=job_id,
        data=data,
        filename=file.filename or "",
        content_type=file.content_type,
        resume_saved=resume_saved,
        resume_filename=resume_filename,
        resume_file_url=resume_file_url,
    )


@router.get("/me")
def get_my_resume(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    profiles = load_csv("student_profiles")
    target = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            target = p
            break

    if not target:
        raise HTTPException(status_code=404, detail="Student profile not found")

    resume_path = (target.get("resume_path") or "").strip()
    resume_name = (target.get("resume_name") or "").strip()
    resume_uploaded_at = (target.get("resume_uploaded_at") or "").strip()

    uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "resumes"))
    if not resume_path:
        return {"has_resume": False}

    abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", resume_path))
    if not os.path.exists(abs_path):
        # Fallback: find the most recent file for this user
        latest_path = None
        latest_mtime = None
        if os.path.isdir(uploads_dir):
            prefix = f"{user_id}_"
            for name in os.listdir(uploads_dir):
                if not name.startswith(prefix):
                    continue
                full = os.path.join(uploads_dir, name)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_path = full

        if latest_path:
            resume_path = os.path.join("resumes", os.path.basename(latest_path))
            target["resume_path"] = resume_path
            if not resume_name:
                resume_name = os.path.basename(latest_path)
                target["resume_name"] = resume_name
            if not resume_uploaded_at:
                resume_uploaded_at = datetime.utcnow().isoformat()
                target["resume_uploaded_at"] = resume_uploaded_at
            fieldnames = list(profiles[0].keys())
            for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
                if extra not in fieldnames:
                    fieldnames.append(extra)
            write_csv("student_profiles", profiles, fieldnames=fieldnames)
        else:
            return {"has_resume": False}

    clean_path = resume_path.replace("\\", "/")
    file_url = f"/uploads/{clean_path}"
    return {
        "has_resume": True,
        "resume_name": resume_name,
        "resume_uploaded_at": resume_uploaded_at,
        "file_url": file_url,
    }


@router.post("/upload")
async def upload_resume(resume: UploadFile = File(...), authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)
    if not resume:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    data = await resume.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 8MB).")

    profiles = load_csv("student_profiles")
    target = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            target = p
            break

    if not target:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Remove old resume if present
    old_path = (target.get("resume_path") or "").strip()
    if old_path:
        abs_old = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", old_path))
        try:
            if os.path.exists(abs_old):
                os.remove(abs_old)
        except OSError:
            pass

    original_name = os.path.basename(resume.filename or "resume.pdf")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "resumes"))
    os.makedirs(upload_dir, exist_ok=True)
    stored_name = f"{user_id}_{ts}_{original_name}"
    file_path = os.path.join(upload_dir, stored_name)
    with open(file_path, "wb") as f:
        f.write(data)

    target["resume_path"] = os.path.join("resumes", stored_name)
    target["resume_name"] = original_name
    target["resume_uploaded_at"] = datetime.utcnow().isoformat()
    fieldnames = list(profiles[0].keys())
    for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
        if extra not in fieldnames:
            fieldnames.append(extra)
    write_csv("student_profiles", profiles, fieldnames=fieldnames)

    return {
        "ok": True,
        "resume_name": original_name,
        "resume_uploaded_at": target["resume_uploaded_at"],
        "file_url": f"/uploads/resumes/{stored_name}",
    }


@router.delete("/me")
def delete_my_resume(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    profiles = load_csv("student_profiles")
    target = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            target = p
            break

    if not target:
        raise HTTPException(status_code=404, detail="Student profile not found")

    resume_path = (target.get("resume_path") or "").strip()
    removed = False
    if resume_path:
        abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", resume_path))
        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
                removed = True
        except OSError:
            pass

    target["resume_path"] = ""
    target["resume_name"] = ""
    target["resume_uploaded_at"] = ""
    fieldnames = list(profiles[0].keys())
    for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
        if extra not in fieldnames:
            fieldnames.append(extra)
    write_csv("student_profiles", profiles, fieldnames=fieldnames)

    return {"ok": True, "removed": removed}


@router.post("/ocr-skill-gap-existing")
async def ocr_skill_gap_existing(
    job_id: int = Query(..., description="jobs.id (primary key)"),
    authorization: str | None = Header(default=None),
):
    user_id = require_user_id(authorization)

    profiles = load_csv("student_profiles")
    target = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            target = p
            break

    if not target:
        raise HTTPException(status_code=404, detail="Student profile not found")

    resume_path = (target.get("resume_path") or "").strip()
    resume_name = (target.get("resume_name") or "").strip()
    if not resume_path:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "resumes"))
    abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", resume_path))
    if not os.path.exists(abs_path):
        # Fallback: find the most recent file for this user
        latest_path = None
        latest_mtime = None
        if os.path.isdir(uploads_dir):
            prefix = f"{user_id}_"
            for name in os.listdir(uploads_dir):
                if not name.startswith(prefix):
                    continue
                full = os.path.join(uploads_dir, name)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_path = full

        if latest_path:
            resume_path = os.path.join("resumes", os.path.basename(latest_path))
            abs_path = latest_path
            target["resume_path"] = resume_path
            if not resume_name:
                resume_name = os.path.basename(latest_path)
                target["resume_name"] = resume_name
            if not target.get("resume_uploaded_at"):
                target["resume_uploaded_at"] = datetime.utcnow().isoformat()
            fieldnames = list(profiles[0].keys())
            for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
                if extra not in fieldnames:
                    fieldnames.append(extra)
            write_csv("student_profiles", profiles, fieldnames=fieldnames)
        else:
            raise HTTPException(status_code=404, detail="Resume file not found on server")

    try:
        with open(abs_path, "rb") as f:
            data = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read resume file: {e}")

    try:
        job = get_job_by_id(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    guessed_type, _ = mimetypes.guess_type(abs_path)
    clean_path = resume_path.replace("\\", "/")
    return _process_resume_for_job(
        job=job,
        job_id=job_id,
        data=data,
        filename=resume_name or os.path.basename(abs_path),
        content_type=guessed_type,
        resume_saved=True,
        resume_filename=resume_name or os.path.basename(abs_path),
        resume_file_url=f"/uploads/{clean_path}",
    )


def _process_resume_for_job(
    *,
    job: dict,
    job_id: int,
    data: bytes,
    filename: str,
    content_type: str | None,
    resume_saved: bool,
    resume_filename: str | None,
    resume_file_url: str | None,
) -> dict:
    try:
        resume_text, _pages = ocr_bytes(
            file_bytes=data,
            filename=filename or "",
            content_type=content_type,
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
            "company": job.get("company") or "",
            "resume_chars": len(resume_text),
            "resume_text_preview": resume_text[:300],
            "resume_saved": resume_saved,
            "resume_filename": resume_filename,
            "resume_file_url": resume_file_url,
            "gap": gap,
            "courses": courses,
            "career_draft": draft,
            "verdict": verdict,
            "final_recommendation": final_response,
            "issues_found": critique.get("issues_found", []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM failed: {e}")
