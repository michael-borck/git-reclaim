# Shared bats helpers: every test runs in a throwaway tree with a hermetic
# git config (no user/system gitconfig can leak in).

common_setup() {
  BIN="$BATS_TEST_DIRNAME/../bin"
  export GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_GLOBAL=/dev/null
  export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com
  export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
  TREE="$BATS_TEST_TMPDIR/tree"
  mkdir -p "$TREE"
  cd "$TREE" || exit 1
}

# mkrepo PATH — init a repo with one empty commit on branch main
mkrepo() {
  git init -q -b main "$1"
  git -C "$1" commit -q --allow-empty -m init
}
