#!/usr/bin/env bash
# feature_slug.sh — resolve FEATURE_SLUG, the shared handoff-contract anchor
# between /immutable:design, /immutable:plan-review-ceo, /immutable:plan-review-eng,
# /immutable:ship and /immutable:office-hours. Single source of truth; replaces
# the same one-line derivation previously hand-copied at every call site, which
# has already caused two production bugs (CHANGELOG v0.6.1 "FEATURE_SLUG
# undefined", v0.7.2 "slug-derivation drift between writer and reader").
#
# USAGE
#   This script is intended to be SOURCED by a SKILL.md bash block, not executed
#   directly:
#       source "${CLAUDE_PLUGIN_ROOT}/scripts/feature_slug.sh"
#   After sourcing, FEATURE_SLUG is set in the caller's shell. Each fenced bash
#   block in a SKILL.md is a SEPARATE tool call with a fresh shell, so this must
#   be re-sourced at the top of every block that reads FEATURE_SLUG — sourcing
#   it once does not survive to a later block.
#
# EXPORTED VARIABLES
#   FEATURE_SLUG   The design-handoff-note slug for the current work. Resolution
#                  order: (1) an already-set FEATURE_SLUG in the caller's
#                  environment (explicit override), (2) the current git branch
#                  name with `/` replaced by `-`, (3) the literal "no-branch"
#                  when git branch detection fails (detached HEAD, no repo).
#
# Why a script and not a one-liner comment to copy: the two incidents above were
# both copy-paste/drift failures, not logic failures — the one-liner itself was
# always correct. Making it a single sourced file removes the copy step, not
# the logic.

FEATURE_SLUG="${FEATURE_SLUG:-$(git branch --show-current 2>/dev/null | tr '/' '-' || echo "no-branch")}"
