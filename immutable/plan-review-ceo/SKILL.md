---
name: plan-review-ceo
description: Adversarial CEO-style review of the implementation plan grounded in the pitch + linked ADRs + design handoff note. Walks Phase 0 nuclear scope challenge (premise / existing-code leverage / dream-state / mandatory alternatives / mode selection) and 11 review sections. Surfaces pitch-supersede triggers and ADR-authoring triggers. Triggers - "/immutable:plan-review-ceo", "CEO 리뷰", "스코프 검토", "plan review scope".
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion, WebSearch
license: MIT
---

# /immutable:plan-review-ceo — Scope challenge + 11-section review

This is the heavier of the two plan-review skills. It runs scope challenge
first (Phase 0), then walks 11 review sections that catch silent failures,
weak rollout posture, and architectural debt before code lands.

The skill expects three review targets:

1. **Pitch** — in the spec repo (`pitches/<domain>/...md`) or single-repo
   pitches subtree. The canonical WHAT.
2. **Linked ADRs** — files in the app repo's `adr/` directory whose
   frontmatter `references.pitches:` matches this pitch. The recorded WHY.
3. **Design handoff note** — `.claude/immutable/design/{slug}.md` written
   by the previous `/immutable:design` skill. Captures app-side context
   the pitch could not include.

Output: an inline review (questions + recommendations) plus a transient
review-note at `.claude/immutable/plan-review/{slug}-ceo.md` capturing the
verdict, scope decisions, and trigger surfaces (pitch-supersede candidates,
ADR-authoring candidates).

## Strings catalog & locale

User-facing prompts come from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml`.
`team_language` is read from `.immutable-prd/config.yml` (default: `ko`).

Per-string fallback: primary catalog → `strings.en.yml` (with
`common.fallback_warning`) → hardcoded English in this SKILL.md (last resort).

## Engineering principles

- **Boil lakes, flag oceans.** Recommend the complete option when minutes more,
  not weeks. With AI assistance, completeness costs ~5-10× less than human
  estimates suggest — re-frame "this would take 2 weeks" as "this would take
  ~1 hour Claude-assisted."
- **Search before building.** Layer 1 (built-in) → Layer 2 (popular,
  scrutinize) → Layer 3 (first principles). Use WebSearch in Phase 0
  Step 5 (Landscape Check) when scope is being expanded — surface
  "eureka" moments where conventional wisdom is wrong.
- **User sovereignty.** Recommend, then let the user decide. Never silent-skip,
  never silent-reduce, never silent-expand.
- **Generation-verification loop.** Every recommendation gets a confidence
  rating; below 7/10 must be prefaced "Low confidence — verify first:".
- **Anti-skip rule.** Never condense, abbreviate, or skip any section (1-11)
  regardless of plan type. "Strategy doc, so implementation sections don't
  apply" is always wrong — implementation details are where strategy breaks.

## Preconditions

1. `.immutable-prd/config.yml` exists. Refuse with `common.refuse_legacy_mode`
   otherwise.
2. `repo_mode` is `single-repo` or `two-repo-app`. Refuse with
   `prc.refuse.spec_only_repo` if `two-repo-spec`.
3. A pitch is reachable (single-repo or via `IMMUTABLE_PRD_SPEC_CONFIG`
   resolution). If no pitch and the user is not in refactor mode, refuse with
   `prc.refuse.no_pitch`.
4. Optional: a design handoff note at `.claude/immutable/design/{slug}.md`
   from a prior `/immutable:design` run. If absent, surface
   `prc.warn.no_design_note` and ask whether to proceed without it.

## SDD mode detection

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
```

Refuse with `common.refuse_legacy_mode` if `SDD_MODE != immutable-prd`.

If on a protected branch (main / master / develop), render
`common.protected_branch_warn`.

## Invocation

```
/immutable:plan-review-ceo
```

Optional free-text initial context (pitch hint, mode hint):

```
/immutable:plan-review-ceo cart review-request — focus on payments boundary
```

---

## Overall Process

