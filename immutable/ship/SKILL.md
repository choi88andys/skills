---
name: ship
description: Minimum-viable PR creation skill for the immutable SDD flow. Runs pre-ship checklist, verifies commit hygiene, runs build/test, composes a PR body that auto-includes pitch and linked ADR paths, then creates the PR via `gh pr create`. Refuses if the eng review did not APPROVE. Logs one lightweight learning entry per attempt natively; richer capture (multi-entry retrospectives, pruning, cross-skill aggregation) and harness-policy gating are left to a wrapper — teams that want those layers should wrap this skill rather than fork it. Triggers - "/immutable:ship", "PR 만들어", "배포 준비", "ship it".
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
license: MIT
---

# /immutable:ship — Pre-ship + PR creation (minimum-viable)

This is the final skill in the 7-step immutable SDD flow. By the time it
runs, the implementation should be complete and tests should be green.
This skill verifies that, composes a PR body grounded in the pitch + linked
ADRs + design / review notes, and creates the PR.

## Scope and positioning

This skill is intentionally **minimum-viable**. It covers the chain-integrity
work — verify eng APPROVE, ensure pitch and ADR paths land in the PR body,
guard against shipping a dirty tree or a protected-branch commit. It does
NOT cover:

- **Richer learnings capture** beyond one lightweight entry per attempt
  (see "Log learning to project memory" below) — multi-entry
  retrospectives, pruning, or cross-skill aggregation need a
  project-specific wrapper hook.
- Worktree policy enforcement beyond a one-line warning — branch-write
  guards belong in `PreToolUse` hooks, not in this skill.
- Status ledgers, archive workflows, or per-team telemetry.

Teams that want those layers should add them as hooks or wrapper skills
around the `/immutable:ship` invocation rather than fork the skill.

The skill expects:

1. **An eng review APPROVE** at `.claude/immutable/plan-review/{slug}-eng.md`.
2. **A clean working tree** — all changes committed.
3. **Tests passing** — verified by Step 4.

Output: a GitHub PR. The PR body includes:
- Summary bullets distilled from pitch + design note + review notes
- Test plan derived from the eng review's Test Coverage Diagram
- Pitch path + linked ADR paths
- Spec-repo PR placeholder (filled by user when a pitch supersede was
  also authored during this sprint)

## Strings catalog & locale

User-facing prompts come from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml`.
`team_language` from `.immutable-prd/config.yml` (default: `ko`).

Per-string fallback: primary catalog → `strings.en.yml` (with
`common.fallback_warning`) → hardcoded English in this SKILL.md.

## Engineering principles

- **Boil lakes, flag oceans.** Verify completeness before shipping. Don't
  defer "we'll fix it in a follow-up" items into TODOS.md silently —
  surface them to the user explicitly.
- **User sovereignty.** Always confirm before `gh pr create`. The PR is a
  visible artifact; the user owns the moment of creation.

## Preconditions

1. `.immutable-prd/config.yml` exists. Refuse with `common.refuse_legacy_mode`
   otherwise.
2. `repo_mode` is `single-repo` or `two-repo-app`. Refuse with
   `ship.refuse.spec_only_repo` if `two-repo-spec`.
3. Eng review APPROVE note exists. Refuse with `ship.refuse.eng_not_approved`
   otherwise (with options: rerun eng review, or skip ship).
4. Working tree is clean. Refuse with `ship.refuse.dirty_tree` otherwise
   (offering: commit, stash, or abort).
5. Current branch is NOT a protected branch (main / master / develop).
   Refuse with `ship.refuse.protected_branch` otherwise.

## SDD mode detection

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
```

Refuse with `common.refuse_legacy_mode` if `SDD_MODE != immutable-prd`.

---

## Overall Process (7 steps)

```
Step 1: Pre-ship checklist        — branch, tree, mixed concerns
Step 2: Commit hygiene            — conventional prefix, bisect-friendly
Step 3: Review artifact verify    — design + ceo + eng notes present, eng APPROVE
Step 4: Build + test              — auto-detect project type, run appropriate command
Step 5: PR body composition       — pr-body-template.md + pitch + ADRs
Step 6: PR creation               — gh pr create with HEREDOC, after user confirm
Step 7: Cleanup hint              — post-merge cleanup recommendation
```

