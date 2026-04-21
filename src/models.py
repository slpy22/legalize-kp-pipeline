"""
Data models for the legalize-kp-pipeline project.
Defines structured representations of North Korean law entries,
law versions, and article nodes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LawVersion:
    """Represents a single version/revision of a law."""
    date: str                          # ISO date string, e.g. "2023-09-07"
    action: str                        # e.g. "제정", "수정보충", "채택"
    source: str                        # e.g. "nis", "mobu", "unknown"
    text: Optional[str] = None         # Full text content (may be None if not available)
    text_available: bool = False       # Whether the text is actually available
    date_estimated: bool = False       # Whether the date is an estimate
    enactment_basis: Optional[str] = None  # Legal basis for enactment, if known


@dataclass
class LawEntry:
    """Represents a single law entry in the master list."""
    name: str
    category: str
    enactment_date: Optional[str] = None
    latest_version_date: Optional[str] = None
    total_articles: Optional[int] = None
    chapter_count: Optional[int] = None
    amendment_count: int = 0
    chapters: List[str] = field(default_factory=list)
    has_appendix: bool = False
    in_nis: bool = False
    in_mobu: bool = False
    nis_volume: Optional[int] = None
    nis_page: Optional[int] = None
    mobu_key: Optional[str] = None
    mobu_files: List[str] = field(default_factory=list)
    is_constitutional: bool = False
    is_ocr: bool = False
    ocr_confidence: Optional[float] = None
    versions: List[LawVersion] = field(default_factory=list)

    @property
    def file_type(self) -> str:
        """Returns '헌법' for constitutional documents, '법령' for regular laws."""
        return "헌법" if self.is_constitutional else "법령"

    @property
    def dir_name(self) -> str:
        """Directory name is the law name itself."""
        return self.name

    @property
    def file_name(self) -> str:
        """File name is '<file_type>.md'."""
        return f"{self.file_type}.md"


@dataclass
class ArticleNode:
    """Represents a node in the hierarchical structure of a law document."""
    level: int                         # Nesting level (0 = top, 1 = chapter, 2 = article, etc.)
    number: str                        # e.g. "제1조", "제1장"
    title: Optional[str] = None        # Optional section title
    content: Optional[str] = None      # Article text content
    children: List[ArticleNode] = field(default_factory=list)
