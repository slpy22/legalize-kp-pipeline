"""남한어↔문화어 용어 대조표 v2 — 대규모 생성 + 중복/유추 가능 쌍 제거.

1. 기존 시드 용어 유지
2. 북한법 전체 텍스트에서 자주 등장하는 단어 추출
3. Gemini AI로 대규모 용어 쌍 생성 (카테고리별 배치)
4. 유추 가능한 파생어 제거 (로동→노동이 있으면 로동법→노동법 제거)
"""
import asyncio
import json
import os
import sys
import time
import re
from collections import Counter
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
from app.core.config import load_config

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "term_pairs.json")
MAX_RETRIES = 3
RETRY_DELAY = 30

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
]


async def fetch_all_words(cfg) -> Counter:
    """북한법 전체 텍스트에서 단어 빈도 추출."""
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"], port=db["port"],
        user=db["user"], password=db["password"],
        database=db["database"],
    )
    # 법령명 + 조문 내용 모두 수집
    rows = await conn.fetch("""
        SELECT content FROM articles WHERE content IS NOT NULL
        UNION ALL
        SELECT name FROM laws
    """)
    await conn.close()

    counter = Counter()
    for row in rows:
        words = re.findall(r"[가-힣]{2,6}", row["content"] if "content" in row.keys() else row["name"])
        counter.update(words)
    return counter


def filter_candidates(counter: Counter, existing_terms: set) -> list:
    """AI에 보낼 후보 단어 필터링."""
    # 두음법칙 + 문화어 특징적인 음절 패턴
    culture_patterns = re.compile(
        r"[렬련로룡류리녀뇨뉴니래력론록롱루릉림립렵령]|"
        r"페|봉사|규률|조종|지도통제|수행|담보|선차|"
        r"끊임없|틀어쥐|세우도록|떨구|바치|일떠서"
    )

    candidates = []
    for word, count in counter.most_common(3000):
        if word in existing_terms:
            continue
        if count < 5:
            continue
        if culture_patterns.search(word):
            candidates.append({"word": word, "count": count})

    return candidates[:500]


def call_gemini_batch(client, words_batch: list, batch_num: int) -> list:
    """Gemini에 단어 배치를 보내 용어 쌍 생성."""
    words_str = ", ".join(words_batch)

    prompt = f"""다음은 북한 법령에서 자주 사용되는 단어 목록입니다.
각 단어에 대해 남한에서 사용하는 대응 표현을 찾아주세요.

중요 규칙:
1. 남한어와 완전히 동일한 단어는 제외하세요.
2. 차이가 있는 것만 포함하세요.
3. "기본 형태소"만 포함하세요. 예를 들어 "로동→노동"이 있으면 "로동자→노동자", "로동법→노동법" 같은 파생어는 포함하지 마세요. 기본 매핑으로 유추 가능하니까요.
4. 고유명사(인명, 지명)는 제외하세요.
5. 분류: IT, 법률, 경제, 산업, 환경, 건설, 교통, 교육, 보건, 군사, 외교, 과학, 일반

단어 목록: {words_str}

JSON 배열만 응답하세요 (다른 텍스트 없이):
[{{"kp": "북한어", "kr": "남한어", "category": "분류"}}]"""

    for attempt in range(1, MAX_RETRIES + 1):
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
                return [
                    {"kp": p["kp"], "kr": p["kr"], "category": p.get("category", "일반"), "verified": False}
                    for p in pairs
                    if p.get("kp") and p.get("kr") and p["kp"] != p["kr"]
                ]
        except Exception as e:
            if "503" in str(e) and attempt < MAX_RETRIES:
                print(f"    503 에러, {RETRY_DELAY}초 대기 (시도 {attempt}/{MAX_RETRIES})")
                time.sleep(RETRY_DELAY)
            else:
                print(f"    실패: {e}")
                return []
    return []


def remove_derivable(terms: list) -> list:
    """유추 가능한 파생어 제거.

    로동→노동이 있으면 로동자→노동자, 로동법→노동법 등은 제거.
    기준: 기존 매핑의 kp가 다른 매핑의 kp에 포함되면 파생어로 간주.
    """
    # 길이 짧은 순 정렬 (기본 형태소가 먼저)
    sorted_terms = sorted(terms, key=lambda t: len(t["kp"]))

    base_mappings = []  # (kp, kr) 기본 매핑
    result = []

    for term in sorted_terms:
        kp, kr = term["kp"], term["kr"]

        # 이 용어가 기존 기본 매핑으로 유추 가능한지 체크
        is_derivable = False
        for base_kp, base_kr in base_mappings:
            if base_kp in kp and base_kr in kr and kp != base_kp:
                # 예: base=(로동,노동), current=(로동자,노동자) → 유추 가능
                # kp에서 base_kp를 base_kr로 치환하면 kr이 되는지 확인
                derived = kp.replace(base_kp, base_kr)
                if derived == kr:
                    is_derivable = True
                    break

        if not is_derivable:
            result.append(term)
            base_mappings.append((kp, kr))

    return result


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)

    print("전체 텍스트 빈도 분석 중...")
    counter = await fetch_all_words(cfg)
    print(f"  고유 단어: {len(counter)}개")

    # 기존 시드의 kp를 제외 목록에 추가
    existing_kp = {t["kp"] for t in SEED_TERMS}

    print("후보 필터링 중...")
    candidates = filter_candidates(counter, existing_kp)
    print(f"  후보: {len(candidates)}개")

    from google import genai
    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    # 100개씩 배치로 AI 생성
    BATCH_SIZE = 80
    all_ai_terms = []

    for i in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[i:i + BATCH_SIZE]
        batch_words = [c["word"] for c in batch]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"\n배치 {batch_num}/{total_batches}: {len(batch_words)}개 단어...")
        pairs = call_gemini_batch(client, batch_words, batch_num)
        all_ai_terms.extend(pairs)
        print(f"  → {len(pairs)}개 용어 쌍 생성")
        time.sleep(3)

    print(f"\nAI 생성 총: {len(all_ai_terms)}개")

    # 시드 + AI 합치기 (중복 제거)
    all_terms = list(SEED_TERMS)
    existing = {(t["kp"], t["kr"]) for t in all_terms}
    for t in all_ai_terms:
        if (t["kp"], t["kr"]) not in existing:
            all_terms.append(t)
            existing.add((t["kp"], t["kr"]))

    print(f"중복 제거 후: {len(all_terms)}개")

    # 유추 가능한 파생어 제거
    filtered = remove_derivable(all_terms)
    removed = len(all_terms) - len(filtered)
    print(f"파생어 제거: {removed}개 제거 → {len(filtered)}개 최종")

    output = {
        "version": "2.0.0",
        "generated": time.strftime("%Y-%m-%d"),
        "method": "seed+ai_generated_v2",
        "total": len(filtered),
        "verified_count": sum(1 for t in filtered if t["verified"]),
        "terms": sorted(filtered, key=lambda t: t["kp"]),
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"완료: {len(filtered)}개 용어 (검수: {output['verified_count']})")
    print(f"출력: {OUTPUT_PATH}")

    # 카테고리별 통계
    cats = Counter(t["category"] for t in filtered)
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt}개")


if __name__ == "__main__":
    asyncio.run(main())
