from fastapi import APIRouter, File, UploadFile, HTTPException
# from server.db import db
from server.csv_store import load_csv, append_row, safe_int, find_by_id
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
