import os
from pathlib import Path
import psycopg
from server.db import db

OUT_DIR = Path("csv-db")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """)
            tables = [r[0] for r in cur.fetchall()]

        for t in tables:
            out_path = OUT_DIR / f"{t}.csv"
            with conn.cursor() as cur:
                copy_sql = f"COPY public.{t} TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
                with out_path.open("w", newline="", encoding="utf-8") as f:
                    with cur.copy(copy_sql) as copy:
                        for data in copy:
                            f.write(bytes(data).decode("utf-8"))


            print(f"Exported: {t} -> {out_path}")

if __name__ == "__main__":
    main()
