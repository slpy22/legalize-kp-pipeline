"""남북법 대응 매핑 생성 — AI 기반 (beopmang 대체).

beopmang API 장애 시 Google Gemini를 사용하여
북한법 법령명 → 대응하는 남한법 법령명을 매핑합니다.
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


async def fetch_kp_laws(cfg):
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"], port=db["port"],
        user=db["user"], password=db["password"],
        database=db["database"],
    )
    rows = await conn.fetch("SELECT id, name, category FROM laws ORDER BY category, name")
    await conn.close()
    return [dict(r) for r in rows]


def generate_mappings_with_ai(laws):
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    # 카테고리별로 배치 처리
    categories = {}
    for law in laws:
        cat = law["category"]
        categories.setdefault(cat, []).append(law["name"])

    all_mappings = []

    for cat, names in categories.items():
        print(f"\n[{cat}] {len(names)}건 매핑 중...")
        names_str = "\n".join(f"- {n}" for n in names)

        prompt = f"""다음은 북한 법령 목록입니다 (카테고리: {cat}).
각 북한 법령에 대해 가장 유사하거나 대응하는 대한민국(남한) 법률명을 찾아주세요.

북한 법령 목록:
{names_str}

규칙:
1. 대응하는 남한법이 명확한 경우만 매핑하세요.
2. 대응하는 남한법이 없으면 kr_name을 빈 문자열로 두세요.
3. 확신도: high(거의 확실), medium(유사), low(추정)
4. 북한 문화어를 남한어로 변환하여 생각하세요 (예: 로동→노동, 콤퓨터→컴퓨터, 쏘프트웨어→소프트웨어)

JSON 배열만 응답하세요 (설명 없이):
[{{"kp_name": "북한법명", "kr_name": "남한법명 또는 빈문자열", "confidence": "high/medium/low"}}]"""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = response.text

            # JSON 추출
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                pairs = json.loads(json_match.group())
                for p in pairs:
                    all_mappings.append({
                        "kp_name": p.get("kp_name", ""),
                        "kp_category": cat,
                        "kr_name": p.get("kr_name", ""),
                        "kr_query": p.get("kr_name", ""),
                        "confidence": p.get("confidence", "low"),
                        "source": "ai_generated",
                        "notes": "",
                    })
                mapped = sum(1 for p in pairs if p.get("kr_name"))
                print(f"  → {mapped}/{len(pairs)} 매핑됨")
            else:
                print(f"  → JSON 파싱 실패")
        except Exception as e:
            print(f"  → 오류: {e}")

        time.sleep(2)  # Rate limit 대응

    return all_mappings


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)

    print("북한법 로드 중...")
    laws = await fetch_kp_laws(cfg)
    print(f"  {len(laws)}건 로드")

    print("\nAI 매핑 생성 중...")
    mappings = generate_mappings_with_ai(laws)

    # 통계
    mapped = [m for m in mappings if m["kr_name"]]
    high = sum(1 for m in mapped if m["confidence"] == "high")
    medium = sum(1 for m in mapped if m["confidence"] == "medium")
    low = sum(1 for m in mapped if m["confidence"] == "low")

    output = {
        "version": "1.0.0",
        "generated": time.strftime("%Y-%m-%d"),
        "method": "ai_generated",
        "total": len(laws),
        "matched": len(mapped),
        "mappings": sorted(mappings, key=lambda m: m["kp_name"]),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"완료: {len(mapped)}/{len(laws)}건 매핑")
    print(f"  high: {high}, medium: {medium}, low: {low}")
    print(f"  미매핑: {len(laws) - len(mapped)}건")
    print(f"출력: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