---

## Step 1 — Pre-ship checklist

```bash
_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "Shipping from: $_BRANCH"
git status --short
git diff --stat
```

Verify:
- [ ] On a feature / fix / chore branch (not main / master / develop)
- [ ] All changes committed (clean working tree)
- [ ] No unrelated changes mixed in (check diff against base branch)

If the diff against the base branch (main / develop) shows files outside
the area the pitch describes, surface them via `ship.step1.mixed_concerns`
and ask whether to:
- A) Split the unrelated changes into a separate commit / PR
- B) Proceed (the user accepts the mixed PR)

---

## Step 2 — Commit hygiene

```bash
# Resolve base branch (main or develop, whichever the branch was created from).
BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
  | sed 's@^refs/remotes/origin/@@' || echo "main")
git log --oneline $(git merge-base HEAD "$BASE_BRANCH" 2>/dev/null \
  || git merge-base HEAD develop 2>/dev/null)..HEAD
```

Verify:
- [ ] Each commit has a conventional prefix (`feat:`, `fix:`, `chore:`,
  `refactor:`, `docs:`, etc.)
- [ ] Each commit is a single logical change (bisect-friendly)
- [ ] No "wip", "tmp", "oops", or empty-message commits
- [ ] Refactoring and feature changes are in separate commits

If commit hygiene issues exist, surface via `ship.step2.hygiene_issues`
and offer:
- A) Interactive rebase to fix (user runs `git rebase -i` themselves)
- B) Continue as-is (the issues are flagged in the verdict)

The skill does NOT run interactive git operations on behalf of the user.

---

## Step 3 — Review artifact verification

```bash
# Derive the slug from the current branch (matches the convention used by
# every upstream skill in the 7-step flow). Each Bash invocation is a fresh
# shell — variables don't persist across blocks, so this derivation repeats
# in every block that needs the slug.
source "${CLAUDE_PLUGIN_ROOT}/scripts/feature_slug.sh"

DESIGN_NOTE=".claude/immutable/design/${FEATURE_SLUG}.md"
CEO_NOTE=".claude/immutable/plan-review/${FEATURE_SLUG}-ceo.md"
ENG_NOTE=".claude/immutable/plan-review/${FEATURE_SLUG}-eng.md"

[ -f "$DESIGN_NOTE" ] && echo "design note present"
[ -f "$CEO_NOTE" ]    && echo "ceo note present"
[ -f "$ENG_NOTE" ]    && echo "eng note present"

# Eng note verdict must be APPROVE. The grep is whitespace-tolerant but
# requires `Verdict:` at line start (no markdown bold or heading prefix —
# the writer side enforces this; see plan-review-{ceo,eng} Phase 4.2).
if ! grep -qE '^Verdict:[[:space:]]+APPROVE' "$ENG_NOTE" 2>/dev/null; then
  echo "ENG NOT APPROVED"
fi
```

If notes are missing or eng verdict is not APPROVE, refuse via
`ship.refuse.eng_not_approved`.

