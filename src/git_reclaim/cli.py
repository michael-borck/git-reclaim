"""Command-line entry point for git-reclaim.

The tool is installed as ``git-reclaim``, so git runs it as ``git reclaim``.
It has three independent jobs:

* report and optionally purge regenerable cache directories
* compact every repository's ``.git`` with ``git gc``
* list clones that are safe to delete because the remote has everything
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from git_reclaim import __version__

# Directory names that are regenerable and never source. dist/ and build/ are
# deliberately excluded because they are occasionally committed.
CACHE_NAMES = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".next",
        "target",
    }
)

# Directories not worth descending into while looking for repos. A directory
# that is itself a repo is detected before this list is applied.
PRUNE_NAMES = CACHE_NAMES | {".tox", "vendor"}

GIT_TIMEOUT = 60
GC_TIMEOUT = 600


@dataclass(frozen=True)
class Style:
    """ANSI colours, disabled when output is not a terminal."""

    red: str = ""
    green: str = ""
    yellow: str = ""
    grey: str = ""
    bold: str = ""
    reset: str = ""

    @classmethod
    def auto(cls) -> Style:
        if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
            return cls()
        return cls(
            red="\033[31m",
            green="\033[32m",
            yellow="\033[33m",
            grey="\033[90m",
            bold="\033[1m",
            reset="\033[0m",
        )


def human(kb: int) -> str:
    """Format a size in KiB the way the old shell version did."""
    if kb >= 1024 * 1024:
        return f"{kb / 1024 / 1024:.1f}G"
    if kb >= 1024:
        return f"{kb // 1024}M"
    return f"{kb}K"


def parse_size(text: str) -> int:
    """Parse a human size such as 10M, 500K, or 1G into KiB."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?)B?\s*", text, re.IGNORECASE)
    if not match:
        raise ValueError(f"invalid size: {text}")
    value = float(match.group(1))
    unit = match.group(2).upper()
    factor = {"": 1, "K": 1, "M": 1024, "G": 1024**2, "T": 1024**3}[unit]
    return int(value * factor)


def du_kb(path: Path) -> int:
    """Return disk usage for a path in KiB, without following symlinks."""
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in [*dirs, *files]:
            entry = Path(root) / name
            if entry.is_symlink():
                continue
            try:
                stat = entry.lstat()
            except OSError:
                continue
            blocks = getattr(stat, "st_blocks", 0)
            total += blocks * 512 if blocks else stat.st_size
    return total // 1024


def find_cache_dirs(root: Path) -> list[Path]:
    """Find cache directories under root, without descending into them."""
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        keep: list[str] = []
        for name in dirnames:
            entry = current / name
            if name == ".git" or entry.is_symlink():
                continue
            if name in CACHE_NAMES:
                found.append(entry)
                continue
            keep.append(name)
        dirnames[:] = keep
    return found


def find_repos(root: Path) -> list[Path]:
    """Find git repositories under root, stopping at each repo boundary."""
    repos: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        if (current / ".git").exists():
            repos.append(current)
            dirnames[:] = []
            continue

        keep: list[str] = []
        for name in dirnames:
            entry = current / name
            if name in PRUNE_NAMES or entry.is_symlink():
                continue
            keep.append(name)
        dirnames[:] = keep
    return repos


