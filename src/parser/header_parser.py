"""
header_parser.py — Parse the header block of North Korean law texts.

Handles:
  - 주체 (Juche) calendar year conversion
  - Law name extraction after "조선민주주의인민공화국"
  - Amendment history extraction with multiline OCR artifacts
  - body_start_index detection
"""

import re
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Juche calendar conversion
# ---------------------------------------------------------------------------

def juche_to_western(juche_year: int) -> int:
    """Convert a Juche year to the Western (Gregorian) year.

    주체1년 = 1912, so western = 1911 + juche_year.
    """
    return 1911 + juche_year


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Amendment:
    """A single amendment entry in the law header."""
    date: str    # ISO-8601: YYYY-MM-DD
    action: str  # "채택" or "수정보충"
    basis: str   # Authority text, e.g. "정령 제1032호" or full sentence fragment


@dataclass
class HeaderInfo:
    """Parsed header of a North Korean law text."""
    law_name: str
    amendments: List[Amendment] = field(default_factory=list)
    body_start_index: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Regex for 주체 year lines, tolerating optional whitespace/newline between
# 년 and the month.
#
# Captures (주체 형식 또는 평년 형식 모두 허용):
#   group 1 — 주체 형식의 서기년도(괄호 안), 평년 형식이면 None
#   group 2 — 평년 형식의 서기년도, 주체 형식이면 None
#   group 3 — month (1–2 digits)
#   group 4 — day   (1–2 digits)
#   group 5 — the rest up to 채택/수정보충/수정/승인/제정 (the basis + action)
# ※ 본문 오탐 방지를 위해 parse_header 는 이 정규식을 '헤더 영역'에만 적용한다.
_AMENDMENT_RE = re.compile(
    r'(?:주체\s*\d+\s*\(\s*(\d{4})\s*\)|(\d{4}))\s*년\s*\n?\s*'      # 주체NN(YYYY)년  또는  YYYY년
    r'(\d{1,2})\s*월\s*(\d{1,2})(?:\s*[~∼−–-]\s*\d{1,2})?\s*일\s+'  # MM 월 DD 일 또는 DD~DD일 (공백 허용)
    r'(.+?(?:채택|수정보충|수정|승인|제정))',                       # basis + action (수정/승인/제정 추가)
    re.DOTALL
)

# Marker line for the body (first chapter/article/section/preface)
_BODY_START_RE = re.compile(
    r'^(제\d+[장조편절관]|서\s*문)',
    re.MULTILINE
)

# "결정 제N호" or "정령 제N호" style basis extraction
_BASIS_RE = re.compile(r'(?:결정|정령|법령|명령)\s*제\d+호')


def _extract_basis(raw: str) -> str:
    """Extract a concise basis string from the raw authority text.

    Tries to find a '결정/정령/... 제N호' pattern; if not found returns the
    full raw text (stripped).
    """
    m = _BASIS_RE.search(raw)
    if m:
        return m.group(0)
    return raw.strip()


def _extract_law_name(text: str) -> str:
    """Return the law name following '조선민주주의인민공화국'.

    Two layouts are supported:
      1. Same-line: "조선민주주의인민공화국 로동법"
      2. Next-line:  "조선민주주의인민공화국\n\n과학기술법"
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "조선민주주의인민공화국" in stripped:
            # Check if the law name is on the same line
            after = stripped.replace("조선민주주의인민공화국", "").strip()
            if after:
                return after
            # Otherwise find the next non-empty line
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if candidate:
                    return candidate
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_header(text: str) -> HeaderInfo:
    """Parse the header block of a North Korean law text.

    Parameters
    ----------
    text:
        Full raw text of the law document.

    Returns
    -------
    HeaderInfo
        Parsed header with law name, amendments (sorted by date), and the
        character index where the body starts.
    """
    law_name = _extract_law_name(text)

    # --- Find body start index (먼저 계산: 개정일 검색을 헤더 영역으로 한정) ---
    body_match = _BODY_START_RE.search(text)
    body_start_index = body_match.start() if body_match else 0
    # 헤더 영역(본문 시작 전)만 스캔 — 평년형식 허용에 따른 본문 오탐 방지.
    header_region = text[:body_start_index] if body_start_index else text

    # --- Find amendments ---
    amendments: List[Amendment] = []
    for m in _AMENDMENT_RE.finditer(header_region):
        # 주체 형식이면 group(1), 평년 형식이면 group(2) 에 서기년도가 들어 있다.
        western_year = int(m.group(1) or m.group(2))
        month = int(m.group(3))
        day = int(m.group(4))
        raw_rest = m.group(5)

        date_str = f"{western_year:04d}-{month:02d}-{day:02d}"

        # Determine action
        if raw_rest.endswith("채택"):
            action = "채택"
        else:
            action = "수정보충"

        basis = _extract_basis(raw_rest)

        amendments.append(Amendment(date=date_str, action=action, basis=basis))

    # Sort by date string (ISO-8601 sorts lexicographically)
    amendments.sort(key=lambda a: a.date)

    return HeaderInfo(
        law_name=law_name,
        amendments=amendments,
        body_start_index=body_start_index,
    )
