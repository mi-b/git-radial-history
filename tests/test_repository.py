from __future__ import annotations

import pytest

from git_radial_history.model import RadialHistoryError
from git_radial_history.repository import (
    acquire,
    is_remote_url,
    repository_name,
    sanitise_url,
)


def test_local_acquire_resolves_commit(sample_repo):
    repo = acquire(str(sample_repo), "HEAD")
    assert len(repo.commit_hash) == 40
    assert repo.name == "sample"


def test_invalid_path():
    with pytest.raises(RadialHistoryError):
        acquire("/no/such/path/here", "HEAD")


def test_not_a_repo(tmp_path):
    with pytest.raises(RadialHistoryError):
        acquire(str(tmp_path), "HEAD")


def test_bad_revision(sample_repo):
    with pytest.raises(RadialHistoryError):
        acquire(str(sample_repo), "nope-does-not-exist")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/git/git", True),
        ("git@github.com:git/git.git", True),
        ("ssh://git@host/path.git", True),
        ("/local/path", False),
        ("./rel", False),
    ],
)
def test_is_remote_url(url, expected):
    assert is_remote_url(url) is expected


def test_reject_embedded_credentials():
    with pytest.raises(RadialHistoryError):
        sanitise_url("https://user:secret@github.com/foo/bar.git")


def test_reject_ext_helper():
    with pytest.raises(RadialHistoryError):
        sanitise_url("ext::sh -c evil")


def test_sanitise_strips_username():
    assert sanitise_url("https://token@github.com/x/y.git") == "https://github.com/x/y.git"


@pytest.mark.parametrize(
    "source,name",
    [
        ("https://github.com/git/git.git", "git"),
        ("git@github.com:org/repo.git", "repo"),
        ("/a/b/myproject/", "myproject"),
    ],
)
def test_repository_name(source, name):
    assert repository_name(source) == name


def test_bare_remote_via_file_url(sample_repo, tmp_path):
    remote = f"file://{sample_repo}"
    repo = acquire(remote, "HEAD")
    assert len(repo.commit_hash) == 40
    assert repo.path.exists()
