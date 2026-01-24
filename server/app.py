import os
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import psycopg

from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / "job-db" / ".env"
load_dotenv(dotenv_path=ENV_PATH)


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in server/.env")

app = FastAPI()

# Serve your frontend folder
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Ascent"))
print ("debug: FRONTEND_DIR path is:")
print(FRONTEND_DIR)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "landing.html"))

@app.get("/results")
def results_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "results.html"))

@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    filter: str | None = None,
    limit: int = 20,
    offset: int = 0
):
    """
    Full-text search using jobs.search_tsv (from earlier SQL).
    Falls back to ILIKE if search_tsv isn't populated.
    """
    q = q.strip()

    sql = """
    SELECT
    id, source, title, company, location, employment_type, salary, url,
    COALESCE(description, '') as description
    FROM jobs
    WHERE
    (
        (search_tsv IS NOT NULL AND search_tsv @@ websearch_to_tsquery('english', %s))
        OR
        (search_tsv IS NULL AND (
        COALESCE(title,'') ILIKE %s OR
        COALESCE(company,'') ILIKE %s OR
        COALESCE(description,'') ILIKE %s
        ))
    )
    """

    like = f"%{q}%"

    filters_sql = ""
    params = [q, like, like, like]

    if filter == "internship":
        filters_sql += " AND employment_norm = 'internship'"
    elif filter == "full-time":
        filters_sql += " AND employment_norm = 'full_time'"
    elif filter == "remote":
        filters_sql += " AND work_mode_norm = 'remote'"

    order_sql = """
    ORDER BY
    CASE WHEN search_tsv IS NOT NULL THEN ts_rank(search_tsv, websearch_to_tsquery('english', %s)) END DESC NULLS LAST,
    posted_days ASC NULLS LAST,
    id DESC
    LIMIT %s OFFSET %s;
    """

    final_sql = sql + filters_sql + order_sql
    params += [q, limit, offset]


    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(final_sql, params)
            rows = cur.fetchall()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "source": r[1],
            "title": r[2],
            "company": r[3],
            "location": r[4],
            "employment_type": r[5],
            "salary": r[6],
            "url": r[7],
            "description": r[8],
        })

    return {"query": q, "count": len(results), "results": results}
