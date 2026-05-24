# git-toolkit

Small, zero-dependency **local git** helpers for people who keep many clones
side by side. Pure bash, no network/API tokens, fully offline — it reads your
working copies, it doesn't talk to GitHub.

> Complements [`gh`](https://cli.github.com/) and
> [gh-toolkit](https://github.com/michael-borck/gh-toolkit) (which manage
> GitHub *remotely*). This one is about the state of your *local* clones.

Each tool is a [git custom subcommand](https://git-scm.com/book/en/v2/Git-Internals-Git-Internals):
an executable named `git-foo` on your `PATH` is runnable as `git foo`.

## Tools

| Command | What it does |
|---------|--------------|
| `git repos` | Recursively scan a folder of clones and report each repo's branch, working-tree state (clean/dirty), and sync vs. upstream (in sync / ahead / behind / diverged / no upstream). Can fast-forward the clean-behind ones. |

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
- To avoid hanging on credential prompts when fetching many repos, run with
  `GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes'` so auth
  failures fail fast instead of blocking.

## License

MIT — see [LICENSE](LICENSE).