Read the eng note's Test Coverage Diagram — it informs Step 4 (which tests
to run) and Step 5 (the PR's Test Plan section).

Read the ceo note's Phase 3 triggers — pitch supersede or ADR authoring
recommendations get surfaced in the PR body so reviewers know what was
deferred to spec / app repo work.

---

## Step 4 — Build & test verification

Auto-detect project type:

```bash
_PROJECT_TYPES=()
[ -f "pubspec.yaml" ] && _PROJECT_TYPES+=("flutter")
[ -f "Package.swift" ] || ls *.xcodeproj >/dev/null 2>&1 && _PROJECT_TYPES+=("ios")
[ -f "package.json" ] && _PROJECT_TYPES+=("node")
[ -f "pyproject.toml" ] || [ -f "requirements.txt" ] && _PROJECT_TYPES+=("python")
[ -f "Cargo.toml" ] && _PROJECT_TYPES+=("rust")
[ -f "go.mod" ] && _PROJECT_TYPES+=("go")
echo "DETECTED: ${_PROJECT_TYPES[*]}"
```

For each detected type, run the appropriate build / test command. Look for
project-specific overrides in `CLAUDE.md` first (the user may have
documented "to test, run X").

Default commands per type:
- **flutter**: `flutter analyze && flutter test`
- **ios**: `xcodebuild build && xcodebuild test` (the user may have a
  fastlane lane; check `Fastfile` and prefer that)
- **node**: per `package.json` scripts — typically `npm test` or `yarn test`
- **python**: `pytest` (or `python -m unittest` if no pytest config)
- **rust**: `cargo build && cargo test`
- **go**: `go build ./... && go test ./...`

If tests fail, refuse via `ship.step4.tests_failing` with the failure
output. Do not proceed to PR creation. The user fixes tests, recommits,
then reruns `/immutable:ship`.

If tests pass, render `ship.step4.build_passed` with the project types
checked.

---

## Step 5 — PR body composition

The PR body template lives at `pr-body-template.md` in this skill's
directory. Read it now and render with captured values:

- `{title}` — PR title (≤ 70 chars, conventional prefix)
- `{summary_bullets}` — 3-5 bullets from pitch + design note + ceo note
- `{test_plan}` — derived from eng note's Test Coverage Diagram
- `{pitch_path}` — relative pitch path inside the spec repo (or
  "(none — internal refactor)" in refactor mode)
- `{adr_paths}` — bullet list of linked ADR paths in the app repo's `adr/`
  directory (matched by frontmatter `references.pitches:`)
- `{spec_repo_pr_placeholder}` — a placeholder line `Spec repo PR: <fill in>`
  if the user is also authoring a pitch supersede in the spec repo this
  sprint. Empty otherwise.
- `{ceo_phase3_triggers}` — pitch supersede / ADR candidates from CEO
  note's Phase 3 (so reviewers see what was deferred to spec / future ADRs)

### 5.1 Resolve pitch path

```bash
# Re-derive slug + design-note path (this is a fresh Bash invocation; vars
# from Step 3 don't persist).
source "${CLAUDE_PLUGIN_ROOT}/scripts/feature_slug.sh"
DESIGN_NOTE=".claude/immutable/design/${FEATURE_SLUG}.md"

PITCHES_REL="$(sed -n 's/^pitches_path:[[:space:]]*\([^[:space:]]*\).*/\1/p' \
  "$IMMUTABLE_PRD_SPEC_CONFIG" 2>/dev/null | head -1)"
PITCHES_REL="${PITCHES_REL:-pitches/}"
# The pitch filename is captured in the design note's frontmatter; read it. Only the first
# token after `Pitch:` — refactor mode writes "(none — internal refactor)" there and the
# check below deliberately keys on the leading "(none".
PITCH_REL_PATH=$(sed -n 's/^Pitch:[[:space:]]*\([^[:space:]]*\).*/\1/p' \
  "$DESIGN_NOTE" 2>/dev/null | head -1)
```

If `PITCH_REL_PATH` is `(none` (refactor mode), set the PR body's pitch
section to "(none — internal refactor)".

### 5.2 Resolve linked ADRs

```bash
ADR_REL="$(sed -n 's/^adr_path:[[:space:]]*\([^[:space:]]*\).*/\1/p' \
  "$IMMUTABLE_PRD_APP_CONFIG" 2>/dev/null | head -1)"
ADR_REL="${ADR_REL:-adr/}"
APP_ROOT="$(dirname "$(dirname "$IMMUTABLE_PRD_APP_CONFIG")")"
PITCH_FILENAME="$(basename "$PITCH_REL_PATH")"

# Find ADRs whose frontmatter references this pitch.
grep -l "^[[:space:]]*-[[:space:]]*${PITCH_FILENAME}$" \
  "$APP_ROOT/$ADR_REL"*.md 2>/dev/null | grep -v TEMPLATE.md
```

If none, the PR body's ADR section reads "(no linked ADRs in this PR)".

### 5.3 Compose

Render the template. Confirm the assembled body with the user via
`ship.step5.body_preview` before Step 6. The user may edit before sending.

---

## Step 6 — PR creation

```bash
# Use HEREDOC for the body (avoids shell escaping issues).
gh pr create --title "{title}" --body "$(cat <<'EOF'
{rendered_body}
EOF
)"
```

Refuse to run `gh pr create` without explicit user confirmation. Render
`ship.step6.confirm_create` showing the title + body preview, with options:
- A) Create — runs `gh pr create`
- B) Edit body — user provides revised body, return to Step 5.3
- C) Cancel — abort

