"""
Tests for src/merger/source_merger.py

TDD: these tests are written first; the implementation must make them pass.
"""
import json
import os
import pytest

from src.merger.source_merger import (
    CONSTITUTIONAL_NAMES,
    load_master_list,
    find_text_files,
    merge_sources,
)
from src.models import LawEntry, LawVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_master_json(tmp_path, laws: list) -> str:
    """Write a minimal master-list JSON and return its path."""
    data = {"total_laws": len(laws), "laws": laws}
    p = tmp_path / "마스터목록.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# CONSTITUTIONAL_NAMES
# ---------------------------------------------------------------------------

class TestConstitutionalNames:
    def test_contains_expected_entries(self):
        assert "사회주의헌법" in CONSTITUTIONAL_NAMES
        assert "조선로동당규약" in CONSTITUTIONAL_NAMES
        assert "당의유일적령도체계확립의 10대 원칙" in CONSTITUTIONAL_NAMES

    def test_is_a_set(self):
        assert isinstance(CONSTITUTIONAL_NAMES, (set, frozenset))


# ---------------------------------------------------------------------------
# load_master_list
# ---------------------------------------------------------------------------

class TestLoadMasterList:
    def _sample_law(self):
        return {
            "name": "과학기술법",
            "category": "과학기술·지적소유권·체신",
            "latest_version_date": "2022-08-23",
            "enactment_date": "1988-12-15",
            "amendment_count": 9,
            "total_articles": 91,
            "chapter_count": 8,
            "chapters": ["기본", "발전계획"],
            "has_appendix": False,
            "in_mobu": True,
            "in_nis2024": True,
            "mobu_files": ["과학기술법(2013.10.23.).hwp"],
            "nis_volume": "하권",
            "nis_page": 533,
        }

    def test_returns_list_of_law_entry(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entries = load_master_list(path)
        assert isinstance(entries, list)
        assert len(entries) == 1
        assert isinstance(entries[0], LawEntry)

    def test_basic_fields_mapped(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.name == "과학기술법"
        assert entry.category == "과학기술·지적소유권·체신"
        assert entry.latest_version_date == "2022-08-23"
        assert entry.enactment_date == "1988-12-15"
        assert entry.amendment_count == 9
        assert entry.total_articles == 91
        assert entry.chapter_count == 8
        assert entry.has_appendix is False

    def test_in_nis2024_maps_to_in_nis(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.in_nis is True

    def test_in_mobu_mapped(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.in_mobu is True

    def test_mobu_files_mapped(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.mobu_files == ["과학기술법(2013.10.23.).hwp"]

    def test_chapters_mapped(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.chapters == ["기본", "발전계획"]

    def test_is_constitutional_false_for_regular_law(self, tmp_path):
        path = _make_master_json(tmp_path, [self._sample_law()])
        entry = load_master_list(path)[0]
        assert entry.is_constitutional is False

    def test_is_constitutional_true_for_헌법(self, tmp_path):
        law = self._sample_law()
        law["name"] = "사회주의헌법"
        path = _make_master_json(tmp_path, [law])
        entry = load_master_list(path)[0]
        assert entry.is_constitutional is True

    def test_is_constitutional_true_for_당규약(self, tmp_path):
        law = self._sample_law()
        law["name"] = "조선로동당규약"
        path = _make_master_json(tmp_path, [law])
        entry = load_master_list(path)[0]
        assert entry.is_constitutional is True

    def test_multiple_laws(self, tmp_path):
        law2 = self._sample_law()
        law2["name"] = "로동법"
        path = _make_master_json(tmp_path, [self._sample_law(), law2])
        entries = load_master_list(path)
        assert len(entries) == 2

    def test_in_nis2024_false(self, tmp_path):
        law = self._sample_law()
        law["in_nis2024"] = False
        path = _make_master_json(tmp_path, [law])
        entry = load_master_list(path)[0]
        assert entry.in_nis is False

    def test_missing_optional_fields_use_defaults(self, tmp_path):
        """A minimal law dict with only required fields should load without error."""
        minimal = {"name": "최소법", "category": "기타"}
        path = _make_master_json(tmp_path, [minimal])
        entry = load_master_list(path)[0]
        assert entry.name == "최소법"
        assert entry.amendment_count == 0
        assert entry.mobu_files == []
        assert entry.chapters == []


# ---------------------------------------------------------------------------
# find_text_files
# ---------------------------------------------------------------------------

class TestFindTextFilesNis:
    """NIS directory: category/lawname.txt — 2-part path → current version."""

    def _make_nis_dir(self, tmp_path):
        nis = tmp_path / "국정원2024" / "변환텍스트"
        cat = nis / "과학기술·지적소유권·체신"
        cat.mkdir(parents=True)
        (cat / "과학기술법.txt").write_text("NIS text", encoding="utf-8")
        (cat / "전자상거래법.txt").write_text("NIS text 2", encoding="utf-8")
        return str(nis)

    def test_returns_dict(self, tmp_path):
        nis_dir = self._make_nis_dir(tmp_path)
        result = find_text_files(nis_dir)
        assert isinstance(result, dict)

    def test_law_name_is_stem(self, tmp_path):
        nis_dir = self._make_nis_dir(tmp_path)
        result = find_text_files(nis_dir)
        assert "과학기술법" in result
        assert "전자상거래법" in result

    def test_current_path_set(self, tmp_path):
        nis_dir = self._make_nis_dir(tmp_path)
        result = find_text_files(nis_dir)
        assert result["과학기술법"]["current"] is not None
        assert result["과학기술법"]["current"].endswith("과학기술법.txt")

    def test_previous_empty_for_nis(self, tmp_path):
        nis_dir = self._make_nis_dir(tmp_path)
        result = find_text_files(nis_dir)
        assert result["과학기술법"]["previous"] == []


class TestFindTextFilesMobu:
    """MOBU directory: category/lawname/file.txt and category/lawname/이전버전/file.txt"""

    def _make_mobu_dir(self, tmp_path):
        mobu = tmp_path / "법무부" / "변환텍스트"
        law_dir = mobu / "과학기술,지적소유권,체신" / "과학기술법"
        law_dir.mkdir(parents=True)
        (law_dir / "과학기술법(2022.08.23.).txt").write_text("current mobu text", encoding="utf-8")
        prev = law_dir / "이전버전"
        prev.mkdir()
        (prev / "과학기술법(2013.10.23.).txt").write_text("prev text 1", encoding="utf-8")
        (prev / "과학기술법(2005.03.09.).txt").write_text("prev text 2", encoding="utf-8")
        return str(mobu)

    def test_law_name_is_parent_directory(self, tmp_path):
        mobu_dir = self._make_mobu_dir(tmp_path)
        result = find_text_files(mobu_dir)
        assert "과학기술법" in result

    def test_current_set_for_mobu(self, tmp_path):
        mobu_dir = self._make_mobu_dir(tmp_path)
        result = find_text_files(mobu_dir)
        assert result["과학기술법"]["current"] is not None
        assert "과학기술법(2022.08.23.).txt" in result["과학기술법"]["current"]

    def test_previous_versions_found(self, tmp_path):
        mobu_dir = self._make_mobu_dir(tmp_path)
        result = find_text_files(mobu_dir)
        prev = result["과학기술법"]["previous"]
        assert len(prev) == 2

    def test_previous_paths_contain_이전버전(self, tmp_path):
        mobu_dir = self._make_mobu_dir(tmp_path)
        result = find_text_files(mobu_dir)
        for p in result["과학기술법"]["previous"]:
            assert "이전버전" in p

    def test_law_with_only_previous_versions(self, tmp_path):
        """A law that only has 이전버전 files but no current file in law_dir."""
        mobu = tmp_path / "법무부2" / "변환텍스트"
        law_dir = mobu / "기타" / "구법령"
        law_dir.mkdir(parents=True)
        prev = law_dir / "이전버전"
        prev.mkdir()
        (prev / "구법령(2000.01.01.).txt").write_text("old text", encoding="utf-8")
        result = find_text_files(str(mobu))
        assert result["구법령"]["current"] is None
        assert len(result["구법령"]["previous"]) == 1


# ---------------------------------------------------------------------------
# merge_sources
# ---------------------------------------------------------------------------

class TestMergeSourcesNisPriority:
    """When a law exists in both NIS and MOBU, NIS text should be used for current."""

    def _setup(self, tmp_path):
        # Master list
        law = {
            "name": "과학기술법",
            "category": "과학기술·지적소유권·체신",
            "latest_version_date": "2022-08-23",
            "enactment_date": "1988-12-15",
            "amendment_count": 1,
            "total_articles": 91,
            "chapter_count": 8,
            "chapters": [],
            "has_appendix": False,
            "in_mobu": True,
            "in_nis2024": True,
            "mobu_files": ["과학기술법(2022.08.23.).hwp"],
            "nis_volume": "하권",
            "nis_page": 533,
        }
        master_path = _make_master_json(tmp_path, [law])

        # NIS directory
        nis_dir = tmp_path / "국정원2024" / "변환텍스트"
        cat = nis_dir / "과학기술·지적소유권·체신"
        cat.mkdir(parents=True)
        (cat / "과학기술법.txt").write_text("NIS CURRENT TEXT", encoding="utf-8")

        # MOBU directory
        mobu_dir = tmp_path / "법무부" / "변환텍스트"
        law_dir = mobu_dir / "과학기술,지적소유권,체신" / "과학기술법"
        law_dir.mkdir(parents=True)
        (law_dir / "과학기술법(2022.08.23.).txt").write_text("MOBU CURRENT TEXT", encoding="utf-8")

        return master_path, str(nis_dir), str(mobu_dir)

    def test_returns_list(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        assert isinstance(result, list)

    def test_entries_are_law_entry(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        assert all(isinstance(e, LawEntry) for e in result)

    def test_nis_text_chosen_over_mobu(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        current_version = next(
            (v for v in entry.versions if v.source == "nis"), None
        )
        assert current_version is not None
        assert current_version.text == "NIS CURRENT TEXT"

    def test_current_version_source_is_nis(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        nis_versions = [v for v in entry.versions if v.source == "nis"]
        assert len(nis_versions) >= 1

    def test_text_available_true_when_file_found(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        nis_v = next(v for v in entry.versions if v.source == "nis")
        assert nis_v.text_available is True


class TestMergeSourcesMobuFallback:
    """When NIS is unavailable, MOBU current text should be used."""

    def _setup(self, tmp_path):
        law = {
            "name": "가족법",
            "category": "사회",
            "latest_version_date": "2020-10-05",
            "enactment_date": "1990-10-24",
            "amendment_count": 3,
            "total_articles": 60,
            "chapter_count": 5,
            "chapters": [],
            "has_appendix": False,
            "in_mobu": True,
            "in_nis2024": False,
            "mobu_files": ["가족법(2020.10.05.).hwp"],
            "nis_volume": None,
            "nis_page": None,
        }
        master_path = _make_master_json(tmp_path, [law])

        # No NIS file for this law
        nis_dir = tmp_path / "국정원2024" / "변환텍스트"
        nis_dir.mkdir(parents=True)

        # MOBU directory
        mobu_dir = tmp_path / "법무부" / "변환텍스트"
        law_dir = mobu_dir / "사회" / "가족법"
        law_dir.mkdir(parents=True)
        (law_dir / "가족법(2020.10.05.).txt").write_text("MOBU FALLBACK TEXT", encoding="utf-8")

        return master_path, str(nis_dir), str(mobu_dir)

    def test_mobu_version_present(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        mobu_v = next((v for v in entry.versions if v.source == "mobu"), None)
        assert mobu_v is not None

    def test_mobu_text_content(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        mobu_v = next(v for v in entry.versions if v.source == "mobu")
        assert mobu_v.text == "MOBU FALLBACK TEXT"

    def test_mobu_text_available_true(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        mobu_v = next(v for v in entry.versions if v.source == "mobu")
        assert mobu_v.text_available is True

    def test_no_nis_version(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        nis_versions = [v for v in entry.versions if v.source == "nis"]
        assert len(nis_versions) == 0


class TestMergeSourcesPreviousVersions:
    """Previous versions from MOBU 이전버전 directory."""

    def _setup(self, tmp_path):
        law = {
            "name": "과학기술법",
            "category": "과학기술·지적소유권·체신",
            "latest_version_date": "2022-08-23",
            "enactment_date": "1988-12-15",
            "amendment_count": 9,
            "total_articles": 91,
            "chapter_count": 8,
            "chapters": [],
            "has_appendix": False,
            "in_mobu": True,
            "in_nis2024": True,
            "mobu_files": ["과학기술법(2013.10.23.).hwp"],
            "nis_volume": "하권",
            "nis_page": 533,
        }
        master_path = _make_master_json(tmp_path, [law])

        # NIS
        nis_dir = tmp_path / "국정원2024" / "변환텍스트"
        cat = nis_dir / "과학기술·지적소유권·체신"
        cat.mkdir(parents=True)
        (cat / "과학기술법.txt").write_text("NIS LATEST TEXT", encoding="utf-8")

        # MOBU with previous versions
        mobu_dir = tmp_path / "법무부" / "변환텍스트"
        law_dir = mobu_dir / "과학기술,지적소유권,체신" / "과학기술법"
        law_dir.mkdir(parents=True)
        (law_dir / "과학기술법(2022.08.23.).txt").write_text("MOBU CURRENT", encoding="utf-8")
        prev = law_dir / "이전버전"
        prev.mkdir()
        (prev / "과학기술법(2013.10.23.).txt").write_text("MOBU PREV 2013", encoding="utf-8")
        (prev / "과학기술법(2005.03.09.).txt").write_text("MOBU PREV 2005", encoding="utf-8")

        return master_path, str(nis_dir), str(mobu_dir)

    def test_previous_versions_in_entry(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        mobu_prev = [v for v in entry.versions if v.source == "mobu"]
        assert len(mobu_prev) >= 2

    def test_date_extracted_from_filename(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        dates = {v.date for v in entry.versions}
        assert "2013-10-23" in dates
        assert "2005-03-09" in dates

    def test_previous_version_text_loaded(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        v2013 = next(v for v in entry.versions if v.date == "2013-10-23")
        assert v2013.text == "MOBU PREV 2013"
        assert v2013.text_available is True

    def test_versions_sorted_by_date(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        dated = [v for v in entry.versions if v.date]
        dates = [v.date for v in dated]
        assert dates == sorted(dates)

    def test_all_previous_text_available(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path)
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        mobu_versions = [v for v in entry.versions if v.source == "mobu"]
        for v in mobu_versions:
            assert v.text_available is True


class TestMergeSourcesDateExtraction:
    """Date extraction from MOBU filenames like 과학기술법(2013.10.23.).txt"""

    def _setup(self, tmp_path, filename):
        law = {
            "name": "테스트법",
            "category": "기타",
            "latest_version_date": None,
            "enactment_date": None,
            "amendment_count": 0,
            "total_articles": 10,
            "chapter_count": 1,
            "chapters": [],
            "has_appendix": False,
            "in_mobu": True,
            "in_nis2024": False,
            "mobu_files": [],
            "nis_volume": None,
            "nis_page": None,
        }
        master_path = _make_master_json(tmp_path, [law])

        nis_dir = tmp_path / "nis"
        nis_dir.mkdir(parents=True)

        mobu_dir = tmp_path / "mobu"
        law_dir = mobu_dir / "기타" / "테스트법"
        prev = law_dir / "이전버전"
        prev.mkdir(parents=True)
        (prev / filename).write_text("text", encoding="utf-8")

        return master_path, str(nis_dir), str(mobu_dir)

    def test_date_format_dots(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path, "테스트법(2013.10.23.).txt")
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        assert any(v.date == "2013-10-23" for v in entry.versions)

    def test_date_format_single_digit_month_day(self, tmp_path):
        master_path, nis_dir, mobu_dir = self._setup(tmp_path, "테스트법(2005.3.9.).txt")
        result = merge_sources(master_path, nis_dir, mobu_dir)
        entry = result[0]
        assert any(v.date == "2005-03-09" for v in entry.versions)
