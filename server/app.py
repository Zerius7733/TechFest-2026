import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException
# import psycopg
from fastapi import UploadFile, File, HTTPException
from pydantic import BaseModel
from server.services.ocr_service import ocr_bytes
from server.routes.resume import router as resume_router
from server.routes.auth import router as auth_router
from server.routes.roadmaps import router as roadmaps_router
from server.routes.applications import router as applications_router
# from server.db import db
from server.csv_store import load_csv, find_by_id, safe_int, parse_datetime,write_csv, append_row
from typing import List, Dict, Optional, Any, Iterable
from pathlib import Path



# ENV_PATH = Path(__file__).resolve().parents[1] / "job-db" / ".env"
# Load root .env first (LLM, app-level config)
load_dotenv()

# Load job-db .env second (DB config)
# load_dotenv(dotenv_path=ENV_PATH, override=True)


# DATABASE_URL = os.getenv("DATABASE_URL")
# if not DATABASE_URL:
#     raise RuntimeError("DATABASE_URL not set in job-db/.env")

app = FastAPI()

app.include_router(resume_router)
app.include_router(auth_router)
app.include_router(roadmaps_router)
app.include_router(applications_router)

from server.routes.auth import require_user_id


@app.get("/api/student_profiles/me")
def get_my_student_profile(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    # DB disabled: read from CSV instead.
    users = load_csv("users")
    profiles = load_csv("student_profiles")
    user = find_by_id(users, "id", user_id)
    profile = None
    for p in profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            profile = p
            break

    if not user or not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")

    return {
        "userId": safe_int(user.get("id")),
        "name": user.get("name").title() or "",
        "email": user.get("email") or "",
        "university": profile.get("university") or "",
        "major": profile.get("major") or "",
        "avatarUrl": profile.get("avatar_url") or "",
    }


@app.get("/api/company_profiles/me")
def get_my_company_profile(authorization: str | None = Header(default=None)):
    user_id = require_user_id(authorization)

    users = load_csv("users")
    company_profiles = load_csv("company_profiles")
    companies = load_csv("companies")

    user = find_by_id(users, "id", user_id)
    profile = None
    for p in company_profiles:
        if safe_int(p.get("user_id")) == safe_int(user_id):
            profile = p
            break

    if not user or not profile:
        raise HTTPException(status_code=404, detail="Company profile not found")

    company_id = safe_int(profile.get("company_id"))
    company = find_by_id(companies, "id", company_id) if company_id is not None else None

    return {
        "userId": safe_int(user.get("id")),
        "name": user.get("name") or "",
        "email": user.get("email") or "",
        "companyId": company_id,
        "companyName": (company.get("name") if company else "") or "",
        "title": "Employer Admin",
    }


from fastapi import Header
from server.routes.auth import require_user_id


@app.post("/api/resume/ocr")
async def resume_ocr(file: UploadFile = File(...)):
    # basic guardrails
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    data = await file.read()

    # 8 MB limit (adjust if you want)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 8MB).")

    try:
        text, pages = ocr_bytes(
            file_bytes=data,
            filename=file.filename or "",
            content_type=file.content_type,
            max_pages=4,
        )
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    # Return both full text + per-page (useful later for debugging / chunking)
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "chars": len(text),
        "text": text,
        "pages": pages,
    }


# Serve your frontend folder
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Ascent"))
UPLOADS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(UPLOADS_DIR, exist_ok=True)
print ("debug: FRONTEND_DIR path is:")
print(FRONTEND_DIR)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "landing.html"))


@app.get("/results")
def results_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "results.html"))


@app.get("/optimize")
def optimize_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "optimize.html"))


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    filter: str | None = None,
    limit: int = 20,
    offset: int = 0
):
    """
    CSV search: simple substring match on title/company/description.
    """
    # DB disabled. Previous query used search_tsv + ILIKE + ORDER BY posted_days/id.
    q = q.strip()

    q_lc = q.lower()
    rows = load_csv("jobs")
    filtered = []
    for r in rows:
        title = (r.get("title") or "").lower()
        company = (r.get("company") or "").lower()
        desc = (r.get("description_clean") or r.get("description") or "").lower()
        if q_lc not in title and q_lc not in company and q_lc not in desc:
            continue
        if filter == "internship" and (r.get("employment_norm") or "") != "internship":
            continue
        if filter == "full-time" and (r.get("employment_norm") or "") != "full_time":
            continue
        if filter == "remote" and (r.get("work_mode_norm") or "") != "remote":
            continue
        filtered.append(r)

    def _sort_key(row):
        posted_days = safe_int(row.get("posted_days"))
        job_id = safe_int(row.get("id")) or 0
        return (posted_days is None, posted_days or 0, -job_id)

    filtered.sort(key=_sort_key)
    page = filtered[offset:offset + limit]

    results = []
    for r in page:
        results.append({
            "id": safe_int(r.get("id")),
            "source": r.get("source"),
            "title": r.get("title"),
            "company": r.get("company"),
            "location": r.get("location"),
            "employment_type": r.get("employment_type"),
            "salary": r.get("salary"),
            "url": r.get("url"),
            "description": r.get("description_clean") or r.get("description") or "",
        })

    return {"query": q, "count": len(results), "results": results}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    # DB disabled. Previous query selected by jobs.id.
    row = find_by_id(load_csv("jobs"), "id", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": safe_int(row.get("id")),
        "source": row.get("source"),
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "employment_type": row.get("employment_type"),
        "salary": row.get("salary"),
        "url": row.get("url"),
        "description": row.get("description_clean") or row.get("description") or "",
    }


