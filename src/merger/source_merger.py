"""
Source merger for legalize-kp-pipeline.

Loads the master list JSON, finds matching text files from NIS (국정원)
and MOBU (법무부) directories, and determines the best version for each law.

Priority rules:
  - Current version: NIS (국정원) if available, otherwise MOBU (법무부)
  - Previous versions: MOBU 이전버전 directory
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from src.models import LawEntry, LawVersion
from src.parser.header_parser import parse_header


def _date_from_header(text: str) -> str:
    """버전 텍스트의 헤더에서 가장 최신(마지막) 개정일을 ISO 문자열로 반환.

    파일명·마스터목록에 날짜가 없는 버전(법무부 이전버전 등)의 시행일을
    본문 헤더의 개정이력에서 보충하기 위한 폴백.
    """
    try:
        info = parse_header(unicodedata.normalize("NFC", text))
    except Exception:
        return ""
    if not info.amendments:
        return ""
    return max(a.date for a in info.amendments)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONSTITUTIONAL_NAMES: set = {
    "조선민주주의인민공화국 헌법",
    "사회주의헌법",
    "조선로동당규약",
    "당의유일적령도체계확립의 10대 원칙",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 괄호 안의 날짜. 월·일은 선택적이며, 날짜 뒤 부가어(채택/제정/승인 등)나
# 닫는 괄호 누락도 허용한다. 연도만으로도 매칭된다.
_DATE_IN_FILENAME_RE = re.compile(
    r"\(\s*(\d{4})(?:\.\s*(\d{1,2}))?(?:\.\s*(\d{1,2}))?(?:\s*[-~∼–]\s*(\d{1,2}))?"
)


def _extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract an ISO date string from a MOBU filename.

    Patterns handled:
      과학기술법(2013.10.23.).txt              → 2013-10-23
      테스트법(2005.3.9.).txt                  → 2005-03-09
      헌법(2023.9.26-27.).txt                  → 2023-09-27  (range, later day)
      행정처벌법(2020. 12. 18.).txt            → 2020-12-18  (with spaces)
      사회주의헌법(2016.06.29).txt              → 2016-06-29  (no trailing dot)
      조선로동당 규약(2021.1).txt              → 2021-01-01  (월만, 일 없음)
      문화유물보호법(2011).txt                 → 2011-01-01  (연도만)
      과학기술인재관리법(2023.4.11. 채택).txt   → 2023-04-11  (부가어 '채택')
      회계법(2003.3.26. 제정).txt              → 2003-03-26  (부가어 '제정')
      지방예산법(2012.12.19                     → 2012-12-19  (닫는 괄호 누락)
      도시경영법(1992.1.29. 채택, 1992.4. 9...)→ 1992-01-29  (첫 날짜=채택일)
    """
    match = _DATE_IN_FILENAME_RE.search(filename)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 1
    day1 = int(match.group(3)) if match.group(3) else 1
    day2 = int(match.group(4)) if match.group(4) else day1
    day = max(day1, day2)
    # 잘못 파싱된 월/일 방어
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    return f"{year}-{month:02d}-{day:02d}"


def _file_version_date(path: str) -> Optional[str]:
    """파일명 일자. 파일명에 일(日)이 없으면(예: '문화유물보호법(2011)') 머리 개정이력의
    최신 일자가 같은 연도(월이 있으면 같은 월)일 때 그 일자를 쓴다 — 01-01 자리표 방지.
    맞는 머리 일자가 없으면 파일명 일자(자리표)를 그대로 돌려준다.
    """
    name = Path(path).name
    date = _extract_date_from_filename(name)
    m = _DATE_IN_FILENAME_RE.search(name)
    if not date or not m or m.group(3):
        return date
    prefix = f"{int(m.group(1)):04d}" + (f"-{int(m.group(2)):02d}" if m.group(2) else "")
    header_date = _date_from_header(_read_text(path))
    return header_date if header_date.startswith(prefix) else date


