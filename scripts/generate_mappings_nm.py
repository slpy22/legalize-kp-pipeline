"""남북법 N:M 매핑 생성 — 조문 레벨 상세 분석.

각 북한법에 대해:
1. 대응하는 남한법 여러 개 매핑 (N:M)
2. 공통 규율 영역 / 고유 영역 분석
3. 조문 레벨 대응 관계
"""
import asyncio
import json
import os
import sys
import time
import re
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
from app.core.config import load_config

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "law_mappings.json")
MAX_RETRIES = 3
RETRY_DELAY = 30


async def fetch_kp_laws_with_articles(cfg):
    """북한법 + 주요 조문 로드."""
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"], port=db["port"],
        user=db["user"], password=db["password"],
        database=db["database"],
    )
    laws = await conn.fetch("""
        SELECT l.id, l.name, l.category, l.total_articles, l.chapter_count
        FROM laws l ORDER BY l.category, l.name
    """)

    result = []
    for law in laws:
        articles = await conn.fetch("""
            SELECT article_number, article_title, chapter, content
            FROM articles WHERE law_id = $1
            ORDER BY position LIMIT 15
        """, law["id"])

        result.append({
            "name": law["name"],
            "category": law["category"],
            "total_articles": law["total_articles"],
            "chapter_count": law["chapter_count"],
            "key_articles": [
                f"제{a['article_number']}조({a['article_title'] or ''}): {(a['content'] or '')[:150]}"
                for a in articles
            ]
        })

    await conn.close()
    return result


def generate_nm_mapping(client, laws_batch):
    """Gemini로 N:M 매핑 생성."""
    laws_info = ""
    for law in laws_batch:
        arts_str = "\n    ".join(law["key_articles"][:8])
        laws_info += f"""
  [{law['name']}] (카테고리: {law['category']}, {law['total_articles']}조)
    주요 조문:
    {arts_str}
"""

    prompt = f"""다음은 북한 법령 목록과 주요 조문입니다. 각 북한법에 대해 대응하는 남한(대한민국) 법률을 분석해주세요.

중요: 1:1이 아닌 N:M 매핑입니다. 하나의 북한법이 여러 남한법에 걸칠 수 있고, 반대도 마찬가지입니다.

북한 법령:
{laws_info}

각 북한법에 대해 다음을 분석해주세요:
1. kr_names: 대응하는 남한 법률명 배열 (여러 개 가능, 없으면 빈 배열)
2. relationship: "equivalent"(거의 동일법), "partial"(부분 대응), "related"(관련), "none"(대응 없음)
3. overlap_areas: 남북이 공통으로 규율하는 영역 (예: ["소프트웨어 등록", "저작권 보호"])
4. kp_unique: 북한법에만 있는 고유 영역 (예: ["주체사상 반영", "당 지도"])
5. kr_unique: 남한법에만 있는 영역 (예: ["온라인 플랫폼 규제"])
6. article_mappings: 주요 조문 대응 (예: [{{"kp": "제1조", "kr_law": "정보통신망법", "kr_article": "제1조", "topic": "목적"}}])

문화어→남한어 변환 참고: 로동→노동, 콤퓨터→컴퓨터, 쏘프트웨어→소프트웨어, 에네르기→에너지, 체신→통신, 봉사→서비스, 리용→이용

JSON 배열만 응답하세요:
[{{
  "kp_name": "북한법명",
  "kr_names": ["남한법1", "남한법2"],
  "relationship": "partial",
  "overlap_areas": ["영역1", "영역2"],
  "kp_unique": ["고유1"],
  "kr_unique": ["고유1"],
  "article_mappings": [{{"kp": "제1조", "kr_law": "남한법명", "kr_article": "제1조", "topic": "목적"}}],
  "confidence": "high"
}}]"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = response.text
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            if "503" in str(e) and attempt < MAX_RETRIES:
                print(f"    503 에러, {RETRY_DELAY}초 대기 ({attempt}/{MAX_RETRIES})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    실패: {e}")
                return None
    return None


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)

    print("북한법 + 조문 로드 중...")
    laws = await fetch_kp_laws_with_articles(cfg)
    print(f"  {len(laws)}건 로드")

    from google import genai
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    # 카테고리별로 5~8개씩 배치
    categories = {}
    for law in laws:
        categories.setdefault(law["category"], []).append(law)

    all_mappings = []
    total_mapped = 0

    for cat, cat_laws in categories.items():
        # 카테고리 내에서 5개씩 배치
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
                    all_mappings.append(mapping)
                    if mapping["kr_names"]:
                        total_mapped += 1

                mapped = sum(1 for r in result if r.get("kr_names"))
                print(f"  → {mapped}/{len(result)} 매핑")
            else:
                # 실패 시 빈 매핑
                for law in batch:
                    all_mappings.append({
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
                    })
                print(f"  → 실패")

            time.sleep(4)  # Rate limit

    # 중복 제거
    seen = {}
    for m in all_mappings:
        seen[m["kp_name"]] = m
    final = sorted(seen.values(), key=lambda m: m["kp_name"])

    output = {
        "version": "2.0.0",
        "generated": time.strftime("%Y-%m-%d"),
        "method": "ai_nm_analysis",
        "schema": "N:M with article-level mappings",
        "total": len(final),
        "matched": sum(1 for m in final if m["kr_names"]),
        "mappings": final,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    matched = sum(1 for m in final if m["kr_names"])
    equiv = sum(1 for m in final if m["relationship"] == "equivalent")
    partial = sum(1 for m in final if m["relationship"] == "partial")
    related = sum(1 for m in final if m["relationship"] == "related")

    print(f"\n{'='*60}")
    print(f"완료: {matched}/{len(final)}건 매핑")
    print(f"  equivalent: {equiv}, partial: {partial}, related: {related}")
    print(f"출력: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
