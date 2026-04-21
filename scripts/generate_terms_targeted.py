"""특정 분야별 타겟 용어 생성 — 기존에 부족한 분야를 보강."""
import json
import os
import sys
import re
import time

TERMS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "term_pairs.json")

# 기존 로드
with open(TERMS_PATH, "r", encoding="utf-8") as f:
    existing = json.load(f)
existing_kp = {t["kp"] for t in existing["terms"]}

from google import genai
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

# 분야별 타겟 프롬프트
targets = [
    {
        "name": "형사법",
        "prompt": "북한 형법과 형사소송법에서 사용되는 문화어 법률 용어를 남한어로 대조해주세요. 형벌 종류, 소송 절차, 수사 용어 등을 포함하세요.",
    },
    {
        "name": "민사법",
        "prompt": "북한 민법, 민사소송법, 가족법에서 사용되는 문화어 법률 용어를 남한어로 대조해주세요. 계약, 재산, 혼인, 상속 관련 용어를 포함하세요.",
    },
    {
        "name": "경제/무역",
        "prompt": "북한 대외경제법, 합영법, 합작법, 외국인투자법 등에서 사용되는 경제/무역 문화어를 남한어로 대조해주세요.",
    },
    {
        "name": "IT/과학기술",
        "prompt": "북한 콤퓨터망관리법, 쏘프트웨어산업법, 전자인증법, 이동통신법 등에서 사용되는 IT/과학기술 문화어를 남한어로 대조해주세요.",
    },
    {
        "name": "환경/국토",
        "prompt": "북한 환경보호법, 산림법, 국토계획법, 수산법 등에서 사용되는 환경/국토 관련 문화어를 남한어로 대조해주세요.",
    },
    {
        "name": "교통/건설",
        "prompt": "북한 도로교통법, 철도법, 배등록법, 건설법, 살림집법 등에서 사용되는 교통/건설 문화어를 남한어로 대조해주세요.",
    },
    {
        "name": "보건/사회",
        "prompt": "북한 인민보건법, 비상방역법, 의약품관리법, 녀성권리보장법, 아동권리보장법 등에서 사용되는 보건/사회 문화어를 남한어로 대조해주세요.",
    },
]

COMMON_SUFFIX = """
규칙:
1. 남한어와 완전히 동일한 단어는 제외하세요.
2. "기본 형태소"만 포함하세요. 예: "로동→노동"이 있으면 "로동자→노동자"는 불필요.
3. 고유명사 제외.
4. 최소 15개 이상 찾아주세요.
5. 분류: 법률, 경제, IT, 산업, 환경, 건설, 교통, 교육, 보건, 군사, 외교, 과학, 일반, 정치, 농업, 사회

JSON 배열만 응답:
[{"kp": "북한어", "kr": "남한어", "category": "분류"}]
"""

all_new = []
for target in targets:
    print(f"\n[{target['name']}] 생성 중...")
    prompt = target["prompt"] + "\n\n" + COMMON_SUFFIX

    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = response.text
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                pairs = json.loads(json_match.group())
                new = [
                    {"kp": p["kp"], "kr": p["kr"], "category": p.get("category", target["name"]), "verified": False}
                    for p in pairs
                    if p.get("kp") and p.get("kr") and p["kp"] != p["kr"] and p["kp"] not in existing_kp
                ]
                all_new.extend(new)
                existing_kp.update(p["kp"] for p in new)
                print(f"  → {len(new)}개 신규")
                break
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                print(f"  503, 30초 대기...")
                time.sleep(30)
            else:
                print(f"  실패: {e}")
    time.sleep(3)

# 파생어 제거
sorted_all = sorted(existing["terms"] + all_new, key=lambda t: len(t["kp"]))
base_mappings = []
result = []
for term in sorted_all:
    kp, kr = term["kp"], term["kr"]
    is_derivable = False
    for base_kp, base_kr in base_mappings:
        if base_kp in kp and base_kr in kr and kp != base_kp:
            if kp.replace(base_kp, base_kr) == kr:
                is_derivable = True
                break
    if not is_derivable:
        result.append(term)
        base_mappings.append((kp, kr))

result.sort(key=lambda t: t["kp"])

output = {
    "version": "3.2.0",
    "generated": "2026-04-19",
    "method": "seed+claude+gemini_targeted",
    "description": "북한 문화어↔남한어 법률 용어 대조표 v3.2. 분야별 타겟 생성으로 확장.",
    "total": len(result),
    "verified_count": sum(1 for t in result if t["verified"]),
    "terms": result,
}

with open(TERMS_PATH, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"신규 추가: {len(all_new)}개")
print(f"파생어 제거 후 최종: {len(result)}개 (기존 {len(existing['terms'])}개)")

from collections import Counter
cats = Counter(t["category"] for t in result)
for cat, cnt in cats.most_common():
    print(f"  {cat}: {cnt}개")
