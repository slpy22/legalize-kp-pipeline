"""
Tests for src/validate/validator.py

TDD: these tests are written first and must FAIL before implementation,
then ALL PASS after implementation.
"""
import textwrap
import pytest

from src.models import LawEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_law_file(path, frontmatter: dict, body: str) -> None:
    """Write a Markdown file with YAML frontmatter and body to *path*."""
    import yaml
    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
    content = f"---\n{fm_str}\n---\n{body}"
    path.write_text(content, encoding="utf-8")


GOOD_FRONTMATTER = {
    "제목": "로동법",
    "카테고리": "노동",
    "채택일": "1974-04-18",
    "최신버전일": "2023-09-07",
    "조문수": 3,
    "개정횟수": 1,
    "출처": "nis",
    "날짜추정": False,
    "OCR여부": False,
    "정본여부": True,
    "개정이력": [],
}

GOOD_BODY = textwrap.dedent("""\
    ## 제1장 일반원칙

    ##### 제1조 (정의)
    이 법은 로동관계를 규제한다.

    ##### 제2조 (원칙)
    국가는 로동조건을 개선한다.

    ##### 제3조 (권리)
    공민은 로동의 권리를 가진다.
""")


# ---------------------------------------------------------------------------
# test_validate_good_file
# ---------------------------------------------------------------------------

def test_validate_good_file(tmp_path):
    """A fully valid file should return status='success'."""
    from src.validate.validator import validate_law_file

    law_file = tmp_path / "법령.md"
    _write_law_file(law_file, GOOD_FRONTMATTER, GOOD_BODY)

    result = validate_law_file(str(law_file), expected_articles=3)

    assert result["status"] == "success", f"Expected success, got: {result}"
    assert str(law_file) == result["file"]


# ---------------------------------------------------------------------------
# test_validate_article_count_mismatch
# ---------------------------------------------------------------------------

def test_validate_article_count_mismatch(tmp_path):
    """When expected_articles=5 but file has 3, return status='warning' mentioning '조문수'."""
    from src.validate.validator import validate_law_file

    law_file = tmp_path / "법령.md"
    _write_law_file(law_file, GOOD_FRONTMATTER, GOOD_BODY)

    result = validate_law_file(str(law_file), expected_articles=5)

    assert result["status"] == "warning", f"Expected warning, got: {result}"
    assert "조문수" in result["message"], f"Expected '조문수' in message: {result['message']}"


# ---------------------------------------------------------------------------
# test_validate_missing_required_field
# ---------------------------------------------------------------------------

def test_validate_missing_required_field(tmp_path):
    """File with only '제목' field should return status='warning' mentioning '필수 필드'."""
    from src.validate.validator import validate_law_file

    law_file = tmp_path / "법령.md"
    sparse_fm = {"제목": "로동법"}
    _write_law_file(law_file, sparse_fm, GOOD_BODY)

    result = validate_law_file(str(law_file))

    assert result["status"] == "warning", f"Expected warning, got: {result}"
    assert "필수 필드" in result["message"], f"Expected '필수 필드' in message: {result['message']}"


# ---------------------------------------------------------------------------
# test_validate_empty_body
# ---------------------------------------------------------------------------

def test_validate_empty_body(tmp_path):
    """File with frontmatter but no body should return status='failure'."""
    from src.validate.validator import validate_law_file

    law_file = tmp_path / "법령.md"
    _write_law_file(law_file, GOOD_FRONTMATTER, "")

    result = validate_law_file(str(law_file))

    assert result["status"] == "failure", f"Expected failure, got: {result}"


# ---------------------------------------------------------------------------
# test_validate_all
# ---------------------------------------------------------------------------

def test_validate_all(tmp_path):
    """validate_all with 2 entries: one file exists (good), one does not → failures=1."""
    from src.validate.validator import validate_all

    # Entry 1: create a valid file
    entry1 = LawEntry(name="로동법", category="노동", total_articles=3)
    law_dir = tmp_path / "로동법"
    law_dir.mkdir()
    law_file = law_dir / "법령.md"
    _write_law_file(law_file, GOOD_FRONTMATTER, GOOD_BODY)

    # Entry 2: no file created (missing)
    entry2 = LawEntry(name="가족법", category="가족", total_articles=5)

    result = validate_all(str(tmp_path), [entry1, entry2])

    assert result["total_laws"] == 2
    assert result["failures"] >= 1, f"Expected at least 1 failure: {result}"
    assert len(result["details"]) == 2

    # The missing file entry must be a failure
    missing = next(d for d in result["details"] if d["law_name"] == "가족법")
    assert missing["status"] == "failure"
