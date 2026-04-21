#!/usr/bin/env python3
"""
남한어↔문화어 용어 대조표 생성 스크립트

Generates term_pairs.json by combining:
1. Hardcoded seed terms (verified=True)
2. AI-generated terms via Google Gemini (verified=False)
   - Candidate words fetched from PostgreSQL articles table
"""

import asyncio
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import asyncpg

# ---------------------------------------------------------------------------
# Seed terms (manually verified)
# ---------------------------------------------------------------------------
SEED_TERMS = [
    {"kp": "쏘프트웨어", "kr": "소프트웨어", "category": "IT", "verified": True},
    {"kp": "콤퓨터", "kr": "컴퓨터", "category": "IT", "verified": True},
    {"kp": "에네르기", "kr": "에너지", "category": "산업", "verified": True},
    {"kp": "로동", "kr": "노동", "category": "일반", "verified": True},
    {"kp": "녀성", "kr": "여성", "category": "일반", "verified": True},
    {"kp": "련합", "kr": "연합", "category": "일반", "verified": True},
    {"kp": "림업", "kr": "임업", "category": "산업", "verified": True},
    {"kp": "류통", "kr": "유통", "category": "경제", "verified": True},
    {"kp": "리용", "kr": "이용", "category": "일반", "verified": True},
    {"kp": "리행", "kr": "이행", "category": "법률", "verified": True},
    {"kp": "공민", "kr": "국민", "category": "법률", "verified": True},
    {"kp": "인민", "kr": "국민", "category": "법률", "verified": True},
    {"kp": "기업소", "kr": "기업", "category": "경제", "verified": True},
    {"kp": "봉사", "kr": "서비스", "category": "일반", "verified": True},
    {"kp": "체신", "kr": "통신", "category": "IT", "verified": True},
    {"kp": "규격", "kr": "표준", "category": "산업", "verified": True},
    {"kp": "품질감독", "kr": "품질관리", "category": "산업", "verified": True},
    {"kp": "채택", "kr": "제정", "category": "법률", "verified": True},
    {"kp": "수정보충", "kr": "개정", "category": "법률", "verified": True},
    {"kp": "정령", "kr": "법령", "category": "법률", "verified": True},
    {"kp": "재판소", "kr": "법원", "category": "법률", "verified": True},
    {"kp": "검찰소", "kr": "검찰청", "category": "법률", "verified": True},
    {"kp": "인민보안", "kr": "경찰", "category": "법률", "verified": True},
    {"kp": "살림집", "kr": "주택", "category": "건설", "verified": True},
    {"kp": "도시경영", "kr": "도시관리", "category": "건설", "verified": True},
    {"kp": "원림록화", "kr": "조경녹화", "category": "환경", "verified": True},
    {"kp": "페기물", "kr": "폐기물", "category": "환경", "verified": True},
    {"kp": "페설물", "kr": "폐기물", "category": "환경", "verified": True},
    {"kp": "전기통신", "kr": "전기통신", "category": "IT", "verified": True},
    {"kp": "방송", "kr": "방송", "category": "IT", "verified": True},
]

# ---------------------------------------------------------------------------
# DB config
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "devadmin",
    "password": "devadmin123",
    "database": "legalize_kp",
}

# 두음법칙 variant characters that indicate North Korean orthography
DUEUM_CHARS = re.compile(r"[렬련로룡류리녀뇨뉴니래]")

OUTPUT_PATH = Path("E:/004_북한법/legalize-kp/compare/term_pairs.json")


# ---------------------------------------------------------------------------
# DB: fetch frequent words
# ---------------------------------------------------------------------------
async def fetch_candidate_words(top_n: int = 500) -> list[str]:
    """
    Pull the top_n most-frequent Korean words from articles.content.
    Words are split on whitespace/punctuation and counted.
    Returns a plain list of word strings, most-frequent first.
    """
    print("[DB] Connecting to PostgreSQL …")
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        # Fetch all article content; we'll tokenise in Python for flexibility
        rows = await conn.fetch("SELECT content FROM articles WHERE content IS NOT NULL")
    finally:
        await conn.close()

    print(f"[DB] Fetched {len(rows)} articles, counting word frequencies …")

    freq: dict[str, int] = {}
    token_re = re.compile(r"[가-힣]{2,}")  # Korean words, ≥2 chars

    for row in rows:
        for word in token_re.findall(row["content"]):
            freq[word] = freq.get(word, 0) + 1

    sorted_words = sorted(freq, key=lambda w: freq[w], reverse=True)
    return sorted_words[:top_n]


# ---------------------------------------------------------------------------
# Filter candidates with 두음법칙 variants
# ---------------------------------------------------------------------------
def filter_candidates(words: list[str], top_k: int = 50) -> list[str]:
    candidates = [w for w in words if DUEUM_CHARS.search(w)]
    # Exclude words already covered by seed terms
    seed_kp_set = {t["kp"] for t in SEED_TERMS}
    candidates = [w for w in candidates if w not in seed_kp_set]
    print(f"[Filter] {len(candidates)} candidates after 두음법칙 filter (showing top {top_k})")
    return candidates[:top_k]


