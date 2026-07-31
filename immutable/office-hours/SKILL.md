---
name: office-hours
description: Heavy context-gather skill for ambiguous SDD requests. Forces premise challenge plus 3 implementation alternatives before writing anything. Output is a transient design-doc note intended as Stage 1.5 Context Intake input for `/immutable:prd`. Use when the user is exploring a new feature, the problem is fuzzy, or you sense they are about to pick option 1 without considering options 2 or 3. Triggers - "/immutable:office-hours", "오피스 아워", "premise challenge", "explore options".
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
license: MIT
---

# /immutable:office-hours — Premise challenge + 3 alternatives

This is the heaviest context-gather skill in the SDD flow. It produces a transient
design-doc note that the next skill (`/immutable:prd`) consumes during Stage 1.5
Context Intake. Use it when the request is fuzzy enough that picking the first
implementation idea would be premature.

**HARD GATE**: this skill writes ONLY one transient note at
`.claude/immutable/office-hours/{slug}.md`. It does NOT write code, scaffold files,
or invoke implementation skills. If the user asks for code during this skill, refuse
and remind them to finish the alternatives step first.

## Strings catalog & locale (v0.5 / S3)

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml` —
not embedded inline. SKILL.md refers to catalog keys via the pattern
``render `<key>` `` with single-brace `{placeholder}` substitution performed by
the skill.

**Locale resolution**: `team_language` comes from `.immutable-prd/config.yml`
(default: `ko`). Per-string fallback:

1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit one-line warning via `common.fallback_warning`,
   never silent)
3. Hardcoded last-resort English in this SKILL.md (plugin file corruption; emit
   warning and abort the stage)

See `../SCHEMA.md#strings-catalog-v05-s3` for the schema, responsibility split,
and key naming convention.

## Engineering principles

Apply throughout:

- **Boil lakes, flag oceans.** Prefer the complete option when it costs minutes
  more, not weeks.
- **Search before building.** Layer 1 (built-in / tried-and-true) → Layer 2
  (popular, scrutinize) → Layer 3 (first principles). Surface a "eureka"
  moment when conventional wisdom is wrong for this case.
- **User sovereignty.** Recommend, then let the user decide. Two LLMs agreeing
  is signal, not proof.
- **Generation-verification loop.** Never skip the user's verification step.

## Preconditions

1. `.immutable-prd/config.yml` exists and is reachable via walk-up from `$PWD`.
   If absent, render `common.refuse_legacy_mode` and abort.
2. `${CLAUDE_PLUGIN_ROOT}` is set by Claude Code when invoking plugin skills.
   If unset (rare), fall back to walking up from this skill's own location.
3. The skill writes to `.claude/immutable/office-hours/{slug}.md` only. It
   never commits, pushes, or modifies anything outside that path.

## SDD mode detection

