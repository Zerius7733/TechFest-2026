import re

HEADINGS = [
    "overview",
    "description",
    "responsibilities",
    "primary responsibilities",
    "requirements",
    "qualifications",
    "competencies",
    "skills",
    "about you",
    "about the role",
    "what you will do",
    "what you'll do",
    "who you are",
]

BOILERPLATE_PATTERNS = [
    r"\b(equal opportunity employer|eeo|e\.e\.o\.)\b.*$",  # EOE tail
    r"for more information on .*?,\s*click here\.?$",
]

def clean_description(raw: str) -> str:
    if not raw:
        return ""

    t = raw

    # Normalize whitespace
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    # Insert paragraph breaks before headings (case-insensitive)
    for h in sorted(HEADINGS, key=len, reverse=True):
        pattern = rf"(?i)\b({re.escape(h)})\b\s*:?"
        t = re.sub(pattern, lambda m: f"\n\n{m.group(1).upper()}:\n", t)

    # Fix common "HEADING text" run-ons (e.g. "RESPONSIBILITIES Mentor and lead ...")
    t = re.sub(r"(?m)(^[A-Z][A-Z /&]{3,}:\s*)([A-Z][a-z])", r"\1\n\2", t)

    # Bulletize lists when you see lots of "X. Y. Z." or many sentence fragments
    # Heuristic: split after ". " when the next token starts with a capital letter and the line is long
    lines = []
    for block in t.split("\n\n"):
        b = block.strip()
        if len(b) > 500 and ". " in b:
            parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", b)
            # If it looks like a list (many short-ish items), bullet it
            if len(parts) >= 6 and sum(len(p) < 160 for p in parts) >= 4:
                b = "\n".join([f"• {p.strip()}" for p in parts if p.strip()])
        lines.append(b)

    t = "\n\n".join(lines)

    # Remove boilerplate tails (do this near the end so formatting is stable)
    for pat in BOILERPLATE_PATTERNS:
        t = re.sub(pat, "", t, flags=re.I | re.S).strip()

    # Final cleanup
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


import os
import psycopg,dotenv,pathlib   
from dotenv import load_dotenv
ENV_PATH = pathlib.Path(__file__).resolve().parents[1] / "job-db" / ".env"
load_dotenv(dotenv_path=ENV_PATH)
DATABASE_URL = os.getenv("DATABASE_URL")  # set this to your Railway URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

def main():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, COALESCE(description,'') FROM jobs;")
            rows = cur.fetchall()

        with conn.cursor() as cur:
            for job_id, desc in rows:
                cleaned = clean_description(desc)
                cur.execute(
                    "UPDATE jobs SET description_clean = %s WHERE id = %s;",
                    (cleaned, job_id),
                )

        conn.commit()

if __name__ == "__main__":
    main()
