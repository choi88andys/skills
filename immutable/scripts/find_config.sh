#!/usr/bin/env bash
# find_config.sh — locate `.immutable-prd/config.yml` via walk-up from $PWD.
#
# Exits 0 with the absolute path printed on stdout when found.
# Exits 1 with empty stdout when nothing is found before hitting either
# the filesystem root or a `.git` directory (repo boundary — stops walking).
#
# Usage (from any prd:* skill invocation):
#     CONFIG_PATH="$(bash <plugin>/prd/scripts/find_config.sh)" \
#       || { echo "no .immutable-prd/config.yml detected"; exit 1; }
#
# The walk-up stops at the repo root to keep this host-safe even when the user
# has an ancestor directory containing an unrelated `.immutable-prd/` tree.

set -u

current="$(pwd)"

while :; do
  candidate="$current/.immutable-prd/config.yml"
  if [ -f "$candidate" ]; then
    echo "$candidate"
    exit 0
  fi

  # Repo-root boundary: stop walking once we hit a `.git` directory.
  if [ -d "$current/.git" ]; then
    break
  fi

  parent="$(dirname "$current")"
  if [ "$parent" = "$current" ]; then
    break
  fi
  current="$parent"
done

exit 1
