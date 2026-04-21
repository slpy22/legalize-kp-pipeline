"""
Tests for src/models.py data classes.
"""
import pytest
from src.models import ArticleNode, LawEntry, LawVersion


# ---------------------------------------------------------------------------
# LawVersion tests
# ---------------------------------------------------------------------------

class TestLawVersion:
    def test_basic_creation(self):
        v = LawVersion(date="1974-04-18", action="제정", source="nis")
        assert v.date == "1974-04-18"
        assert v.action == "제정"
        assert v.source == "nis"

    def test_defaults(self):
        v = LawVersion(date="2023-09-07", action="수정보충", source="mobu")
        assert v.text is None
        assert v.text_available is False
        assert v.date_estimated is False
        assert v.enactment_basis is None

    def test_with_text(self):
        v = LawVersion(
            date="2023-09-07",
            action="수정보충",
            source="nis",
            text="제1조 이 법은...",
            text_available=True,
        )
        assert v.text_available is True
        assert v.text.startswith("제1조")

    def test_estimated_date(self):
        v = LawVersion(date="2020-01-01", action="수정보충", source="unknown",
                       date_estimated=True)
        assert v.date_estimated is True

    def test_enactment_basis(self):
        v = LawVersion(date="1972-12-27", action="채택", source="nis",
                       enactment_basis="최고인민회의 제5기 제1차회의")
        assert "최고인민회의" in v.enactment_basis


# ---------------------------------------------------------------------------
# LawEntry tests
# ---------------------------------------------------------------------------

class TestLawEntry:
    def test_basic_creation(self):
        entry = LawEntry(name="로동법", category="경제")
        assert entry.name == "로동법"
        assert entry.category == "경제"

    def test_defaults(self):
        entry = LawEntry(name="로동법", category="경제")
        assert entry.enactment_date is None
        assert entry.latest_version_date is None
        assert entry.total_articles is None
        assert entry.chapter_count is None
        assert entry.amendment_count == 0
        assert entry.chapters == []
        assert entry.has_appendix is False
        assert entry.in_nis is False
        assert entry.in_mobu is False
        assert entry.nis_volume is None
        assert entry.nis_page is None
        assert entry.mobu_key is None
        assert entry.mobu_files == []
        assert entry.is_constitutional is False
        assert entry.is_ocr is False
        assert entry.ocr_confidence is None
        assert entry.versions == []

    def test_versions_list(self):
        v1 = LawVersion(date="1974-04-18", action="제정", source="nis")
        v2 = LawVersion(date="2023-09-07", action="수정보충", source="mobu")
        entry = LawEntry(name="로동법", category="경제", versions=[v1, v2])
        assert len(entry.versions) == 2
        assert entry.versions[0].action == "제정"
        assert entry.versions[1].action == "수정보충"

    def test_versions_list_mutable_default(self):
        """Two separate LawEntry instances must not share the same versions list."""
        e1 = LawEntry(name="로동법", category="경제")
        e2 = LawEntry(name="가족법", category="사회")
        e1.versions.append(LawVersion(date="1974-04-18", action="제정", source="nis"))
        assert len(e2.versions) == 0

    def test_chapters_list_mutable_default(self):
        """Two separate LawEntry instances must not share the same chapters list."""
        e1 = LawEntry(name="로동법", category="경제")
        e2 = LawEntry(name="가족법", category="사회")
        e1.chapters.append("제1장 일반원칙")
        assert len(e2.chapters) == 0

    def test_mobu_files_mutable_default(self):
        """Two separate LawEntry instances must not share the same mobu_files list."""
        e1 = LawEntry(name="로동법", category="경제")
        e2 = LawEntry(name="가족법", category="사회")
        e1.mobu_files.append("rodong_2023.txt")
        assert len(e2.mobu_files) == 0

    def test_full_fields(self):
        entry = LawEntry(
            name="로동법",
            category="경제",
            enactment_date="1974-04-18",
            latest_version_date="2023-09-07",
            total_articles=50,
            chapter_count=5,
            amendment_count=10,
            chapters=["제1장 일반원칙", "제2장 로동과 휴식"],
            has_appendix=False,
            in_nis=True,
            in_mobu=True,
            nis_volume=3,
            nis_page=245,
            mobu_key="rodong",
            mobu_files=["rodong_2023.txt"],
        )
        assert entry.total_articles == 50
        assert entry.chapter_count == 5
        assert entry.amendment_count == 10
        assert entry.nis_volume == 3
        assert entry.nis_page == 245
        assert entry.mobu_key == "rodong"
        assert len(entry.mobu_files) == 1


# ---------------------------------------------------------------------------
# LawEntry.file_type property tests
# ---------------------------------------------------------------------------

class TestLawEntryFileType:
    def test_regular_law_file_type(self):
        entry = LawEntry(name="로동법", category="경제", is_constitutional=False)
        assert entry.file_type == "법령"

    def test_constitutional_law_file_type(self):
        entry = LawEntry(name="사회주의헌법", category="헌법", is_constitutional=True)
        assert entry.file_type == "헌법"

    def test_regular_law_file_name(self):
        entry = LawEntry(name="로동법", category="경제", is_constitutional=False)
        assert entry.file_name == "법령.md"

    def test_constitutional_law_file_name(self):
        entry = LawEntry(name="사회주의헌법", category="헌법", is_constitutional=True)
        assert entry.file_name == "헌법.md"

    def test_dir_name_equals_law_name(self):
        entry = LawEntry(name="가족법", category="사회")
        assert entry.dir_name == "가족법"

    def test_dir_name_constitutional(self):
        entry = LawEntry(name="사회주의헌법", category="헌법", is_constitutional=True)
        assert entry.dir_name == "사회주의헌법"


# ---------------------------------------------------------------------------
# ArticleNode tests
# ---------------------------------------------------------------------------

class TestArticleNode:
    def test_basic_creation(self):
        node = ArticleNode(level=2, number="제1조")
        assert node.level == 2
        assert node.number == "제1조"
        assert node.title is None
        assert node.content is None
        assert node.children == []

    def test_with_content(self):
        node = ArticleNode(
            level=2,
            number="제1조",
            content="이 법은 공화국의 로동관계를 규제하는 기본법이다.",
        )
        assert "로동관계" in node.content

    def test_children_mutable_default(self):
        """Two separate ArticleNode instances must not share the same children list."""
        n1 = ArticleNode(level=1, number="제1장")
        n2 = ArticleNode(level=1, number="제2장")
        n1.children.append(ArticleNode(level=2, number="제1조"))
        assert len(n2.children) == 0

    def test_nested_structure(self):
        article = ArticleNode(level=2, number="제1조",
                              content="이 법은 공화국의 로동관계를 규제하는 기본법이다.")
        chapter = ArticleNode(level=1, number="제1장", title="일반원칙",
                              children=[article])
        assert len(chapter.children) == 1
        assert chapter.children[0].number == "제1조"