Do NOT add `--draft` automatically. The user signals draft preference
through their own conventions.

After creation, capture the PR URL from `gh pr create` output. Render
`ship.step6.pr_created` with the URL.

---

## Step 7 — Cleanup hint

After the PR is created, render `ship.step7.cleanup_hint`:

> PR created: {pr_url}
>
> After the PR merges:
> - Pull the merged commit on the base branch
> - Delete the feature branch (locally and remote)
> - Run `/immutable:adr` again if the merged code introduced any further
>   architectural decisions during implementation that the eng review
>   didn't catch
> - For two-repo mode: if a pitch supersede is pending in the spec repo,
>   create that PR now (it can land before or after this PR — the chain
>   doesn't require ordering)

The skill does NOT run cleanup commands. The user owns the post-merge
flow.

---

## Strings catalog key anchors

| Key | Used in |
|-----|---------|
| `ship.step1.mixed_concerns` | Step 1 |
| `ship.step2.hygiene_issues` | Step 2 |
| `ship.step3.notes_check` | Step 3 |
| `ship.step4.build_passed` | Step 4 |
| `ship.step4.tests_failing` | Step 4 (refusal) |
| `ship.step5.body_preview` | Step 5.3 |
| `ship.step6.confirm_create` | Step 6 |
| `ship.step6.pr_created` | Step 6 |
| `ship.step7.cleanup_hint` | Step 7 |
| `ship.refuse.spec_only_repo` | Preconditions |
| `ship.refuse.eng_not_approved` | Preconditions / Step 3 |
| `ship.refuse.dirty_tree` | Preconditions |
| `ship.refuse.protected_branch` | Preconditions |

Plus shared `common.*` keys.

---

## Log learning to project memory (mandatory final step)

Before returning control to the user (success **or** abort), append one learning entry to the project store. Best-effort — if `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is unavailable, the guard exits silently and never blocks the flow.

Pick ONE branch below based on outcome and substitute the placeholders (`<pitch-basename>`, `<N>`, `<reason>`, etc.) with concrete values before running. The branch name (`$BRANCH`) keys the success entry — it is stable across the cycle and known before `gh pr create` runs.

```bash
LH="${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh"
[ -x "$LH" ] || exit 0
SLUG=$("$LH" slug)
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# === On success (PR created) ===
TYPE=tool; SOURCE=observed; CONF=7
KEY="ship-${BRANCH}-${SLUG}"
INSIGHT="PR <pitch-basename>; ADRs: <comma-separated paths or 'none'>; build/test: <ok | issues=...>"
FILES='[]'   # PR lives on GitHub; no local-file artifact for prune to track

# === On abort / refusal (eng-not-approved, dirty tree, protected branch, tests failing, user-cancel before gh pr create) ===
# TYPE=pitfall; SOURCE=observed; CONF=6
# KEY="ship-aborted-${BRANCH}-${SLUG}"
# INSIGHT="Aborted at Step <N>: <reason in one sentence>"
# FILES='[]'

"$LH" log "$(jq -nc --arg skill "immutable-ship" --arg type "$TYPE" --arg key "$KEY" \
  --arg insight "$INSIGHT" --arg src "$SOURCE" --argjson conf "$CONF" --argjson files "$FILES" \
  '{skill:$skill,type:$type,key:$key,insight:$insight,confidence:$conf,source:$src,files:$files}' 2>/dev/null)" || true
```

---

## Critical rules

- **No automatic PR creation.** Always confirm before `gh pr create`.
- **No automatic git operations.** Don't rebase, force-push, amend, or
  delete branches without explicit user instruction.
- **Tests must pass.** No "skip tests for now" path. If tests fail, the
  skill refuses.
- **Eng review must be APPROVE.** No "skip review" path.

---

## Supporting files

- **`pr-body-template.md`** — markdown template for Step 5 PR body
  composition.

Plugin-bundled at `${CLAUDE_PLUGIN_ROOT}/ship/`.
