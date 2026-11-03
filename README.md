# git-reclaim

A small, dependency-free **disk-reclaim** helper for people who keep many git
clones side by side. It finds space you can safely get back across a whole tree
of repos, and flags clones that are safe to delete because the remote already
has everything.

`git-reclaim` is a [git custom subcommand](https://git-scm.com/book/en/v2/Git-Internals-Git-Internals):
an executable named `git-reclaim` on your `PATH` is runnable as `git reclaim`.

> **Scope:** `git-reclaim` does one thing: reclaim disk space across local
> clones. For multi-repo **status and sync** (branch, ahead/behind, batch
> `git` commands), use [gita](https://github.com/nosarthur/gita). For anything
> needing the **GitHub API** (bulk listing, health checks, topics, portfolio
> sites), use [gh-toolkit](https://github.com/michael-borck/gh-toolkit) or
> [`gh`](https://cli.github.com/). If you want one verb set across all of them,
> use [gx](https://github.com/michael-borck/gx).

## Install

```bash
uv tool install git-reclaim
# or
pipx install git-reclaim
# or
pip install git-reclaim
```

No dependencies beyond Python 3.10+ and `git`.

## `git reclaim`

```
git reclaim [-p] [-g] [-r] [-d DIR]

  (default)  dry run: report reclaimable cache space; deletes nothing
  -p         purge the cache directories (any dir git tracks files inside is
             skipped, never deleted)
  -g         compact history: run `git gc` (and `git lfs prune` if installed)
             in every repo and report the .git space reclaimed
  -r         also list repos that are safe to delete (size + last commit + URL)
  -d DIR     directory to scan (default: current directory)
```

Three ways to free space across a tree of clones:

- **Purge regenerable caches.** It finds `node_modules`, `.venv`/`venv`,
  `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.next`, and
  `target`. These rebuild on demand. So `git reclaim -p` recovers space without
  touching your source, history, or uncommitted work. If a directory with one
  of these names turns out to be git-tracked (a committed `target/`, say), the
  purge detects that and skips it. `dist/` and `build/` are deliberately
  excluded because they are occasionally committed. Re-run `npm install` or
  `uv sync` next time you open a project.

- **Compact `.git` itself.** `git reclaim -g` runs `git gc` (plus
  `git lfs prune` when git-lfs is installed) in every repo and reports the
  space recovered per repo. This is standard git maintenance: nothing reachable
  is deleted, and lfs prune always retains unpushed objects.

- **Find repos that are safe to delete.** `git reclaim -r` lists repos where
  the remote already has everything: clean working tree, has a remote, no
  unpushed commits on any local branch, no stashes, and no tags. Rows are sorted
  by size, with each repo's last-commit date and re-clone URL. Anything not
  fully synced is counted as "keep" and never listed as safe. Tags are treated
  conservatively because a local tag ref can be lost even when its commit is on
  the remote.

### How discovery works

It walks the tree but **prunes at repo boundaries**. The moment a directory
contains a `.git` entry it is recorded as a repo and not descended into. So
workspace folders are descended into to find their child repos, while a repo's
own working tree (and its `node_modules`, `vendor`, submodules, etc.) is not
re-scanned. `.git` is detected as a **file or directory**, so submodule and
worktree clones are recognised too.

### Examples

```bash
git reclaim              # what could I free from caches? (dry run)
git reclaim -p           # actually purge the caches
git reclaim -g           # repack every repo's .git (git gc)
git reclaim -r           # caches report + list of repos safe to delete
git reclaim -r -d ~/work # scan a different tree
git reclaim --json       # machine-readable report
git reclaim -r --min-size 100M  # only big clones
```

> `git reclaim` only ever deletes **caches**, and only with `-p`; `-g` just
> repacks history in place. It never deletes a repo. It just reports which are
> safe, so you stay in control of removing whole clones. Pair it with the
> re-clone URLs it prints.

## JSON output

`--json` prints one object with the cache report and any requested sections:

```bash
git reclaim --json
git reclaim -p -g -r --json --min-size 10M
```

The object has `root`, `caches`, and optional `gc` and `safe_repos` sections.
It is suitable for scripts, dashboards, and `jq`.

## Using it from `gita`

If you manage your clones with `gita`, you can make `git-reclaim` feel native.
gita loads a user command file from `~/.config/gita/cmds.json` and lets custom
commands shadow the defaults. Add:

```json
{
  "reclaim": {
    "cmd": "git-reclaim -d .",
    "disable_async": true,
    "help": "reclaim caches / flag safe-to-delete clones"
  }
}
```

Now `gita reclaim` (or `gita reclaim <group>`) runs `git-reclaim` in each
registered repo. No-config alternative:

```bash
gita shell 'git-reclaim -d .'
```

Note this runs it **per repo**, which suits the cache purge (`-p`) and
`git gc` (`-g`) modes. For the cross-tree "what's safe to delete, biggest
first" view (`-r`), run `git-reclaim` standalone against the parent folder
(`git reclaim -r -d ~/projects`) so you get the single aggregate, size-sorted
report.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

CI runs the same checks on every push and pull request.

## License

MIT. See [LICENSE](LICENSE).
