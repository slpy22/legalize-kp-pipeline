"""
Tests for markdown_writer.py — generate_frontmatter, generate_markdown, write_law_file.

TDD: these tests are written before the implementation.
"""
import yaml
import pytest

from src.models import LawEntry, ArticleNode
from src.parser.markdown_writer import (
    generate_frontmatter,
    generate_markdown,
    write_law_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(**kwargs) -> LawEntry:
    defaults = dict(
        name="저작권법",
        category="문화예술",
        enactment_date="1986-01-15",
        latest_version_date="2021-09-22",
        total_articles=50,
        chapter_count=5,
        amendment_count=3,
        in_nis=True,
        nis_volume=2,
        nis_page=145,
        mobu_key="copyright-001",
        is_ocr=False,
        ocr_confidence=None,
        is_constitutional=False,
    )
    defaults.update(kwargs)
    return LawEntry(**defaults)


def _make_amendments() -> list:
    return [
        {"일자": "1986-01-15", "내용": "채택"},
        {"일자": "2010-06-30", "내용": "수정보충"},
        {"일자": "2021-09-22", "내용": "수정보충"},
    ]


# ---------------------------------------------------------------------------
# test_generate_frontmatter
# ---------------------------------------------------------------------------

def test_generate_frontmatter():
    """Frontmatter YAML contains all required fields."""
    entry = _make_entry()
    amendments = _make_amendments()

    raw = generate_frontmatter(entry, amendments=amendments, source="nis")
    data = yaml.safe_load(raw)

    assert data["제목"] == "저작권법"
    assert data["카테고리"] == "문화예술"
    assert data["채택일"] == "1986-01-15"
    assert data["출처"] == "nis"
    assert len(data["개정이력"]) == 3


def test_generate_frontmatter_optional_fields():
    """Required numeric fields are present; None fields are omitted."""
    entry = _make_entry(nis_page=None, mobu_key=None, ocr_confidence=None)
    raw = generate_frontmatter(entry, amendments=[], source="unknown")
    data = yaml.safe_load(raw)

    # None-valued optional fields should be absent
    assert "국정원페이지" not in data
    assert "법무부키" not in data
    assert "OCR신뢰도" not in data

    # Required fields must still be present
    assert "제목" in data
    assert "카테고리" in data


def test_generate_frontmatter_text_unavailable():
    """텍스트미확보 flag appears only when text_unavailable=True."""
    entry = _make_entry()

    raw_no_flag = generate_frontmatter(entry, amendments=[], source="nis", text_unavailable=False)
    data_no = yaml.safe_load(raw_no_flag)
    assert "텍스트미확보" not in data_no

    raw_with_flag = generate_frontmatter(entry, amendments=[], source="nis", text_unavailable=True)
    data_yes = yaml.safe_load(raw_with_flag)
    assert data_yes.get("텍스트미확보") is True


def test_generate_frontmatter_ocr_fields():
    """OCR 여부 and OCR신뢰도 are serialized when available."""
    entry = _make_entry(is_ocr=True, ocr_confidence=0.92)
    raw = generate_frontmatter(entry, amendments=[], source="nis")
    data = yaml.safe_load(raw)

    assert data["OCR여부"] is True
    assert abs(data["OCR신뢰도"] - 0.92) < 1e-6


# ---------------------------------------------------------------------------
# test_generate_markdown — headings
# ---------------------------------------------------------------------------

def test_generate_markdown_chapter_heading():
    """장 becomes ## and 조 becomes ##### with title."""
    chapter = ArticleNode(level="장", number="1", title="기본", children=[
        ArticleNode(level="조", number="1", title="사명", content="이 법은 기본법이다.", children=[]),
    ])
    output = generate_markdown([chapter])

    assert "## 제1장 기본" in output
    assert "##### 제1조 (사명)" in output


def test_generate_markdown_part_heading():
    """편 becomes # heading."""
    part = ArticleNode(level="편", number="1", title="총칙", children=[])
    output = generate_markdown([part])
    assert "# 제1편 총칙" in output


def test_generate_markdown_section_heading():
    """절 becomes ### heading."""
    section = ArticleNode(level="절", number="2", title="특별규정", children=[])
    output = generate_markdown([section])
    assert "### 제2절 특별규정" in output


def test_generate_markdown_subsection_heading():
    """관 becomes #### heading."""
    subsec = ArticleNode(level="관", number="1", title="일반관", children=[])
    output = generate_markdown([subsec])
    assert "#### 제1관 일반관" in output


def test_generate_markdown_appendix():
    """부칙 node becomes ## 부칙 (no number in heading)."""
    appendix = ArticleNode(level="부칙", number="부칙", title=None, content="공포한 날부터 시행한다.", children=[])
    output = generate_markdown([appendix])
    assert "## 부칙" in output


# ---------------------------------------------------------------------------
# test_generate_markdown — items (호, 목)
# ---------------------------------------------------------------------------

def test_generate_markdown_items():
    """호 children render as 2-space-indented numbered list items."""
    article = ArticleNode(
        level="조", number="1", title="대상",
        content="다음을 금지한다.",
        children=[
            ArticleNode(level="호", number="1", title=None, content="복제", children=[]),
            ArticleNode(level="호", number="2", title=None, content="배포", children=[]),
        ],
    )
    output = generate_markdown([article])
    assert "  1. 복제" in output
    assert "  2. 배포" in output


def test_generate_markdown_mok():
    """목 children render as 4-space-indented items with Korean label."""
    ho_node = ArticleNode(
        level="호", number="1", title=None, content="다음의 경우",
        children=[
            ArticleNode(level="목", number="가", title=None, content="첫번째 목", children=[]),
            ArticleNode(level="목", number="나", title=None, content="두번째 목", children=[]),
        ],
    )
    article = ArticleNode(level="조", number="1", title="항목", content=None, children=[ho_node])
    output = generate_markdown([article])
    assert "    가) 첫번째 목" in output
    assert "    나) 두번째 목" in output


# ---------------------------------------------------------------------------
# test_generate_markdown — multi-node separation
# ---------------------------------------------------------------------------

def test_generate_markdown_double_newline_between_nodes():
    """Top-level nodes are separated by a double newline."""
    nodes = [
        ArticleNode(level="장", number="1", title="제1장", children=[]),
        ArticleNode(level="장", number="2", title="제2장", children=[]),
    ]
    output = generate_markdown(nodes)
    assert "\n\n" in output


# ---------------------------------------------------------------------------
# test_write_law_file
# ---------------------------------------------------------------------------

def test_write_law_file(tmp_path):
    """write_law_file creates a properly structured Markdown file."""
    entry = _make_entry()
    amendments = _make_amendments()
    tree = [
        ArticleNode(level="장", number="1", title="기본", children=[
            ArticleNode(level="조", number="1", title="목적", content="이 법은 저작권을 보호한다.", children=[]),
        ]),
    ]
    out_path = tmp_path / "저작권법" / "법령.md"

    write_law_file(entry, tree, amendments=amendments, output_path=str(out_path), source="nis")

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")

    # File must start with ---
    assert content.startswith("---\n")
    # Frontmatter closing delimiter
    assert "---\n\n" in content
    # Body contains chapter heading
    assert "## 제1장 기본" in content
    # Body contains article heading
    assert "##### 제1조 (목적)" in content

    # Parse frontmatter
    fm_block = content.split("---\n")[1]
    data = yaml.safe_load(fm_block)
    assert data["제목"] == "저작권법"
    assert len(data["개정이력"]) == 3