```
Phase 0: Pre-Review Audit            — locate targets, system audit, retrospective
Phase 1: Nuclear Scope Challenge     — premises / leverage / dream / alternatives / mode
Phase 2: Section Reviews             — walk 11 sections (sections.md)
Phase 3: Post-Review Triggers        — pitch supersede + ADR authoring recommendations
Phase 4: Verdict + Handoff           — APPROVE / REJECT / REVISE; recommend plan-review-eng
```

Phase 1 and 2 each include sub-phases that pause for user input. Do not
batch issues — one issue = one AskUserQuestion call.

---

## Phase 0 — Pre-Review Audit

### 0.1 Locate review targets

```bash
# Spec config gives pitches; app config gives ADRs.
SPEC_ROOT="$(dirname "$(dirname "$IMMUTABLE_PRD_SPEC_CONFIG")")"
PITCHES_REL="$(grep '^pitches_path:' "$IMMUTABLE_PRD_SPEC_CONFIG" 2>/dev/null \
  | head -1 | awk '{print $2}')"
PITCHES_DIR="$SPEC_ROOT/${PITCHES_REL:-pitches/}"

APP_ROOT="$(dirname "$(dirname "$IMMUTABLE_PRD_APP_CONFIG")")"
ADR_REL="$(grep '^adr_path:' "$IMMUTABLE_PRD_APP_CONFIG" 2>/dev/null \
  | head -1 | awk '{print $2}')"
ADR_DIR="$APP_ROOT/${ADR_REL:-adr/}"

echo "PITCHES_DIR=$PITCHES_DIR"
echo "ADR_DIR=$ADR_DIR"
```

Ask the user via `prc.phase0.target_pitch_question` which pitch this review
covers. Surface the active pitches in `PITCHES_DIR` (excluding deprecated)
as picker options.

After the pitch is selected, scan `ADR_DIR` for ADRs whose frontmatter
`references.pitches:` matches the selected pitch. List them.

If a design handoff note exists at `.claude/immutable/design/{slug}.md`,
read it. If not, render `prc.warn.no_design_note`.

### 0.2 System audit

```bash
git log --oneline -30
git diff --stat
git stash list
grep -rl "TODO\|FIXME\|HACK\|XXX" --exclude-dir=node_modules --exclude-dir=.git \
  --exclude-dir=vendor . 2>/dev/null | head -30
git log --since=30.days --name-only --format="" 2>/dev/null \
  | sort | uniq -c | sort -rn | head -20
```

Read `CLAUDE.md`, `TODOS.md` (if present), and any docs under `docs/` that
touch this plan's domain.

Map:
- Current system state
- In-flight work (open PRs, other branches, stashed changes)
- Known pain points relevant to this plan
- FIXME / TODO comments in files this plan will touch (from the design note's
  "Files most likely touched")

### 0.3 Retrospective check

If the branch has prior commits suggesting a review cycle (review-driven
refactors, reverted changes), note what was changed and whether the current
plan re-touches those areas. Be MORE aggressive reviewing areas that were
previously problematic — recurring problem areas are architectural smells.

### 0.4 Frontend / UI scope detection

Analyze the plan. If it involves: new UI screens, changes to existing UI
components, user-facing interaction flows, frontend framework changes,
user-visible state changes, mobile / responsive behavior, or design system
changes — set `DESIGN_SCOPE=true`. Section 11 (UX review) runs only when
this is true.

### 0.5 Landscape check (only when scope-expansion is on the table)

When the user is leaning toward `SCOPE EXPANSION` or `SELECTIVE EXPANSION`
in Phase 1.6, run WebSearch for:
- "[product category] landscape 2026"
- "[key feature] alternatives"
- "why [conventional approach] [succeeds/fails]"

If WebSearch is unavailable, skip and note: "Search unavailable — proceeding
with in-distribution knowledge only."

Run the three-layer synthesis: Layer 1 / Layer 2 / Layer 3 with explicit
labels. Surface eureka moments.

Report Phase 0 findings before proceeding to Phase 1.

---

