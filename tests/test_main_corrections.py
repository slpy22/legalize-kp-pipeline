"""main.py — 권말 색인 절단, corrections.yaml 정정, annotations.yaml 날짜이견·이력추가."""
import yaml

from main import (_apply_corrections, _attach_annotations, _check_disputes,
                  _merge_history_additions, _process_version)
from src.git.history_builder import CommitEntry
from src.models import LawEntry, LawVersion
from src.parser.markdown_writer import generate_frontmatter


def _commit(content: str) -> CommitEntry:
    return CommitEntry(date="2024-02-06", law_name="민법", action="수정보충",
                       file_path="kp/민법/법령.md", content=content)


def test_correction_applied_once():
    c = _commit("본문 온행 끝")
    corr = [{"law": "민법", "date": "2024-02-06", "old": "온행", "new": "은행"}]
    errors: list[str] = []
    _apply_corrections(c, corr, errors)
    assert c.content == "본문 은행 끝" and not errors and corr[0]["_applied"]


def test_correction_count_mismatch_is_error():
    c = _commit("온행 온행")
    corr = [{"law": "민법", "date": "2024-02-06", "old": "온행", "new": "은행"}]
    errors: list[str] = []
    _apply_corrections(c, corr, errors)
    assert c.content == "온행 온행" and len(errors) == 1


def test_correction_other_version_untouched():
    c = _commit("온행")
    corr = [{"law": "민법", "date": "2007-03-20", "old": "온행", "new": "은행"}]
    errors: list[str] = []
    _apply_corrections(c, corr, errors)
    assert c.content == "온행" and not errors and "_applied" not in corr[0]


def test_volume_index_is_cut():
    text = """조선민주주의인민공화국 허풍방지법
주체111(2022)년 5월 31일 최고인민회의 상임위원회 정령 제1000호로 채택
제1장 일반규정
제1조 (사명)
이 법은 사명을 정한다.

법령색인

색인
가격법 .......... 上694
"""
    entry = LawEntry(name="허풍방지법", category="계량", latest_version_date="2022-05-31")
    v = LawVersion(date="2022-05-31", action="채택", source="nis", text=text, text_available=True)
    out = _process_version(entry, v, []).content
    assert "제1조 (사명)" in out
    assert "법령색인" not in out and "가격법" not in out


_DISPUTE = {"항목": "채택일", "원문값": "2022-08-07", "이견값": "2022-09-07", "출처": "학보 2025-3호", "비고": "회의 9-7~8"}


def test_date_dispute_attached_and_rendered():
    entry = LawEntry(name="사회주의농촌발전법", category="농업·임업·수산", enactment_date="2022-08-07")
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "사회주의농촌발전법", "날짜이견": [dict(_DISPUTE)]}], errors)
    assert not errors and entry.date_disputes == [_DISPUTE]
    commit = _commit("---\n채택일: '2022-08-07'\n개정이력: []\n---\n본문\n")
    _check_disputes(commit, entry, errors)
    assert not errors
    fm = generate_frontmatter(entry, amendments=[], source="nis")
    assert yaml.safe_load(fm)["날짜이견"] == [_DISPUTE]


def test_date_dispute_original_value_mismatch_is_error():
    entry = LawEntry(name="사회주의농촌발전법", category="농업·임업·수산")
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "사회주의농촌발전법", "날짜이견": [dict(_DISPUTE)]}], errors)
    _check_disputes(_commit("---\n채택일: '2022-09-07'\n---\n"), entry, errors)
    assert len(errors) == 1


def test_date_dispute_unknown_law_is_error():
    errors: list[str] = []
    _attach_annotations([], [{"law": "없는법", "날짜이견": [dict(_DISPUTE)]}], errors)
    assert len(errors) == 1


def test_history_addition_inserted_in_date_order():
    entry = LawEntry(name="하천법", category="국토·환경보호")
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "하천법", "이력추가": [
        {"일자": "2023-10", "내용": "수정보충", "외부근거": "학보 2025-2호", "비고": "정령 제1476호"}]}], errors)
    assert not errors
    merged = _merge_history_additions(
        [{"일자": "2002-11-07", "내용": "채택"}, {"일자": "2022-03-15", "내용": "수정보충"}],
        entry.history_additions)
    assert [m["일자"] for m in merged] == ["2002-11-07", "2022-03-15", "2023-10"]
    assert merged[-1] == {"일자": "2023-10", "내용": "수정보충", "원문미확보": True,
                          "외부근거": "학보 2025-2호", "비고": "정령 제1476호"}


def test_history_addition_same_date_marks_existing_item():
    merged = _merge_history_additions(
        [{"일자": "2022-06-30", "내용": "수정보충"}],
        [{"일자": "2022-06-30", "내용": "수정보충", "원문미확보": True, "외부근거": "NK TechLab 2023 본 머리"}])
    assert merged == [{"일자": "2022-06-30", "내용": "수정보충", "원문미확보": True,
                       "외부근거": "NK TechLab 2023 본 머리"}]


