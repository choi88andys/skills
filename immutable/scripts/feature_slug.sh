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
# copy-paste/drift failures. Centralizing removes the copy step — and, because the
# derivation is now read once instead of skimmed at five call sites, it also exposed
# a latent logic bug in the one-liner itself, fixed below.
#
# THE `|| echo "no-branch"` TRAP (fixed 2026-07-31 — do not "simplify" this back).
# `git branch --show-current` EXITS 0 AND PRINTS NOTHING on a detached HEAD, so a
# trailing `|| echo "no-branch"` never runs there. Measured on both branchless cases:
# detached HEAD and non-repo each yielded an EMPTY slug, never "no-branch".
# An empty slug is not cosmetic — it is CHANGELOG v0.6.1 verbatim: every consumer
# composes `${FEATURE_SLUG}.md`, so a blank one produces the hidden, glob-invisible
# `.claude/immutable/design/.md` / `.claude/immutable/plan-review/-ceo.md`, which
# "could never match real notes" and blocked every PR through ship's APPROVE gate.
# Worse than v0.6.1: an empty slug is not merely unmatchable, it is SHARED — two
# different branchless runs collide on the same path, so ship can read a stale note
# from unrelated work and treat it as this feature's approval.
# Branch on the RESULT being non-empty, never on the exit status.

if [ -z "${FEATURE_SLUG:-}" ]; then
  FEATURE_SLUG="$(git branch --show-current 2>/dev/null | tr '/' '-')"
  [ -n "$FEATURE_SLUG" ] || FEATURE_SLUG="no-branch"
fi
