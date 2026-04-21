"""
Shared pytest fixtures for legalize-kp-pipeline tests.
Provides sample law text in NIS (국정원) and 법무부 formats.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample NIS (국정원) text
# Features:
#   - 주체 calendar year (e.g. 주체112(2023)년)
#   - Tab-newline patterns in article numbers (제N조\t\n)
#   - Occasional OCR noise
# ---------------------------------------------------------------------------
SAMPLE_NIS_TEXT = """\
조선민주주의인민공화국 로동법

주체63(1974)년 4월 18일 최고인민회의 제5기 제3차회의에서 채택
주체112(2023)년 9월 7일 최고인민회의 제14기 제9차회의에서 수정보충

제1장 일반원칙

제1조\t
이 법은 공화국의 로동관계를 규제하는 기본법이다.
모든 공민은 로동의 권리를 가진다.

제2조\t
국가는 로동자들의 로동조건을 끊임없이 개선하고
그들의 물질문화생활을 높이기 위하여 힘쓴다.

제2장 로동과 휴식

제3조\t
로동시간은 하루 8시간이다.
무거운 로동 또는 특수한 조건에서 하는 로동의 경우에는
그보다 짧은 로동시간제를 적용한다.

제4조\t
로동자들은 정기 및 보충휴가를 받는다.
정기휴가는 14일이다.
"""

# ---------------------------------------------------------------------------
# Sample 법무부 text
# Features:
#   - Gregorian calendar (서기) or mixed dates
#   - Cleaner formatting without tab-newline artifacts
#   - Article numbers on same line as content
# ---------------------------------------------------------------------------
SAMPLE_MOBU_TEXT = """\
조선민주주의인민공화국 로동법

1974년 4월 18일 채택
2023년 9월 7일 수정보충

제1장 일반원칙

제1조 이 법은 공화국의 로동관계를 규제하는 기본법이다.
모든 공민은 로동의 권리를 가진다.

제2조 국가는 로동자들의 로동조건을 끊임없이 개선하고 그들의 물질문화생활을 높이기 위하여 힘쓴다.

제2장 로동과 휴식

제3조 로동시간은 하루 8시간이다.
무거운 로동 또는 특수한 조건에서 하는 로동의 경우에는 그보다 짧은 로동시간제를 적용한다.

제4조 로동자들은 정기 및 보충휴가를 받는다.
정기휴가는 14일이다.
"""

# ---------------------------------------------------------------------------
# Simple law text with items (호) — no chapters, flat structure
# ---------------------------------------------------------------------------
SAMPLE_SIMPLE_TEXT = """\
조선민주주의인민공화국 가족법

주체105(2016)년 6월 29일 최고인민회의 상임위원회 정령으로 수정보충

제1조 이 법은 가족관계를 규제하는 기본법이다.

제2조 결혼은 다음의 요건을 갖추어야 한다.
1. 당사자들사이의 자유로운 합의
2. 법정결혼년령에 이르렀을 것
3. 결혼등록기관에 등록할 것

제3조 결혼년령은 녀자는 17살, 남자는 18살이다.
"""


@pytest.fixture
def sample_nis_text() -> str:
    """Return sample NIS-format law text."""
    return SAMPLE_NIS_TEXT


@pytest.fixture
def sample_mobu_text() -> str:
    """Return sample 법무부-format law text."""
    return SAMPLE_MOBU_TEXT


@pytest.fixture
def sample_simple_text() -> str:
    """Return sample simple law text with items (호)."""
    return SAMPLE_SIMPLE_TEXT
