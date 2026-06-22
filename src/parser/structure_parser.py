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
# 조 번호와 제목 사이의 OCR 잡음(언더스코어 '_')도 허용 — main.py 의 장-이전 조문
# 우회 regex(제\d+조[\s_]*)와 동일하게 맞춤.
_ARTICLE_RE = re.compile(r'^제(\d+)조[\s_]*[\(（](.+?)[\)）]')

# Article without parenthesized title: 제N조 content... or 제N조content...
#
# 주의: '제N조' 바로 뒤(공백 없이)에 조사가 붙는 경우는 본문 속 '교차참조'
# (예: "제46조의 행위에 대하여...", "제47조에 따라...")이므로 새 조문 헤더로
# 오인하면 안 된다. 공백 없는 분기에서 조사로 시작하면 매치하지 않는다.
#   - 공백/언더스코어가 있으면(제N조 내용) 정상 조문으로 본다.
#   - 공백 없이 한글이 바로 오면(제2조대외경제중재법…) 조문이되, 조사 시작은 제외.
_JOSA = r'의|에|를|을|은|는|이|가|와|과|로|및|도|만|나|란|며|부터|까지|에서|에게|보다|마다'
_ARTICLE_NOTITLE_RE = re.compile(
    r'^제(\d+)조(?:[\s_]+|(?=[가-힣])(?!(?:' + _JOSA + r')))(.*)'
)

# 부칙 — 단, '부칙은/부칙을/부칙에...' 처럼 조사가 붙은 본문 문장은 부칙 섹션
# 헤더가 아니므로 제외한다(예: 법제정법 제67조 "부칙은 해당 법문건의 시행과...").
# 실제 부칙 헤더는 '부칙' 단독, '부칙 <날짜>', '부칙(...)' 형태로 뒤에 한글이 붙지 않는다.
_APPENDIX_RE = re.compile(r'^부\s*칙(?![가-힣])')

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


# 조 제목 줄바꿈 결합용: 여는 괄호 있고 닫는 괄호 없는 '제N조(' 헤더 줄 판별
_ARTICLE_OPEN_RE = re.compile(r'^제(\d+)조[\s_]*[\(（]')
# 결합을 중단해야 하는 새 구조 헤더(다음 조문/장 등 삼킴 방지)
_STRUCT_HEADER_RE = re.compile(r'^(?:제\d+[조장절관편]|부\s*칙)')


def _join_wrapped_article_titles(text: str, max_lookahead: int = 3) -> str:
    """제목이 여러 줄로 끊긴 조 헤더를 한 줄로 결합한다.

    예) '제5조(문화유물을 ... 보호관리할데 대한\n원칙)' → '제5조(... 대한 원칙)'
    여는 괄호만 있고 닫는 괄호가 없는 '제N조(' 헤더 줄을, 닫는 괄호가 나오는
    줄까지(최대 max_lookahead 줄) 공백으로 이어 붙인다.

    안전장치:
      - 닫는 괄호를 찾기 전에 새 구조 헤더(제N조/장/절/관/편/부칙)를 만나면
        결합을 중단하고 원래 줄을 그대로 둔다(다음 조문을 삼키지 않음).
        예) 제목 괄호가 OCR로 안 닫힌 경우, 또는 닫는 괄호가 '〉' 등으로
        잘못 인식된 경우에도 다음 조문이 보존된다.
      - max_lookahead 안에 닫는 괄호가 없으면 결합하지 않는다.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        if _ARTICLE_OPEN_RE.match(ln.strip()) and ")" not in ln and "）" not in ln:
            j = i + 1
            merged = ln.rstrip()
            found = False
            while j < n and (j - i) <= max_lookahead:
                nxt = lines[j].strip()
                # 다음 줄이 새 구조 헤더면 결합 중단(다음 조문 삼킴 방지)
                if _STRUCT_HEADER_RE.match(nxt):
                    break
                merged = merged + " " + nxt
                if ")" in lines[j] or "）" in lines[j]:
                    found = True
                    j += 1
                    break
                j += 1
            if found:
                out.append(merged)
                i = j
                continue
        out.append(ln)
        i += 1
    return "\n".join(out)


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
    # 줄바꿈으로 끊긴 조 제목을 먼저 한 줄로 결합(조문 누락 방지).
    text = _join_wrapped_article_titles(text)
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