def test_history_addition_bad_format_is_error():
    entry = LawEntry(name="하천법", category="국토·환경보호")
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "하천법", "이력추가": [
        {"일자": "2023년 10월", "내용": "수정보충", "외부근거": "x"}]}], errors)
    assert len(errors) == 1 and not entry.history_additions


def test_excerpt_dates_validated_and_rendered():
    entry = LawEntry(name="형법", category="형·민사",
                     versions=[LawVersion(date="2013-06-19", action="수정보충", source="mobu")])
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "형법", "발췌본": ["2013-06-19", "2013-01-01"]}], errors)
    assert entry.excerpt_dates == ["2013-06-19"] and len(errors) == 1
    fm = yaml.safe_load(generate_frontmatter(entry, [], "mobu", excerpt_articles=["제19조"]))
    assert fm["발췌본"] is True and fm["발췌조문"] == ["제19조"]
    assert "발췌본" not in yaml.safe_load(generate_frontmatter(entry, [], "mobu"))


# ── NKLAWSVC-T9 (7차 #72·#29) ────────────────────────────────────────────────

_HYUNGBEOP = """조선민주주의인민공화국 형법
주체63(1974)년 12월 19일 최고인민회의 상설회의 결정으로 채택
주체109(2020)년 11월 26일 최고인민회의 상임위원회 정령 제471호로 수정보충
제1장 일반규정
제1조 (사명)
이 법은 사명을 정한다.
"""


def test_version_action_from_same_day_history():
    entry = LawEntry(name="형법", category="형·민사")
    v = LawVersion(date="1974-12-19", action="수정보충", source="mobu",
                   text=_HYUNGBEOP.split("주체109")[0] + "제1장 일반규정\n제1조 (사명)\n본문\n",
                   text_available=True)
    assert _process_version(entry, v, []).action == "채택"
    v2 = LawVersion(date="2020-11-26", action="수정보충", source="nis", text=_HYUNGBEOP, text_available=True)
    assert _process_version(entry, v2, []).action == "수정보충"


def test_version_action_falls_back_to_enactment_date():
    text = "조선민주주의인민공화국 개성공업지구법\n제1장 일반규정\n제1조 (사명)\n본문\n"
    entry = LawEntry(name="개성공업지구법", category="외교·대외경제", enactment_date="2002-11-20")
    v = LawVersion(date="2002-11-20", action="수정보충", source="mobu", text=text, text_available=True)
    assert _process_version(entry, v, []).action == "채택"


_EFFECTIVE = {"항목": "시행일", "원문값": "2020-11-26", "이견값": "2021-03-01", "출처": "학보 2026-1호"}


def test_effective_date_dispute_only_on_versions_with_that_amendment():
    from main import _check_effective_disputes
    entry = LawEntry(name="형법", category="형·민사")
    errors: list[str] = []
    _attach_annotations([entry], [{"law": "형법", "날짜이견": [dict(_EFFECTIVE)]}], errors)
    old = LawVersion(date="1974-12-19", action="수정보충", source="mobu",
                     text=_HYUNGBEOP.split("주체109")[0] + "제1장 일반규정\n제1조 (사명)\n본문\n",
                     text_available=True)
    new = LawVersion(date="2020-11-26", action="수정보충", source="nis", text=_HYUNGBEOP, text_available=True)
    c_old, c_new = _process_version(entry, old, []), _process_version(entry, new, [])
    fm_old = yaml.safe_load(c_old.content.split("---", 2)[1])
    fm_new = yaml.safe_load(c_new.content.split("---", 2)[1])
    assert "날짜이견" not in fm_old
    assert fm_new["날짜이견"] == [_EFFECTIVE]
    _check_disputes(c_new, entry, errors)
    _check_effective_disputes(entry, [c_old, c_new], errors)
    assert not errors
    _check_effective_disputes(entry, [c_old], errors)
    assert len(errors) == 1


# ── NKLAWSVC-T10 (8차 #76) 법령집 부문 머리 ───────────────────────────────────

def test_trailing_section_heading_cut():
    from main import _cut_trailing_section_heading
    assert _cut_trailing_section_heading("제42조 (분쟁해결)\n해결할수 있다.\n\n교육·문화·\n체육부문") == "제42조 (분쟁해결)\n해결할수 있다."
    assert _cut_trailing_section_heading("책임을 지운다.\n\n사회복리부문") == "책임을 지운다."
    # 부문 이름이 아니면 두고, 본문 문장 끝의 '부문' 도 건드리지 않는다
    assert _cut_trailing_section_heading("본문.\n\n기타부문") == "본문.\n\n기타부문"
    assert _cut_trailing_section_heading("투자를 늘인다.\n해당 부문") == "투자를 늘인다.\n해당 부문"
