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
    "사회주의헌법",
    "조선로동당규약",
    "당의유일적령도체계확립의 10대 원칙",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Extract an ISO date string from a MOBU filename.

    Patterns handled:
      과학기술법(2013.10.23.).txt  →  2013-10-23
      테스트법(2005.3.9.).txt      →  2005-03-09
    """
    match = re.search(r"\((\d{4})\.(\d{1,2})\.(\d{1,2})\.?\)", filename)
    if match:
        year, month, day = match.group(1), match.group(2), match.group(3)
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


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
            nis_volume=law.get("nis_volume"),
            nis_page=law.get("nis_page"),
            mobu_files=list(law.get("mobu_files", [])),
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

def merge_sources(
    master_path: str,
    nis_dir: str,
    mobu_dir: str,
) -> list[LawEntry]:
    """
    Load master list and combine NIS + MOBU text files into LawEntry.versions.

    Version selection:
      - Current: NIS if available, else MOBU
      - Previous versions: always from MOBU 이전버전

    Versions are sorted by date (ascending) before being attached.
    """
    entries = load_master_list(master_path)
    nis_files = find_text_files(nis_dir)
    mobu_files = find_text_files(mobu_dir)

    for entry in entries:
        versions: list[LawVersion] = []

        nis_info = nis_files.get(entry.name)
        mobu_info = mobu_files.get(entry.name)

        # ── Current version ────────────────────────────────────────────────
        if nis_info and nis_info["current"]:
            text = _read_text(nis_info["current"])
            date = entry.latest_version_date or ""
            versions.append(LawVersion(
                date=date,
                action="수정보충",
                source="nis",
                text=text,
                text_available=True,
            ))
        elif mobu_info and mobu_info["current"]:
            text = _read_text(mobu_info["current"])
            date = _extract_date_from_filename(
                Path(mobu_info["current"]).name
            ) or entry.latest_version_date or ""
            versions.append(LawVersion(
                date=date,
                action="수정보충",
                source="mobu",
                text=text,
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
