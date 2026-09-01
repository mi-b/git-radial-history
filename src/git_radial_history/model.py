"""Typed data models shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class RadialHistoryError(Exception):
    """Base class for all expected, user-facing failures."""


@dataclass(frozen=True)
class DailyChange:
    """Aggregated line changes and commits for a single calendar day."""

    date: date
    additions: int
    deletions: int
    net_lines: int
    commit_count: int
    commit_hashes: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RootCommit:
    """Details of the earliest reachable root commit."""

    commit_hash: str
    abbreviated_hash: str
    author_name: str
    date: date
    subject: str


@dataclass(frozen=True)
class Analysis:
    """The complete analysed history of a repository at a revision."""

    schema_version: int
    source: str
    ref: str
    commit_hash: str
    repository_name: str
    root: RootCommit | None
    root_count: int
    earliest_date: date | None
    latest_date: date | None
    total_commits: int
    binary_records: int
    days: tuple[DailyChange, ...] = field(default_factory=tuple)
