from fastapi import APIRouter, File, UploadFile, HTTPException
from server.db import db
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

        # Insert application record into DB
        conn = db()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications (user_id, job_id, resume_filename, status, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING application_id;
                """,
                (user_id, job_id, file_path, 'pending', datetime.now())
            )
            application_id = cur.fetchone()[0]

        return {"ok": True, "application_id": application_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
