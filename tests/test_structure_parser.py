"""
Tests for structure_parser.py — parse_structure(text) -> list[ArticleNode]

Covers:
  - Chapters with nested articles
  - Articles with numbered items (호)
  - 부칙 (appendix) as a top-level node
  - Laws with no chapters (flat article list)
  - Article count helpers
"""
import pytest
from src.parser.structure_parser import parse_structure
from src.models import ArticleNode


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_by_level(nodes: list, level: str) -> list:
    """Recursively collect all nodes with the given level string."""
    result = []
    for node in nodes:
        if node.level == level:
            result.append(node)
        result.extend(_find_by_level(node.children, level))
    return result


def _count_articles(nodes: list) -> int:
    """Count all 조-level nodes recursively."""
    return len(_find_by_level(nodes, "조"))


# ---------------------------------------------------------------------------
# Test 1: Two chapters with articles
# ---------------------------------------------------------------------------

def test_parse_chapters():
    """Two chapters, first has 2 articles, second has 1."""
    text = """제1장 과학기술법의 기본

제1조 (과학기술법의 사명)
본문 내용이다.
제2조 (과학기술중시원칙)
국가는 과학기술을 발전시킨다.

제2장 과학기술발전계획

제3조 (계획작성원칙)
계획을 세운다."""

    result = parse_structure(text)

    # Should have exactly 2 top-level chapter nodes
    chapters = [n for n in result if n.level == "장"]
    assert len(chapters) == 2, f"Expected 2 chapters, got {len(chapters)}"

    ch1, ch2 = chapters
    assert ch1.number == "1"
    assert ch1.title == "과학기술법의 기본"

    # First chapter has 2 article children
    articles_in_ch1 = [c for c in ch1.children if c.level == "조"]
    assert len(articles_in_ch1) == 2, f"Expected 2 articles in ch1, got {len(articles_in_ch1)}"

    # Second chapter has 1 article child
    articles_in_ch2 = [c for c in ch2.children if c.level == "조"]
    assert len(articles_in_ch2) == 1, f"Expected 1 article in ch2, got {len(articles_in_ch2)}"

    # Article titles are extracted correctly
    assert articles_in_ch1[0].title == "과학기술법의 사명"
    assert articles_in_ch1[1].title == "과학기술중시원칙"
    assert articles_in_ch2[0].title == "계획작성원칙"


# ---------------------------------------------------------------------------
# Test 2: Article with numbered items (호)
# ---------------------------------------------------------------------------

def test_parse_articles_with_items():
    """Article with numbered items (호) as children."""
    text = """제1장 기본

제1조 (대상)
다음의 행위를 할수 없다.
 1. 쏘프트웨어를 복제하는 행위
 2. 쏘프트웨어를 배포하는 행위"""

    result = parse_structure(text)

    # Navigate to the article
    chapters = [n for n in result if n.level == "장"]
    assert len(chapters) == 1

    articles = [c for c in chapters[0].children if c.level == "조"]
    assert len(articles) == 1

    article = articles[0]
    assert article.title == "대상"

    # Article should have 2 호 children
    ho_children = [c for c in article.children if c.level == "호"]
    assert len(ho_children) == 2, f"Expected 2 호 children, got {len(ho_children)}"

    assert "복제" in ho_children[0].content
    assert "배포" in ho_children[1].content


# ---------------------------------------------------------------------------
# Test 3: 부칙 (appendix) as a separate node
# ---------------------------------------------------------------------------

def test_parse_appendix():
    """부칙 appears as a top-level node after chapters."""
    text = """제1장 기본

제1조 (사명)
본문이다.

부칙

이 법은 공포한 날부터 시행한다."""

    result = parse_structure(text)

    # Find the 부칙 node
    appendix_nodes = [n for n in result if n.level == "부칙"]
    assert len(appendix_nodes) == 1, f"Expected 1 부칙 node, got {len(appendix_nodes)}"

    appendix = appendix_nodes[0]
    assert appendix.number == "부칙"
    # Content should include the implementation date line
    assert appendix.content is not None
    assert "시행" in appendix.content


# ---------------------------------------------------------------------------
# Test 4: Law with only articles, no chapters
# ---------------------------------------------------------------------------

def test_parse_no_chapter():
    """Law with only articles, no chapters — articles are root-level nodes."""
    text = """제1조 (사명)
본문이다.
제2조 (적용범위)
범위를 정한다."""

    result = parse_structure(text)

    # All top-level nodes should be 조-level
    articles = [n for n in result if n.level == "조"]
    assert len(articles) == 2, f"Expected 2 root articles, got {len(articles)}"

    assert articles[0].number == "1"
    assert articles[0].title == "사명"
    assert articles[1].number == "2"
    assert articles[1].title == "적용범위"


# ---------------------------------------------------------------------------
# Test 5: Article count across chapters
# ---------------------------------------------------------------------------

def test_article_count():
    """Count total articles: 3 articles under 1 chapter."""
    text = """제1장 기본원칙

제1조 (목적)
이 법의 목적이다.
제2조 (적용범위)
이 법은 전국에 적용된다.
제3조 (원칙)
기본원칙을 지킨다."""

    result = parse_structure(text)

    total = _count_articles(result)
    assert total == 3, f"Expected 3 articles, got {total}"


# ---------------------------------------------------------------------------
# Test 6: 편 > 장 > 조 deep nesting
# ---------------------------------------------------------------------------

def test_parse_deep_nesting():
    """편 contains 장 which contains 조."""
    text = """제1편 총칙

제1장 일반원칙

제1조 (목적)
목적이다.

제2장 기본원칙

제2조 (기본)
기본이다.

제2편 각칙

제3장 세부사항

제3조 (세부)
세부사항이다."""

    result = parse_structure(text)

    # Two 편 nodes at root
    parts = [n for n in result if n.level == "편"]
    assert len(parts) == 2

    # First 편 has 2 chapters
    chapters_in_p1 = [c for c in parts[0].children if c.level == "장"]
    assert len(chapters_in_p1) == 2

    # Second 편 has 1 chapter
    chapters_in_p2 = [c for c in parts[1].children if c.level == "장"]
    assert len(chapters_in_p2) == 1

    # Total articles = 3
    assert _count_articles(result) == 3


# ---------------------------------------------------------------------------
# Test 7: Article content is accumulated correctly
# ---------------------------------------------------------------------------

def test_article_content_accumulation():
    """Multi-line article content is joined and stored."""
    text = """제1조 (내용)
첫번째 줄이다.
두번째 줄이다.
세번째 줄이다."""

    result = parse_structure(text)

    assert len(result) == 1
    article = result[0]
    assert article.content is not None
    assert "첫번째" in article.content
    assert "두번째" in article.content
    assert "세번째" in article.content


# ---------------------------------------------------------------------------
# Test 8: 절 (section) nesting under 장
# ---------------------------------------------------------------------------

def test_parse_sections():
    """절 nodes appear as children of 장."""
    text = """제1장 총칙

제1절 일반규정

제1조 (목적)
목적이다.

제2절 특별규정

제2조 (특별)
특별이다."""

    result = parse_structure(text)

    chapters = [n for n in result if n.level == "장"]
    assert len(chapters) == 1

    sections = [c for c in chapters[0].children if c.level == "절"]
    assert len(sections) == 2

    assert sections[0].title == "일반규정"
    assert sections[1].title == "특별규정"

    # Articles are under sections
    art1 = [c for c in sections[0].children if c.level == "조"]
    art2 = [c for c in sections[1].children if c.level == "조"]
    assert len(art1) == 1
    assert len(art2) == 1
