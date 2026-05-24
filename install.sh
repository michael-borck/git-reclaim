#!/usr/bin/env bash
#
# install.sh — symlink every git-* tool in ./bin into a directory on your PATH
# so git picks them up as subcommands (e.g. bin/git-repos -> `git repos`).
#
# Usage:
#   ./install.sh [TARGET_DIR]
#
# TARGET_DIR defaults to ~/.local/bin.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/bin" && pwd)"
TARGET_DIR="${1:-$HOME/.local/bin}"

mkdir -p "$TARGET_DIR"

for tool in "$SRC_DIR"/git-*; do
  [ -e "$tool" ] || continue
  name="$(basename "$tool")"
  chmod +x "$tool"
  ln -sf "$tool" "$TARGET_DIR/$name"
  echo "linked $name -> $TARGET_DIR/$name"
done

echo
case ":$PATH:" in
  *":$TARGET_DIR:"*) echo "$TARGET_DIR is on your PATH — try: git repos" ;;
  *) echo "NOTE: $TARGET_DIR is not on your PATH. Add it, e.g.:"
     echo "  echo 'export PATH=\"$TARGET_DIR:\$PATH\"' >> ~/.zshrc" ;;
esac
