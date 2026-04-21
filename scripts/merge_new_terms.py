"""generate_terms_v2로 생성된 새 용어를 기존 용어에 병합.

기존 v3 데이터를 DB에서 복원하고 새 항목만 추가.
"""
import asyncio
import json
import os
import sys
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
from app.core.config import load_config

TERMS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "term_pairs.json")


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"], port=db["port"],
        user=db["user"], password=db["password"],
        database=db["database"],
    )

    # DB에서 기존 222개 복원
    rows = await conn.fetch("SELECT kp_term, kr_term, category, verified FROM compare_terms ORDER BY kp_term")
    await conn.close()

    db_terms = [
        {"kp": r["kp_term"], "kr": r["kr_term"], "category": r["category"], "verified": r["verified"]}
        for r in rows
    ]
    print(f"DB에서 복원: {len(db_terms)}개")

    # 현재 파일에서 새로 생성된 것 로드
    with open(TERMS_PATH, "r", encoding="utf-8") as f:
        new_data = json.load(f)
    new_terms = new_data.get("terms", [])
    print(f"새로 생성된: {len(new_terms)}개")

    # 병합 (중복 제거)
    existing_kp = {t["kp"] for t in db_terms}
    added = 0
    for t in new_terms:
        if t["kp"] not in existing_kp:
            t["verified"] = False  # 새 항목은 미검수
            db_terms.append(t)
            existing_kp.add(t["kp"])
            added += 1

    # 파생어 제거
    sorted_terms = sorted(db_terms, key=lambda t: len(t["kp"]))
    base_mappings = []
    result = []
    for term in sorted_terms:
        kp, kr = term["kp"], term["kr"]
        is_derivable = False
        for base_kp, base_kr in base_mappings:
            if base_kp in kp and base_kr in kr and kp != base_kp:
                derived = kp.replace(base_kp, base_kr)
                if derived == kr:
                    is_derivable = True
                    break
        if not is_derivable:
            result.append(term)
            base_mappings.append((kp, kr))

    removed = len(db_terms) - len(result) + added - added  # just for display
    result.sort(key=lambda t: t["kp"])

    output = {
        "version": "3.1.0",
        "generated": "2026-04-19",
        "method": "seed+claude+gemini_merged",
        "description": "북한 문화어↔남한어 법률 용어 대조표 v3.1. DB 기존분 + Gemini 신규분 병합.",
        "total": len(result),
        "verified_count": sum(1 for t in result if t["verified"]),
        "terms": result,
    }

    with open(TERMS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"추가: {added}개, 파생어 제거 후 최종: {len(result)}개")
    print(f"  검수됨: {output['verified_count']}, 미검수: {len(result) - output['verified_count']}")

    from collections import Counter
    cats = Counter(t["category"] for t in result)
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt}개")


if __name__ == "__main__":
    asyncio.run(main())
