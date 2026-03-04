import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CSV_DIR = Path(__file__).resolve().parents[1] / "csv-db"

_cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}


def _csv_path(name: str) -> Path:
    return CSV_DIR / f"{name}.csv"


def safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def load_csv(name: str) -> List[Dict[str, str]]:
    path = _csv_path(name)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    cached = _cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    rows = _read_csv(path)
    _cache[name] = (mtime, rows)
    return rows


def write_csv(name: str, rows: Iterable[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path = _csv_path(name)
    rows_list = [dict(r) for r in rows]
    if fieldnames is None:
        fieldnames = list(rows_list[0].keys()) if rows_list else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_list:
            writer.writerow(row)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    _cache[name] = (mtime, rows_list)


def append_row(name: str, row: Dict[str, Any]) -> None:
    rows = load_csv(name)
    fieldnames = list(rows[0].keys()) if rows else list(row.keys())
    rows.append(row)
    write_csv(name, rows, fieldnames)


def find_by_id(rows: Iterable[Dict[str, str]], key: str, value: Any) -> Optional[Dict[str, str]]:
    target = safe_int(value)
    for row in rows:
        if safe_int(row.get(key)) == target:
            return row
    return None