## Phase 1 — Nuclear Scope Challenge

This is the highest-leverage block. Run all six sub-phases (0A through 0F).
Detailed prompts and decision rubrics live in `nuclear-scope-rubric.md` —
read it now before starting.

### 1A. Premise Challenge
### 1B. Existing Code Leverage
### 1C. Dream State Mapping
### 1C-bis. Implementation Alternatives (mandatory ≥2-3)
### 1D. Mode-Specific Analysis
### 1E. Temporal Interrogation
### 1F. Mode Selection (EXPANSION / SELECTIVE / HOLD / REDUCTION)

For each sub-phase, see `nuclear-scope-rubric.md` for the question banks,
output formats, and worked examples.

**Critical rule**: do not proceed past 1F without explicit user mode selection
and a committed answer to "which Approach (from 1C-bis) applies under this
mode."

After mode is locked, render `prc.phase1.scope_locked` summarizing the
agreed scope envelope and selected approach.

---

## Phase 2 — Section Reviews

Walk all 11 sections. Detailed prompts, output tables, and templates live
in `sections.md` — **read it now before starting Section 1**.

```
Section 1:  Architecture Review
Section 2:  Error & Rescue Map
Section 3:  Security & Threat Model
Section 4:  Data Flow & Interaction Edge Cases
Section 5:  Code Quality
Section 6:  Test Review
Section 7:  Performance Review
Section 8:  Observability & Debuggability
Section 9:  Deployment & Rollout
Section 10: Long-Term Trajectory
Section 11: Design & UX Review (skip unless DESIGN_SCOPE=true)
```

Anti-skip rule strict: every section is evaluated, even when "no issues found"
is the result. State "Section X: No issues found." and move on. Do not skip.

Between sections, pause for user feedback before proceeding to the next.

For Section 2 specifically, the output table template is at
`templates/error-rescue-map.md`. For Section 1's data-flow ASCII diagram,
the template is at `templates/data-flow-diagram.md`.

---

## Phase 3 — Post-Review Triggers

Catalog the surfaces from Phase 1 and Phase 2 that imply downstream actions.
Render `prc.phase3.trigger_summary` with three bins:

### 3.1 Pitch supersede candidates

Any of the following found during the review trigger a recommendation to
the user to author a pitch supersede via `/immutable:prd` in the spec repo:

- Scope changed (1F selected EXPANSION / REDUCTION)
- Accessibility intent changed (Section 11 surfaced new a11y requirements)
- Motion intent changed (Section 11 surfaced new animation contract)
- Open UX questions answered or new ones raised (the pitch's optional
  Open UX questions section is no longer accurate)

For each, surface the specific delta and recommend: "spec repo →
`/immutable:prd` → supersede with new file in `pitches/<domain>/`."
Do NOT auto-author. Pitch supersede is a separate spec-repo PR.

### 3.2 ADR-authoring candidates

Any of the following found during the review trigger a recommendation to
author an ADR via `/immutable:adr` in the app repo:

- Section 1 (Architecture) — new abstraction, new dependency, new SPOF
  added, rollback strategy
- Section 3 (Security) — auth or data-access boundary change
- Section 9 (Deployment) — new rollout strategy, new feature-flag scheme
- Section 10 (Long-term) — explicit decision on tech-debt handling

For each, surface the decision and recommend: "app repo →
`/immutable:adr` → new ADR referencing this pitch."

### 3.3 Transient note only (no upstream action)

Minor review notes that don't trigger spec or ADR changes. These get
captured in the transient review note at
`.claude/immutable/plan-review/{slug}-ceo.md`.

---

## Phase 4 — Verdict + Handoff

### 4.1 Verdict

Render via AskUserQuestion using `prc.phase4.verdict_question`:

- **APPROVE** — proceed to `/immutable:plan-review-eng`. Triggers from Phase 3
  may be acted on in parallel (pitch supersede in spec repo doesn't block
  app-repo eng review).
- **REVISE** — issues surfaced require pitch supersede or scope change.
  Pause review, return after pitch is updated.