Run this once at the start of the skill, before any phase logic:

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
```

The script exports `SDD_MODE`, `IMMUTABLE_PRD_CONFIG`, `IMMUTABLE_PRD_SPEC_CONFIG`,
`IMMUTABLE_PRD_APP_CONFIG`, `IMMUTABLE_PRD_REPO_MODE`, and `SDD_AMBIGUITY_FLAG`
into the caller's shell. See `../scripts/sdd_mode_detect.sh` header for the
full contract.

If `SDD_MODE != immutable-prd`, render `common.refuse_legacy_mode` and abort.

If `SDD_AMBIGUITY_FLAG == 1`, render `common.transient_namespace_hint` (informational
note), then surface the ambiguity to the user and proceed (`.claude/sdd-mode`
disambiguation is the user's call).

If the current branch is `main`, `master`, or `develop`, render
`common.protected_branch_warn` once. Continue regardless — the skill's only
write is a transient note, not source code, but the warning is informational.

## Invocation

```
/immutable:office-hours
```

Optional free-text initial context (in any language):

```
/immutable:office-hours add review request flow to the cart screen
```

Free-text is captured and surfaced in Phase 1 as the initial framing.

---

## Overall Process (5 phases)

```
Phase 1: Context Gathering          — git log, repo overview, mode question
Phase 2: Premise Challenge          — list premises, confirm each via AskUserQuestion
Phase 3: Alternatives Generation    — ≥3 approaches (Minimal / Ideal / Creative)
Phase 4: Design Doc Write           — one transient note under .claude/immutable/office-hours/
Phase 5: Handoff                    — recommend `/immutable:prd` next, mode-specific
```

Stop on user refusal at any phase. Partial output is forbidden — either Phase 4
writes the complete design doc or the skill aborts.

---

## Phase 1 — Context Gathering

Keep this short. The heavy lifting is Phase 2 and 3.

### 1.1 Repo probe

```bash
_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
_SLUG=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')
echo "BRANCH: $_BRANCH"
echo "SLUG: $_SLUG"
git log --oneline -30 2>/dev/null || true
git diff --stat 2>/dev/null || true
```

### 1.2 Skim the codebase

- Read `CLAUDE.md` if it exists. Skim `README.md` for project intent.
- Grep / Glob the codebase areas most relevant to the user's ask. Note 3-5
  files that will likely be touched.
- If `.claude/immutable/office-hours/{slug}.md` already exists, read the most
  recent one — you may be iterating on a prior premise check.

### 1.3 Mode question

Render `oh.phase1.mode_question` via AskUserQuestion. The 4 options drive
downstream prompting tone:

| Mode | Behavior |
|------|----------|
| `product` | New feature for users — full premise challenge, hardest scrutiny |
| `tooling` | Internal tooling / DX — premise challenge applied but lighter touch |
| `refactor` | Architecture change — focus on first-principles reasoning |
| `spike` | Exploration / learning — alternatives still required, premises lighter |

### 1.4 Context summary

Output one paragraph at the end of Phase 1 using the `oh.phase1.context_summary_template`
key:

> Here is what I understand about this project and the area you want to change: …

Do NOT proceed to Phase 2 until the user agrees the summary is accurate.

---

## Phase 2 — Premise Challenge (mandatory)

Before proposing any approach, list the premises the user's framing assumes.
Output as numbered statements; render each via `oh.phase2.premise_question_template`.

```
PREMISES:
1. [statement] — agree / disagree?
2. [statement] — agree / disagree?
3. [statement] — agree / disagree?
```

For each premise, consider:

- **Is this the right problem?** Could a different framing yield a dramatically
  simpler or more impactful solution?
- **What happens if we do nothing?** Real pain or hypothetical?
- **What existing code already partially solves this?** Map existing patterns
  found during Phase 1.
- **Distribution** (only if the deliverable is a new artifact — CLI, library,
  package, app): how do users get it? CI/CD pipeline? Release channel? Or
  explicitly deferred?

Use AskUserQuestion **once per premise** (one issue = one call, never batch).
If the user disagrees, revise the premise and loop.

When all premises are confirmed, render `oh.phase2.premises_locked` and proceed
to Phase 3.

---

## Phase 3 — Alternatives Generation (mandatory — at least 3)

Produce **3 distinct implementation approaches**. This is non-negotiable. One-option
designs skip the most important step.

### 3.1 Required composition

| Slot | What it must be |
|------|----------------|
| Approach A — Minimal viable | Fewest files, smallest diff, ships today. Ugly is OK. |
| Approach B — Ideal architecture | Best long-term trajectory. Elegant, extensible, more files touched. |
| Approach C — Creative / lateral | A meaningfully different framing — different abstraction, different entry point, or "what if the user didn't have to do anything?" |

**If you cannot generate Approach C, say so explicitly in the output.** Do not
fake a third option, and do not skip the attempt — the failure to find a
creative reframing is itself a useful signal.

### 3.2 Per-approach format

Render via `oh.phase3.approach_template`. Each approach captures:

```
APPROACH {letter}: {Name}
  Summary: 1-2 sentences
  Effort:  S / M / L / XL  (Claude-assisted effort, not human-team weeks)
  Risk:    Low / Med / High
  Pros:    2-3 bullets
  Cons:    2-3 bullets
  Reuses:  existing files / patterns it leverages from Phase 1
