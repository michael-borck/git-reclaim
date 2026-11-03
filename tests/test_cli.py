"""Tests for git-reclaim."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from git_reclaim.cli import (
    du_kb,
    find_cache_dirs,
    find_repos,
    main,
    parse_size,
)


@pytest.fixture(autouse=True)
def git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git hermetic and set an identity for test commits."""
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def run_git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


def test_default_dry_run_lists_caches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "f").write_text("x")

    assert main(["-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "node_modules" in out
    assert "dry run" in out
    assert (repo / "node_modules").is_dir()


def test_purge_removes_untracked_caches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "node_modules").mkdir()
    (repo / "sub" / "target").mkdir(parents=True)

    assert main(["-p", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert not (repo / "node_modules").exists()
    assert not (repo / "sub" / "target").exists()
    assert "purged 2 of 2" in out


def test_purge_skips_a_dir_git_tracks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "target").mkdir()
    (repo / "target" / "tracked.txt").write_text("hello")
    run_git(repo, "add", "target")
    run_git(repo, "commit", "-q", "-m", "commit target dir")
    (repo / "node_modules").mkdir()

    assert main(["-p", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert (repo / "target").is_dir()
    assert (repo / "target" / "tracked.txt").is_file()
    assert not (repo / "node_modules").exists()
    assert "skipped" in out
    assert "purged 1 of 2" in out


def test_purge_never_touches_refs_inside_git(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "a")
    run_git(repo, "branch", "target/v2")
    run_git(repo, "branch", "venv/x")
    (repo / "node_modules").mkdir()

    assert main(["-p", "-d", str(tmp_path)]) == 0

    run_git(repo, "rev-parse", "--verify", "-q", "refs/heads/target/v2")
    run_git(repo, "rev-parse", "--verify", "-q", "refs/heads/venv/x")
    assert not (repo / "node_modules").exists()


def test_purge_does_not_follow_symlinks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "a")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (repo / "node_modules").symlink_to(outside, target_is_directory=True)

    assert main(["-p", "-d", str(tmp_path)]) == 0

    assert (outside / "keep.txt").exists()


def test_repos_lists_clean_pushed_clone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = make_repo(tmp_path / "origin")
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(tmp_path / "pushed")], check=True
    )
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(tmp_path / "messy")], check=True
    )
    (tmp_path / "messy" / "uncommitted.txt").write_text("x")

    assert main(["-r", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "pushed" in out
    assert "messy" not in out
    assert "1 safe" in out
    assert "2 keep" in out


def test_repos_counts_unpushed_commits_as_keep(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = make_repo(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    run_git(clone, "commit", "-q", "--allow-empty", "-m", "unpushed")

    assert main(["-r", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "clone" not in out
    assert "0 safe" in out


def test_repos_keeps_tagged_clone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin = make_repo(tmp_path / "origin")
    tagged = tmp_path / "zeta"
    subprocess.run(["git", "clone", "-q", str(origin), str(tagged)], check=True)
    run_git(tagged, "tag", "local-only")

    assert main(["-r", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "zeta" not in out
    assert "0 safe" in out


def test_gc_runs_across_repos(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "big.txt").write_text("\n".join(str(i) for i in range(5000)))
    run_git(repo, "add", "big.txt")
    run_git(repo, "commit", "-q", "-m", "big")

    assert main(["-g", "-d", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "gc'd 1 repo(s)" in out


def test_find_repos_stops_at_repo_boundary(tmp_path: Path) -> None:
    outer = make_repo(tmp_path / "outer")
    make_repo(outer / "inner")

    repos = find_repos(tmp_path)

    assert repos == [outer]


def test_find_cache_dirs_ignores_git_refs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "a")
    run_git(repo, "branch", "target/v2")

    caches = find_cache_dirs(tmp_path)

    assert all(".git" not in path.parts for path in caches)


def test_du_kb_counts_file_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.write_bytes(b"x" * (1024 * 1024))

    assert du_kb(tmp_path) >= 1000


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["-h"])

    assert exc.value.code == 0
    assert "usage: git reclaim" in capsys.readouterr().out


def test_missing_dir_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    assert main(["-d", str(missing)]) == 1
    assert "Cannot cd into" in capsys.readouterr().err


def test_parse_size() -> None:
    assert parse_size("10M") == 10240
    assert parse_size("500K") == 500
    assert parse_size("1G") == 1024 * 1024
    assert parse_size("1.5M") == 1536
    with pytest.raises(ValueError):
        parse_size("nope")


def test_json_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "f").write_text("x")

    assert main(["--json", "-d", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["caches"]["count"] == 1
    assert payload["caches"]["entries"][0]["path"] == "a/node_modules"
    assert payload["caches"]["entries"][0]["purged"] is False


def test_json_purge(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "node_modules").mkdir()

    assert main(["--json", "-p", "-d", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["caches"]["purged"] == 1
    assert not (repo / "node_modules").exists()


def test_min_size_filters(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "f").write_bytes(b"x" * (2 * 1024 * 1024))

    assert main(["--json", "--min-size", "10M", "-d", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["caches"]["count"] == 0

    assert main(["--json", "--min-size", "1K", "-d", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["caches"]["count"] == 1


def test_json_safe_repos(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    origin = make_repo(tmp_path / "origin")
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(tmp_path / "pushed")], check=True
    )

    assert main(["--json", "-r", "-d", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["safe_repos"]["safe"] == 1
    assert payload["safe_repos"]["entries"][0]["repo"] == "pushed"


def test_json_gc(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path / "a")
    (repo / "big.txt").write_text("\n".join(str(i) for i in range(5000)))
    run_git(repo, "add", "big.txt")
    run_git(repo, "commit", "-q", "-m", "big")

    assert main(["--json", "-g", "-d", str(tmp_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["gc"]["count"] == 1
