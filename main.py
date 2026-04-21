"""
main.py — CLI entry point for legalize-kp-pipeline.

Pipeline:
  Phase 1: merge_sources()
  Phase 2-3: normalize → parse header → parse structure → build CommitEntry objects
  Phase 4: build_history() or write files directly (--skip-git)
  Phase 5: validate_all() → validation_report.json
  Phase 6: stats.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

from src.merger.source_merger import merge_sources
from src.models import LawEntry, LawVersion
from src.parser.normalizer import normalize_text
from src.parser.header_parser import parse_header
from src.parser.structure_parser import parse_structure
from src.parser.markdown_writer import generate_frontmatter, generate_markdown
from src.git.history_builder import build_history, CommitEntry
from src.validate.validator import validate_all


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.yaml") -> dict:
    """Load and return the YAML configuration file as a dict."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Placeholder content builder
# ---------------------------------------------------------------------------

def _build_placeholder_content(entry: LawEntry, version: LawVersion) -> str:
    """Build a minimal Markdown file content for a version without text."""
    amendments_list = [{"일자": version.date, "내용": version.action}] if version.date else []
    frontmatter = generate_frontmatter(
        entry,
        amendments=amendments_list,
        source=version.source,
        text_unavailable=True,
    )
    return f"---\n{frontmatter}---\n\n텍스트 미확보\n"


# ---------------------------------------------------------------------------
# Per-version processing
# ---------------------------------------------------------------------------

def _process_version(
    entry: LawEntry,
    version: LawVersion,
    constitutional_names: list[str],
) -> CommitEntry:
    """
    Normalize, parse, and build a CommitEntry for a single law version.

    Raises on any parsing error — caller should catch and continue.
    """
    # Set is_constitutional based on config list
    entry.is_constitutional = entry.name in constitutional_names

    file_path = f"kp/{entry.name}/{entry.file_type}.md"

    # No text available → placeholder
    if not version.text_available or not version.text:
        content = _build_placeholder_content(entry, version)
        return CommitEntry(
            date=version.date or "1900-01-01",
            law_name=entry.name,
            action=version.action,
            file_path=file_path,
            content=content,
        )

    # Full processing pipeline
    normalized = normalize_text(version.text)
    header = parse_header(normalized)

    # Extract body text starting from header.body_start_index
    body_text = normalized[header.body_start_index:]
    tree = parse_structure(body_text)

    # Build amendments list for frontmatter (list of dicts)
    amendments_dicts = [
        {"일자": amend.date, "내용": amend.action}
        for amend in header.amendments
    ]

    # enactment_basis: last amendment's .basis field
    enactment_basis = header.amendments[-1].basis if header.amendments else ""

    frontmatter_str = generate_frontmatter(
        entry,
        amendments=amendments_dicts,
        source=version.source,
        is_authentic=(version.source == "nis"),
    )

    # Store enactment_basis on the version object so generate_frontmatter
    # can pick it up from entry.versions when called via write_law_file
    version.enactment_basis = enactment_basis

    body_md = generate_markdown(tree)
    # If structure parser found no nodes, use the raw body text as-is
    if not body_md.strip() and body_text.strip():
        body_md = body_text.strip()
    content = f"---\n{frontmatter_str}---\n\n{body_md}\n"

    return CommitEntry(
        date=version.date or "1900-01-01",
        law_name=entry.name,
        action=version.action,
        file_path=file_path,
        content=content,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config_path: str = "config.yaml", skip_git: bool = False) -> None:
    """Execute the full legalize-kp pipeline."""

    # ── Load config ────────────────────────────────────────────────────────
    print(f"[config] {config_path} 로드 중...")
    cfg = load_config(config_path)

    master_path: str = cfg["master_list"]
    nis_dir: str = cfg["nis_text_dir"]
    mobu_dir: str = cfg["mobu_text_dir"]
    output_repo: str = cfg["output_repo"]
    output_kp_dir: str = cfg["output_kp_dir"]
    constitutional_names: list[str] = cfg.get("constitutional_names", [])

    # ── Phase 1: Merge sources ─────────────────────────────────────────────
    print("\n[Phase 1] 소스 병합 중...")
    entries = merge_sources(master_path, nis_dir, mobu_dir)
    print(f"  → 법령 {len(entries)}건 로드")

    # ── Phase 2-3: Process each entry / version ────────────────────────────
    print("\n[Phase 2-3] 법령 파싱 중...")
    commits: list[CommitEntry] = []
    failures: list[str] = []
    processed = 0

    for entry_idx, entry in enumerate(entries):
        # Set is_constitutional from config
        entry.is_constitutional = entry.name in constitutional_names

        if not entry.versions:
            # No text at all — create single placeholder
            placeholder_version = LawVersion(
                date=entry.latest_version_date or entry.enactment_date or "1900-01-01",
                action="수정보충",
                source="unknown",
                text=None,
                text_available=False,
            )
            entry.versions = [placeholder_version]

        for version in entry.versions:
            try:
                commit = _process_version(entry, version, constitutional_names)
                commits.append(commit)
            except Exception as exc:
                msg = f"  [FAIL] {entry.name} ({version.date}): {exc}"
                print(msg)
                failures.append(msg)

        processed += 1
        if processed % 50 == 0:
            print(f"  진행: {processed}/{len(entries)} 법령 처리 완료")

    print(f"  → 총 {len(commits)}건 커밋 엔트리 생성, 실패 {len(failures)}건")

    # ── Phase 4: Build git history or write files directly ─────────────────
    if not skip_git:
        print("\n[Phase 4] Git 히스토리 빌드 중...")
        build_history(output_repo, commits)
        print(f"  → {output_repo} 에 Git 리포지터리 생성 완료")
    else:
        print("\n[Phase 4] --skip-git: 파일 직접 쓰기...")
        os.makedirs(output_kp_dir, exist_ok=True)
        for commit in commits:
            abs_path = os.path.join(output_repo, commit.file_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(commit.content)
        print(f"  → {len(commits)}개 파일 기록 완료")

    # ── Phase 5: Validate ──────────────────────────────────────────────────
    print("\n[Phase 5] 검증 중...")
    validation = validate_all(output_kp_dir, entries)

    summary_line = (
        f"  총 {validation['total_laws']}건: "
        f"성공 {validation['success']}, "
        f"경고 {validation['warnings']}, "
        f"실패 {validation['failures']}"
    )
    print(summary_line)

    report_path = os.path.join(output_repo, "validation_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)
    print(f"  → {report_path} 저장 완료")

    # ── Phase 6: Stats ─────────────────────────────────────────────────────
    print("\n[Phase 6] 통계 생성 중...")
    category_counts: dict[str, int] = {}
    for entry in entries:
        category_counts[entry.category] = category_counts.get(entry.category, 0) + 1

    stats = {
        "total_laws": len(entries),
        "total_commits": len(commits),
        "categories": category_counts,
    }

    stats_path = os.path.join(output_repo, "stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  → {stats_path} 저장 완료")
    print(f"\n완료: 법령 {stats['total_laws']}건, 커밋 {stats['total_commits']}건")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="legalize-kp-pipeline",
        description="북한 법령 텍스트를 Markdown+YAML로 변환하고 Git 히스토리를 생성합니다.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="설정 파일 경로 (기본값: config.yaml)",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Git 히스토리 생성 없이 파일만 출력합니다.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entry point."""
    args = _parse_args(argv)
    run_pipeline(config_path=args.config, skip_git=args.skip_git)


if __name__ == "__main__":
    main()
