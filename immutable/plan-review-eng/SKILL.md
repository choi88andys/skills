---
name: plan-review-eng
description: Engineering-perspective review of the implementation plan. Walks 4 sections (Architecture, Code Quality, Test Coverage, Performance) with a worktree-parallelization analysis and surfaces ADR-authoring triggers. Runs in two modes - "ceo-grounded" (when /immutable:plan-review-ceo APPROVED first; uses the CEO scope envelope) and "standalone" (no CEO note; reviews pitch directly with a built-in lightweight scope check). Triggers - "/immutable:plan-review-eng", "ENG 리뷰", "엔지니어 리뷰", "engineering review".
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
license: MIT
---

# /immutable:plan-review-eng — Engineering review (4 sections)

This skill applies engineering rigor — architecture, code quality, test
coverage, performance, parallelization — to the implementation plan. It
runs in two modes:

- **ceo-grounded** — `/immutable:plan-review-ceo` ran first and returned
  APPROVE. The eng review consumes the CEO note's scope envelope (Phase 1F
  decision) and Phase 3 trigger list, and skips its own scope check (already
  done by CEO).
- **standalone** — no CEO note exists. The eng review is the only review
  for this work. It reviews the pitch + linked ADRs + (optional) design
  handoff note directly, runs a lightweight scope check (Phase 0.3) in
  place of the CEO's nuclear scope challenge, and produces ADR-authoring
  triggers from its own findings.

Standalone mode exists for small, clear-scope tasks where the full CEO
review is overkill: quick architecture decisions, follow-up PRs to
already-scoped pitches, internal refactors with a known shape. Non-trivial
work should still run CEO first; the eng review's scope check is
deliberately lighter than CEO Phase 1.

Output: an inline review (issues + recommendations) plus a transient
review-note at `.claude/immutable/plan-review/{slug}-eng.md` capturing the
mode, verdict, and any ADR-authoring triggers.

## Strings catalog & locale

User-facing prompts come from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml`.
`team_language` is read from `.immutable-prd/config.yml` (default: `ko`).

Per-string fallback: primary catalog → `strings.en.yml` (with
`common.fallback_warning`) → hardcoded English in this SKILL.md.

## Engineering principles

- **Boil lakes, flag oceans.** Recommend the complete option when minutes more.
  Tests are the cheapest lake to boil — never accept "we'll add tests later."
- **Search before building.** Layer 1 (built-in) → Layer 2 (popular,
  scrutinize) → Layer 3 (first principles).
- **User sovereignty.** Recommend, then let the user decide.
- **Generation-verification loop.** Confidence calibration on every recommendation.
  Below 7/10 → "Low confidence — verify first:" prefix.
- **Anti-skip rule.** Walk all 4 sections regardless of plan size. "Strategy
  doc, so test review doesn't apply" is wrong — strategy fails at
  implementation seams.

## Preconditions

1. `.immutable-prd/config.yml` exists (refuse with `common.refuse_legacy_mode`
   otherwise).
2. `repo_mode` is `single-repo` or `two-repo-app` (refuse with
   `pre.refuse.spec_only_repo` if `two-repo-spec`).
3. A pitch is reachable (or refactor mode is explicitly chosen). Without a
   pitch and without refactor opt-in, refuse with `pre.refuse.no_pitch`.
4. CEO review note state determines mode (Phase 0.1 handles the routing):
   - APPROVE → ceo-grounded mode
   - REVISE / REJECT → refuse with `pre.refuse.ceo_not_approved` (CEO
     surfaced blockers that must be addressed first)
   - missing → ask the user via `pre.phase0.ceo_missing_question` whether
     to proceed in standalone mode or pause to run CEO first

## SDD mode detection

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
```

Refuse with `common.refuse_legacy_mode` if `SDD_MODE != immutable-prd`.

If on a protected branch, render `common.protected_branch_warn`.

## Invocation

```
/immutable:plan-review-eng
```

Optional free-text initial context:

```
/immutable:plan-review-eng cart review-request — focus on the API client
```

---

## Overall Process

```
Phase 0: Intake & mode selection — ceo-grounded vs standalone routing,
                                   locate targets, scope check
Phase 1: Section Reviews         — walk 4 sections (sections.md)
Phase 2: Worktree Analysis       — dependency table + parallel lanes
Phase 3: Post-Review Triggers    — ADR authoring recommendations
Phase 4: Verdict + Handoff       — APPROVE / REJECT / REVISE; recommend
                                   ship or adr
```

---

## Phase 0 — Intake & mode selection

### 0.1 Mode routing

