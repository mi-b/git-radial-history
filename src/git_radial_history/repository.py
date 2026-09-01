"""Repository acquisition: local validation and remote cloning with caching."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir

from git_radial_history.model import RadialHistoryError

APP_NAME = "git-radial-history"
_CACHE_ROOT = Path(user_cache_dir(APP_NAME))

_SCP_SSH = re.compile(r"^[^/@]+@[^/:]+:.+$")
_ALLOWED_SCHEMES = ("https", "ssh", "git", "file")
_REJECTED_PREFIXES = ("ext::", "fd::")


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git subprocess and return its captured stdout.

    Arguments are always passed as a list; input never touches a shell.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RadialHistoryError("Git executable not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RadialHistoryError(f"git {' '.join(args)} failed: {stderr}") from exc
    return result.stdout


def is_remote_url(source: str) -> bool:
    """Return True if the source looks like a Git remote URL rather than a path."""
    if source.startswith(_REJECTED_PREFIXES):
        return True  # so validation can reject it explicitly
    if _SCP_SSH.match(source):
        return True
    return "://" in source


def sanitise_url(source: str) -> str:
    """Strip embedded credentials and reject unsupported schemes."""
    if source.startswith(_REJECTED_PREFIXES):
        raise RadialHistoryError(f"Unsupported remote helper in URL: {source!r}")

    if _SCP_SSH.match(source):
        return source

    if "://" not in source:
        raise RadialHistoryError(f"Unsupported remote URL: {source!r}")

    scheme, rest = source.split("://", 1)
    if scheme not in _ALLOWED_SCHEMES:
        raise RadialHistoryError(f"Unsupported URL scheme: {scheme!r}")

    if "@" in rest.split("/", 1)[0]:
        userinfo, host = rest.split("@", 1)
        if ":" in userinfo:  # user:password
            raise RadialHistoryError(
                "Refusing HTTPS URL with embedded credentials; use a credential helper."
            )
        # A bare username in ssh URLs is fine, but strip it from stored metadata.
        rest = host if scheme in ("https", "git") else rest
    return f"{scheme}://{rest}"


def repository_name(source: str) -> str:
    """Infer a human-readable project name from a path or URL."""
    trimmed = source.rstrip("/")
    if _SCP_SSH.match(trimmed):
        trimmed = trimmed.split(":", 1)[1]
    name = trimmed.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repository"


def _cache_key(source: str, ref: str) -> str:
    digest = hashlib.sha256(f"{source}\0{ref}".encode()).hexdigest()
    return f"{repository_name(source)}-{digest[:16]}"


@dataclass(frozen=True)
class Repository:
    """A resolved repository ready for history extraction."""

    path: Path
    source: str
    name: str
    ref: str
    commit_hash: str


def _resolve_commit(path: Path, ref: str) -> str:
    output = run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=path).strip()
    if not output:
        raise RadialHistoryError(f"Could not resolve revision: {ref!r}")
    return output


def _check_shallow(path: Path) -> None:
    shallow = run_git(["rev-parse", "--is-shallow-repository"], cwd=path).strip()
    if shallow == "true":
        raise RadialHistoryError(
            "Repository has shallow history; a complete clone is required for accurate analysis."
        )


def open_local(source: str, ref: str) -> Repository:
    path = Path(source).expanduser()
    if not path.exists():
        raise RadialHistoryError(f"Path does not exist: {source}")
    try:
        run_git(["rev-parse", "--git-dir"], cwd=path)
    except RadialHistoryError as exc:
        raise RadialHistoryError(f"Not a Git repository: {source}") from exc

    _check_shallow(path)
    commit = _resolve_commit(path, ref)
    return Repository(
        path=path,
        source=str(path),
        name=repository_name(str(path)),
        ref=ref,
        commit_hash=commit,
    )


def _clone_bare_default(source: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _log(f"Cloning {source} ...")
    run_git(["clone", "--bare", source, str(target)])


def open_remote(
    source: str,
    ref: str,
    *,
    refresh: bool = False,
) -> Repository:
    clean = sanitise_url(source)
    name = repository_name(clean)

    target = _CACHE_ROOT / "repos" / f"{_cache_key(clean, ref)}.git"
    if target.exists() and not refresh:
        _log(f"Using cached clone: {target}")
    elif target.exists() and refresh:
        _log("Refreshing cached clone ...")
        run_git(["fetch", "--tags", "--prune", "origin"], cwd=target)
    else:
        _clone_bare_default(clean, target)

    commit = _resolve_commit(target, ref)
    return Repository(path=target, source=clean, name=name, ref=ref, commit_hash=commit)


def acquire(
    source: str,
    ref: str,
    *,
    refresh: bool = False,
) -> Repository:
    """Resolve a source string into an analysable :class:`Repository`."""
    if is_remote_url(source):
        return open_remote(source, ref, refresh=refresh)
    return open_local(source, ref)
