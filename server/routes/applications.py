from fastapi import APIRouter, File, UploadFile, HTTPException, Header
# from server.db import db
from server.csv_store import load_csv, append_row, safe_int, find_by_id
from server.routes.auth import require_user_id
from datetime import datetime
import os

router = APIRouter(prefix="/api/applications", tags=["applications"])

@router.post("/apply")
async def apply_for_job(job_id: int, user_id: int, resume: UploadFile = File(...)):
    # Save resume file to a location or DB
    upload_dir = "uploads"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{resume.filename}"
    file_path = os.path.join(upload_dir, filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await resume.read())

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
