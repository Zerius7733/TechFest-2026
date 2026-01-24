import os
import psycopg
from typing import Dict


def get_job_by_id(job_id: int) -> Dict[str, str]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    sql = """
    SELECT title, COALESCE(description, '') as description
    FROM jobs
    WHERE id = %s
    LIMIT 1;
    """

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [job_id])
            row = cur.fetchone()

    if not row:
        raise KeyError(f"Job not found: {job_id}")

    return {"title": row[0] or "", "description": row[1] or ""}
