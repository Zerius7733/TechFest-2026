#reads TECHFEST-2026/dataset files and ingests into job-db Postgres database
import os
import json
import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
  raise RuntimeError("DATABASE_URL not set in job-db/.env")

# Your CSVs live in ../dataset relative to job-db/
DATASET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))

CSV_FILES = [
  ("efinancialcareers", os.path.join(DATASET_DIR, "efinancialcareers.csv")),
  ("glassdoor", os.path.join(DATASET_DIR, "glassdoor.csv")),
  ("indeed", os.path.join(DATASET_DIR, "indeed.csv")),
  ("jobstreet", os.path.join(DATASET_DIR, "jobstreet.csv")),
  ("mycareersfuture", os.path.join(DATASET_DIR, "mycareersfuture.csv")),
  ("prosple", os.path.join(DATASET_DIR, "prosple.csv")),
]

def pick_col(df, candidates):
  cols = {c.lower(): c for c in df.columns}
  for cand in candidates:
    if cand.lower() in cols:
      return cols[cand.lower()]
  return None

def norm(v):
  if v is None:
    return None
  if pd.isna(v):
    return None
  s = str(v).strip()
  return None if s == "" or s.lower() == "nan" else s

def main():
  with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
      for source, path in CSV_FILES:
        if not os.path.exists(path):
          print(f"Skip (missing): {path}")
          continue

        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]

        col_title = pick_col(df, ["title", "job_title", "position"])
        col_company = pick_col(df, ["company", "company_name", "employer"])
        col_location = pick_col(df, ["location", "job_location", "address"])
        col_salary = pick_col(df, ["salary", "pay", "salary_range"])
        col_url = pick_col(df, ["url", "link", "job_url"])
        col_desc = pick_col(df, ["description", "job_description", "desc", "summary"])
        col_job_id = pick_col(df, ["job_id", "id", "listing_id"])

        rows = []
        for _, r in df.iterrows():
          raw = {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}

          rows.append((
            source,
            os.path.basename(path),
            norm(raw.get(col_job_id)) if col_job_id else None,
            norm(raw.get(col_title)) if col_title else None,
            norm(raw.get(col_company)) if col_company else None,
            norm(raw.get(col_location)) if col_location else None,
            None,  # country
            None,  # employment_type
            norm(raw.get(col_salary)) if col_salary else None,
            norm(raw.get(col_url)) if col_url else None,
            norm(raw.get(col_desc)) if col_desc else None,
            None,  # posted_at
            json.dumps(raw, ensure_ascii=False, default=str),
          ))

        cur.executemany(
          """
          INSERT INTO jobs (
            source, source_file, job_id,
            title, company, location, country, employment_type, salary,
            url, description, posted_at, raw
          )
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
          """,
          rows
        )
        conn.commit()
        print(f"Inserted {len(rows)} rows from {os.path.basename(path)}")

if __name__ == "__main__":
  main()
