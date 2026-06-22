# git-sweep

A small, zero-dependency **disk-reclaim** helper for people who keep many git
clones side by side. Pure bash — no GitHub API, no tokens. It finds space you
can safely get back across a whole tree of repos, and flags clones that are
safe to delete because the remote already has everything.

`git-sweep` is a [git custom subcommand](https://git-scm.com/book/en/v2/Git-Internals-Git-Internals):
an executable named `git-sweep` on your `PATH` is runnable as `git sweep`.

> **Scope:** `git-sweep` does one thing — reclaim disk space across local
> clones. For multi-repo **status and sync** (branch, ahead/behind, batch
> `git` commands), use [gita](https://github.com/nosarthur/gita), which is
> mature and does that well. For anything needing the **GitHub API** — bulk
> listing, health checks, topics, portfolio sites — that's
> [gh-toolkit](https://github.com/michael-borck/gh-toolkit) (or
> [`gh`](https://cli.github.com/)). `git-sweep` deliberately stays out of all
> three of those lanes.

## Install

```bash
git clone https://github.com/michael-borck/git-sweep.git
cd git-sweep
./install.sh            # symlinks bin/git-sweep into ~/.local/bin
```

Make sure `~/.local/bin` is on your `PATH` (most shells already have it). Then:

```bash
git sweep               # what could I reclaim under the current directory?
```

No build step, no dependencies beyond `git`, `bash`, `find`, and `awk`.

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

### How discovery works

It walks the tree but **prunes at repo boundaries** — the moment a directory
contains a `.git` entry it's recorded as a repo and not descended into. So
workspace folders are descended into to find their child repos, while a repo's
own working tree (and its `node_modules`, `vendor`, submodules, etc.) is not
re-scanned. `.git` is detected as a **file or directory**, so submodule and
worktree clones are recognised too.

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

## Using it from `gita`

If you manage your clones with [gita](https://github.com/nosarthur/gita), you
can make `git-sweep` feel native. gita loads a user command file from
`~/.config/gita/cmds.json` and lets custom commands shadow the defaults — add:

```json
{
  "sweep": {
    "cmd": "git-sweep -d .",
    "disable_async": true,
    "help": "reclaim caches / flag safe-to-delete clones"
  }
}
```

Now `gita sweep` (or `gita sweep <group>`) runs `git-sweep` in each registered
repo. No-config alternative:

```bash
gita shell 'git-sweep -d .'
```

Note this runs sweep **per repo**, which suits the cache purge (`-p`) and
`git gc` (`-g`) modes. For the cross-tree "what's safe to delete, biggest
first" view (`-r`), run `git-sweep` standalone against the parent folder
(`git sweep -r -d ~/projects`) so you get the single aggregate, size-sorted
report.

## Development

CI runs [shellcheck](https://www.shellcheck.net/) and a
[bats](https://github.com/bats-core/bats-core) suite (`test/`) that builds
throwaway repo trees and exercises discovery and the purge safety guards.
Locally:

```bash
brew install bats-core shellcheck   # or: apt-get install bats shellcheck
shellcheck bin/git-sweep install.sh
bats test/
```

## License

MIT — see [LICENSE](LICENSE).
