"""
Tests for git/history_builder.py

TDD: write tests first → they fail → implement → all pass.
"""
import pytest
from git import Repo

from src.git.history_builder import CommitEntry, build_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(date: str, law_name: str, action: str = "채택",
                content: str = "본문") -> CommitEntry:
    safe = law_name.replace("/", "_")
    return CommitEntry(
        date=date,
        law_name=law_name,
        action=action,
        file_path=f"kp/{safe}/법령.md",
        content=content,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_history_creates_repo(tmp_path):
    """Single commit → .git directory must exist."""
    output_dir = str(tmp_path / "legalize-kp")
    entries = [_make_entry("1988-01-15", "쏘프트웨어보호법")]

    build_history(output_dir, entries)

    assert (tmp_path / "legalize-kp" / ".git").is_dir()


def test_build_history_commit_date(tmp_path):
    """Two commits for the same law (1988, 2022) → commit dates match."""
    output_dir = str(tmp_path / "legalize-kp")
    entries = [
        _make_entry("1988-01-15", "쏘프트웨어보호법", "채택"),
        _make_entry("2022-09-07", "쏘프트웨어보호법", "수정보충",
                    content="수정된 본문"),
    ]

    build_history(output_dir, entries)

    repo = Repo(output_dir)
    commits = list(repo.iter_commits("HEAD", reverse=True))
    assert len(commits) == 2

    # First commit: 1988-01-15T12:00:00+09:00
    c0 = commits[0]
    assert c0.authored_date == c0.committed_date  # same timestamp
    # authored_datetime is timezone-aware
    dt0 = c0.authored_datetime
    assert dt0.year == 1988
    assert dt0.month == 1
    assert dt0.day == 15
    assert dt0.hour == 12
    assert dt0.minute == 0

    # Second commit: 2022-09-07
    dt1 = commits[1].authored_datetime
    assert dt1.year == 2022
    assert dt1.month == 9
    assert dt1.day == 7


def test_build_history_commit_message(tmp_path):
    """Commit message must be '{law_name} ({action})'."""
    output_dir = str(tmp_path / "legalize-kp")
    entries = [_make_entry("1988-01-15", "쏘프트웨어보호법", "채택")]

    build_history(output_dir, entries)

    repo = Repo(output_dir)
    commit = list(repo.iter_commits("HEAD"))[0]
    assert commit.message == "쏘프트웨어보호법 (채택)"


def test_build_history_multiple_laws_same_date(tmp_path):
    """Same date: '가법' and '나법' → 가법 committed first (가나다순)."""
    output_dir = str(tmp_path / "legalize-kp")
    entries = [
        # Intentionally pass 나법 first to verify sorting
        _make_entry("2000-03-01", "나법"),
        _make_entry("2000-03-01", "가법"),
    ]

    build_history(output_dir, entries)

    repo = Repo(output_dir)
    # iter_commits without reverse=True gives newest-first; use reverse=True
    commits = list(repo.iter_commits("HEAD", reverse=True))
    assert len(commits) == 2
    assert commits[0].message == "가법 (채택)"
    assert commits[1].message == "나법 (채택)"


def test_build_history_file_content(tmp_path):
    """File written to repo must contain exactly the content passed in."""
    output_dir = str(tmp_path / "legalize-kp")
    content = "# 쏘프트웨어보호법\n\n제1조 본문이다.\n"
    entries = [_make_entry("1988-01-15", "쏘프트웨어보호법", content=content)]

    build_history(output_dir, entries)

    written = (tmp_path / "legalize-kp" / "kp" / "쏘프트웨어보호법" / "법령.md").read_text(
        encoding="utf-8"
    )
    assert written == content
