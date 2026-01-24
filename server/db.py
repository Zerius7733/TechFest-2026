import os
import psycopg
from dotenv import load_dotenv
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / "job-db" / ".env"

# Load envs once
load_dotenv()
load_dotenv(dotenv_path=ENV_PATH, override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

def db():
    return psycopg.connect(DATABASE_URL)
