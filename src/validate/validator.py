"""
Validator for generated Markdown law files.

Validates files against the master list: article count, chapter count,
required frontmatter fields, and non-empty body.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

import yaml

from src.models import LawEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "제목",
    "카테고리",
    "채택일",
    "최신버전일",
    "조문수",
    "개정횟수",
    "출처",
    "날짜추정",
    "OCR여부",
    "정본여부",
    "개정이력",
]

# Regex to extract frontmatter block (between --- delimiters)
_FM_RE = re.compile(r"^---\n(.+?)\n---", re.DOTALL)

# Article heading: ##### 제N조
_ARTICLE_RE = re.compile(r"^#{5}\s+제\d+조", re.MULTILINE)

# Chapter heading: ## 제N장
_CHAPTER_RE = re.compile(r"^##\s+제\d+장", re.MULTILINE)

# Article count tolerance (±)
_ARTICLE_TOLERANCE = 2


# ---------------------------------------------------------------------------
# validate_law_file
# ---------------------------------------------------------------------------

def validate_law_file(
    file_path: str,
    expected_articles: Optional[int] = None,
    expected_chapters: Optional[int] = None,
) -> dict:
    """Validate a single Markdown law file.

    Parameters
    ----------
    file_path:
        Absolute (or relative) path to the ``.md`` file.
    expected_articles:
        Expected number of articles (조문수) from the master list.
        Tolerance of ±2 is applied.
    expected_chapters:
        Expected number of chapters (장) from the master list.

    Returns
    -------
    dict with keys: ``status`` ("success"|"warning"|"failure"),
    ``message`` (str), ``file`` (str).
    """

    def _result(status: str, message: str) -> dict:
        return {"status": status, "message": message, "file": file_path}

    # --- Read file -----------------------------------------------------------
    try:
        text = Path(file_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return _result("failure", f"파일을 찾을 수 없음: {file_path}")
    except OSError as exc:
        return _result("failure", f"파일 읽기 오류: {exc}")

    # --- Parse frontmatter ---------------------------------------------------
    fm_match = _FM_RE.match(text)
    if not fm_match:
        return _result("failure", "프론트매터(---) 블록을 찾을 수 없음")

    try:
        frontmatter = yaml.safe_load(fm_match.group(1)) or {}
    except yaml.YAMLError as exc:
        return _result("failure", f"YAML 파싱 오류: {exc}")

    if not isinstance(frontmatter, dict):
        return _result("failure", "프론트매터가 딕셔너리 형식이 아님")

    # --- Body ----------------------------------------------------------------
    # Everything after the closing ---
    closing_end = fm_match.end()
    body = text[closing_end:]

    if not body.strip():
        return _result("failure", "본문(body)이 비어 있음")

    # --- Required fields -----------------------------------------------------
    missing = [f for f in REQUIRED_FIELDS if f not in frontmatter]
    if missing:
        return _result(
            "warning",
            f"필수 필드 누락: {', '.join(missing)}",
        )

    # --- Article count -------------------------------------------------------
    actual_articles = len(_ARTICLE_RE.findall(body))

    if expected_articles is not None:
        diff = abs(actual_articles - expected_articles)
        if diff >= _ARTICLE_TOLERANCE:
            return _result(
                "warning",
                f"조문수 불일치: 기대={expected_articles}, 실제={actual_articles} (허용범위 ±{_ARTICLE_TOLERANCE})",
            )

    # --- Chapter count -------------------------------------------------------
    actual_chapters = len(_CHAPTER_RE.findall(body))

    if expected_chapters is not None:
        if actual_chapters != expected_chapters:
            return _result(
                "warning",
                f"장(章) 수 불일치: 기대={expected_chapters}, 실제={actual_chapters}",
            )

    return _result("success", "검증 통과")


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

def validate_all(kp_dir: str, master_entries: List[LawEntry]) -> dict:
    """Validate all law files against master list entries.

    Parameters
    ----------
    kp_dir:
        Root directory that contains one sub-directory per law.
    master_entries:
        List of :class:`~src.models.LawEntry` objects from the master list.

    Returns
    -------
    dict with keys:
        ``total_laws``, ``success``, ``warnings``, ``failures``,
        ``details`` (list of dicts with ``law_name``, ``status``,
        ``message``, ``file``).
    """
    details: list[dict] = []
    success_count = 0
    warning_count = 0
    failure_count = 0

    for entry in master_entries:
        file_path = os.path.join(kp_dir, entry.name, f"{entry.file_type}.md")

        if not os.path.exists(file_path):
            status = "failure"
            message = f"파일 없음: {file_path}"
            failure_count += 1
        else:
            result = validate_law_file(
                file_path,
                expected_articles=entry.total_articles,
                expected_chapters=entry.chapter_count,
            )
            status = result["status"]
            message = result["message"]
            if status == "success":
                success_count += 1
            elif status == "warning":
                warning_count += 1
            else:
                failure_count += 1

        details.append(
            {
                "law_name": entry.name,
                "status": status,
                "message": message,
                "file": file_path,
            }
        )

    return {
        "total_laws": len(master_entries),
        "success": success_count,
        "warnings": warning_count,
        "failures": failure_count,
        "details": details,
    }
