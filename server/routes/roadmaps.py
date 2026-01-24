from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from server.db import db
from server.routes.auth import require_user_id

router = APIRouter(prefix="/api/roadmaps", tags=["roadmaps"])


class RoadmapUpsert(BaseModel):
    job_id: Optional[int] = None  # jobs.id is bigint; Python int is fine
    company: Optional[str] = None
    role: Optional[str] = None
    payload: Any  # JSON


@router.get("/me")
def list_my_roadmaps(user_id: int = Depends(require_user_id)):
    conn = db()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, job_id, company, role, payload, created_at, updated_at
            FROM roadmaps
            WHERE user_id = %s
            ORDER BY updated_at DESC, created_at DESC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "user_id": r[1],
                "job_id": r[2],
                "company": r[3],
                "role": r[4],
                "payload": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "updated_at": r[7].isoformat() if r[7] else None,
            }
        )
    return out


@router.post("")
def upsert_my_roadmap(body: RoadmapUpsert, user_id: int = Depends(require_user_id)):
    if body.payload is None:
        raise HTTPException(status_code=400, detail="payload is required")

    conn = db()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO roadmaps (user_id, job_id, company, role, payload, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, now(), now())
            ON CONFLICT (user_id, job_id)
            DO UPDATE SET
              company = EXCLUDED.company,
              role = EXCLUDED.role,
              payload = EXCLUDED.payload,
              updated_at = now()
            RETURNING id;
            """,
            (user_id, body.job_id, body.company, body.role, body.payload),
        )
        new_id = cur.fetchone()[0]

    return {"ok": True, "id": new_id}
