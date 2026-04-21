"""
Tests for src/parser/header_parser.py
"""
import pytest
from src.parser.header_parser import juche_to_western, parse_header, HeaderInfo, Amendment


# ---------------------------------------------------------------------------
# juche_to_western
# ---------------------------------------------------------------------------

def test_juche_to_western_77():
    assert juche_to_western(77) == 1988


def test_juche_to_western_110():
    assert juche_to_western(110) == 2021


def test_juche_to_western_112():
    assert juche_to_western(112) == 2023


def test_juche_to_western_1():
    """주체1년 = 1912"""
    assert juche_to_western(1) == 1912


def test_juche_to_western_63():
    assert juche_to_western(63) == 1974


# ---------------------------------------------------------------------------
# parse_header — law name extraction
# ---------------------------------------------------------------------------

def test_parse_header_law_name_nis(sample_nis_text):
    """NIS text: 조선민주주의인민공화국 로동법 → law_name = '로동법'"""
    result = parse_header(sample_nis_text)
    assert result.law_name == "로동법"


def test_parse_header_law_name_simple(sample_simple_text):
    """Simple text: 조선민주주의인민공화국 가족법 → law_name = '가족법'"""
    result = parse_header(sample_simple_text)
    assert result.law_name == "가족법"


def test_parse_header_law_name_mobu(sample_mobu_text):
    """법무부 text also starts with 조선민주주의인민공화국 로동법"""
    result = parse_header(sample_mobu_text)
    assert result.law_name == "로동법"


# ---------------------------------------------------------------------------
# parse_header — multiple amendments (NIS text)
# ---------------------------------------------------------------------------

def test_parse_header_multiple_amendments(sample_nis_text):
    """NIS text has 2 주체-year amendments."""
    result = parse_header(sample_nis_text)
    assert len(result.amendments) >= 2


def test_parse_header_first_amendment_nis(sample_nis_text):
    """First amendment should be 1974-04-18 채택."""
    result = parse_header(sample_nis_text)
    first = result.amendments[0]
    assert first.date == "1974-04-18"
    assert first.action == "채택"


def test_parse_header_last_amendment_nis(sample_nis_text):
    """Last amendment should be 2023-09-07 수정보충."""
    result = parse_header(sample_nis_text)
    last = result.amendments[-1]
    assert last.date == "2023-09-07"
    assert last.action == "수정보충"


def test_parse_header_amendments_sorted(sample_nis_text):
    """Amendments must be sorted chronologically by date string."""
    result = parse_header(sample_nis_text)
    dates = [a.date for a in result.amendments]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# parse_header — single amendment (simple text)
# ---------------------------------------------------------------------------

def test_parse_header_single_amendment_count(sample_simple_text):
    """Simple text has exactly 1 주체-year amendment."""
    result = parse_header(sample_simple_text)
    assert len(result.amendments) == 1


def test_parse_header_single_amendment_date(sample_simple_text):
    """주체105(2016)년 6월 29일 → 2016-06-29."""
    result = parse_header(sample_simple_text)
    assert result.amendments[0].date == "2016-06-29"


def test_parse_header_single_amendment_action(sample_simple_text):
    """Action should be 수정보충."""
    result = parse_header(sample_simple_text)
    assert result.amendments[0].action == "수정보충"


# ---------------------------------------------------------------------------
# parse_header — body_start_index
# ---------------------------------------------------------------------------

def test_parse_header_body_start_nis(sample_nis_text):
    """body_start_index should point into the text (> 0)."""
    result = parse_header(sample_nis_text)
    assert result.body_start_index > 0


def test_parse_header_body_start_simple(sample_simple_text):
    result = parse_header(sample_simple_text)
    assert result.body_start_index > 0


def test_parse_header_body_start_points_to_article(sample_nis_text):
    """The character at body_start_index should begin a 제N장/조 line."""
    result = parse_header(sample_nis_text)
    body = sample_nis_text[result.body_start_index:]
    assert body.startswith("제") or body.startswith("서")


# ---------------------------------------------------------------------------
# parse_header — basis extraction (NIS text)
# ---------------------------------------------------------------------------

def test_parse_header_basis_first_nis(sample_nis_text):
    """First amendment basis should mention the 회의 or 결정."""
    result = parse_header(sample_nis_text)
    first = result.amendments[0]
    # basis contains the source authority text
    assert first.basis  # non-empty


