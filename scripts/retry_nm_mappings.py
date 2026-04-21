"""실패한 N:M 매핑만 재시도."""
import asyncio
import json
import os
import sys
import time
import re
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import load_config
from scripts.generate_mappings_nm import fetch_kp_laws_with_articles, generate_nm_mapping

MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "law_mappings.json")
MAX_RETRIES = 3
RETRY_DELAY = 45


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)

    # 기존 매핑 로드
    with open(MAPPINGS_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # 성공한 것과 실패한 것 분리
    success = {m["kp_name"]: m for m in existing["mappings"] if m.get("source") != "failed"}
    failed_names = {m["kp_name"] for m in existing["mappings"] if m.get("source") == "failed"}
    print(f"기존 성공: {len(success)}, 실패: {len(failed_names)}")

    if not failed_names:
        print("재시도할 항목 없음")
        return

    # 실패한 법령의 조문 로드
    laws = await fetch_kp_laws_with_articles(cfg)
    failed_laws = [l for l in laws if l["name"] in failed_names]

    from google import genai
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    # 카테고리별 5개씩 배치
    categories = {}
    for law in failed_laws:
        categories.setdefault(law["category"], []).append(law)

    new_success = 0
    still_failed = 0

    for cat, cat_laws in categories.items():
        for i in range(0, len(cat_laws), 5):
            batch = cat_laws[i:i+5]
            batch_names = [l["name"] for l in batch]
            print(f"\n[{cat}] {batch_names}")

            result = generate_nm_mapping(client, batch)

            if result:
                for r in result:
                    mapping = {
                        "kp_name": r.get("kp_name", ""),
                        "kp_category": cat,
                        "kr_names": r.get("kr_names", []),
                        "relationship": r.get("relationship", "none"),
                        "overlap_areas": r.get("overlap_areas", []),
                        "kp_unique": r.get("kp_unique", []),
                        "kr_unique": r.get("kr_unique", []),
                        "article_mappings": r.get("article_mappings", []),
                        "confidence": r.get("confidence", "medium"),
                        "source": "ai_nm_analysis",
                    }
                    success[mapping["kp_name"]] = mapping
                    if mapping["kr_names"]:
                        new_success += 1
                mapped = sum(1 for r in result if r.get("kr_names"))
                print(f"  → {mapped}/{len(result)} 매핑")
            else:
                for law in batch:
                    if law["name"] not in success:
                        success[law["name"]] = {
                            "kp_name": law["name"],
                            "kp_category": cat,
                            "kr_names": [],
                            "relationship": "none",
                            "overlap_areas": [],
                            "kp_unique": [],
                            "kr_unique": [],
                            "article_mappings": [],
                            "confidence": "low",
                            "source": "failed",
                        }
                        still_failed += 1
                print(f"  → 실패")

            time.sleep(5)

    final = sorted(success.values(), key=lambda m: m["kp_name"])
    mapped_count = sum(1 for m in final if m.get("kr_names"))

    output = {
        "version": "2.0.0",
        "generated": time.strftime("%Y-%m-%d"),
        "method": "ai_nm_analysis",
        "schema": "N:M with article-level mappings",
        "total": len(final),
        "matched": mapped_count,
        "mappings": final,
    }

    with open(MAPPINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"재시도 결과: 신규 성공 {new_success}, 여전히 실패 {still_failed}")
    print(f"총: {mapped_count}/{len(final)} 매핑")


if __name__ == "__main__":
    asyncio.run(main())
