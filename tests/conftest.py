"""Shared pytest fixtures: temporary Git repositories with fixed history."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout


def _commit(repo: Path, message: str, iso_date: str, base_env: dict) -> None:
    env = dict(base_env)
    env["GIT_AUTHOR_DATE"] = iso_date
    env["GIT_COMMITTER_DATE"] = iso_date
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-m", message, env=env)


@pytest.fixture
def git_env() -> dict:
    import os

    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Ada Test",
        GIT_AUTHOR_EMAIL="ada@example.com",
        GIT_COMMITTER_NAME="Ada Test",
        GIT_COMMITTER_EMAIL="ada@example.com",
    )
    return env


@pytest.fixture
def sample_repo(tmp_path: Path, git_env: dict) -> Path:
    """A repo spanning three years with a positive, negative and growth day, plus a tag."""
    repo = tmp_path / "sample"
    repo.mkdir()
    _git(repo, "init", "-q", env=git_env)

    (repo / "f.txt").write_text("a\nb\nc\n")
    _commit(repo, "init", "2021-03-01T12:00:00+00:00", git_env)

    (repo / "f.txt").write_text("a\nb\n")
    _commit(repo, "trim", "2022-06-15T12:00:00+00:00", git_env)
    _git(repo, "tag", "-a", "v1.0.0", "-m", "release", env=git_env)

    (repo / "f.txt").write_text("a\nb\nx\ny\nz\n")
    _commit(repo, "grow", "2023-01-10T12:00:00+00:00", git_env)

    return repo
