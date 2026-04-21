"""
structure_parser.py — Parse North Korean law body text into a hierarchical tree.

Hierarchy: 편 > 장 > 절 > 관 > 조 > 항/호 > 목
Special:   부칙 treated as a top-level node.

Public API
----------
parse_structure(text: str) -> list[ArticleNode]
"""

from __future__ import annotations

import re
from typing import Optional

from src.models import ArticleNode


# ---------------------------------------------------------------------------
# Level ordering (index = priority; lower index = higher in hierarchy)
# ---------------------------------------------------------------------------

_STRUCTURAL_LEVELS = ["편", "장", "절", "관", "조", "부칙"]

_LEVEL_INDEX: dict[str, int] = {lvl: i for i, lvl in enumerate(_STRUCTURAL_LEVELS)}

# 부칙 is always root-level — give it the same index as 편 so the stack
# is fully cleared before attaching it.
_LEVEL_INDEX["부칙"] = 0

# Sub-article levels (children of 조) are NOT in the main stack
_SUB_LEVELS = ["호", "목"]


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# High-level structural headers (편, 장, 절, 관)
_PART_RE    = re.compile(r'^제(\d+)편\s+(.+)')       # 편
_CHAPTER_RE = re.compile(r'^제(\d+)장\s+(.+)')       # 장
_SECTION_RE = re.compile(r'^제(\d+)절\s+(.+)')       # 절
_SUBSEC_RE  = re.compile(r'^제(\d+)관\s+(.+)')       # 관

# Article: 제N조 (title)  — title may use ASCII or fullwidth parens
_ARTICLE_RE = re.compile(r'^제(\d+)조\s*[\(（](.+?)[\)）]')

# Article without parenthesized title: 제N조 content... or 제N조content...
_ARTICLE_NOTITLE_RE = re.compile(r'^제(\d+)조(?:\s+|(?=[가-힣]))(.*)')

# 부칙
_APPENDIX_RE = re.compile(r'^부\s*칙')

# Sub-article: 호 — indented digit + period or digit + space + content
_HO_RE  = re.compile(r'^\s+(\d+)[.\s]\s*(.*)')

# Sub-article: 목 — 4+ spaces + Korean character + period/paren
_MOK_RE = re.compile(r'^\s{4,}([가-힣])[\.）\)]\s*(.*)')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_structural(stripped: str):
    """
    Try to match a structural pattern on a *stripped* line.

    Returns (level_str, number_str, title_str, inline_content_str) or None.
    inline_content is non-empty only when an article has no parenthesized
    title but has text on the same line (e.g. "제2조대외경제중재법의...").
    """
    m = _PART_RE.match(stripped)
    if m:
        return ("편", m.group(1), m.group(2).strip(), "")

    m = _CHAPTER_RE.match(stripped)
    if m:
        return ("장", m.group(1), m.group(2).strip(), "")

    m = _SECTION_RE.match(stripped)
    if m:
        return ("절", m.group(1), m.group(2).strip(), "")

    m = _SUBSEC_RE.match(stripped)
    if m:
        return ("관", m.group(1), m.group(2).strip(), "")

    m = _ARTICLE_RE.match(stripped)
    if m:
        # Check for content after the closing paren
        after_paren = stripped[m.end():].strip()
        return ("조", m.group(1), m.group(2).strip(), after_paren)

    m = _ARTICLE_NOTITLE_RE.match(stripped)
    if m:
        # No parenthesized title; rest of line is initial content, not title
        rest = m.group(2).strip() if m.group(2) else ""
        return ("조", m.group(1), None, rest)

    m = _APPENDIX_RE.match(stripped)
    if m:
        return ("부칙", "부칙", None, "")

    return None


def _flush_content(pending_lines: list[str]) -> Optional[str]:
    """Convert accumulated content lines to a single string, or None if empty."""
    # Strip leading/trailing blank lines but preserve internal ones
    lines = pending_lines.copy()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    return "\n".join(lines)


def _match_ho(raw_line: str) -> Optional[tuple[str, str]]:
    """Match a 호 (numbered item) line. Returns (number, content) or None."""
    # 목 must be checked first (more specific pattern)
    m = _MOK_RE.match(raw_line)
    if m:
        return None  # 목 is handled separately

    m = _HO_RE.match(raw_line)
    if m and raw_line.startswith(" "):  # must be indented
        return (m.group(1), m.group(2).strip())
    return None


