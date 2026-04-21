"""
markdown_writer.py — Convert ArticleNode tree + law metadata to a Markdown file.

Public API
----------
generate_frontmatter(entry, amendments, source, **kwargs) -> str
generate_markdown(tree) -> str
write_law_file(entry, tree, amendments, output_path, **kwargs)
"""

from __future__ import annotations

import pathlib
from typing import Optional

import yaml

from src.models import ArticleNode, LawEntry


# ---------------------------------------------------------------------------
# Heading map: level string → Markdown heading prefix
# ---------------------------------------------------------------------------

_HEADING_MAP: dict[str, str] = {
    "편": "#",
    "장": "##",
    "절": "###",
    "관": "####",
    "조": "#####",
    "부칙": "##",
}


# ---------------------------------------------------------------------------
# generate_frontmatter
# ---------------------------------------------------------------------------

def generate_frontmatter(
    entry: LawEntry,
    amendments: list,
    source: str,
    *,
    text_unavailable: bool = False,
    is_authentic: Optional[bool] = None,
) -> str:
    """
    Return a YAML string (without --- delimiters) representing the law's frontmatter.

    Parameters
    ----------
    entry : LawEntry
        Law metadata.
    amendments : list of dict
        Revision history, e.g. [{"일자": "1988-12-15", "내용": "채택"}, ...].
    source : str
        Source identifier, e.g. "nis", "mobu", "unknown".
    text_unavailable : bool
        If True, adds 텍스트미확보: true to the output.
    is_authentic : bool | None
        Whether this is the authentic version (정본여부). Omitted if None.
    """
    data: dict = {}

    # Always-present fields
    data["제목"] = entry.name
    data["카테고리"] = entry.category

    if entry.enactment_date is not None:
        data["채택일"] = entry.enactment_date

    if entry.latest_version_date is not None:
        data["최신버전일"] = entry.latest_version_date

    # Enactment basis — pull from the most recent version that has it, if any
    basis: Optional[str] = None
    for version in reversed(entry.versions):
        if version.enactment_basis:
            basis = version.enactment_basis
            break
    if basis is not None:
        data["시행근거"] = basis

    if entry.total_articles is not None:
        data["조문수"] = entry.total_articles

    if entry.chapter_count is not None:
        data["장수"] = entry.chapter_count

    data["개정횟수"] = entry.amendment_count
    data["출처"] = source

    # NIS fields
    if entry.nis_volume is not None:
        data["국정원권"] = entry.nis_volume
    if entry.nis_page is not None:
        data["국정원페이지"] = entry.nis_page

    # 법무부 key
    if entry.mobu_key is not None:
        data["법무부키"] = entry.mobu_key

    # Date estimation flag
    # Check if any version has date_estimated=True
    date_estimated = any(v.date_estimated for v in entry.versions)
    data["날짜추정"] = date_estimated

    # OCR fields
    data["OCR여부"] = entry.is_ocr
    if entry.ocr_confidence is not None:
        data["OCR신뢰도"] = entry.ocr_confidence

    # Authentic version flag
    if is_authentic is not None:
        data["정본여부"] = is_authentic

    # Revision history
    data["개정이력"] = amendments

    # Optional flag: text unavailable
    if text_unavailable:
        data["텍스트미확보"] = True

    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# generate_markdown
# ---------------------------------------------------------------------------

def _render_node(node: ArticleNode) -> str:
    """Recursively render a single ArticleNode to Markdown text."""
    level = node.level
    lines: list[str] = []

    if level == "조":
        # ##### 제N조 (title)
        heading = f"##### 제{node.number}조"
        if node.title:
            heading += f" ({node.title})"
        lines.append(heading)
        if node.content:
            lines.append(node.content)
        for child in node.children:
            lines.append(_render_node(child))

    elif level == "부칙":
        lines.append("## 부칙")
        if node.content:
            lines.append(node.content)
        for child in node.children:
            lines.append(_render_node(child))

    elif level == "호":
        # 2-space indent + number + ". " + content
        content = node.content or ""
        lines.append(f"  {node.number}. {content}")
        for child in node.children:
            lines.append(_render_node(child))

    elif level == "목":
        # 4-space indent + Korean label + ") " + content
        content = node.content or ""
        lines.append(f"    {node.number}) {content}")
        for child in node.children:
            lines.append(_render_node(child))

    else:
        # 편, 장, 절, 관
        prefix = _HEADING_MAP.get(level, "##")
        heading = f"{prefix} 제{node.number}{level}"
        if node.title:
            heading += f" {node.title}"
        lines.append(heading)
        if node.content:
            lines.append(node.content)
        for child in node.children:
            lines.append(_render_node(child))

    return "\n".join(lines)


def generate_markdown(tree: list[ArticleNode]) -> str:
    """
    Convert a list of top-level ArticleNodes to a Markdown body string.

    Top-level nodes are separated by double newlines.
    """
    parts = [_render_node(node) for node in tree]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# write_law_file
# ---------------------------------------------------------------------------

def write_law_file(
    entry: LawEntry,
    tree: list[ArticleNode],
    amendments: list,
    output_path: str,
    **kwargs,
) -> None:
    """
    Combine frontmatter + Markdown body and write to output_path.

    Creates parent directories as needed.
    The file format is::

        ---
        {frontmatter}---

        {body}

    Parameters
    ----------
    entry : LawEntry
    tree : list[ArticleNode]
    amendments : list of dict
    output_path : str
        Destination file path.
    **kwargs
        Passed through to generate_frontmatter (e.g. source, text_unavailable).
    """
    # Extract source from kwargs; default to "unknown"
    source = kwargs.pop("source", "unknown")

    frontmatter = generate_frontmatter(entry, amendments=amendments, source=source, **kwargs)
    body = generate_markdown(tree)

    content = f"---\n{frontmatter}---\n\n{body}\n"

    path = pathlib.Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
