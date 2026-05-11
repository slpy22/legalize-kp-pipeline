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
from pathlib import Path
from typing import Optional

from src.models import LawEntry, LawVersion


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

_DATE_IN_FILENAME_RE = re.compile(
    r"\(\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*(?:-\s*(\d{1,2}))?\s*\.?\s*\)"
)


def _extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract an ISO date string from a MOBU filename.

    Patterns handled:
      과학기술법(2013.10.23.).txt          → 2013-10-23
      테스트법(2005.3.9.).txt              → 2005-03-09
      헌법(2023.9.26-27.).txt              → 2023-09-27  (range, later day)
      행정처벌법(2020. 12. 18.).txt        → 2020-12-18  (with spaces)
      사회주의헌법(2016.06.29).txt          → 2016-06-29  (no trailing dot)
    """
    match = _DATE_IN_FILENAME_RE.search(filename)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    day1 = int(match.group(3))
    day2 = int(match.group(4)) if match.group(4) else day1
    day = max(day1, day2)
    return f"{year}-{month:02d}-{day:02d}"


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
            _extract_date_from_filename(Path(mobu_path).name) if mobu_path else None
        )
        nis_date = entry.latest_version_date or ""

        if uni_path:
            text = _read_text(uni_path)
            versions.append(LawVersion(
                date=uni_date or entry.latest_version_date or "",
                action="수정보충",
                source="unification",
                text=text,
                text_available=True,
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

        # 통일부 본이 현행이면 MOBU current는 별도 이전버전 entry로 보존
        # (역사 기록용). 파일명에서 추출한 정확한 일자(mobu_date)가 unification과
        # 다를 때만 추가 — 같은 일자면 중복이 되므로 생략. NIS current는 일자
        # 정보가 master.latest_version_date 외에 없어 일자 충돌 위험이 있으므로
        # 별도 추가하지 않는다.
        if uni_path and mobu_path and mobu_date and mobu_date != uni_date:
            versions.append(LawVersion(
                date=mobu_date,
                action="수정보충",
                source="mobu",
                text=_read_text(mobu_path),
                text_available=True,
            ))

        # ── Previous versions (MOBU 이전버전) ─────────────────────────────
        if mobu_info:
            for prev_path in mobu_info["previous"]:
                filename = Path(prev_path).name
                date = _extract_date_from_filename(filename) or ""
                text = _read_text(prev_path)
                versions.append(LawVersion(
                    date=date,
                    action="수정보충",
                    source="mobu",
                    text=text,
                    text_available=True,
                ))

        # ── Sort by date ───────────────────────────────────────────────────
        versions.sort(key=lambda v: v.date or "")

        entry.versions = versions

    return entries