def _match_mok(raw_line: str) -> Optional[tuple[str, str]]:
    """Match a 목 (sub-item) line. Returns (label, content) or None."""
    m = _MOK_RE.match(raw_line)
    if m:
        return (m.group(1), m.group(2).strip())
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_structure(text: str) -> list[ArticleNode]:
    """
    Parse the body of a North Korean law text into a hierarchical tree.

    Parameters
    ----------
    text : str
        Full (or body-only) text of the law document.

    Returns
    -------
    list[ArticleNode]
        Top-level nodes of the parsed hierarchy.
    """
    lines = text.split("\n")

    # Root container — collects top-level nodes
    root_children: list[ArticleNode] = []

    # Stack: list of (level_index: int, node: ArticleNode)
    # level_index uses _LEVEL_INDEX for structural levels.
    # A sentinel value of -1 represents the root.
    stack: list[tuple[int, list[ArticleNode]]] = [(-1, root_children)]

    # Content lines pending assignment to the current top-of-stack node
    pending_content: list[str] = []

    # Sub-article state (호/목 within current 조)
    current_article: Optional[ArticleNode] = None
    current_ho: Optional[ArticleNode] = None

    def _flush_to_current(node: ArticleNode) -> None:
        """Assign pending_content to node.content."""
        content = _flush_content(pending_content)
        if content:
            if node.content:
                node.content = node.content + "\n" + content
            else:
                node.content = content
        pending_content.clear()

    def _current_node() -> Optional[ArticleNode]:
        """Return the ArticleNode at the top of the stack (if any)."""
        if len(stack) > 1:
            return stack[-1][1]  # type: ignore[return-value]
        return None

    # Re-implement: stack stores (level_index, ArticleNode) pairs,
    # with a virtual root frame holding the root_children list.
    # Let's use a cleaner approach:

    # Stack of (level_index, ArticleNode)
    node_stack: list[tuple[int, ArticleNode]] = []

    def _parent_children() -> list[ArticleNode]:
        """Return the children list to attach the next structural node to."""
        if not node_stack:
            return root_children
        return node_stack[-1][1].children

    def _pop_to_level(new_level_idx: int) -> None:
        """
        Pop the stack until the top is a node that can be a parent
        of a node with level index `new_level_idx`.
        i.e. pop while stack top level_index >= new_level_idx
        """
        while node_stack and node_stack[-1][0] >= new_level_idx:
            node_stack.pop()

    def _commit_pending_to_top() -> None:
        """Write any accumulated pending_content to the top node on the stack."""
        if not pending_content:
            return
        target = node_stack[-1][1] if node_stack else None
        if target is None:
            pending_content.clear()
            return
        content = _flush_content(pending_content)
        pending_content.clear()
        if content:
            if target.content:
                target.content = target.content + "\n" + content
            else:
                target.content = content

    # Sub-article tracking (호, 목) — children of the innermost 조
    _current_article: Optional[ArticleNode] = None  # innermost 조 node
    _current_ho_node: Optional[ArticleNode] = None  # innermost 호 node
    _ho_pending: list[str] = []                     # content pending for current 호/목
    _in_subarticle: bool = False                    # are we accumulating 호/목?

    def _flush_ho_pending() -> None:
        nonlocal _current_ho_node
        if _ho_pending and _current_ho_node is not None:
            content = _flush_content(_ho_pending)
            if content:
                _current_ho_node.content = (
                    (_current_ho_node.content + "\n" + content)
                    if _current_ho_node.content else content
                )
        _ho_pending.clear()

    for raw_line in lines:
        stripped = raw_line.strip()

        # ----------------------------------------------------------------
        # 1. Try structural match (편/장/절/관/조/부칙)
        # ----------------------------------------------------------------
        match = _match_structural(stripped)
        if match:
            level_str, number, title, inline_content = match
            level_idx = _LEVEL_INDEX[level_str]

            # Flush any sub-article content
            _flush_ho_pending()
            _in_subarticle = False
            _current_ho_node = None
            _current_article = None

            # Flush pending content to current top node
            _commit_pending_to_top()

            # Pop stack to find correct parent
            _pop_to_level(level_idx)

            # Create new node (set inline_content as initial content if present)
            new_node = ArticleNode(
                level=level_str,
                number=number,
                title=title,
                content=inline_content if inline_content else None,
                children=[],
            )

            # Attach to parent
            _parent_children().append(new_node)

            # Push onto stack
            node_stack.append((level_idx, new_node))

            # Track current article for sub-article parsing
            if level_str == "조":
                _current_article = new_node

            continue

        # ----------------------------------------------------------------
        # 2. Try sub-article match (목 before 호 — more specific)
        # ----------------------------------------------------------------
        if _current_article is not None:
            mok = _match_mok(raw_line)
            if mok:
                label, content = mok
                _flush_ho_pending()
                mok_node = ArticleNode(
                    level="목",
                    number=label,
                    title=None,
                    content=content if content else None,
                    children=[],
                )
                # 목 is a child of the current 호 (if any), else of the article
                if _current_ho_node is not None:
                    _current_ho_node.children.append(mok_node)
                else:
                    _current_article.children.append(mok_node)
                _current_ho_node = mok_node
                _in_subarticle = True
                continue

            ho = _match_ho(raw_line)
            if ho:
                number_str, content = ho
                _flush_ho_pending()
                ho_node = ArticleNode(
                    level="호",
                    number=number_str,
                    title=None,
                    content=content if content else None,
                    children=[],
                )
                _current_article.children.append(ho_node)
                _current_ho_node = ho_node
                _in_subarticle = True
                continue

        # ----------------------------------------------------------------
        # 3. Plain content line
        # ----------------------------------------------------------------
        if _in_subarticle and _current_ho_node is not None:
            # Continuation line for current 호/목
            _ho_pending.append(stripped)
        else:
            # Content for the current structural node
            pending_content.append(stripped)

    # ----------------------------------------------------------------
    # End of input — flush any remaining content
    # ----------------------------------------------------------------
    _flush_ho_pending()
    _commit_pending_to_top()

    return root_children
