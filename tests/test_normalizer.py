"""
Tests for src/parser/normalizer.py — normalize_text()

TDD order: write tests first, then implement normalizer.
Each test targets exactly one normalization rule.
"""
import pytest
from src.parser.normalizer import normalize_text


# ---------------------------------------------------------------------------
# Rule 4 & 5: Tab handling
# ---------------------------------------------------------------------------

class TestCollapseTabsToSpace:
    r"""Rule 5: remaining \t → single space."""

    def test_single_tab_replaced(self):
        result = normalize_text("가나\t다라")
        assert "가나 다라" in result

    def test_multiple_tabs_collapsed(self):
        # after tab→space, multiple spaces collapse (rule 7)
        result = normalize_text("가나\t\t다라")
        assert "가나 다라" in result

    def test_tab_only_line_becomes_blank(self):
        result = normalize_text("가나\n\t\n다라")
        # the middle line becomes empty/blank; content lines are preserved
        lines = result.split("\n")
        assert "가나" in lines
        assert "다라" in lines


class TestCollapseTabNewline:
    r"""Rule 4: \t\s*\n → single space (NIS article-number artifact)."""

    def test_tab_newline_joined(self):
        # "제1조\t\n(사명)" → "제1조 (사명)"  (on same line after join)
        result = normalize_text("제1조\t\n(사명)")
        assert "제1조 (사명)" in result

    def test_tab_spaces_newline_joined(self):
        result = normalize_text("제2조\t   \n내용")
        assert "제2조 내용" in result

    def test_tab_newline_full_article(self):
        text = "제1조\t\n이 법은 기본법이다."
        result = normalize_text(text)
        assert "제1조 이 법은 기본법이다." in result


# ---------------------------------------------------------------------------
# Rule 1: NIS page header removal
# ---------------------------------------------------------------------------

class TestRemovePageHeaderNis:
    r"""Rule 1: lines matching ^\d+\s+북한\s*법령집\s*[上下]$ are removed."""

    def test_header_upper(self):
        text = "앞줄\n123 북한법령집 上\n뒷줄"
        result = normalize_text(text)
        assert "북한법령집" not in result
        assert "앞줄" in result
        assert "뒷줄" in result

    def test_header_lower(self):
        text = "내용\n45 북한 법령집 下\n더내용"
        result = normalize_text(text)
        assert "북한 법령집" not in result

    def test_header_no_space_between_북한_법령집(self):
        # 북한법령집 (no space) also matches \s*
        text = "내용\n7 북한법령집上\n더내용"
        result = normalize_text(text)
        assert "북한법령집" not in result

    def test_non_header_preserved(self):
        text = "이것은 북한법령집에 관한 설명이다."
        result = normalize_text(text)
        assert "북한법령집" in result


# ---------------------------------------------------------------------------
# Rule 2: NIS page footer removal
# ---------------------------------------------------------------------------

class TestRemovePageFooterNis:
    r"""Rule 2: short lines matching ^조선민주주의인민공화국\s+.+\s+\d+$ removed."""

    def test_footer_basic(self):
        text = "내용\n조선민주주의인민공화국 로동법 123\n다음내용"
        result = normalize_text(text)
        assert "조선민주주의인민공화국 로동법 123" not in result
        assert "내용" in result
        assert "다음내용" in result

    def test_footer_longer_title(self):
        text = "앞\n조선민주주의인민공화국 사회주의헌법 45\n뒤"
        result = normalize_text(text)
        assert "사회주의헌법 45" not in result

    def test_footer_too_long_preserved(self):
        # Lines >= 80 chars should NOT be removed even if they match pattern
        # "조선민주주의인민공화국" = 11 chars + 1 space + title + " 1" (2 chars)
        # Need total >= 80, so title >= 66 chars
        long_title = "가" * 70  # 70 chars → total line = 84 chars
        text = f"조선민주주의인민공화국 {long_title} 1"
        result = normalize_text(text)
        assert "조선민주주의인민공화국" in result

    def test_footer_without_trailing_number_preserved(self):
        text = "조선민주주의인민공화국 로동법"
        result = normalize_text(text)
        assert "조선민주주의인민공화국 로동법" in result


# ---------------------------------------------------------------------------
# Rule 3: Standalone page number removal
# ---------------------------------------------------------------------------

class TestRemoveTrailingPageNumber:
    r"""Rule 3: lines matching ^\d{1,4}$ are removed."""

    def test_single_digit(self):
        result = normalize_text("앞\n5\n뒤")
        lines = [l for l in result.split("\n") if l.strip()]
        assert "5" not in lines

    def test_four_digits(self):
        result = normalize_text("앞\n1234\n뒤")
        lines = [l for l in result.split("\n") if l.strip()]
        assert "1234" not in lines

    def test_five_digits_preserved(self):
        result = normalize_text("앞\n12345\n뒤")
        assert "12345" in result

    def test_number_with_text_preserved(self):
        result = normalize_text("앞\n3항\n뒤")
        assert "3항" in result