```bash
FEATURE_SLUG="${FEATURE_SLUG:-$(git branch --show-current 2>/dev/null | tr '/' '-' || echo "no-branch")}"
CEO_NOTE=".claude/immutable/plan-review/${FEATURE_SLUG}-ceo.md"

REVIEW_MODE=""
if [ -f "$CEO_NOTE" ]; then
  if grep -q '^Verdict: APPROVE' "$CEO_NOTE" 2>/dev/null; then
    REVIEW_MODE="ceo-grounded"
  elif grep -qE '^Verdict: (REVISE|REJECT)' "$CEO_NOTE" 2>/dev/null; then
    REVIEW_MODE="ceo-blocked"
  fi
fi
[ -z "$REVIEW_MODE" ] && REVIEW_MODE="ceo-missing"
echo "REVIEW_MODE=$REVIEW_MODE"
```

Branch on `$REVIEW_MODE`:

- **`ceo-grounded`** — render `pre.phase0.mode_ceo_grounded` with the CEO
  note path. Read the CEO note end-to-end. Capture the Phase 1F scope
  envelope and the Phase 3 trigger list. Skip Phase 0.3 (complexity check
  is the CEO's responsibility in this mode).
- **`ceo-blocked`** — refuse with `pre.refuse.ceo_not_approved`. The CEO
  surfaced blockers; eng review on a known-blocked plan is wasted work.
- **`ceo-missing`** — ask via `pre.phase0.ceo_missing_question`:
  - (A) **Skip CEO and proceed in standalone mode** (small task, clear scope,
    or ADR-authoring sprint)
  - (B) **Pause and run `/immutable:plan-review-ceo` first** (recommended
    for non-trivial work)
  - (C) **Abort**
  On (A), set `REVIEW_MODE=standalone` and render `pre.phase0.standalone_acknowledged`
  with a one-line reminder that Phase 0.3 is now mandatory (no CEO scope
  envelope to lean on).

### 0.2 Locate review targets

Same set in both modes:

- **Pitch** — relative path inside the spec repo, OR `(none — refactor)`
  for refactor mode. Located via `IMMUTABLE_PRD_SPEC_CONFIG` in standalone
  mode, OR copied from the CEO note in ceo-grounded mode.
- **Linked ADRs** — files in the app repo's `adr/` directory whose
  frontmatter `references.pitches:` matches the pitch filename.
- **Design handoff note** — `.claude/immutable/design/{slug}.md` if a prior
  `/immutable:design` ran; optional in both modes (warn but proceed in
  standalone mode if absent).

In **ceo-grounded** mode, prefer reading paths from the CEO note rather
than re-discovering them — keeps the two reviews consistent.

In **standalone** mode, if no pitch is reachable AND the user is not in
refactor mode, refuse with `pre.refuse.no_pitch`.

### 0.3 Lightweight scope check (standalone mode only)

Skip this section entirely in `ceo-grounded` mode — the CEO review's
Phase 1 already covered scope.

In `standalone` mode, run a lightweight check (NOT the full nuclear scope
challenge — that belongs to CEO):

```bash
# Files touched on this branch since base.
BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
  | sed 's@^refs/remotes/origin/@@' || echo "main")
FILES_TOUCHED=$(git diff --name-only \
  $(git merge-base HEAD "$BASE_BRANCH" 2>/dev/null \
    || git merge-base HEAD develop 2>/dev/null)..HEAD 2>/dev/null \
  | wc -l | tr -d ' ')
echo "FILES_TOUCHED=$FILES_TOUCHED"
```

Render `pre.phase0.standalone_scope_check` with `FILES_TOUCHED` and the
following gates:

- **≥ 8 files OR ≥ 2 new top-level abstractions** (services, classes,
  modules) — surface as a complexity warning. Ask via AskUserQuestion:
  - (A) Proceed in standalone mode (the user accepts the scope is heavier
    than the standalone fast-path is meant for)
  - (B) Pause and run `/immutable:plan-review-ceo` (recommended — at this
    size, scope challenge is high-value)
  - (C) Reduce scope first, then re-enter eng review

- **< 8 files AND < 2 new abstractions** — pass the gate, proceed to Phase 1.

The threshold is intentionally a "smell" not a hard limit. The user can
override on (A) when they have context the heuristic doesn't.

### 0.4 Scan for late additions (ceo-grounded mode only)

Skip in `standalone` mode.

```bash
git log --oneline $(git merge-base HEAD main 2>/dev/null \
  || git merge-base HEAD develop 2>/dev/null)..HEAD
git diff --stat
```

If the branch has commits AFTER the CEO review note's timestamp, surface
them via `pre.phase0.late_changes`. The eng review covers what the CEO
review didn't see — unfair to APPROVE eng without surfacing this delta.

---

## Phase 1 — Section Reviews

Walk all 4 sections. Detailed prompts live in `sections.md` —
**read it now before starting Section 1**.

```
Section 1: Architecture Review (Eng angle)
Section 2: Code Quality Review
Section 3: Test Review (Test Coverage Diagram)
Section 4: Performance Review
```

Anti-skip rule strict. State "No issues found" and move on if a section
has nothing — but always evaluate.

For Section 3, use the test-coverage-diagram template at
`templates/test-coverage-diagram.md`.

Issue surface: one issue per AskUserQuestion call. Never batch.

Pause for user feedback between sections.

---

## Phase 2 — Worktree Parallelization

Analyze the plan's implementation steps for parallel execution opportunities.
This helps the user split work across git worktrees when the plan has
independent workstreams.

### 2.1 Skip conditions

Skip the analysis (state "Sequential implementation, no parallelization
opportunity.") when:

- All steps touch the same primary module
- The plan has fewer than 2 independent workstreams
- The user explicitly opts out (e.g., solo dev, no worktree workflow)

### 2.2 Dependency table

For each implementation step / workstream, fill the table:

```
| Step | Modules touched | Depends on |
|------|----------------|------------|
| (step name) | (directories / modules — NOT specific files) | (other steps, or —) |
```

Work at the **module / directory level**, not file level. Plans describe
intent ("add API endpoints"), not specific files. Module-level
("controllers/", "models/") is reliable; file-level is guesswork.

### 2.3 Parallel lanes

Group steps into lanes:
- Steps with no shared modules and no dependency → **separate lanes (parallel)**.
- Steps sharing a module directory → **same lane (sequential)**.
- Steps depending on other steps → **later lanes**.

Format:
```
Lane A: step1 → step2 (sequential, shared models/)
Lane B: step3 (independent)
```

### 2.4 Execution order

Render which lanes launch in parallel and which wait. Example:
"Launch A + B in parallel worktrees. Merge both. Then C."

### 2.5 Conflict flags

If two parallel lanes touch the same module directory, flag it:
"Lanes X and Y both touch `module/` — potential merge conflict. Consider
sequential execution or careful coordination."

---

## Phase 3 — Post-Review Triggers (ADR authoring)

After Phase 1 + 2 complete, scan for architecture decisions surfaced during
the review. Each is a candidate for ADR authoring via `/immutable:adr` in
the app repo.

Common triggers:

- **Section 1** (Architecture) — new abstraction, new dependency, new SPOF,
  rollback strategy choice
- **Section 4** (Performance) — caching strategy, indexing strategy
- **Phase 2** (Worktree) — parallelization decision affecting which module
  owns what

For each, surface the decision + render `pre.phase3.adr_recommendation`
with the recommended ADR title and the rationale. Do NOT auto-author.

### Cross-reference behavior depends on `REVIEW_MODE`

- **ceo-grounded** — read the CEO review's Phase 3 trigger list. If a
  candidate the eng review surfaced was already flagged by CEO, cross-reference
  the CEO entry instead of restating. The eng review's job is to **add** to
  that list, not duplicate it. Pitch-supersede candidates are NOT eng's
  domain — pass them through if CEO flagged any (they belong to spec repo
  PRs), but don't generate new ones.

- **standalone** — there is no CEO Phase 3 to cross-reference. The eng
  review is the only source of ADR candidates for this work. Be more
  thorough than the ceo-grounded mode would be — surface every architecture
  decision worth recording, including ones that the CEO review's Phase 3
  would normally have caught (rollout strategy, security boundary changes,
  etc.). The pitch may be the only canonical document; the ADR is the only
  way to record decisions made during implementation review.

In both modes, the user owns the decision to actually run `/immutable:adr`.
The skill surfaces candidates with rationale; it does not auto-author.

---

## Phase 4 — Verdict + Handoff

### 4.1 Verdict

Render via AskUserQuestion using `pre.phase4.verdict_question`:

- **APPROVE** — proceed to implementation, then `/immutable:ship`. Run
  `/immutable:adr` for any Phase 3 triggers before or during implementation.
- **REVISE** — issues require code-level changes that affect the plan's
  shape. Pause review; rerun after the plan is updated.
- **REJECT** — engineering concerns are severe enough that scope or approach
  must change. Recommend returning to `/immutable:plan-review-ceo` (or
  `/immutable:office-hours` for full rethink).

### 4.2 Write transient review note

```bash
mkdir -p .claude/immutable/plan-review
OUT=".claude/immutable/plan-review/${FEATURE_SLUG}-eng.md"
echo "OUTPUT_PATH: $OUT"
```

Note structure (record `REVIEW_MODE` near the top so downstream readers
know whether the CEO scope envelope is also in play):

- **Mode**: `ceo-grounded` or `standalone`
- **Verdict**: `APPROVE` / `REVISE` / `REJECT` + one-line rationale
- **Scope context**:
  - ceo-grounded → reference to CEO note (path + Phase 1F decision summary)
  - standalone → Phase 0.3 scope-check result (files touched count, gate
    outcome, any user override)
- Section 1-4 highlights (one bullet per section, even "No issues")
- Test Coverage Diagram (Section 3 output)
- Worktree Analysis (Phase 2 output — dependency table + lanes + execution
  order + conflict flags)
- ADR-authoring candidates (Phase 3 — concrete decisions + rationale)
- Late-changes note (only when ceo-grounded mode and Phase 0.4 surfaced
  post-CEO commits)

### 4.3 Handoff

Render via `pre.phase4.handoff_to_ship` (APPROVE) or
`pre.phase4.handoff_to_revise` (REVISE / REJECT).

For APPROVE:
- Path to the eng review note (`$OUT`)
- ADR triggers (paths in app repo where ADRs should land)
- Recommendation: "Implement → run `/immutable:adr` for each architecture
  decision (if any) → run `/immutable:ship` when implementation is complete."

For REVISE / REJECT:
- Recommendation: rerun `/immutable:plan-review-ceo` or
  `/immutable:office-hours` based on which sub-phase surfaced the blocker.

---

## Critical rules

- **One issue = one AskUserQuestion call.** Never batch.
- **Recommend + WHY.** Map each recommendation to an engineering principle.
- **Confidence calibration.** Rate 1-10 per recommendation. Below 7 →
  "Low confidence — verify first:" prefix.
- **Don't make code changes.** This skill reviews; it does not implement.
- **Anti-skip rule.** All 4 sections evaluated. Phase 2 worktree analysis
  may be skipped (per Phase 2.1 skip conditions) but the decision to skip
  must be recorded in the review note.
- **Worktree parallelization respects user policy.** Only recommend parallel
  lanes when the user has opted into worktree flows. For simple trunk
  workflows, sequential is fine.

---

## Strings catalog key anchors

| Key | Used in |
|-----|---------|
| `pre.phase0.mode_ceo_grounded` | Phase 0.1 (ceo-grounded routing) |
| `pre.phase0.ceo_missing_question` | Phase 0.1 (ceo-missing routing) |
| `pre.phase0.standalone_acknowledged` | Phase 0.1 (standalone mode entered) |
| `pre.phase0.standalone_scope_check` | Phase 0.3 (standalone scope smell) |
| `pre.phase0.late_changes` | Phase 0.4 (ceo-grounded only) |
| `pre.phase2.skip_summary` | Phase 2.1 |
| `pre.phase2.dependency_table_template` | Phase 2.2 |
| `pre.phase2.parallel_lanes_template` | Phase 2.3 |
| `pre.phase2.execution_order_template` | Phase 2.4 |
| `pre.phase2.conflict_flag_template` | Phase 2.5 |
| `pre.phase3.adr_recommendation` | Phase 3 |
| `pre.phase4.verdict_question` | Phase 4.1 |
| `pre.phase4.review_note_written` | Phase 4.2 |
| `pre.phase4.handoff_to_ship` | Phase 4.3 (APPROVE) |
| `pre.phase4.handoff_to_revise` | Phase 4.3 (REVISE / REJECT) |
| `pre.refuse.spec_only_repo` | Preconditions |
| `pre.refuse.no_pitch` | Preconditions / Phase 0.2 (standalone) |
| `pre.refuse.ceo_not_approved` | Phase 0.1 (ceo-blocked routing) |

Plus shared `common.*` keys.

---

## Supporting files

- **`sections.md`** — detailed prompts and output requirements for the 4
  Phase 1 sections. Read before Section 1 begins.
- **`templates/test-coverage-diagram.md`** — Section 3 output diagram template
  with NEW UX FLOWS / NEW DATA FLOWS / NEW CODEPATHS / NEW BACKGROUND JOBS /
  NEW INTEGRATIONS / NEW ERROR / RESCUE PATHS rows.

All plugin-bundled at `${CLAUDE_PLUGIN_ROOT}/plan-review-eng/`.
