"""
generate_mappings.py
--------------------
Load all NK law names + categories from PostgreSQL (legalize_kp DB),
search the beopmang API for a matching SK law, score similarity with
difflib.SequenceMatcher, and write the results to
  E:/004_북한법/legalize-kp/compare/law_mappings.json

Usage:
    python scripts/generate_mappings.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import httpx
import asyncpg

# ---------------------------------------------------------------------------
# Make legalize-kp-api importable so we can reuse load_config
# ---------------------------------------------------------------------------
API_ROOT = Path("E:/004_북한법/legalize-kp-api")
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import load_config  # noqa: E402

CONFIG_PATH = str(API_ROOT / "config.yaml")

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
OUTPUT_PATH = Path("E:/004_북한법/legalize-kp/compare/law_mappings.json")

# ---------------------------------------------------------------------------
# 문화어 → 남한어 기본 치환 테이블
# ---------------------------------------------------------------------------
MUNHWA_MAP: list[tuple[str, str]] = [
    ("로동", "노동"),
    ("에네르기", "에너지"),
    ("쏘프트웨어", "소프트웨어"),
    ("콤퓨터", "컴퓨터"),
    ("뽐프", "펌프"),
    ("통신설비", "통신설비"),
    ("전기통신", "전기통신"),
    ("인민", "국민"),
    ("공화국", ""),
    ("조선민주주의", ""),
    ("사회주의", ""),
]

# 이름 끝에서 제거할 접미사 (순서 중요 – 긴 것 먼저)
SUFFIX_STRIP = ["시행규정", "시행세칙", "규정", "세칙", "규칙", "세부규정", "법", "령", "정"]


def normalize_name(name: str) -> str:
    """Apply 문화어→남한어 substitution and strip common suffixes."""
    result = name
    for munhwa, hangul in MUNHWA_MAP:
        result = result.replace(munhwa, hangul)

    # Strip known suffixes from the end
    for suffix in SUFFIX_STRIP:
        if result.endswith(suffix) and len(result) > len(suffix):
            result = result[: -len(suffix)]
            break  # strip only one suffix

    return result.strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def classify_confidence(score: float) -> str:
    if score > 0.6:
        return "high"
    if score > 0.3:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# beopmang API
# ---------------------------------------------------------------------------
BEOPMANG_BASE = "https://api.beopmang.org/api/v4"
SEARCH_URL = f"{BEOPMANG_BASE}/law"


def search_beopmang(client: httpx.Client, keyword: str) -> list[dict]:
    """
    GET /law?action=search&q={keyword}&mode=keyword
    Returns list of result items (may be empty).
    """
    try:
        resp = client.get(
            SEARCH_URL,
            params={"action": "search", "q": keyword, "mode": "keyword"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # The API may return {"data": [...]} or a direct list – handle both
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "results", "items", "laws"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # Fallback: return single-element list if there's a "name" field
            if "name" in data or "law_name" in data:
                return [data]
        return []
    except Exception as exc:
        print(f"    [WARN] beopmang API error for '{keyword}': {exc}")
        return []


def extract_sk_name(item: dict) -> str:
    """Extract the law name from a beopmang result item."""
    for key in ("법령명", "name", "law_name", "title", "lawName"):
        if key in item and item[key]:
            return str(item[key])
    return ""


# ---------------------------------------------------------------------------
# PostgreSQL – fetch all laws
# ---------------------------------------------------------------------------
async def fetch_all_laws(cfg: dict) -> list[dict]:
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        database=db["database"],
    )
    try:
        rows = await conn.fetch("SELECT id, name, category FROM laws ORDER BY id")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    # Load config
    cfg = load_config(CONFIG_PATH)

    print("Fetching NK laws from PostgreSQL …")
    laws = await fetch_all_laws(cfg)
    total = len(laws)
    print(f"  → {total} laws loaded.\n")

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    mappings: list[dict] = []

    with httpx.Client() as client:
        for idx, law in enumerate(laws, start=1):
            nk_name: str = law["name"]
            category: str = law.get("category") or ""

            keyword = normalize_name(nk_name)

            # Progress every 30 laws
            if idx % 30 == 1 or idx == total:
                print(f"[{idx:3d}/{total}] Searching: '{nk_name}' → keyword='{keyword}'")

            results = search_beopmang(client, keyword)

            best_sk_name = ""
            best_score = 0.0
            best_item: dict = {}

            for item in results:
                sk_name = extract_sk_name(item)
                if not sk_name:
                    continue
                score = similarity(keyword, sk_name)
                if score > best_score:
                    best_score = score
                    best_sk_name = sk_name
                    best_item = item

            entry: dict = {
                "nk_id": law["id"],
                "nk_name": nk_name,
                "nk_category": category,
                "nk_keyword": keyword,
            }

            if best_score > 0.2:
                entry["sk_name"] = best_sk_name
                entry["similarity"] = round(best_score, 4)
                entry["confidence"] = classify_confidence(best_score)
                # Include any extra metadata beopmang provides
                for meta_key in ("법령ID", "id", "law_id", "msq", "법종구분"):
                    if meta_key in best_item:
                        entry[f"sk_{meta_key}"] = best_item[meta_key]
            else:
                entry["sk_name"] = None
                entry["similarity"] = None
                entry["confidence"] = None

            mappings.append(entry)

            # Rate limiting
            time.sleep(0.5)

    # Build final JSON
    output = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(mappings),
        "matched": sum(1 for m in mappings if m["sk_name"] is not None),
        "mappings": mappings,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {output['matched']}/{output['total']} laws matched.")
    print(f"Output written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
