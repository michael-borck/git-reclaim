"""Command-line entry point for git-reclaim.

The tool is installed as ``git-reclaim``, so git runs it as ``git reclaim``.
It has three independent jobs:

* report and optionally purge regenerable cache directories
* compact every repository's ``.git`` with ``git gc``
* list clones that are safe to delete because the remote has everything
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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


def report_caches(root: Path, style: Style, purge: bool) -> None:
    """Report caches and optionally delete them."""
    caches = find_cache_dirs(root)
    sizes = sorted(((du_kb(path), path) for path in caches), reverse=True)

    print(f"{style.bold}Regenerable caches under {root}{style.reset}")
    if not sizes:
        print(f"  {style.grey}none found{style.reset}")
        return

    for kb, path in sizes[:12]:
        print(f"  {human(kb):<8} {style.grey}{path.relative_to(root)}{style.reset}")
    if len(sizes) > 12:
        print(f"  {style.grey}... and {len(sizes) - 12} more{style.reset}")

    total = sum(kb for kb, _ in sizes)
    print(
        f"  {style.bold}{len(sizes)} cache dirs, {human(total)} reclaimable{style.reset}"
    )

    if not purge:
        print(f"  {style.yellow}(dry run, pass -p to delete these){style.reset}")
        return

    before = shutil.disk_usage(root).free // 1024
    purged = skipped = failed = 0
    for _, path in sizes:
        if git_tracks_files(path):
            print(
                f"  {style.yellow}skipped {path.relative_to(root)} "
                f"(git tracks files inside it){style.reset}"
            )
            skipped += 1
            continue
        try:
            shutil.rmtree(path)
        except OSError:
            failed += 1
        else:
            purged += 1

    after = shutil.disk_usage(root).free // 1024
    freed = max(0, after - before)
    print(
        f"  {style.green}-> purged {purged} of {len(sizes)} dirs, "
        f"freed {human(freed)} (free: {human(before)} -> {human(after)}){style.reset}"
    )
    if failed:
        print(f"  {style.red}-> {failed} dir(s) could not be removed{style.reset}")


def report_gc(root: Path, style: Style) -> None:
    """Run git gc, and git lfs prune when available, in every repo."""
    print()
    print(f"{style.bold}Compacting repo history (git gc){style.reset}")

    have_lfs = shutil.which("git-lfs") is not None
    count = before = after = 0

    for repo in find_repos(root):
        rev = git(repo, "rev-parse", "--absolute-git-dir")
        if rev.returncode != 0:
            continue
        gitdir = Path(rev.stdout.strip())
        size_before = du_kb(gitdir)
        git(repo, "gc", "--quiet", timeout=GC_TIMEOUT)
        if have_lfs:
            git(repo, "lfs", "prune", timeout=GC_TIMEOUT)
        size_after = du_kb(gitdir)

        count += 1
        before += size_before
        after += size_after
        if size_before > size_after:
            print(
                f"  -{human(size_before - size_after):<7} "
                f"{style.grey}{repo.relative_to(root)}{style.reset}"
            )

    saved = max(0, before - after)
    print(
        f"  {style.bold}gc'd {count} repo(s): .git {human(before)} -> "
        f"{human(after)} (saved {human(saved)}){style.reset}"
    )


def report_safe_repos(root: Path, style: Style) -> None:
    """List clones where the remote already has everything."""
    print()
    print(
        f"{style.bold}Repos safe to delete (remote has everything), "
        f"biggest first{style.reset}"
    )

    rows: list[tuple[int, str, Path, str]] = []
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
        last = git(repo, "log", "-1", "--format=%cs").stdout.strip()
        url_result = git(repo, "remote", "get-url", "origin")
        url = url_result.stdout.strip() if url_result.returncode == 0 else "?"
        rows.append((size, last, repo, url))

    rows.sort(key=lambda row: row[0], reverse=True)
    for size, last, repo, url in rows:
        print(
            f"  {human(size):<8} last:{last:<10} "
            f"{str(repo.relative_to(root)):<44} {style.grey}{url}{style.reset}"
        )

    total = sum(size for size, _, _, _ in rows)
    print(
        f"{style.bold}{len(rows)} safe ({human(total)}) / {keep} keep{style.reset}  "
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
            "-d DIR     directory to scan (default: current directory)"
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

    root = root.resolve()
    style = Style.auto()

    report_caches(root, style, args.purge)
    if args.gc:
        report_gc(root, style)
    if args.repos:
        report_safe_repos(root, style)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
