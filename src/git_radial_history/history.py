"""History extraction: stream ``git log`` and aggregate daily changes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from platformdirs import user_cache_dir

from git_radial_history.model import (
    Analysis,
    DailyChange,
    RadialHistoryError,
    RootCommit,
)
from git_radial_history.repository import APP_NAME, Repository, run_git

SCHEMA_VERSION = 1
_CACHE_ROOT = Path(user_cache_dir(APP_NAME)) / "analysis"

# Record separator and field separator that will not appear in git output.
_RECORD = "\x1e"
_FIELD = "\x1f"

# Custom pretty format: hash, abbrev, author date (ISO strict), author name,
# parents, subject. Fields are FIELD-separated; commits RECORD-separated.
_FORMAT = _RECORD + _FIELD.join(["%H", "%h", "%aI", "%aN", "%P", "%s"])


def _log(message: str) -> None:
    print(message, file=sys.stderr)


class _DayAccumulator:
    __slots__ = ("additions", "deletions", "commits", "tags")

    def __init__(self) -> None:
        self.additions = 0
        self.deletions = 0
        self.commits: list[str] = []
        self.tags: set[str] = set()


def _tag_map(repo: Repository) -> dict[str, list[str]]:
    """Map commit hash -> list of tag names pointing at it (directly or via annotation)."""
    output = run_git(
        ["for-each-ref", "--format=%(objectname) %(*objectname) %(refname:short)", "refs/tags"],
        cwd=repo.path,
    )
    mapping: dict[str, list[str]] = defaultdict(list)
    for line in output.splitlines():
        parts = line.split(" ")
        if len(parts) < 3:
            continue
        obj, peeled, name = parts[0], parts[1], " ".join(parts[2:])
        target = peeled or obj
        mapping[target].append(name)
    return mapping


def _stream_log(repo: Repository):
    """Yield raw commit records from a single streaming ``git log`` process."""
    args = [
        "git",
        "log",
        repo.commit_hash,
        "--numstat",
        "--use-mailmap",
        "--no-ext-diff",
        "--no-textconv",
        "-M",  # detect renames
        f"--pretty=format:{_FORMAT}",
    ]
    try:
        proc = subprocess.Popen(
            args,
            cwd=repo.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise RadialHistoryError("Git executable not found on PATH.") from exc

    assert proc.stdout is not None
    buffer = ""
    for chunk in proc.stdout:
        buffer += chunk
        while _RECORD in buffer:
            record, buffer = buffer.split(_RECORD, 1)
            record = record.strip("\n")
            if record:
                yield record
    tail = buffer.strip("\n")
    if tail:
        yield tail

    proc.stdout.close()
    returncode = proc.wait()
    if returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RadialHistoryError(f"git log failed: {stderr.strip()}")


def _parse_record(record: str) -> tuple[dict, list[tuple[str, str]]]:
    """Split a record into header fields and numstat lines."""
    lines = record.split("\n")
    header = lines[0]
    fields = header.split(_FIELD)
    if len(fields) < 6:
        raise RadialHistoryError("Unexpected git log record structure.")
    full, abbrev, author_iso, author_name, parents, subject = fields[:6]
    stats: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) >= 3:
            stats.append((cols[0], cols[1]))
    meta = {
        "hash": full,
        "abbrev": abbrev,
        "author_iso": author_iso,
        "author_name": author_name,
        "parents": parents.split() if parents else [],
        "subject": subject,
    }
    return meta, stats


def extract(repo: Repository) -> Analysis:
    """Analyse the repository by streaming its full reachable history."""
    tags = _tag_map(repo)
    days: dict[date, _DayAccumulator] = defaultdict(_DayAccumulator)
    total_commits = 0
    binary_records = 0
    roots: list[RootCommit] = []
    earliest: date | None = None
    latest: date | None = None

    for record in _stream_log(repo):
        meta, stats = _parse_record(record)
        total_commits += 1
        # Author-local date preserved from ISO 8601 with offset.
        day = datetime.fromisoformat(meta["author_iso"]).date()
        if earliest is None or day < earliest:
            earliest = day
        if latest is None or day > latest:
            latest = day

        acc = days[day]
        acc.commits.append(meta["abbrev"])
        for tag in tags.get(meta["hash"], []):
            acc.tags.add(tag)

        for add, delete in stats:
            if add == "-" or delete == "-":
                binary_records += 1
                continue
            acc.additions += int(add)
            acc.deletions += int(delete)

        if not meta["parents"]:
            roots.append(
                RootCommit(
                    commit_hash=meta["hash"],
                    abbreviated_hash=meta["abbrev"],
                    author_name=meta["author_name"],
                    date=day,
                    subject=meta["subject"],
                )
            )

    daily = tuple(
        DailyChange(
            date=day,
            additions=acc.additions,
            deletions=acc.deletions,
            net_lines=acc.additions - acc.deletions,
            commit_count=len(acc.commits),
            commit_hashes=tuple(acc.commits),
            tags=tuple(sorted(acc.tags)),
        )
        for day, acc in sorted(days.items())
    )

    root = min(roots, key=lambda r: r.date) if roots else None
    if total_commits == 0:
        raise RadialHistoryError("Repository has no commits reachable from the revision.")

    return Analysis(
        schema_version=SCHEMA_VERSION,
        source=repo.source,
        ref=repo.ref,
        commit_hash=repo.commit_hash,
        repository_name=repo.name,
        root=root,
        root_count=len(roots),
        earliest_date=earliest,
        latest_date=latest,
        total_commits=total_commits,
        binary_records=binary_records,
        days=daily,
    )


def _cache_path(repo: Repository) -> Path:
    key = f"{repo.commit_hash}-{SCHEMA_VERSION}"
    return _CACHE_ROOT / f"{repo.name}-{key}.json"


def _to_json(analysis: Analysis) -> str:
    def day_dict(d: DailyChange) -> dict:
        return {
            "date": d.date.isoformat(),
            "additions": d.additions,
            "deletions": d.deletions,
            "net_lines": d.net_lines,
            "commit_count": d.commit_count,
            "commit_hashes": list(d.commit_hashes),
            "tags": list(d.tags),
        }

    payload = {
        "schema_version": analysis.schema_version,
        "source": analysis.source,
        "ref": analysis.ref,
        "commit_hash": analysis.commit_hash,
        "repository_name": analysis.repository_name,
        "root": None
        if analysis.root is None
        else {
            "commit_hash": analysis.root.commit_hash,
            "abbreviated_hash": analysis.root.abbreviated_hash,
            "author_name": analysis.root.author_name,
            "date": analysis.root.date.isoformat(),
            "subject": analysis.root.subject,
        },
        "root_count": analysis.root_count,
        "earliest_date": analysis.earliest_date.isoformat() if analysis.earliest_date else None,
        "latest_date": analysis.latest_date.isoformat() if analysis.latest_date else None,
        "total_commits": analysis.total_commits,
        "binary_records": analysis.binary_records,
        "days": [day_dict(d) for d in analysis.days],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _from_json(text: str) -> Analysis:
    payload = json.loads(text)
    root = payload["root"]
    return Analysis(
        schema_version=payload["schema_version"],
        source=payload["source"],
        ref=payload["ref"],
        commit_hash=payload["commit_hash"],
        repository_name=payload["repository_name"],
        root=None
        if root is None
        else RootCommit(
            commit_hash=root["commit_hash"],
            abbreviated_hash=root["abbreviated_hash"],
            author_name=root["author_name"],
            date=date.fromisoformat(root["date"]),
            subject=root["subject"],
        ),
        root_count=payload["root_count"],
        earliest_date=date.fromisoformat(payload["earliest_date"])
        if payload["earliest_date"]
        else None,
        latest_date=date.fromisoformat(payload["latest_date"]) if payload["latest_date"] else None,
        total_commits=payload["total_commits"],
        binary_records=payload["binary_records"],
        days=tuple(
            DailyChange(
                date=date.fromisoformat(d["date"]),
                additions=d["additions"],
                deletions=d["deletions"],
                net_lines=d["net_lines"],
                commit_count=d["commit_count"],
                commit_hashes=tuple(d["commit_hashes"]),
                tags=tuple(d["tags"]),
            )
            for d in payload["days"]
        ),
    )


def analyse(repo: Repository) -> Analysis:
    """Return an :class:`Analysis`, reusing the on-disk cache when possible."""
    cache_path = _cache_path(repo)
    if cache_path.exists():
        _log(f"Using cached analysis: {cache_path}")
        try:
            return _from_json(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):  # pragma: no cover
            _log("Cached analysis is corrupt; re-extracting.")

    analysis = extract(repo)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    with open(fd, "w", encoding="utf-8") as handle:
        handle.write(_to_json(analysis))
    tmp.replace(cache_path)

    return analysis
