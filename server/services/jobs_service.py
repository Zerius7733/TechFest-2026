import os
# import psycopg
from typing import Dict
from server.csv_store import load_csv, find_by_id


def get_job_by_id(job_id: int) -> Dict[str, str]:
    # DB disabled. Previous query:
    # SELECT title, COALESCE(description, '') as description FROM jobs WHERE id = %s LIMIT 1;
    row = find_by_id(load_csv("jobs"), "id", job_id)
    if not row:
        raise KeyError(f"Job not found: {job_id}")

    return {
        "title": row.get("title") or "",
        "description": row.get("description") or "",
        "company": row.get("company") or "",
    }