@app.get("/api/applications/student/{student_id}")
def get_applications_for_student(student_id: int):
    # DB disabled. Previous query joined applications/companies/jobs by student_id.
    applications = load_csv("applications")
    companies = load_csv("companies")
    jobs = load_csv("jobs")

    companies_by_id = {safe_int(c.get("id")): c for c in companies}
    jobs_by_id = {safe_int(j.get("id")): j for j in jobs}

    rows = []
    for a in applications:
        if safe_int(a.get("student_id")) != safe_int(student_id):
            continue
        rows.append(a)

    def _app_sort_key(row):
        created = parse_datetime(row.get("created_at"))
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        app_id = safe_int(row.get("id")) or 0
        return (created is None, created or datetime.min, -app_id)

    rows.sort(key=_app_sort_key, reverse=True)
    rows = rows[:100]

    out = []
    for r in rows:
        company = companies_by_id.get(safe_int(r.get("company_id"))) or {}
        job = jobs_by_id.get(safe_int(r.get("job_id"))) or {}
        created = parse_datetime(r.get("created_at"))
        out.append(
            {
                "application_id": safe_int(r.get("id")),
                "company": (company.get("name") or "—"),
                "role": (job.get("title") or "—"),
                "status": (r.get("status") or "pending"),
                "created_at": created.isoformat() if created else None,
            }
        )
    return out


@app.get("/api/applications/company/{company_id}")
def get_company_applications(company_id: int):
    # DB disabled. Previous query joined applications/jobs/users by company_id.
    applications = load_csv("applications")
    jobs = load_csv("jobs")
    users = load_csv("users")

    jobs_by_id = {safe_int(j.get("id")): j for j in jobs}
    users_by_id = {safe_int(u.get("id")): u for u in users}

    rows = []
    for a in applications:
        if safe_int(a.get("company_id")) != safe_int(company_id):
            continue
        rows.append(a)

    def _app_sort_key(row):
        created = parse_datetime(row.get("created_at"))
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        app_id = safe_int(row.get("id")) or 0
        return (created is None, created or datetime.min, -app_id)

    rows.sort(key=_app_sort_key, reverse=True)

    out = []
    for r in rows:
        job = jobs_by_id.get(safe_int(r.get("job_id"))) or {}
        user = users_by_id.get(safe_int(r.get("student_id"))) or {}
        created = parse_datetime(r.get("created_at"))
        out.append(
            {
                "application_id": safe_int(r.get("id")),
                "status": r.get("status") or "pending",
                "created_at": created.isoformat() if created else None,
                "student_id": safe_int(r.get("student_id")),
                "student_name": user.get("name").title(),
                "student_email": user.get("email"),
                "job_id": safe_int(job.get("id")),
                "role": job.get("title"),
            }
        )
    return out


class ApplicationStatusUpdate(BaseModel):
    status: str


@app.patch("/api/applications/{application_id}/status")
def update_application_status(application_id: int, payload: ApplicationStatusUpdate, authorization: str | None = Header(default=None)):
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
    target = None
    for a in applications:
        if safe_int(a.get("id")) == safe_int(application_id):
            target = a
            break

    if not target:
        raise HTTPException(status_code=404, detail="Application not found")

    if safe_int(target.get("company_id")) != safe_int(company_id):
        raise HTTPException(status_code=403, detail="Not allowed for this application")

    status = (payload.status or "").strip().lower()
    if status not in {"pending", "offer", "reject", "interview"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    target["status"] = status
    fieldnames = list(applications[0].keys()) if applications else ["id", "student_id", "job_id", "company_id", "status", "created_at"]
    write_csv("applications", applications, fieldnames=fieldnames)

    return {"ok": True, "application_id": safe_int(application_id), "status": status}


@app.get("/job")
def job_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "details.html"))


@app.get("/apply")
def apply_page():
    return FileResponse(
        os.path.join(FRONTEND_DIR, "apply.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


@app.get("/roadmap")
def roadmap_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "roadmap.html"))


@app.get("/student_profile")
def student_profile_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "student_profile.html"))


@app.get("/employer_profile")
def employer_profile_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "employer_profile.html"))
