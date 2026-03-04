from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from pydantic import BaseModel
from typing import Any, Optional

# from server.db import db
from server.csv_store import load_csv, write_csv, safe_int, parse_datetime
import json
from server.routes.auth import require_user_id

router = APIRouter(prefix="/api/roadmaps", tags=["roadmaps"])


class RoadmapUpsert(BaseModel):
    job_id: Optional[int] = None  # jobs.id is bigint; Python int is fine
    company: Optional[str] = None
    role: Optional[str] = None
    payload: Any  # JSON


@router.get("/me")
def list_my_roadmaps(user_id: int = Depends(require_user_id)):
    # DB disabled. Previous query:
    # SELECT id, user_id, job_id, company, role, payload, created_at, updated_at FROM roadmaps WHERE user_id = %s;
    rows = load_csv("roadmaps")
    out = []
    for r in rows:
        if safe_int(r.get("user_id")) != safe_int(user_id):
            continue
        payload = r.get("payload")
        try:
            payload = json.loads(payload) if payload else None
        except (TypeError, json.JSONDecodeError):
            pass
        created = parse_datetime(r.get("created_at"))
        updated = parse_datetime(r.get("updated_at"))
        out.append(
            {
                "id": safe_int(r.get("id")),
                "user_id": safe_int(r.get("user_id")),
                "job_id": safe_int(r.get("job_id")) if r.get("job_id") else None,
                "company": r.get("company"),
                "role": r.get("role"),
                "payload": payload,
                "created_at": created.isoformat() if created else None,
                "updated_at": updated.isoformat() if updated else None,
            }
        )
    return out


@router.post("")
def upsert_my_roadmap(body: RoadmapUpsert, user_id: int = Depends(require_user_id)):
    if body.payload is None:
        raise HTTPException(status_code=400, detail="payload is required")

    # DB disabled. Previous query used INSERT ... ON CONFLICT.
    rows = load_csv("roadmaps")
    now = datetime.utcnow().isoformat()
    payload_value = body.payload
    if not isinstance(payload_value, str):
        payload_value = json.dumps(payload_value)

    target = None
    for r in rows:
        if safe_int(r.get("user_id")) == safe_int(user_id) and safe_int(r.get("job_id")) == safe_int(body.job_id):
            target = r
            break

    if target:
        target["company"] = body.company or ""
        target["role"] = body.role or ""
        target["payload"] = payload_value
        target["updated_at"] = now
        new_id = safe_int(target.get("id"))
    else:
        next_id = max([safe_int(r.get("id")) or 0 for r in rows], default=0) + 1
        new_id = next_id
        rows.append(
            {
                "id": str(new_id),
                "user_id": str(user_id),
                "job_id": str(body.job_id) if body.job_id is not None else "",
                "company": body.company or "",
                "role": body.role or "",
                "payload": payload_value,
                "created_at": now,
                "updated_at": now,
            }
        )

    fieldnames = ["id", "user_id", "job_id", "company", "role", "payload", "created_at", "updated_at"]
    write_csv("roadmaps", rows, fieldnames=fieldnames)
    return {"ok": True, "id": new_id}
