# Releasing git-reclaim

1. `uv sync --group dev`
2. `uv run pytest`
3. `uv run ruff check src tests`
4. `uv run ruff format --check src tests`
5. Bump `version` in `pyproject.toml` and `src/git_reclaim/__init__.py`.
6. Update `CHANGELOG.md`.
7. Commit, tag, and push:
   ```bash
   git tag -a vX.Y.Z -m "git-reclaim X.Y.Z"
   git push origin main --tags
   ```
8. The `release` workflow publishes to PyPI through trusted publishing.
9. Create a GitHub release: `gh release create vX.Y.Z --generate-notes`

PyPI trusted publishing must be configured for this repository, workflow
`release.yml`, and environment `pypi`.
