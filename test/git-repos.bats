#!/usr/bin/env bats

load helpers

setup() { common_setup; }

@test "clean repo with no upstream is reported" {
  mkrepo a
  run "$BIN/git-repos"
  [ "$status" -eq 0 ]
  [[ "$output" == *"no upstream"* ]]
  [[ "$output" == *clean* ]]
}

@test "untracked file marks repo dirty" {
  mkrepo a
  touch a/untracked.txt
  run "$BIN/git-repos"
  [[ "$output" == *dirty* ]]
}

@test "clone behind upstream is reported and -p fast-forwards it" {
  mkrepo origin
  git clone -q origin clone
  git -C origin commit -q --allow-empty -m two
  run "$BIN/git-repos" -p
  [ "$status" -eq 0 ]
  [[ "$output" == *"fast-forwarded"* ]]
  [ "$(git -C clone rev-parse HEAD)" = "$(git -C origin rev-parse HEAD)" ]
}

@test "-p -n reports would-fast-forward without moving HEAD" {
  mkrepo origin
  git clone -q origin clone
  git -C origin commit -q --allow-empty -m two
  before=$(git -C clone rev-parse HEAD)
  run "$BIN/git-repos" -p -n
  [[ "$output" == *"would fast-forward"* ]]
  [ "$(git -C clone rev-parse HEAD)" = "$before" ]
}

@test "ahead repo is reported and -p leaves it alone" {
  mkrepo origin
  git clone -q origin clone
  git -C clone commit -q --allow-empty -m local-only
  before=$(git -C clone rev-parse HEAD)
  run "$BIN/git-repos" -p
  [[ "$output" == *"ahead +1"* ]]
  [ "$(git -C clone rev-parse HEAD)" = "$before" ]
}

@test "regression: missing upstream ref reports 'upstream gone', not 'in sync'" {
  mkrepo origin
  git clone -q origin clone
  git -C clone update-ref -d refs/remotes/origin/main
  run "$BIN/git-repos"
  [[ "$output" == *"upstream gone"* ]]
  [[ "$output" != *"in sync"* ]]
}

@test "-a hides clean in-sync repos and keeps attention ones" {
  mkrepo origin
  git clone -q origin clone
  run "$BIN/git-repos" -a
  [[ "$output" == *origin* ]]   # no upstream -> needs attention
  [[ "$output" != *clone* ]]    # clean + in sync -> hidden
}

@test "-h prints usage and exits 0" {
  run "$BIN/git-repos" -h
  [ "$status" -eq 0 ]
  [[ "$output" == *Usage:* ]]
}

@test "-n without -p warns" {
  mkrepo a
  run "$BIN/git-repos" -n
  [ "$status" -eq 0 ]
  [[ "$output" == *"-n has no effect without -p"* ]]
}
