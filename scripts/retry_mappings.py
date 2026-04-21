"""실패한 카테고리만 재시도하여 기존 매핑에 추가."""
import asyncio
import json
import os
import sys
import time
import re
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
from app.core.config import load_config

MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "law_mappings.json")
MAX_RETRIES = 3
RETRY_DELAY = 30  # 503 대기


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


def call_gemini(client, cat, names):
    names_str = "\n".join(f"- {n}" for n in names)
    prompt = f"""다음은 북한 법령 목록입니다 (카테고리: {cat}).
각 북한 법령에 대해 가장 유사하거나 대응하는 대한민국(남한) 법률명을 찾아주세요.

북한 법령 목록:
{names_str}

규칙:
1. 대응하는 남한법이 명확한 경우만 매핑하세요.
2. 대응하는 남한법이 없으면 kr_name을 빈 문자열로 두세요.
3. 확신도: high(거의 확실), medium(유사), low(추정)
4. 북한 문화어를 남한어로 변환하여 생각하세요 (예: 로동→노동, 콤퓨터→컴퓨터)

JSON 배열만 응답하세요:
[{{"kp_name": "북한법명", "kr_name": "남한법명 또는 빈문자열", "confidence": "high/medium/low"}}]"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = response.text
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return None


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)

    # 기존 매핑 로드
    with open(MAPPINGS_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)

    existing_kp_names = {m["kp_name"] for m in existing["mappings"]}
    print(f"기존 매핑: {len(existing_kp_names)}건")

    # 미매핑 법령 찾기
    laws = await fetch_kp_laws(cfg)
    missing = [l for l in laws if l["name"] not in existing_kp_names]
    print(f"미매핑: {len(missing)}건")

    if not missing:
        print("모든 법령이 매핑되어 있습니다.")
        return

    # 카테고리별 그룹
    categories = {}
    for law in missing:
        categories.setdefault(law["category"], []).append(law["name"])

    from google import genai
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    new_mappings = []
    for cat, names in categories.items():
        print(f"\n[{cat}] {len(names)}건 매핑 중...")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                pairs = call_gemini(client, cat, names)
                if pairs:
                    for p in pairs:
                        new_mappings.append({
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
                    break
                else:
                    print(f"  → 파싱 실패 (시도 {attempt})")
            except Exception as e:
                if "503" in str(e) and attempt < MAX_RETRIES:
                    print(f"  → 503 에러, {RETRY_DELAY}초 대기 후 재시도 ({attempt}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY)
                else:
                    print(f"  → 실패: {e}")
                    # 실패 시 빈 매핑으로 채움
                    for name in names:
                        new_mappings.append({
                            "kp_name": name,
                            "kp_category": cat,
                            "kr_name": "",
                            "kr_query": "",
                            "confidence": "",
                            "source": "failed",
                            "notes": str(e)[:100],
                        })
                    break

        time.sleep(3)

    # 기존 + 신규 합치기
    all_mappings = existing["mappings"] + new_mappings
    # 중복 제거 (kp_name 기준, 나중 것 우선)
    seen = {}
    for m in all_mappings:
        seen[m["kp_name"]] = m
    merged = sorted(seen.values(), key=lambda m: m["kp_name"])

    matched = [m for m in merged if m.get("kr_name")]
    output = {
        "version": "1.0.0",
        "generated": time.strftime("%Y-%m-%d"),
        "method": "ai_generated",
        "total": len(merged),
        "matched": len(matched),
        "mappings": merged,
    }

    with open(MAPPINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"완료: {len(matched)}/{len(merged)}건 매핑")
    print(f"출력: {MAPPINGS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