def _read_text(path: str) -> str:
    """Read a UTF-8 text file, falling back to cp949 on decode errors."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, encoding="cp949") as f:
            return f.read()


# ---------------------------------------------------------------------------
# load_master_list
# ---------------------------------------------------------------------------

def load_master_list(master_path: str) -> list[LawEntry]:
    """
    Load the master list JSON and return a list of LawEntry objects.

    JSON field mapping:
      in_nis2024  →  in_nis
      mobu_files  →  mobu_files
      (name in CONSTITUTIONAL_NAMES)  →  is_constitutional
    """
    with open(master_path, encoding="utf-8") as f:
        data = json.load(f)

    entries: list[LawEntry] = []
    for law in data.get("laws", []):
        name = law.get("name", "")
        entry = LawEntry(
            name=name,
            category=law.get("category", ""),
            enactment_date=law.get("enactment_date"),
            latest_version_date=law.get("latest_version_date"),
            total_articles=law.get("total_articles"),
            chapter_count=law.get("chapter_count"),
            amendment_count=law.get("amendment_count", 0),
            chapters=list(law.get("chapters", [])),
            has_appendix=law.get("has_appendix", False),
            in_nis=bool(law.get("in_nis2024", False)),
            in_mobu=bool(law.get("in_mobu", False)),
            in_unification=bool(law.get("in_unification", False)),
            nis_volume=law.get("nis_volume"),
            nis_page=law.get("nis_page"),
            mobu_files=list(law.get("mobu_files", [])),
            former_names=list(law.get("former_names") or []),
            is_constitutional=name in CONSTITUTIONAL_NAMES,
        )
        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# find_text_files
# ---------------------------------------------------------------------------

def find_text_files(text_dir: str) -> dict:
    """
    Walk *text_dir* recursively and map each law name to its text files.

    Returns a dict:
        {
            law_name: {
                "current": path_or_none,
                "previous": [paths],
            }
        }

    Path-depth detection:
      - NIS layout:  text_dir / <category> / <law>.txt
        → 2-part relative path (category/law.txt) → current
      - MOBU layout: text_dir / <category> / <law_name> / <file>.txt
        → 3-part relative path (category/law_name/file.txt) → current
      - MOBU previous: text_dir / <category> / <law_name> / 이전버전 / <file>.txt
        → 4-part relative path, "이전버전" segment → previous
    """
    result: dict = {}
    root = Path(text_dir)

    for abs_path in root.rglob("*.txt"):
        rel = abs_path.relative_to(root)
        parts = rel.parts  # tuple of path components

        if len(parts) == 2:
            # NIS: category/law.txt
            law_name = abs_path.stem
            entry = result.setdefault(law_name, {"current": None, "previous": []})
            entry["current"] = str(abs_path)

        elif len(parts) >= 3:
            # MOBU layout — law name is the directory one level below category
            # parts[0] = category, parts[1] = law_name dir, parts[2:] = file/이전버전/...
            law_name = parts[1]
            entry = result.setdefault(law_name, {"current": None, "previous": []})

            if "이전버전" in parts:
                entry["previous"].append(str(abs_path))
            else:
                # Current version inside law_name directory (not under 이전버전)
                if entry["current"] is None:
                    entry["current"] = str(abs_path)

    return result


# ---------------------------------------------------------------------------
# merge_sources
# ---------------------------------------------------------------------------

def _lookup(files_dict: dict, entry: LawEntry):
    """현 이름 + former_names 별칭으로 find_text_files 결과 탐색."""
    info = files_dict.get(entry.name)
    if info is not None:
        return info
    for alias in entry.former_names:
        info = files_dict.get(alias)
        if info is not None:
            return info
    return None


def load_unification_meta(unification_dir: str | None) -> dict:
    """개별법령/_meta.json 의 entries 를 변환텍스트 절대경로 → 항목 으로.

    개별법령에는 여러 입수 경로(통일부 발표 자료, NK TechLab 등)가 섞이므로 판본별
    source_id(기본 "unification")·ocr 여부·action(채택/수정보충)을 여기서 읽는다.
    """
    if not unification_dir:
        return {}
    meta_path = Path(unification_dir).parent / "_meta.json"
    if not meta_path.exists():
        return {}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    default_id = meta.get("source_id", "unification")
    out = {}
    for item in meta.get("entries", []):
        if item.get("text_file"):
            path = os.path.normcase(str((meta_path.parent / item["text_file"]).resolve()))
            out[path] = {"source_id": item.get("source_id", default_id), "ocr": bool(item.get("ocr")),
                         "action": item.get("action", "수정보충")}
    return out


def merge_sources(
    master_path: str,
    nis_dir: str,
    mobu_dir: str,
    unification_dir: str | None = None,
) -> list[LawEntry]:
    """
    Load master list and combine NIS + MOBU + (선택) 통일부 텍스트를 LawEntry.versions 로 통합.

    Version selection priority:
      1. unification (통일부 발표 자료) — 가장 새로 입수한 출처
      2. NIS/MOBU 중 더 최신 일자 — 기존 로직
      3. 이전버전: MOBU의 이전버전 폴더

    NIS/MOBU 텍스트는 entry.name 또는 former_names 별칭으로 매칭(법명 변경 대응).
    Versions are sorted by date (ascending) before being attached.
    """
    entries = load_master_list(master_path)
    nis_files = find_text_files(nis_dir)
    mobu_files = find_text_files(mobu_dir)
    uni_files = find_text_files(unification_dir) if unification_dir else {}
    uni_meta = load_unification_meta(unification_dir)

    for entry in entries:
        versions: list[LawVersion] = []

        nis_info = _lookup(nis_files, entry)
        mobu_info = _lookup(mobu_files, entry)
        uni_info = _lookup(uni_files, entry)

        # ── Current version ────────────────────────────────────────────────
        # 통일부 > (MOBU·NIS 중 더 최신 일자) 순. 같은 출처들 내에서는 파일명 일자 기준.
        uni_path = uni_info["current"] if uni_info else None
        nis_path = nis_info["current"] if nis_info else None
        mobu_path = mobu_info["current"] if mobu_info else None

        uni_date = (
            _extract_date_from_filename(Path(uni_path).name) if uni_path else None
        )
        mobu_date = (
            _file_version_date(mobu_path) if mobu_path else None
        )
        nis_date = entry.latest_version_date or ""

        if uni_path:
            text = _read_text(uni_path)
            meta = uni_meta.get(os.path.normcase(str(Path(uni_path).resolve())), {})
            versions.append(LawVersion(
                date=uni_date or entry.latest_version_date or "",
                action=meta.get("action", "수정보충"),
                source=meta.get("source_id", "unification"),
                text=text,
                text_available=True,
                is_ocr=meta.get("ocr", False),
            ))
        else:
            use_mobu = bool(mobu_path) and (
                not nis_path or (mobu_date and mobu_date > nis_date)
            )
            if use_mobu and mobu_path:
                text = _read_text(mobu_path)
                versions.append(LawVersion(
                    date=mobu_date or nis_date,
                    action="수정보충",
                    source="mobu",
                    text=text,
                    text_available=True,
                ))
            elif nis_path:
                text = _read_text(nis_path)
                versions.append(LawVersion(
                    date=nis_date,
                    action="수정보충",
                    source="nis",
                    text=text,
                    text_available=True,
                ))
            elif mobu_path:
                text = _read_text(mobu_path)
                versions.append(LawVersion(
                    date=mobu_date or nis_date,
                    action="수정보충",
                    source="mobu",
                    text=text,
                    text_available=True,
                ))

        # 개별법령 본이 현행이면 그보다 앞선 MOBU·NIS current 는 이전 판본으로 보존한다
        # (예: 형사소송법 2021-01-20 국정원 본). 개별법령 본과 같은 일자면 중복이라 넣지 않고,
        # MOBU·NIS 가 같은 일자면 개별법령이 없을 때처럼 NIS 를 쓴다.
        nis_kept = bool(uni_path and nis_path and nis_date and nis_date != uni_date)
        if (uni_path and mobu_path and mobu_date and mobu_date != uni_date
                and not (nis_kept and mobu_date == nis_date)):
            versions.append(LawVersion(
                date=mobu_date,
                action="수정보충",
                source="mobu",
                text=_read_text(mobu_path),
                text_available=True,
            ))
        if nis_kept:
            versions.append(LawVersion(
                date=nis_date,
                action="수정보충",
                source="nis",
                text=_read_text(nis_path),
                text_available=True,
            ))

        # ── Previous versions (MOBU 이전버전) ─────────────────────────────
        if mobu_info:
            for prev_path in mobu_info["previous"]:
                date = _file_version_date(prev_path) or ""
                text = _read_text(prev_path)
                versions.append(LawVersion(
                    date=date,
                    action="수정보충",
                    source="mobu",
                    text=text,
                    text_available=True,
                ))

        # ── 날짜 없는 버전: 헤더 개정이력에서 시행일 보충 ────────────────────
        # 파일명/마스터목록에 일자가 없는 법무부 이전버전 등은 본문 헤더의
        # 최신 개정일을 시행일로 사용한다.
        for v in versions:
            if not v.date:
                v.date = _date_from_header(getattr(v, "text", "") or "")

        # ── 같은 일자 중복 제거(텍스트가 더 완전한 쪽을 남김) ─────────────────
        # 동일 법령에서 같은 시행일 버전이 둘 이상이면(파일명변형+이전버전 등)
        # 본문이 가장 긴(완전한) 하나만 남긴다.
        by_date: dict = {}
        for v in versions:
            key = v.date or ""
            cur = by_date.get(key)
            if cur is None or len(getattr(v, "text", "") or "") > len(getattr(cur, "text", "") or ""):
                by_date[key] = v
        versions = list(by_date.values())

        # ── Sort by date ───────────────────────────────────────────────────
        versions.sort(key=lambda v: v.date or "")

        entry.versions = versions

        # ── latest_version_date 보정 ────────────────────────────────────────
        # 마스터 목록이 최신본 일자를 누락/오기한 경우(예: 당규약 2021.1 본을
        # 못 잡고 2016.5.9 로 기록), 실제 보유한 버전 중 최신 일자로 끌어올린다.
        dated = [v.date for v in versions if v.date]
        if dated:
            newest = max(dated)
            if not entry.latest_version_date or newest > entry.latest_version_date:
                entry.latest_version_date = newest

    return entries
