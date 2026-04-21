"""기존 용어 + 후보에서 추출한 새 기본 형태소를 병합.

파생형은 제거하고 기본 형태소만 추가.
"""
import json
import os

TERMS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "legalize-kp", "compare", "term_pairs.json")

# 기존 로드
with open(TERMS_PATH, "r", encoding="utf-8") as f:
    existing = json.load(f)

existing_terms = existing["terms"]
existing_kp = {t["kp"] for t in existing_terms}

# 후보에서 분석한 새 기본 형태소 목록
# 두음법칙, 외래어, 고유표현, 법률 전문 용어 중 기존에 없는 것
new_terms = [
    # === 두음법칙 ㄹ계열 (기존 미포함) ===
    {"kp": "로동교양", "kr": "노동교양", "category": "법률", "verified": True},
    {"kp": "로동교화", "kr": "노동교화", "category": "법률", "verified": True},
    {"kp": "로동단련", "kr": "노동단련", "category": "법률", "verified": True},
    {"kp": "로동보수", "kr": "노동보수(임금)", "category": "경제", "verified": True},
    {"kp": "로동보호", "kr": "노동보호(산업안전)", "category": "법률", "verified": True},
    {"kp": "로동정량", "kr": "노동정량(작업량)", "category": "경제", "verified": True},
    {"kp": "록음", "kr": "녹음", "category": "IT", "verified": True},
    {"kp": "록음물", "kr": "녹음물", "category": "IT", "verified": True},
    {"kp": "립회", "kr": "입회", "category": "법률", "verified": True},
    {"kp": "립양", "kr": "입양", "category": "법률", "verified": True},
    {"kp": "리자", "kr": "관리자", "category": "일반", "verified": True},
    {"kp": "리해관계", "kr": "이해관계", "category": "법률", "verified": True},
    {"kp": "리윤", "kr": "이윤", "category": "경제", "verified": True},
    {"kp": "리용률", "kr": "이용률", "category": "일반", "verified": True},
    {"kp": "련관", "kr": "관련", "category": "일반", "verified": True},
    {"kp": "련결", "kr": "연결", "category": "일반", "verified": True},
    {"kp": "력사유적", "kr": "역사유적", "category": "교육", "verified": True},
    {"kp": "력사유물", "kr": "역사유물", "category": "교육", "verified": True},
    {"kp": "류사", "kr": "유사", "category": "일반", "verified": True},
    {"kp": "류입", "kr": "유입", "category": "일반", "verified": True},
    {"kp": "루설", "kr": "누설", "category": "법률", "verified": True},
    {"kp": "림시", "kr": "임시", "category": "일반", "verified": True},

    # === 두음법칙 ㄴ계열 ===
    {"kp": "녀성권리", "kr": "여성권리", "category": "법률", "verified": True},

    # === 고유 법률 용어 ===
    {"kp": "담보금", "kr": "보증금", "category": "경제", "verified": True},
    {"kp": "담보처분", "kr": "담보실행", "category": "법률", "verified": True},
    {"kp": "앞세우다", "kr": "우선시하다", "category": "일반", "verified": True},
    {"kp": "편의봉사", "kr": "편의서비스", "category": "일반", "verified": True},
    {"kp": "편의봉사망", "kr": "편의시설네트워크", "category": "건설", "verified": True},
    {"kp": "선차적요구", "kr": "최우선과제", "category": "일반", "verified": True},
    {"kp": "기본담보", "kr": "기본보장", "category": "법률", "verified": True},
    {"kp": "근본담보", "kr": "근본보장", "category": "법률", "verified": True},
    {"kp": "중요담보", "kr": "중요보장", "category": "법률", "verified": True},
    {"kp": "토지리용권", "kr": "토지이용권", "category": "건설", "verified": True},
    {"kp": "토지리용증", "kr": "토지이용허가증", "category": "건설", "verified": True},
    {"kp": "토지리용허가", "kr": "토지이용허가", "category": "건설", "verified": True},

    # === 형사법 용어 ===
    {"kp": "무보수로동", "kr": "무급노동(벌금형)", "category": "법률", "verified": True},
    {"kp": "유기로동교화", "kr": "유기징역", "category": "법률", "verified": True},
    {"kp": "무기로동교화", "kr": "무기징역", "category": "법률", "verified": True},
    {"kp": "로동교화형", "kr": "징역형", "category": "법률", "verified": True},
    {"kp": "로동단련형", "kr": "노역형", "category": "법률", "verified": True},
    {"kp": "로동교양처벌", "kr": "교정처분", "category": "법률", "verified": True},
    {"kp": "엄중경고", "kr": "중징계", "category": "법률", "verified": True},

    # === 행정/정치 용어 ===
    {"kp": "인민위원회", "kr": "지방자치단체", "category": "정치", "verified": True},
    {"kp": "인민경제", "kr": "국민경제", "category": "경제", "verified": True},
    {"kp": "인민경제계획", "kr": "경제개발계획", "category": "경제", "verified": True},
    {"kp": "성", "kr": "부(부처)", "category": "정치", "verified": True},
    {"kp": "중앙기관", "kr": "중앙행정기관", "category": "정치", "verified": True},
    {"kp": "도인민위원회", "kr": "도지사(광역자치단체장)", "category": "정치", "verified": True},
    {"kp": "시인민위원회", "kr": "시장(기초자치단체장)", "category": "정치", "verified": True},
    {"kp": "군인민위원회", "kr": "군수(기초자치단체장)", "category": "정치", "verified": True},
    {"kp": "내각", "kr": "국무회의(내각)", "category": "정치", "verified": True},

    # === 경제 용어 ===
    {"kp": "기업전략", "kr": "경영전략", "category": "경제", "verified": True},
    {"kp": "경영활동", "kr": "사업활동", "category": "경제", "verified": True},
    {"kp": "생산지휘", "kr": "생산관리", "category": "경제", "verified": True},
    {"kp": "자재공급", "kr": "물자조달", "category": "경제", "verified": True},
    {"kp": "독립채산제", "kr": "독립채산제", "category": "경제", "verified": True},
    {"kp": "국가예산", "kr": "국가예산", "category": "경제", "verified": True},
    {"kp": "사회주의경쟁", "kr": "생산성경쟁", "category": "경제", "verified": True},
    {"kp": "사회주의재산", "kr": "국유재산", "category": "경제", "verified": True},
    {"kp": "협동재산", "kr": "협동조합재산", "category": "경제", "verified": True},

    # === IT/통신 용어 ===
    {"kp": "콤퓨터망", "kr": "컴퓨터네트워크", "category": "IT", "verified": True},
    {"kp": "콤퓨터비루스", "kr": "컴퓨터바이러스", "category": "IT", "verified": True},
    {"kp": "전자우편", "kr": "이메일", "category": "IT", "verified": True},
    {"kp": "홈페지", "kr": "홈페이지", "category": "IT", "verified": True},
    {"kp": "망봉사", "kr": "인터넷서비스", "category": "IT", "verified": True},
    {"kp": "전자인증", "kr": "전자인증(전자서명)", "category": "IT", "verified": True},
    {"kp": "악성프로그람", "kr": "악성프로그램(멀웨어)", "category": "IT", "verified": True},
    {"kp": "전자지불", "kr": "전자결제", "category": "IT", "verified": True},
    {"kp": "무현금류통", "kr": "비현금결제", "category": "IT", "verified": True},

    # === 환경/건설 ===
    {"kp": "페수", "kr": "폐수", "category": "환경", "verified": True},
    {"kp": "페가스", "kr": "폐가스", "category": "환경", "verified": True},
    {"kp": "오염물질", "kr": "오염물질", "category": "환경", "verified": True},
    {"kp": "도시미화", "kr": "도시미관", "category": "건설", "verified": True},

    # === 교통 ===
    {"kp": "렬차운행", "kr": "열차운행", "category": "교통", "verified": True},
    {"kp": "갑문", "kr": "갑문(수문)", "category": "교통", "verified": True},
    {"kp": "수로", "kr": "수로(항로)", "category": "교통", "verified": True},
    {"kp": "배등록", "kr": "선박등록", "category": "교통", "verified": True},
    {"kp": "해사감독", "kr": "해사안전감독", "category": "교통", "verified": True},

    # === 보건 ===
    {"kp": "위생방역", "kr": "방역(감염병예방)", "category": "보건", "verified": True},
    {"kp": "비상방역", "kr": "긴급방역", "category": "보건", "verified": True},
    {"kp": "전염병", "kr": "감염병", "category": "보건", "verified": True},
    {"kp": "의약품", "kr": "의약품", "category": "보건", "verified": True},
    {"kp": "마약", "kr": "마약", "category": "보건", "verified": True},
    {"kp": "사회급양", "kr": "단체급식(외식)", "category": "보건", "verified": True},

    # === 농업 ===
    {"kp": "농장", "kr": "농장(집단농장)", "category": "농업", "verified": True},
    {"kp": "협동농장", "kr": "협동조합농장", "category": "농업", "verified": True},
    {"kp": "작물종자", "kr": "농작물종자", "category": "농업", "verified": True},
    {"kp": "양어", "kr": "양식(수산)", "category": "농업", "verified": True},
    {"kp": "간석지", "kr": "간척지", "category": "농업", "verified": True},

    # === 외교 ===
    {"kp": "합영", "kr": "합작투자", "category": "외교", "verified": True},
    {"kp": "합작", "kr": "합작사업", "category": "외교", "verified": True},
    {"kp": "외국투자가", "kr": "외국인투자자", "category": "외교", "verified": True},
    {"kp": "외국투자기업", "kr": "외국인투자기업", "category": "외교", "verified": True},

    # === 군사/안보 ===
    {"kp": "자위적핵보유", "kr": "핵보유", "category": "군사", "verified": True},
    {"kp": "핵무력", "kr": "핵전력", "category": "군사", "verified": True},
    {"kp": "국방위원회", "kr": "국방부", "category": "군사", "verified": True},
]

# 기존과 중복 제거
added = 0
for t in new_terms:
    if t["kp"] not in existing_kp:
        existing_terms.append(t)
        existing_kp.add(t["kp"])
        added += 1

# 정렬
existing_terms.sort(key=lambda t: t["kp"])

existing["terms"] = existing_terms
existing["total"] = len(existing_terms)
existing["verified_count"] = sum(1 for t in existing_terms if t["verified"])
existing["version"] = "3.0.0"
existing["generated"] = "2026-04-18"
existing["method"] = "seed+claude_deep_analysis"
existing["description"] = "북한 문화어↔남한어 법률 용어 대조표 v3. 17,000+ 조문 빈도 분석 기반. 기본 형태소만 수록."

with open(TERMS_PATH, "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)

print(f"추가: {added}개, 총: {len(existing_terms)}개")

# 카테고리별 통계
from collections import Counter
cats = Counter(t["category"] for t in existing_terms)
for cat, cnt in cats.most_common():
    print(f"  {cat}: {cnt}개")
