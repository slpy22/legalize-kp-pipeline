"""
history_builder.py

Builds a Git repository where each commit represents a law's enactment
or amendment, with the commit date set to the actual adoption date.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from git import Repo, Actor

# Korean Standard Time (UTC+9)
KST = timezone(timedelta(hours=9))

# Single bot identity used for all commits
_BOT_AUTHOR = Actor("legalize-kp-bot", "bot@legalize-kp.org")


@dataclass
class CommitEntry:
    """One law enactment or amendment to be recorded as a git commit."""

    date: str        # "YYYY-MM-DD"
    law_name: str    # e.g. "쏘프트웨어보호법"
    action: str      # "채택" | "수정보충"
    file_path: str   # relative path, e.g. "kp/과학기술법/법령.md"
    content: str     # full file text


def build_history(repo_path: str, commits: list[CommitEntry]) -> None:
    """Create a git repository at *repo_path* and replay all commit entries.

    Commits are ordered by (date ascending, law_name Korean-alphabetical).
    Each commit's author/committer date is set to noon KST on the entry date.
    """
    # --- Sort: date ascending, then law_name lexicographic (Korean 가나다순) ---
    sorted_commits = sorted(commits, key=lambda e: (e.date, e.law_name))

    # --- Initialise repository ---
    os.makedirs(repo_path, exist_ok=True)
    repo = Repo.init(repo_path)

    for entry in sorted_commits:
        # Write file (create intermediate directories as needed)
        abs_file_path = os.path.join(repo_path, entry.file_path)
        os.makedirs(os.path.dirname(abs_file_path), exist_ok=True)
        with open(abs_file_path, "w", encoding="utf-8") as fh:
            fh.write(entry.content)

        # Stage the file using a relative path (no leading slash/backslash)
        rel_path = entry.file_path.lstrip("/\\").replace("\\", "/")
        repo.index.add([rel_path])

        # Build commit timestamp: YYYY-MM-DDT12:00:00+09:00
        # 날짜가 없거나 잘못된 경우 1970-01-01 사용 (Git 호환 최소 날짜)
        try:
            parts = entry.date.split("-")
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 1970:
                year = 1970  # Git은 음수 타임스탬프를 badDate로 처리
            dt = datetime(year, month, day, 12, 0, 0, tzinfo=KST)
        except (ValueError, IndexError):
            dt = datetime(1970, 1, 1, 12, 0, 0, tzinfo=KST)

        # Pass the datetime object directly — GitPython's parse_date handles
        # aware datetime instances correctly; ISO strings with colon-tz offsets
        # (e.g. "+09:00") trip up an older strptime path in some versions.
        repo.index.commit(
            message=f"{entry.law_name} ({entry.action})",
            author=_BOT_AUTHOR,
            committer=_BOT_AUTHOR,
            author_date=dt,
            commit_date=dt,
        )
