# git-toolkit

Small, zero-dependency **local git** helpers for people who keep many clones
side by side. Pure bash, no GitHub API, no tokens — everything is plain `git`
against your local working copies. The only network it ever touches is
`git fetch`, and only when you explicitly ask for it with `-f`.

> **Scope:** if the `git` binary on a local clone can do it, it belongs here.
> If it needs the GitHub API — bulk listing, health checks, topics, portfolio
> sites — that's [gh-toolkit](https://github.com/michael-borck/gh-toolkit)'s
> job (or [`gh`](https://cli.github.com/)'s). This toolkit only reports on and
> tidies the clones you already have.

Each tool is a [git custom subcommand](https://git-scm.com/book/en/v2/Git-Internals-Git-Internals):
an executable named `git-foo` on your `PATH` is runnable as `git foo`.

## Tools

| Command | What it does |
|---------|--------------|
| `git repos` | Recursively scan a folder of clones and report each repo's branch, working-tree state (clean/dirty), and sync vs. upstream (in sync / ahead / behind / diverged / no upstream). Can fast-forward the clean-behind ones. |
| `git sweep` | Reclaim disk space: report (and optionally purge) regenerable cache dirs (`node_modules`, virtualenvs, build/test caches), and flag repos that are safe to delete because the remote already has everything. |

## Install

```bash
git clone https://github.com/michael-borck/git-toolkit.git
cd git-toolkit
./install.sh            # symlinks bin/git-* into ~/.local/bin
```

Make sure `~/.local/bin` is on your `PATH` (most shells already have it). Then:

```bash
git repos               # status of every repo under the current directory
```

No build step, no dependencies beyond `git`, `bash`, `find`, and `awk`.

## `git repos`

```
git repos [-f] [-a] [-p] [-n] [-d DIR]

  -f        fetch from each remote first (slower, but ahead/behind is current)
  -a        attention only: show only repos that are dirty, ahead, behind,
            diverged, or have no upstream (hide clean & in-sync repos)
  -p        pull: fast-forward repos that are clean AND strictly behind their
            upstream. Dirty, ahead, and diverged repos are never touched.
            Implies -f so the fast-forward uses fresh remote state.
  -n        dry run: with -p, report which repos WOULD be fast-forwarded.
  -d DIR    directory to scan (default: current directory)
```

### How discovery works

It walks the tree but **prunes at repo boundaries** — the moment a directory
contains a `.git` entry it's recorded as a repo and not descended into. So:

- **Workspace folders** (no `.git` of their own) are descended into, finding
  their child repos — including nested workspaces several levels deep.
- A repo's own working tree, `node_modules`, `vendor`, `.venv`, submodules,
  etc. are **not** re-scanned, so it's fast and never double-counts.
- `.git` is detected as a **file or directory**, so submodule/worktree clones
  are recognised too.

### Examples

```bash
# Quick local-only snapshot (uses last-known remote state)
git repos

# Accurate ahead/behind by fetching first, only showing what needs attention
git repos -f -a

# See what a fast-forward would touch, without changing anything
git repos -p -n

# Actually fast-forward every clean, strictly-behind repo
git repos -p

# Scan a different tree
git repos -f -a -d ~/work
```

### Safety notes

- `-p` only fast-forwards repos that are **clean and strictly behind**. Dirty,
  ahead, and diverged repos are skipped entirely; `--ff-only` would refuse a
  non-fast-forward anyway. Fast-forwards are reversible via `git reflog`.
- Fetching **never prompts for credentials**: the script sets
  `GIT_TERMINAL_PROMPT=0` and ssh `BatchMode` itself, so a repo with broken
  auth fails fast instead of hanging the whole scan. (This means
  passphrase-protected keys need an agent; a caller-provided
  `GIT_SSH_COMMAND` is respected.)
- A branch whose upstream is configured but whose remote-tracking ref is
  missing (deleted on the remote, then pruned) is reported as
  **`upstream gone`**, not "in sync".

## `git sweep`

```
git sweep [-p] [-g] [-r] [-d DIR]

  (default)  dry run: report reclaimable cache space; deletes nothing
  -p         purge: delete the cache directories (any dir git tracks files
             inside is skipped, never deleted)
  -g         compact history: run `git gc` (and `git lfs prune` if installed)
             in every repo and report the .git space reclaimed
  -r         also list repos that are safe to delete (size + last commit + URL)
  -d DIR     directory to scan (default: current directory)
```

Three ways to free space across a tree of clones:

- **Purge regenerable caches.** It finds `node_modules`, `.venv`/`venv`,
  `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.next`, and
  `target` — caches that rebuild on demand. So `git sweep -p` reclaims space
  **without touching your source, history, or uncommitted work**, and it's
  safe to run on every repo regardless of its git state: if a directory with
  one of these names turns out to be git-tracked (a committed `target/`,
  say), the purge detects that and **skips it**. (`dist/` and `build/` are
  deliberately excluded, since those are occasionally committed.) Re-run
  `npm install` / `uv sync` next time you open a project.

- **Compact `.git` itself.** `git sweep -g` runs `git gc` (plus
  `git lfs prune` when git-lfs is installed) in every repo and reports the
  space reclaimed per repo — often the biggest win on long-lived clones.
  This is standard git maintenance: nothing reachable is deleted, and lfs
  prune always retains unpushed objects.

- **Find repos that are safe to delete.** `git sweep -r` lists repos where the
  remote already has everything — clean working tree, has a remote, no unpushed
  commits on any local branch, no stashes — sorted by size, with each repo's
  last-commit date and re-clone URL. Anything *not* fully synced is counted as
  "keep" and never listed as safe.

### Examples

```bash
git sweep              # what could I reclaim from caches? (dry run)
git sweep -p           # actually purge the caches
git sweep -g           # repack every repo's .git (git gc)
git sweep -r           # caches report + list of repos safe to delete
git sweep -r -d ~/work # scan a different tree
```

> `git sweep` only ever deletes **caches** (and only with `-p`; `-g` just
> repacks history in place). It never deletes a repo — it just *reports*
> which are safe, so you stay in control of removing whole clones. Pair it
> with the re-clone URLs it prints.

## Development

CI runs [shellcheck](https://www.shellcheck.net/) and a
[bats](https://github.com/bats-core/bats-core) suite (`test/`) that builds
throwaway repo trees and exercises discovery, fast-forwarding, and the purge
safety guards. Locally:

```bash
brew install bats-core shellcheck   # or: apt-get install bats shellcheck
shellcheck bin/git-* install.sh
bats test/
```

## License

MIT — see [LICENSE](LICENSE).
