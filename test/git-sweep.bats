#!/usr/bin/env bats

load helpers

setup() { common_setup; }

@test "default dry run lists caches and deletes nothing" {
  mkrepo a
  mkdir -p a/node_modules && touch a/node_modules/f
  run "$BIN/git-sweep"
  [ "$status" -eq 0 ]
  [[ "$output" == *node_modules* ]]
  [[ "$output" == *"dry run"* ]]
  [ -d a/node_modules ]
}

@test "-p purges untracked cache dirs" {
  mkrepo a
  mkdir -p a/node_modules && touch a/node_modules/f
  mkdir -p a/sub/target && touch a/sub/target/f
  run "$BIN/git-sweep" -p
  [ "$status" -eq 0 ]
  [ ! -d a/node_modules ]
  [ ! -d a/sub/target ]
  [[ "$output" == *"purged 2 of 2"* ]]
}

@test "regression: -p never touches ref dirs inside .git" {
  mkrepo a
  git -C a branch target/v2
  git -C a branch venv/x
  mkdir -p a/node_modules && touch a/node_modules/f
  run "$BIN/git-sweep" -p
  git -C a rev-parse --verify -q refs/heads/target/v2
  git -C a rev-parse --verify -q refs/heads/venv/x
  [ ! -d a/node_modules ]
}

@test "-p skips a dir git tracks files inside" {
  mkrepo a
  mkdir -p a/target && echo hello > a/target/tracked.txt
  git -C a add target
  git -C a commit -qm "commit target dir"
  mkdir -p a/node_modules && touch a/node_modules/f
  run "$BIN/git-sweep" -p
  [ -d a/target ]
  [ -f a/target/tracked.txt ]
  [ ! -d a/node_modules ]
  [[ "$output" == *skipped* ]]
  [[ "$output" == *"purged 1 of 2"* ]]
}

@test "-r lists fully-pushed clone as safe, counts dirty and remoteless as keep" {
  mkrepo origin
  git clone -q origin pushed
  git clone -q origin messy
  touch messy/uncommitted.txt
  run "$BIN/git-sweep" -r
  [ "$status" -eq 0 ]
  [[ "$output" == *pushed* ]]
  [[ "$output" != *messy* ]]
  [[ "$output" == *"1 safe"* ]]
  [[ "$output" == *"2 keep"* ]]   # messy (dirty) + origin (no remote)
}

@test "-r counts unpushed commits as keep" {
  mkrepo origin
  git clone -q origin clone
  git -C clone commit -q --allow-empty -m unpushed
  run "$BIN/git-sweep" -r
  [[ "$output" != *clone* ]]
  [[ "$output" == *"0 safe"* ]]
}

@test "-g runs gc across repos and reports" {
  mkrepo a
  seq 1 5000 > a/big.txt
  git -C a add big.txt
  git -C a commit -qm big
  run "$BIN/git-sweep" -g
  [ "$status" -eq 0 ]
  [[ "$output" == *"gc'd 1 repo(s)"* ]]
}

@test "-h prints usage and exits 0" {
  run "$BIN/git-sweep" -h
  [ "$status" -eq 0 ]
  [[ "$output" == *Usage:* ]]
}
