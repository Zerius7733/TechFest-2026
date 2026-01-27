from __future__ import annotations

import os
import hashlib
from typing import List, Dict, Any, Tuple

import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer


# Paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSV_PATH = os.path.join(REPO_ROOT, "dataset_gov", "MySkillsFutureCourseDirectory_v2.csv")
PERSIST_DIR = os.path.join(REPO_ROOT, "server", "data", "chroma_courses")
COLLECTION_NAME = "skillsfuture_courses"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 128
MODEL_ENV_VAR = "SENTENCE_TRANSFORMER_MODEL"
LOCAL_ONLY_ENV_VAR = "SENTENCE_TRANSFORMER_LOCAL_ONLY"


def _get_model_name() -> str:
    return os.getenv(MODEL_ENV_VAR, MODEL_NAME)


def _get_model() -> SentenceTransformer:
    """
    Load embedding model, with a local-only fallback for offline setups.
    """
    model_name = _get_model_name()
    local_only = os.getenv(LOCAL_ONLY_ENV_VAR, "").strip() == "1" or os.getenv("HF_HUB_OFFLINE", "").strip() == "1"
    try:
        return SentenceTransformer(model_name, local_files_only=local_only)
    except Exception as e:
        if not local_only:
            # If download fails (DNS/offline), retry using cached files only.
            try:
                return SentenceTransformer(model_name, local_files_only=True)
            except Exception:
                pass
        raise RuntimeError(
            f"Embedding model unavailable: {model_name}. "
            f"Set {MODEL_ENV_VAR} to a local path or pre-download the model, "
            f"or set {LOCAL_ONLY_ENV_VAR}=1 to force local-only mode."
        ) from e


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_dirs() -> None:
    os.makedirs(PERSIST_DIR, exist_ok=True)


def _make_course_text(row: Dict[str, Any]) -> str:
    # Semantic text we embed per course row
    title = str(row.get("coursetitle", "")).strip()
    about = str(row.get("about_this_course", "")).strip()
    learn = str(row.get("what_you_learn", "")).strip()
    provider = str(row.get("trainingprovideralias", "")).strip()

    parts = []
    if title:
        parts.append(f"Course Title: {title}")
    if provider:
        parts.append(f"Provider: {provider}")
    if about:
        parts.append(f"About: {about}")
    if learn:
        parts.append(f"What you learn: {learn}")
    return "\n".join(parts).strip()


def _load_courses_df() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Course CSV not found at: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    # Keep only known columns (based on your header list)
    needed_cols = [
        "coursereferencenumber",
        "coursetitle",
        "trainingprovideruen",
        "trainingprovideralias",
        "full_course_fee",
        "course_fee_after_subsidies",
        "number_of_hours",
        "about_this_course",
        "what_you_learn",
    ]
    for c in needed_cols:
        if c not in df.columns:
            raise ValueError(f"Missing expected column in CSV: {c}")

    return df[needed_cols].fillna("")


def _get_client() -> chromadb.PersistentClient:
    _ensure_dirs()
    return chromadb.PersistentClient(
        path=PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )


def get_collection():
    client = _get_client()
    return client.get_or_create_collection(name=COLLECTION_NAME)


def build_index(force_rebuild: bool = False) -> Dict[str, Any]:
    """
    Build the Chroma collection if it's empty OR if force_rebuild is True.
    Stores CSV hash in collection metadata so we can detect changes.
    """
    df = _load_courses_df()
    csv_hash = _sha256_file(CSV_PATH)

    col = get_collection()

    # If already built and CSV unchanged, skip
    meta = col.metadata or {}
    existing_hash = meta.get("csv_sha256")
    existing_count = col.count()

    if (not force_rebuild) and existing_count > 0 and existing_hash == csv_hash:
        return {
            "status": "ok",
            "action": "skipped",
            "reason": "index exists and CSV hash unchanged",
            "count": existing_count,
            "csv_sha256": existing_hash,
            "persist_dir": PERSIST_DIR,
            "collection": COLLECTION_NAME,
        }

    # Rebuild: delete + recreate
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    model_name = _get_model_name()
    col = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"csv_sha256": csv_hash, "model": model_name},
    )

    model = _get_model()

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []

    seen_ids: dict[str, int] = {}

    for _, r in df.iterrows():
        row = r.to_dict()
        base_id = str(row["coursereferencenumber"]).strip()
        if not base_id:
            continue

        # Ensure unique IDs for Chroma (CSV can contain duplicate reference numbers)
        n = seen_ids.get(base_id, 0)
        seen_ids[base_id] = n + 1
        course_id = base_id if n == 0 else f"{base_id}#{n}"


        text = _make_course_text(row)
        if not text:
            continue

        ids.append(course_id)
        docs.append(text)
        metas.append(
            {
                "coursereferencenumber": course_id,
                "coursetitle": str(row["coursetitle"]).strip(),
                "trainingprovideralias": str(row["trainingprovideralias"]).strip(),
                "trainingprovideruen": str(row["trainingprovideruen"]).strip(),
                "full_course_fee": str(row["full_course_fee"]).strip(),
                "course_fee_after_subsidies": str(row["course_fee_after_subsidies"]).strip(),
                "number_of_hours": str(row["number_of_hours"]).strip(),
            }
        )

    # Embed + add in batches
    for i in range(0, len(docs), BATCH_SIZE):
        batch_docs = docs[i : i + BATCH_SIZE]
        batch_ids = ids[i : i + BATCH_SIZE]
        batch_metas = metas[i : i + BATCH_SIZE]

        embeddings = model.encode(batch_docs, normalize_embeddings=True).tolist()
        col.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas, embeddings=embeddings)

    return {
        "status": "ok",
        "action": "rebuilt",
        "count": col.count(),
        "csv_sha256": csv_hash,
        "persist_dir": PERSIST_DIR,
        "collection": COLLECTION_NAME,
        "model": MODEL_NAME,
    }


def query_courses(query_text: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """
    Query the Chroma index with semantic embeddings.
    Returns list of course metadata + distance score.
    """
    col = get_collection()
    if col.count() == 0:
        # build once automatically if missing
        build_index(force_rebuild=False)

    model = _get_model()
    q_emb = model.encode([query_text], normalize_embeddings=True).tolist()[0]

    res = col.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        include=["metadatas", "distances", "documents"],
    )
    metadatas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]
    documents = (res.get("documents") or [[]])[0]

    out: List[Dict[str, Any]] = []
    for m, d, doc in zip(metadatas, distances, documents):
        item = dict(m)
        item["distance"] = float(d)
        item["evidence"] = (doc or "")[:800]  # short snippet for prompting
        out.append(item)
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build/query SkillsFuture course Chroma index")
    parser.add_argument("cmd", choices=["build", "rebuild"])
    args = parser.parse_args()

    if args.cmd == "build":
        print(build_index(force_rebuild=False))
    elif args.cmd == "rebuild":
        print(build_index(force_rebuild=True))
