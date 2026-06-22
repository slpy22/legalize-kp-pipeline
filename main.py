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
import re
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

    # 서문(헌법 등) 추출 — "서 문" ~ 첫 "제N장" 사이를 별도로 보존.
    # structure_parser 가 "제N장/제N조"만 트리로 만들어 서문 내용이 버려지므로
    # 여기서 미리 분리해 두고 markdown 앞에 prepend 한다.
    preamble_md = ""
    pre_m = re.search(r"^\s*서\s*문\s*\n+(.+?)(?=\n\s*제\s*\d+\s*장)",
                       body_text, re.DOTALL | re.MULTILINE)
    if pre_m:
        preamble_body = pre_m.group(1).strip()
        if preamble_body:
            preamble_md = f"## 서 문\n\n{preamble_body}\n\n"
        # 구조 파서엔 서문 다음(제1장 시작)부터 전달
        body_text = body_text[pre_m.end():]

    # 첫 '제N장' 이전 영역에 조문이 있으면(=제1장이 명시 안 된 법령),
    # 그 조문들을 직접 markdown 형식으로 변환해 prepend 한다.
    # (parse_structure 는 '제N장' 컨테이너 밖의 조문을 트리에 못 담는 한계 우회)
    head_md = ""
    first_ch = re.search(r"^\s*제\s*\d+\s*장", body_text, re.MULTILINE)
    if first_ch and first_ch.start() > 0:
        head = body_text[:first_ch.start()].strip()
        if re.search(r"제\s*\d+\s*조", head):
            head_md = "## 제1장 일반규정\n"
            for m in re.finditer(
                r"제\s*(\d+)\s*조[\s_]*(?:\(([^)]+)\))?\s*(.+?)(?=\n\s*제\s*\d+\s*조|\Z)",
                head, re.DOTALL,
            ):
                num = m.group(1)
                title = (m.group(2) or "").strip()
                content = re.sub(r"\s+", " ", m.group(3).strip())
                head_md += f"##### 제{num}조"
                if title:
                    head_md += f" ({title})"
                head_md += f"\n{content}\n"
            # 구조 파서엔 첫 장부터 전달 (중복 방지)
            body_text = body_text[first_ch.start():]

    tree = parse_structure(body_text)

    # Build amendments list for frontmatter (list of dicts)
    amendments_dicts = [
        {"일자": amend.date, "내용": amend.action}
        for amend in header.amendments
    ]

    # enactment_basis: last amendment's .basis field
    enactment_basis = header.amendments[-1].basis if header.amendments else ""

    # Store enactment_basis on the version object BEFORE building frontmatter
    # so generate_frontmatter (which scans entry.versions in reverse) picks
    # up the latest version's basis instead of an older one.
    version.enactment_basis = enactment_basis

    # 채택일 보충: master 에 enactment_date 가 없으면 파싱된 개정이력의 '채택'
    # 항목(가장 이른 채택)에서 가져온다. 채택 항목 자체가 없으면 그대로 둔다.
    if entry.enactment_date is None:
        chae_date = next(
            (a.date for a in header.amendments if a.action == "채택"), None
        )
        if chae_date:
            entry.enactment_date = chae_date

    # 본문 마크다운을 먼저 조립한다(조문수를 실제값으로 세기 위해).
    body_md = generate_markdown(tree)
    # If structure parser found no nodes, use the raw body text as-is
    if not body_md.strip() and body_text.strip():
        body_md = body_text.strip()
    # 서문/첫 장 누락분이 있으면 본문 앞에 합친다 (순서: 서문 → 첫 장 조문 → 본문)
    if preamble_md or head_md:
        body_md = preamble_md + head_md + body_md

    # 조문수 교정: master 목록값 대신 실제 생성된 '본문' 조문(##### 제N조) 수로
    # 설정한다. 부칙(## 부칙)은 별도 보충규정이고 조번호도 재시작하므로 제외하여
    # articles 테이블/통상적 의미(본문 조문수)와 일치시킨다.
    _bu_m = re.search(r'(?m)^#+\s*부\s*칙', body_md)
    _count_region = body_md[:_bu_m.start()] if _bu_m else body_md
    actual_article_count = len(re.findall(r'(?m)^#{5}\s*제\d+조', _count_region))
    if actual_article_count > 0:
        entry.total_articles = actual_article_count

    frontmatter_str = generate_frontmatter(
        entry,
        amendments=amendments_dicts,
        source=version.source,
        is_authentic=(version.source == "nis"),
    )

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

def run_pipeline(config_path: str = "config.yaml", skip_git: bool = False, emit_versions: Optional[str] = None) -> None:
    """Execute the full legalize-kp pipeline."""

    # ── Load config ────────────────────────────────────────────────────────
    print(f"[config] {config_path} 로드 중...")
    cfg = load_config(config_path)

    master_path: str = cfg["master_list"]
    nis_dir: str = cfg["nis_text_dir"]
    mobu_dir: str = cfg["mobu_text_dir"]
    unification_dir: str | None = cfg.get("unification_text_dir")
    output_repo: str = cfg["output_repo"]
    output_kp_dir: str = cfg["output_kp_dir"]
    constitutional_names: list[str] = cfg.get("constitutional_names", [])

    # ── Phase 1: Merge sources ─────────────────────────────────────────────
    print("\n[Phase 1] 소스 병합 중...")
    entries = merge_sources(master_path, nis_dir, mobu_dir, unification_dir)
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

    # ── (선택) 모든 버전 dump — DB law_versions 적재용 ───────────────────────
    if emit_versions:
        print(f"\n[emit-versions] {len(commits)}개 버전 → {emit_versions}")
        with open(emit_versions, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "law_name": c.law_name,
                        "version_date": c.date,
                        "action": c.action,
                        "file_path": c.file_path,
                        "markdown": c.content,
                    }
                    for c in commits
                ],
                f,
                ensure_ascii=False,
            )
        print(f"  → 저장 완료")

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
    parser.add_argument(
        "--emit-versions",
        default=None,
        metavar="PATH",
        help="모든 버전(법령×개정일자)의 markdown 본문을 JSON으로 dump (DB law_versions 적재용)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entry point."""
    args = _parse_args(argv)
    run_pipeline(
        config_path=args.config,
        skip_git=args.skip_git,
        emit_versions=args.emit_versions,
    )


if __name__ == "__main__":
    main()
