from fastapi import APIRouter, File, UploadFile, HTTPException, Header
# from server.db import db
from server.csv_store import load_csv, append_row, safe_int, find_by_id, write_csv
from server.routes.auth import require_user_id
from datetime import datetime
import os

router = APIRouter(prefix="/api/applications", tags=["applications"])

RESUMES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "resumes")
)


def _cleanup_user_resumes(user_id: int, keep_filename: str | None = None) -> int:
    if not os.path.isdir(RESUMES_DIR):
        return 0
    prefix = f"{user_id}_"
    removed = 0
    for name in os.listdir(RESUMES_DIR):
        if not name.startswith(prefix):
            continue
        if keep_filename and name == keep_filename:
            continue
        full = os.path.join(RESUMES_DIR, name)
        try:
            if os.path.isfile(full):
                os.remove(full)
                removed += 1
        except OSError:
            continue
    return removed


@router.post("/apply")
async def apply_for_job(
    job_id: int,
    user_id: int | None = None,
    resume: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    auth_user_id = require_user_id(authorization)
    if user_id is not None and safe_int(user_id) != safe_int(auth_user_id):
        raise HTTPException(status_code=403, detail="user_id does not match token")
    user_id = auth_user_id

    try:
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

        _cleanup_user_resumes(user_id)
        os.makedirs(RESUMES_DIR, exist_ok=True)
        original_name = os.path.basename(resume.filename or "resume.pdf")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        stored_name = f"{user_id}_{ts}_{original_name}"
        file_path = os.path.join(RESUMES_DIR, stored_name)
        with open(file_path, "wb") as f:
            f.write(data)

        target["resume_path"] = os.path.join("resumes", stored_name)
        target["resume_name"] = original_name
        target["resume_uploaded_at"] = datetime.utcnow().isoformat()
        fieldnames = list(profiles[0].keys()) if profiles else [
            "user_id",
            "university",
            "major",
            "avatar_url",
            "created_at",
            "resume_path",
            "resume_name",
            "resume_uploaded_at",
        ]
        for extra in ["resume_path", "resume_name", "resume_uploaded_at"]:
            if extra not in fieldnames:
                fieldnames.append(extra)
        write_csv("student_profiles", profiles, fieldnames=fieldnames)

        # DB disabled: append to CSV instead.
        rows = load_csv("applications")
        job = find_by_id(load_csv("jobs"), "id", job_id)
        company_id = job.get("company_id") if job else ""
        for r in rows:
            if safe_int(r.get("student_id")) == safe_int(user_id) and safe_int(r.get("job_id")) == safe_int(job_id):
                raise HTTPException(status_code=409, detail="Duplicate application")
        next_id = max([safe_int(r.get("id")) or 0 for r in rows], default=0) + 1
        append_row(
            "applications",
            {
                "id": str(next_id),
                "student_id": str(user_id),
                "job_id": str(job_id),
                "company_id": str(company_id) if company_id is not None else "",
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            },
        )

        return {"ok": True, "application_id": next_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{application_id}/resume")
def get_application_resume(application_id: int, authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    company_profiles = load_csv("company_profiles")
    companies = load_csv("companies")

    profile = None
    for p in company_profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            profile = p
            break

    if not profile:
        raise HTTPException(status_code=403, detail="Company profile not found")

    company_id = safe_int(profile.get("company_id"))
    if company_id is None or not find_by_id(companies, "id", company_id):
        raise HTTPException(status_code=403, detail="Company not found")

    applications = load_csv("applications")
    app = None
    for a in applications:
        if safe_int(a.get("id")) == safe_int(application_id):
            app = a
            break

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if safe_int(app.get("company_id")) != safe_int(company_id):
        raise HTTPException(status_code=403, detail="Not allowed for this application")

    student_id = safe_int(app.get("student_id"))
    profiles = load_csv("student_profiles")
    target = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(student_id):
            target = p
            break

    if not target:
        raise HTTPException(status_code=404, detail="Student profile not found")

    resume_path = (target.get("resume_path") or "").strip()
    resume_name = (target.get("resume_name") or "").strip()
    resume_uploaded_at = (target.get("resume_uploaded_at") or "").strip()
    if not resume_path:
        raise HTTPException(status_code=404, detail="No resume on file")

    clean_path = resume_path.replace("\\", "/")
    return {
        "file_url": f"/uploads/{clean_path}",
        "resume_name": resume_name,
        "resume_uploaded_at": resume_uploaded_at,
    }