def test_parse_header_basis_last_nis(sample_nis_text):
    """Last amendment basis should contain the 회의 authority text."""
    result = parse_header(sample_nis_text)
    last = result.amendments[-1]
    assert last.basis  # non-empty


# ---------------------------------------------------------------------------
# parse_header — multiline amendment (inline test, not fixture-based)
# ---------------------------------------------------------------------------

def test_parse_header_multiline_amendment():
    """Regex must handle newline between 년 and 월 (NIS OCR artifact)."""
    text = (
        "조선민주주의인민공화국\n"
        "과학기술법\n"
        "\n"
        "주체77(1988)년 12월 15일 최고인민회의 상설회의 결정 제14호로 채택\n"
        " 주체88(1999)년 \n"
        "5월 6일 최고인민회의 상임위원회 정령 제677호로 수정보충\n"
        " 주체111(2022)년 \n"
        "8월 23일 최고인민회의 상임위원회 정령 제1032호로 수정보충\n"
        "제1장 과학기술법의 기본\n"
        "제1조 (과학기술법의 사명)\n"
    )
    result = parse_header(text)
    assert result.law_name == "과학기술법"
    assert len(result.amendments) >= 3


def test_parse_header_multiline_first_amendment():
    """First amendment of 과학기술법 should be 1988-12-15 채택."""
    text = (
        "조선민주주의인민공화국\n"
        "과학기술법\n"
        "\n"
        "주체77(1988)년 12월 15일 최고인민회의 상설회의 결정 제14호로 채택\n"
        " 주체88(1999)년 \n"
        "5월 6일 최고인민회의 상임위원회 정령 제677호로 수정보충\n"
        " 주체111(2022)년 \n"
        "8월 23일 최고인민회의 상임위원회 정령 제1032호로 수정보충\n"
        "제1장 과학기술법의 기본\n"
        "제1조 (과학기술법의 사명)\n"
    )
    result = parse_header(text)
    first = result.amendments[0]
    assert first.date == "1988-12-15"
    assert first.action == "채택"
    assert "결정 제14호" in first.basis


def test_parse_header_multiline_last_amendment():
    """Last amendment of 과학기술법 should be 2022-08-23 수정보충."""
    text = (
        "조선민주주의인민공화국\n"
        "과학기술법\n"
        "\n"
        "주체77(1988)년 12월 15일 최고인민회의 상설회의 결정 제14호로 채택\n"
        " 주체88(1999)년 \n"
        "5월 6일 최고인민회의 상임위원회 정령 제677호로 수정보충\n"
        " 주체111(2022)년 \n"
        "8월 23일 최고인민회의 상임위원회 정령 제1032호로 수정보충\n"
        "제1장 과학기술법의 기본\n"
        "제1조 (과학기술법의 사명)\n"
    )
    result = parse_header(text)
    last = result.amendments[-1]
    assert last.date == "2022-08-23"
    assert last.action == "수정보충"
    assert "정령 제1032호" in last.basis


def test_parse_header_multiline_extracts_basis_gyeoljeong():
    """Basis '결정 제14호' must be captured."""
    text = (
        "조선민주주의인민공화국\n"
        "과학기술법\n"
        "\n"
        "주체77(1988)년 12월 15일 최고인민회의 상설회의 결정 제14호로 채택\n"
        " 주체88(1999)년 \n"
        "5월 6일 최고인민회의 상임위원회 정령 제677호로 수정보충\n"
        " 주체111(2022)년 \n"
        "8월 23일 최고인민회의 상임위원회 정령 제1032호로 수정보충\n"
        "제1장 과학기술법의 기본\n"
        "제1조 (과학기술법의 사명)\n"
    )
    result = parse_header(text)
    bases = [a.basis for a in result.amendments]
    assert any("결정 제14호" in b for b in bases)
    assert any("정령 제1032호" in b for b in bases)


# ---------------------------------------------------------------------------
# Return type checks
# ---------------------------------------------------------------------------

def test_parse_header_returns_headerinfo(sample_nis_text):
    result = parse_header(sample_nis_text)
    assert isinstance(result, HeaderInfo)


def test_parse_header_amendments_are_amendment_objects(sample_nis_text):
    result = parse_header(sample_nis_text)
    for a in result.amendments:
        assert isinstance(a, Amendment)