def git(
    repo: Path, *args: str, timeout: int = GIT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Run git in a repository, capturing output."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_tracks_files(path: Path) -> bool:
    """True when git tracks at least one file inside path."""
    result = git(path, "ls-files")
    return result.returncode == 0 and bool(result.stdout.strip())


def collect_caches(root: Path, purge: bool, min_kb: int) -> dict[str, Any]:
    """Collect cache data, and purge when requested."""
    caches = find_cache_dirs(root)
    sizes = sorted(((du_kb(path), path) for path in caches), reverse=True)
    sizes = [(kb, path) for kb, path in sizes if kb >= min_kb]
    entries: list[dict[str, Any]] = [
        {
            "path": str(path.relative_to(root)),
            "size_kb": kb,
            "purged": False,
            "skipped": False,
            "error": None,
        }
        for kb, path in sizes
    ]
    result: dict[str, Any] = {
        "count": len(entries),
        "total_kb": sum(kb for kb, _ in sizes),
        "entries": entries,
        "purged": 0,
        "skipped": 0,
        "failed": 0,
        "freed_kb": 0,
    }

    if not purge:
        return result

    before = shutil.disk_usage(root).free // 1024
    for entry, (_, path) in zip(entries, sizes, strict=True):
        if git_tracks_files(path):
            entry["skipped"] = True
            result["skipped"] += 1
            continue
        try:
            shutil.rmtree(path)
        except OSError as e:
            entry["error"] = str(e)
            result["failed"] += 1
        else:
            entry["purged"] = True
            result["purged"] += 1

    after = shutil.disk_usage(root).free // 1024
    result["freed_kb"] = max(0, after - before)
    return result


def report_caches(root: Path, style: Style, data: dict[str, Any]) -> None:
    """Print the cache report."""
    print(f"{style.bold}Regenerable caches under {root}{style.reset}")
    entries = data["entries"]
    if not entries:
        print(f"  {style.grey}none found{style.reset}")
        return

    for entry in entries[:12]:
        print(
            f"  {human(entry['size_kb']):<8} {style.grey}{entry['path']}{style.reset}"
        )
    if len(entries) > 12:
        print(f"  {style.grey}... and {len(entries) - 12} more{style.reset}")

    print(
        f"  {style.bold}{data['count']} cache dirs, "
        f"{human(data['total_kb'])} reclaimable{style.reset}"
    )

    if not data["purged"] and not data["skipped"] and not data["failed"]:
        print(f"  {style.yellow}(dry run, pass -p to delete these){style.reset}")
        return

    for entry in entries:
        if entry["skipped"]:
            print(
                f"  {style.yellow}skipped {entry['path']} "
                f"(git tracks files inside it){style.reset}"
            )
        elif entry["error"]:
            print(f"  {style.red}failed {entry['path']}: {entry['error']}{style.reset}")

    print(
        f"  {style.green}-> purged {data['purged']} of {data['count']} dirs, "
        f"freed {human(data['freed_kb'])}{style.reset}"
    )
    if data["failed"]:
        print(
            f"  {style.red}-> {data['failed']} dir(s) could not be removed{style.reset}"
        )


def collect_gc(root: Path, min_kb: int) -> dict[str, Any]:
    """Run git gc and collect the result."""
    have_lfs = shutil.which("git-lfs") is not None
    entries: list[dict[str, Any]] = []
    before = after = 0

    for repo in find_repos(root):
        rev = git(repo, "rev-parse", "--absolute-git-dir")
        if rev.returncode != 0:
            continue
        gitdir = Path(rev.stdout.strip())
        size_before = du_kb(gitdir)
        if size_before < min_kb:
            continue
        git(repo, "gc", "--quiet", timeout=GC_TIMEOUT)
        if have_lfs:
            git(repo, "lfs", "prune", timeout=GC_TIMEOUT)
        size_after = du_kb(gitdir)

        before += size_before
        after += size_after
        entries.append(
            {
                "repo": str(repo.relative_to(root)),
                "before_kb": size_before,
                "after_kb": size_after,
                "saved_kb": max(0, size_before - size_after),
            }
        )

    return {
        "count": len(entries),
        "before_kb": before,
        "after_kb": after,
        "saved_kb": max(0, before - after),
        "entries": entries,
    }


def report_gc(root: Path, style: Style, data: dict[str, Any]) -> None:
    """Print the git gc report."""
    print()
    print(f"{style.bold}Compacting repo history (git gc){style.reset}")
    for entry in data["entries"]:
        if entry["saved_kb"] > 0:
            print(
                f"  -{human(entry['saved_kb']):<7} "
                f"{style.grey}{entry['repo']}{style.reset}"
            )
    print(
        f"  {style.bold}gc'd {data['count']} repo(s): .git "
        f"{human(data['before_kb'])} -> {human(data['after_kb'])} "
        f"(saved {human(data['saved_kb'])}){style.reset}"
    )


def collect_safe_repos(root: Path, min_kb: int) -> dict[str, Any]:
    """Collect clones where the remote already has everything."""
    entries: list[dict[str, Any]] = []
    keep = 0

    for repo in find_repos(root):
        remotes = git(repo, "remote").stdout.strip()
        dirty = git(repo, "status", "--porcelain").stdout.strip()
        unpushed = git(
            repo, "log", "--branches", "--not", "--remotes", "--oneline"
        ).stdout.strip()
        stash = git(repo, "stash", "list").stdout.strip()
        tags = git(repo, "tag").stdout.strip()

        if not remotes or dirty or unpushed or stash or tags:
            keep += 1
            continue

        size = du_kb(repo)
        if size < min_kb:
            continue
        last = git(repo, "log", "-1", "--format=%cs").stdout.strip()
        url_result = git(repo, "remote", "get-url", "origin")
        url = url_result.stdout.strip() if url_result.returncode == 0 else "?"
        entries.append(
            {
                "repo": str(repo.relative_to(root)),
                "size_kb": size,
                "last_commit": last,
                "url": url,
            }
        )

    entries.sort(key=lambda entry: entry["size_kb"], reverse=True)
    return {
        "safe": len(entries),
        "keep": keep,
        "safe_kb": sum(entry["size_kb"] for entry in entries),
        "entries": entries,
    }


def report_safe_repos(root: Path, style: Style, data: dict[str, Any]) -> None:
    """Print clones where the remote already has everything."""
    print()
    print(
        f"{style.bold}Repos safe to delete (remote has everything), "
        f"biggest first{style.reset}"
    )
    for entry in data["entries"]:
        print(
            f"  {human(entry['size_kb']):<8} last:{entry['last_commit']:<10} "
            f"{entry['repo']:<44} {style.grey}{entry['url']}{style.reset}"
        )
    print(
        f"{style.bold}{data['safe']} safe ({human(data['safe_kb'])}) / "
        f"{data['keep']} keep{style.reset}  "
        f"{style.grey}(keep = dirty, unpushed, stashed, tagged, or no remote)"
        f"{style.reset}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git reclaim",
        description="Reclaim disk space across a tree of git repositories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "(default)  dry run: report reclaimable cache space; deletes nothing\n"
            "-p         purge the cache directories (git-tracked dirs are skipped)\n"
            "-g         run git gc (and git lfs prune) in every repo\n"
            "-r         list repos that are safe to delete (size, last commit, URL)\n"
            "-d DIR     directory to scan (default: current directory)\n"
            "--json     output a JSON report instead of text\n"
            "--min-size SIZE  only include items at least this size (e.g. 10M)"
        ),
    )
    parser.add_argument(
        "-p",
        "--purge",
        action="store_true",
        help="delete the cache directories",
    )
    parser.add_argument(
        "-g",
        "--gc",
        action="store_true",
        help="compact every repository with git gc",
    )
    parser.add_argument(
        "-r",
        "--repos",
        action="store_true",
        help="list repositories that are safe to delete",
    )
    parser.add_argument(
        "-d",
        "--dir",
        default=".",
        metavar="DIR",
        help="directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="output a JSON report instead of text",
    )
    parser.add_argument(
        "--min-size",
        default="0",
        metavar="SIZE",
        help="only include caches and repos at least this size (e.g. 10M)",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.dir).expanduser()

    if not root.is_dir():
        print(f"Cannot cd into {root}", file=sys.stderr)
        return 1

    try:
        min_kb = parse_size(args.min_size)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    root = root.resolve()
    style = Style.auto()

    caches = collect_caches(root, args.purge, min_kb)

    if args.json:
        payload: dict[str, Any] = {"root": str(root), "caches": caches}
        if args.gc:
            payload["gc"] = collect_gc(root, min_kb)
        if args.repos:
            payload["safe_repos"] = collect_safe_repos(root, min_kb)
        print(json.dumps(payload, indent=2))
        return 0

    report_caches(root, style, caches)
    if args.gc:
        report_gc(root, style, collect_gc(root, min_kb))
    if args.repos:
        report_safe_repos(root, style, collect_safe_repos(root, min_kb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
