"""북한법 텍스트에서 문화어 후보를 체계적으로 추출.

1. 두음법칙 차이 (ㄹ→ㄴ/ㅇ, ㄴ→ㅇ)
2. 외래어 표기 차이
3. 고유 법률 용어
4. 빈도 상위 1000개 중 남한어와 다른 것
"""
import asyncio
import json
import os
import sys
import re
from collections import Counter
import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api"))
from app.core.config import load_config

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "culture_word_candidates.json")


async def main():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp-api", "config.yaml")
    cfg = load_config(cfg_path)
    db = cfg["database"]
    conn = await asyncpg.connect(
        host=db["host"], port=db["port"],
        user=db["user"], password=db["password"],
        database=db["database"],
    )

    # 1. 전체 조문 + 법령명 수집
    articles = await conn.fetch("SELECT content FROM articles WHERE content IS NOT NULL")
    laws = await conn.fetch("SELECT name, full_text FROM laws")
    await conn.close()

    # 2. 단어 빈도 계산 (2~8글자 한글)
    counter = Counter()
    for row in articles:
        words = re.findall(r"[가-힣]{2,8}", row["content"])
        counter.update(words)
    for row in laws:
        words = re.findall(r"[가-힣]{2,8}", row["name"])
        counter.update(words)
        if row["full_text"]:
            words = re.findall(r"[가-힣]{2,8}", row["full_text"])
            counter.update(words)

    print(f"고유 단어: {len(counter)}개")

    # 3. 문화어 패턴 필터링

    # 3-1. 두음법칙 패턴 (ㄹ→ㄴ/ㅇ 계열)
    dueum_initial = re.compile(r"^[렬련로룡류리래력론록롱루릉림립렵령]")
    # 3-2. 두음법칙 (ㄴ→ㅇ 계열)
    dueum_n = re.compile(r"^[녀뇨뉴니]")
    # 3-3. 외래어 표기 차이
    foreign_patterns = [
        "쏘", "꼼", "빠", "쁘", "뜨", "딸", "꾸", "까", "쌍",
    ]
    # 3-4. 북한 특유 한자어/표현
    nk_specific = [
        "봉사", "지도통제", "선차", "담보", "리용", "리행", "리익",
        "꾸리", "바로하", "틀어쥐", "다그치", "앞세",
        "일떠서", "세우도록", "높이도록",
    ]
    # 3-5. ㅎ 관련 (페→폐)
    pe_pattern = re.compile(r"^페[기설]")

    categories = {
        "두음법칙_ㄹ": [],
        "두음법칙_ㄴ": [],
        "외래어": [],
        "고유표현": [],
        "ㅎ_탈락": [],
        "기타": [],
    }

    # 기존 매핑에 있는 단어 제외
    existing_path = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "term_pairs.json")
    existing_kp = set()
    if os.path.exists(existing_path):
        with open(existing_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
            existing_kp = {t["kp"] for t in existing.get("terms", [])}

    for word, count in counter.most_common(5000):
        if count < 3:
            continue
        if word in existing_kp:
            continue
        # 일반적인 남한어와 동일한 단어 제외 (조사, 어미 등)
        if len(word) <= 2 and word.endswith(("은", "는", "을", "를", "의", "에", "와", "로", "서")):
            continue

        matched = False

        if dueum_initial.match(word):
            categories["두음법칙_ㄹ"].append({"word": word, "count": count})
            matched = True
        elif dueum_n.match(word):
            categories["두음법칙_ㄴ"].append({"word": word, "count": count})
            matched = True
        elif any(p in word for p in foreign_patterns):
            categories["외래어"].append({"word": word, "count": count})
            matched = True
        elif any(p in word for p in nk_specific):
            categories["고유표현"].append({"word": word, "count": count})
            matched = True
        elif pe_pattern.match(word):
            categories["ㅎ_탈락"].append({"word": word, "count": count})
            matched = True

    # 정렬
    for cat in categories:
        categories[cat].sort(key=lambda x: x["count"], reverse=True)

    total = sum(len(v) for v in categories.values())
    print(f"\n문화어 후보: {total}개")
    for cat, items in categories.items():
        print(f"  {cat}: {len(items)}개")
        for item in items[:10]:
            print(f"    {item['word']}: {item['count']}회")

    # 저장
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