- **REJECT** — premises do not hold or scope is fundamentally wrong. Recommend
  going back to `/immutable:office-hours`.

### 4.2 Write transient review note

```bash
mkdir -p .claude/immutable/plan-review
FEATURE_SLUG="${FEATURE_SLUG:-$(git branch --show-current 2>/dev/null | tr '/' '-' || echo "no-branch")}"
OUT=".claude/immutable/plan-review/${FEATURE_SLUG}-ceo.md"
echo "OUTPUT_PATH: $OUT"
```

Write a structured note containing:
- Verdict (`APPROVE` / `REVISE` / `REJECT`) + one-line rationale
- Scope envelope agreed in Phase 1F (mode + approach name)
- Section-by-section highlights (one bullet per section, even "No issues")
- Pitch supersede candidates (Phase 3.1) — concrete delta lines
- ADR-authoring candidates (Phase 3.2) — concrete decision lines
- Transient notes (Phase 3.3)

### 4.3 Handoff

Render via `prc.phase4.handoff_to_plan_review_eng`:

- Verdict
- Path to the review note (`$OUT`)
- Recommendation: "Run `/immutable:plan-review-eng` next when ready" (only
  if APPROVE)
- Trigger reminders (any from Phase 3.1 / 3.2)

For REVISE / REJECT, recommend the appropriate upstream skill instead
(`/immutable:prd` for pitch supersede, `/immutable:office-hours` for full
rethink).

---

## Critical rules

- **One issue = one AskUserQuestion call.** Never batch.
- **Recommend + WHY.** Every recommendation maps to an engineering principle
  or a section's stated concern. State the connection in one sentence.
- **Confidence calibration.** Rate each recommendation 1-10. Below 7 →
  preface with "Low confidence — verify first:" and describe what evidence
  would raise confidence.
- **Don't make code changes.** This skill reviews; it does not implement.
- **Anti-skip rule.** Every section runs. "No issues found" is acceptable;
  silence is not.

---

## Strings catalog key anchors

| Key | Used in |
|-----|---------|
| `prc.phase0.target_pitch_question` | Phase 0.1 |
| `prc.phase0.system_audit_summary` | Phase 0.2 |
| `prc.phase0.landscape_findings` | Phase 0.5 |
| `prc.phase1.scope_locked` | Phase 1F exit |
| `prc.phase1.alternatives_required` | Phase 1C-bis (refusal if user wants to skip) |
| `prc.phase2.section_intro_template` | Phase 2 (per section) |
| `prc.phase2.section_no_issues` | Phase 2 (per section, when nothing found) |
| `prc.phase3.trigger_summary` | Phase 3 |
| `prc.phase3.pitch_supersede_recommendation` | Phase 3.1 |
| `prc.phase3.adr_authoring_recommendation` | Phase 3.2 |
| `prc.phase4.verdict_question` | Phase 4.1 |
| `prc.phase4.review_note_written` | Phase 4.2 |
| `prc.phase4.handoff_to_plan_review_eng` | Phase 4.3 |
| `prc.refuse.spec_only_repo` | Preconditions |
| `prc.refuse.no_pitch` | Preconditions |
| `prc.warn.no_design_note` | Preconditions / Phase 0.1 |
| `prc.critical.one_issue_one_question` | Critical rules reminder |

Plus shared `common.*` keys.

---

## Supporting files

- **`sections.md`** — detailed prompts and output requirements for all 11
  Phase 2 sections. Read before Section 1 begins.
- **`nuclear-scope-rubric.md`** — Phase 1 question banks, mode-selection
  default matrix, and worked examples for the 4 modes (EXPANSION /
  SELECTIVE / HOLD / REDUCTION). Read before Phase 1A begins.
- **`templates/error-rescue-map.md`** — Section 2 output table template.
- **`templates/data-flow-diagram.md`** — Section 1 ASCII diagram template
  with happy / nil / empty / error paths.

All plugin-bundled at `${CLAUDE_PLUGIN_ROOT}/plan-review-ceo/`.
