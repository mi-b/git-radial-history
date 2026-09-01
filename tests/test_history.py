from __future__ import annotations

from datetime import date

from git_radial_history.history import analyse, extract
from git_radial_history.repository import acquire


def _analyse(repo_path):
    repo = acquire(str(repo_path), "HEAD")
    return extract(repo)


def test_daily_aggregates(sample_repo):
    analysis = _analyse(sample_repo)
    days = {d.date: d for d in analysis.days}

    assert date(2021, 3, 1) in days
    assert date(2022, 6, 15) in days
    assert date(2023, 1, 10) in days

    init = days[date(2021, 3, 1)]
    assert init.additions == 3 and init.deletions == 0
    assert init.net_lines == 3

    trim = days[date(2022, 6, 15)]
    assert trim.net_lines == -1
    assert "v1.0.0" in trim.tags

    grow = days[date(2023, 1, 10)]
    assert grow.net_lines == 3


def test_root_detection(sample_repo):
    analysis = _analyse(sample_repo)
    assert analysis.root is not None
    assert analysis.root.date == date(2021, 3, 1)
    assert analysis.root_count == 1
    assert analysis.total_commits == 3


def test_earliest_latest(sample_repo):
    analysis = _analyse(sample_repo)
    assert analysis.earliest_date == date(2021, 3, 1)
    assert analysis.latest_date == date(2023, 1, 10)


def test_binary_file_recorded(tmp_path, git_env):
    import subprocess

    repo = tmp_path / "bin"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=git_env)
    (repo / "data.bin").write_bytes(bytes(range(256)))
    env = dict(git_env)
    env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "2020-01-01T00:00:00+00:00"
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "bin"], cwd=repo, check=True, env=env)

    r = acquire(str(repo), "HEAD")
    analysis = extract(r)
    assert analysis.binary_records >= 1


def test_cache_roundtrip(sample_repo):
    repo = acquire(str(sample_repo), "HEAD")
    first = analyse(repo)
    second = analyse(repo)
    assert first == second