# ---------------------------------------------------------------------------
# Gemini: generate term pairs
# ---------------------------------------------------------------------------
def generate_with_gemini(candidates: list[str]) -> list[dict]:
    """
    Send candidate North-Korean words to Gemini and ask it to produce
    South-Korean equivalents. Returns a list of term-pair dicts.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[Gemini] GOOGLE_API_KEY not set — skipping AI generation.")
        return []

    try:
        from google import genai  # type: ignore
    except ImportError:
        print("[Gemini] google-genai package not installed — skipping AI generation.")
        return []

    client = genai.Client(api_key=api_key)

    word_list = "\n".join(f"- {w}" for w in candidates)
    prompt = f"""다음은 북한 법령문서에서 자주 나오는 문화어(북한어) 단어 목록입니다.
각 단어에 대해 대응하는 남한어(표준어)를 제시하고, 적절한 카테고리를 분류해주세요.

카테고리 목록: IT, 경제, 건설, 환경, 산업, 법률, 일반

다음 JSON 배열 형식으로만 답변하세요 (다른 텍스트 없이):
[
  {{"kp": "문화어단어", "kr": "남한어단어", "category": "카테고리"}},
  ...
]

문화어 단어 목록:
{word_list}

규칙:
- 남한어와 동일한 단어라면 그대로 출력하세요
- 두음법칙이 적용되는 단어는 해당 규칙을 적용한 남한어로 변환하세요
- 의미가 다른 개념어(예: 봉사→서비스)는 의미 기준으로 대응어를 제시하세요
- JSON 배열만 출력하고 마크다운 코드블록(```)은 사용하지 마세요
"""

    # Try the specified model; fall back to gemini-2.5-flash if unavailable
    model_id = "gemini-2.5-flash-preview-05-20"
    print(f"[Gemini] Sending {len(candidates)} candidates to {model_id} …")
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
        )
    except Exception as exc:
        if "NOT_FOUND" in str(exc) or "404" in str(exc):
            fallback = "gemini-2.5-flash"
            print(f"[Gemini] Model {model_id!r} not found, falling back to {fallback!r} …")
            response = client.models.generate_content(
                model=fallback,
                contents=prompt,
            )
        else:
            raise

    raw = response.text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    try:
        pairs = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[Gemini] JSON parse error: {exc}")
        print(f"[Gemini] Raw response (first 500 chars): {raw[:500]}")
        return []

    # Normalise and tag as unverified
    result = []
    for item in pairs:
        if isinstance(item, dict) and "kp" in item and "kr" in item:
            result.append({
                "kp": str(item["kp"]).strip(),
                "kr": str(item["kr"]).strip(),
                "category": str(item.get("category", "일반")).strip(),
                "verified": False,
            })

    print(f"[Gemini] Received {len(result)} valid term pairs.")
    return result


# ---------------------------------------------------------------------------
# Merge & deduplicate
# ---------------------------------------------------------------------------
def merge_terms(seed: list[dict], ai: list[dict]) -> list[dict]:
    """
    Merge seed + AI terms. Seed terms take precedence (verified=True).
    Deduplicate on kp key; sort by kp.
    """
    merged: dict[str, dict] = {}
    for term in seed:
        merged[term["kp"]] = term
    for term in ai:
        if term["kp"] not in merged:
            merged[term["kp"]] = term
    return sorted(merged.values(), key=lambda t: t["kp"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("=" * 60)
    print("남한어↔문화어 용어 대조표 생성")
    print("=" * 60)

    # 1. Seed terms
    print(f"[Seed] Loaded {len(SEED_TERMS)} seed term pairs.")

    # 2. Fetch frequent words from DB
    ai_terms: list[dict] = []
    candidates: list[str] = []
    try:
        frequent_words = await fetch_candidate_words(top_n=500)
        candidates = filter_candidates(frequent_words, top_k=50)
    except Exception as exc:
        print(f"[DB] Error connecting to database: {exc}")
        print("[DB] Proceeding with seed terms only.")

    # 3. AI generation (independent of DB success/failure)
    if candidates:
        try:
            ai_terms = generate_with_gemini(candidates)
        except Exception as exc:
            print(f"[Gemini] Error during AI generation: {exc}")
            print("[Gemini] Proceeding with seed terms only.")
    else:
        if not candidates:
            print("[AI] No candidates available — skipping AI generation.")

    # 4. Merge
    all_terms = merge_terms(SEED_TERMS, ai_terms)

    verified_count = sum(1 for t in all_terms if t.get("verified"))
    method = "seed+ai_generated" if ai_terms else "seed_only"

    output = {
        "version": "1.0.0",
        "generated": date.today().isoformat(),
        "method": method,
        "total": len(all_terms),
        "verified_count": verified_count,
        "terms": all_terms,
    }

    # 5. Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    print()
    print(f"[Output] Written to: {OUTPUT_PATH}")
    print(f"[Output] Total terms : {output['total']}")
    print(f"[Output] Verified    : {output['verified_count']}")
    print(f"[Output] Method      : {output['method']}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