# ---------------------------------------------------------------------------
# Rule 9: Blank line collapsing
# ---------------------------------------------------------------------------

class TestNormalizeBlankLines:
    """Rule 9: 3+ consecutive newlines → 2 newlines (one blank line)."""

    def test_three_newlines_collapsed(self):
        result = normalize_text("가나\n\n\n다라")
        assert "\n\n\n" not in result
        assert "가나" in result
        assert "다라" in result

    def test_five_newlines_collapsed(self):
        result = normalize_text("가나\n\n\n\n\n다라")
        assert "\n\n\n" not in result

    def test_two_newlines_preserved(self):
        # Exactly two newlines (one blank line) should be kept
        result = normalize_text("가나\n\n다라")
        assert "\n\n" in result

    def test_single_newline_preserved(self):
        # Lines not eligible for Hangul-join (end/start with non-Hangul)
        # should keep the newline between them.
        result = normalize_text("가나다.\n라마바.")
        assert "가나다.\n라마바." in result


# ---------------------------------------------------------------------------
# Rule 8: Strip lines
# ---------------------------------------------------------------------------

class TestStripLines:
    """Rule 8: leading/trailing whitespace stripped per line."""

    def test_leading_spaces_stripped(self):
        result = normalize_text("   앞내용")
        assert result.strip().startswith("앞내용")

    def test_trailing_spaces_stripped(self):
        result = normalize_text("뒷내용   ")
        assert result.strip().endswith("뒷내용")

    def test_mixed_whitespace_stripped(self):
        result = normalize_text("   내용   ")
        assert "내용" in result
        for line in result.split("\n"):
            assert line == line.strip()


# ---------------------------------------------------------------------------
# Rule 7: Collapse multiple spaces
# ---------------------------------------------------------------------------

class TestCollapseWhitespace:
    """Rule 7: multiple consecutive spaces collapsed to one (per line)."""

    def test_double_space_collapsed(self):
        result = normalize_text("가나  다라")
        assert "가나 다라" in result

    def test_many_spaces_collapsed(self):
        result = normalize_text("가나     다라")
        assert "가나 다라" in result

    def test_single_space_unchanged(self):
        result = normalize_text("가나 다라")
        assert "가나 다라" in result


# ---------------------------------------------------------------------------
# Rule 6: Join broken Korean words (Hangul-to-Hangul line wrap)
# ---------------------------------------------------------------------------

class TestJoinBrokenLines:
    """Rule 6: line ending Hangul + next line starting Hangul → joined (no newline)."""

    def test_simple_hangul_join(self):
        # "연구개\n발" → "연구개발"
        result = normalize_text("연구개\n발")
        assert "연구개발" in result

    def test_no_join_when_space_separates(self):
        # If a blank line separates them, they should NOT be joined
        result = normalize_text("연구개\n\n발")
        assert "연구개\n\n발" in result or ("연구개" in result and "발" in result and "연구개발" not in result)

    def test_no_join_latin_start(self):
        # Next line starts with non-Hangul → no join
        result = normalize_text("가나다\nabc")
        assert "가나다\nabc" in result

    def test_no_join_latin_end(self):
        # Current line ends with non-Hangul → no join
        result = normalize_text("abc\n가나다")
        assert "abc\n가나다" in result

    def test_hangul_join_multiline(self):
        text = "이것은 연구개\n발에 관한 내용이다"
        result = normalize_text(text)
        assert "연구개발에" in result

    def test_article_not_joined_across_blank(self):
        # Blank line between articles must remain a separator
        text = "기본법이다.\n\n제2조"
        result = normalize_text(text)
        assert "기본법이다." in result
        assert "제2조" in result
        # They should NOT be joined
        assert "기본법이다.제2조" not in result


# ---------------------------------------------------------------------------
# Integration: full pipeline smoke test
# ---------------------------------------------------------------------------

class TestIntegration:
    """Smoke tests combining multiple rules on realistic NIS text."""

    def test_nis_article_tab_newline_cleaned(self):
        text = "제1조\t\n이 법은 기본법이다.\n\n제2조\t\n국가는 힘쓴다."
        result = normalize_text(text)
        assert "제1조 이 법은 기본법이다." in result
        assert "제2조 국가는 힘쓴다." in result

    def test_headers_footers_page_numbers_removed(self):
        text = (
            "내용줄\n"
            "123 북한법령집 上\n"
            "조선민주주의인민공화국 로동법 45\n"
            "46\n"
            "다음내용줄"
        )
        result = normalize_text(text)
        assert "북한법령집" not in result
        assert "로동법 45" not in result
        assert "내용줄" in result
        assert "다음내용줄" in result

    def test_output_is_stripped(self):
        result = normalize_text("\n\n가나다\n\n")
        assert result == result.strip()