```

For detailed authoring guidance — what each slot is asking for, common pitfalls,
and worked examples — read `premise-rubric.md` in this skill's directory now.

### 3.3 Recommendation + choice

End Phase 3 with a single line via `oh.phase3.recommendation_template`:

```
RECOMMENDATION: Approach {X} because {one-line reason}.
```

Then call AskUserQuestion with `oh.phase3.choice_question`:

- A) Approve the recommended approach — proceed to Phase 4
- B) Pick a different approach — specify which
- C) Revise — my framing changed, regenerate alternatives
- D) None of these — start over from Phase 1

Do NOT proceed to Phase 4 without explicit user approval.

---

## Phase 4 — Design Doc Write

### 4.1 Compute the output path

```bash
mkdir -p .claude/immutable/office-hours
# Prefer a user-provided feature slug (asked early in Phase 1 if relevant);
# otherwise derive from the branch name.
source "${CLAUDE_PLUGIN_ROOT}/scripts/feature_slug.sh"
OUT=".claude/immutable/office-hours/${FEATURE_SLUG}.md"
echo "OUTPUT_PATH: $OUT"
```

### 4.2 Render the template

The output template lives at `design-doc-template.md` in this skill's directory.
Read it now and render with the captured values:

- `{title}` — short feature name
- `{iso_date}` — today's ISO 8601 date
- `{branch}` — current branch name
- `{mode}` — Phase 1 mode (`product` / `tooling` / `refactor` / `spike`)
- `{supersedes}` — prior `office-hours/{slug}.md` filename if iterating; omit
  the line if first time
- `{problem}` — Problem Statement (Phase 1 + Phase 2 framing)
- `{context}` — relevant code areas and existing patterns from Phase 1
- `{premises}` — confirmed premises from Phase 2 (numbered)
- `{approach_a}`, `{approach_b}`, `{approach_c}` — Phase 3 outputs (or
  "No meaningfully different third approach generated — {reason}" for C)
- `{recommended}` — chosen approach + rationale (2-4 sentences)
- `{files}` — list of files touched (Phase 1 list + new files the approach introduces)
- `{edge_cases}` — known edge cases and how the approach handles each
- `{distribution}` — only when a new artifact is being introduced; omit otherwise
- `{open_questions}` — anything unresolved after Phase 2 + 3

### 4.3 Write atomically

Use the Write tool to land the rendered template at `$OUT`. After write,
verify the file exists and emit `oh.phase4.design_doc_written` with the path.

If write fails (permissions, missing parent — but Phase 4.1 created the parent),
abort and surface the error.

---

## Phase 5 — Handoff

Branch on `IMMUTABLE_PRD_REPO_MODE` from the SDD detect step:

- **`single-repo`**: render `oh.phase5.handoff_immutable_prd_single`. Same repo
  hosts pitches and ADRs; the user can move directly to `/immutable:prd` without
  switching directories.
- **`two-repo-spec`**: PWD is the spec repo. Render `oh.phase5.handoff_immutable_prd_two_repo`
  with the spec config path. The user invokes `/immutable:prd` here.
- **`two-repo-app`**: PWD is the app repo. The pitch lives in the spec repo —
  render `oh.phase5.handoff_immutable_prd_two_repo` with the resolved
  `IMMUTABLE_PRD_SPEC_CONFIG` path and instruct the user to `cd` into the spec
  repo before invoking `/immutable:prd`. Attach the design-doc note path
  (`$OUT`) as the Stage 1.5 Context Intake input.

---

## Completion status

Before handing back to the user, state one of:

- **DONE** — design doc written, user approved Approach {X}. Render `oh.completion.done`.
- **DONE_WITH_QUESTIONS** — design doc written, but the Open Questions section
  is non-empty. Render `oh.completion.done_with_questions`. The user should
  resolve open questions in Phase 1.5 of `/immutable:prd`.
- **NEEDS_CONTEXT** — user did not answer all Phase 2 premises; design is
  incomplete. The transient note is NOT written. Render `oh.completion.needs_context`
  and abort.

## Important rules

- **Never start implementation.** This skill outputs one transient note. Not
  even scaffolding files. If the user asks for code, render `oh.refuse.write_during_oh`.
- **Questions ONE AT A TIME.** Never batch multiple prompts into one
  AskUserQuestion call.
- **3 alternatives, not 1 or 2.** If Approach C is genuinely unreachable, say
  so in the doc explicitly — don't fake a third option, but don't skip the attempt.
- **Premises gate Phase 3.** Do not generate alternatives until the user has
  agreed to the top 2-3 premises.
- **Phase 4 is atomic.** Either the doc lands at `$OUT` or the skill aborts.
  No partial writes.

---

## Strings catalog key anchors

The keys this skill consumes (defined in `strings.ko.yml` / `strings.en.yml`):

| Key | Used in |
|-----|---------|
| `oh.phase1.mode_question` | Phase 1.3 |
| `oh.phase1.context_summary_template` | Phase 1.4 |
| `oh.phase2.premise_challenge_intro` | Phase 2 entry |
| `oh.phase2.premise_question_template` | Phase 2 (per premise) |
| `oh.phase2.premises_locked` | Phase 2 exit |
| `oh.phase3.alternatives_intro` | Phase 3 entry |
| `oh.phase3.approach_template` | Phase 3.2 |
| `oh.phase3.recommendation_template` | Phase 3.3 |
| `oh.phase3.choice_question` | Phase 3.3 |
| `oh.phase4.design_doc_path_announce` | Phase 4.1 |
| `oh.phase4.design_doc_written` | Phase 4.3 |
| `oh.phase5.handoff_immutable_prd_single` | Phase 5 (single-repo) |
| `oh.phase5.handoff_immutable_prd_two_repo` | Phase 5 (two-repo) |
| `oh.completion.done` | Completion |
| `oh.completion.done_with_questions` | Completion |
| `oh.completion.needs_context` | Completion |
| `oh.refuse.write_during_oh` | Important rules |

Plus shared `common.*` keys: `common.refuse_legacy_mode`,
`common.protected_branch_warn`, `common.fallback_warning`,
`common.handoff.next_skill`.

---

## Supporting files

- **`design-doc-template.md`** — markdown template for Phase 4 output.
  Read it just before rendering in Phase 4.2.
- **`premise-rubric.md`** — authoring guide for Phase 3 alternatives
  (what each slot is asking for, common pitfalls, worked examples).
  Read it just before generating alternatives in Phase 3.

Both files are plugin-bundled at `${CLAUDE_PLUGIN_ROOT}/office-hours/`.
