---
name: design
description: Lightweight pre-implementation skill for the immutable SDD flow. After a pitch is authored (in spec or single repo) or the user explicitly opts into a no-pitch refactor/internal-work path, this skill confirms which pitch is being implemented (or acknowledges the no-pitch path), captures app-side context the pitch lacks, and writes a transient context note for the plan-review skills. Does NOT generate a design artifact — the pitch is the design artifact in immutable-prd mode. Triggers - "/immutable:design", "디자인 단계", "pitch 확인", "구현 준비".
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
license: MIT
---

# /immutable:design — Pitch confirmation + app-side context capture

In immutable-prd mode the pitch (in the spec repo, or in a `pitches/` subtree
for single-repo) is the canonical design artifact. This skill is the
**lightweight bridge** between pitch authoring and review:

1. Confirm which pitch this app-side work implements.
2. Capture the app-specific context that the pitch could not include
   (which module, hidden path, activation state, dependent features).
3. Write a transient note that the plan-review skills will read.

**HARD GATE**: this skill does NOT write a design artifact. The pitch is the
design artifact. Writing any `design-*.md` outside `.claude/immutable/design/`
would create drift. Phase 4 of this skill writes only one transient note at
`.claude/immutable/design/{slug}.md`.

## Strings catalog & locale

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml`.
`team_language` comes from `.immutable-prd/config.yml` (default: `ko`).

Per-string fallback:

1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit `common.fallback_warning`)
3. Hardcoded last-resort English in this SKILL.md

## Engineering principles

- **Boil lakes, flag oceans.** Capture complete context now; "we'll figure it
  out during review" creates re-work.
- **Search before building.** Map the existing patterns and files this work
  will touch before walking into review.
- **User sovereignty.** Recommend, then confirm. The user knows constraints
  the codebase doesn't.

## Preconditions

1. `.immutable-prd/config.yml` exists, reachable via walk-up from `$PWD`.
   Refuse with `common.refuse_legacy_mode` otherwise.
2. `repo_mode` is `single-repo` or `two-repo-app` (this skill runs on the app
   side). For `two-repo-spec`, refuse with `design.refuse.spec_only_repo` —
   the design step happens in the implementation repo, not the spec repo.
3. At least one pitch file must be reachable (in the spec repo's pitches
   directory or this repo's pitches subtree).

## SDD mode detection

```bash
source "${CLAUDE_PLUGIN_ROOT}/scripts/sdd_mode_detect.sh"
```

Refuse with `common.refuse_legacy_mode` if `SDD_MODE != immutable-prd`.

If `IMMUTABLE_PRD_REPO_MODE == two-repo-spec`, render
`design.refuse.spec_only_repo` and abort.

If on a protected branch (main / master / develop), render
`common.protected_branch_warn` once. Continue.

## Invocation

```
/immutable:design
```

Optional free-text initial context:

```
/immutable:design implementing the new review-request flow from cart pitch
```

Free-text is captured as a Step 1 starting hint when locating the pitch.

---

## Overall Process (4 steps)

```
Step 1: Pitch confirmation         — which pitch (or none — refactor)?
Step 2: Existing code exploration  — git log + relevant files (5-min scan)
Step 3: App-side context capture   — info the pitch lacks
Step 4: Handoff                    — transient note + recommend plan-review-ceo
```

---

## Step 1 — Pitch confirmation

### 1.1 Locate candidate pitches

```bash
# Resolve pitches directory from the SPEC config (which equals primary in single-repo).
PITCHES_REL="$(grep '^pitches_path:' "$IMMUTABLE_PRD_SPEC_CONFIG" 2>/dev/null \
  | head -1 | awk '{print $2}')"
PITCHES_REL="${PITCHES_REL:-pitches/}"
SPEC_ROOT="$(dirname "$(dirname "$IMMUTABLE_PRD_SPEC_CONFIG")")"
PITCHES_DIR="$SPEC_ROOT/$PITCHES_REL"
echo "PITCHES_DIR=$PITCHES_DIR"
```

If `PITCHES_DIR` does not exist or contains no `*.md` files, render
`design.step1.no_pitches_found` and ask the user whether to proceed in
"refactor" mode (Step 1.4 alternative path) or invoke `/immutable:prd` first.

### 1.2 List active (non-deprecated) pitches

```bash
# Scan for pitches with `deprecated: false` in frontmatter.
find "$PITCHES_DIR" -name '*.md' -not -name 'TEMPLATE.md' -not -name 'README.md' \
  -exec grep -L '^deprecated: true' {} \; 2>/dev/null
```

Surface the list to the user via `design.step1.pitch_picker_question`. Include
the pitch path (relative to the spec repo) and the pitch's frontmatter `domain:`
for each candidate. The user picks by number or path.

### 1.3 Read the chosen pitch

Read the chosen pitch file end-to-end. Confirm with the user via
`design.step1.pitch_confirmation` that the pitch summary matches the
intended work. If the pitch is stale (e.g., scope has shifted since
authoring), recommend a pitch supersede via `/immutable:prd` BEFORE
proceeding to Step 2.

### 1.4 Refactor mode (no pitch)

If the user explicitly opts into "no-pitch" path (internal refactor, infra
work, etc.), render `design.step1.refactor_mode_acknowledged` and proceed
to Step 2. The transient note in Step 4 records "no pitch — internal work".

---

## Step 2 — Existing code exploration (≤5 minute scan)

```bash
git log --oneline -30 2>/dev/null || true
git diff --stat 2>/dev/null || true
```

Search the codebase for related patterns, existing abstractions, and naming
conventions in the area the pitch (or the user's free-text) describes.

Identify and capture:

1. **Files most likely touched** — 3 to 8 files, with one-line role description each.
2. **Existing abstractions to reuse** — view models, services, patterns already
   solving part of the problem.
3. **Existing tests** — what coverage exists for the affected area, and what
   the conventions look like.

Do NOT propose changes to these files yet. Step 2 is observational only.

---

## Step 3 — App-side context capture

The pitch describes WHAT to build. Step 3 captures **what the pitch could
not specify**:

### 3.1 Activation status

Ask via `design.step3.activation_question`:

- Which version / when does this become user-visible?
- What hidden paths or feature flags gate it before launch? Capture exact
  identifiers.
- What metric / approval / date triggers the live flip?

The pitch may already cover some of this (in the optional `Open UX questions`
section) — read that first, then ask only what is unclear or missing.

### 3.2 Dependent features

Ask via `design.step3.dependencies_question`:

- What other features in the app depend on the same data, screen, or service?
- Are any of those features in active development on a different branch?
- Will this work block or be blocked by another feature's ship date?

### 3.3 Module placement

Ask via `design.step3.module_question`:

- Which module / package owns this work? (Be specific — e.g., `lib/cart/` not
  "cart")
- Are there cross-module dependencies the pitch doesn't surface?
- Does this introduce a new module? If so, what's its boundary contract?

### 3.4 Capture only what the pitch lacks

Do not duplicate what the pitch already states. The transient note in Step 4
should be **delta-only** — context that is not in the pitch.

---

## Step 4 — Handoff

### 4.1 Compute the output path

```bash
mkdir -p .claude/immutable/design
FEATURE_SLUG="${FEATURE_SLUG:-$(git branch --show-current 2>/dev/null | tr '/' '-' || echo "no-branch")}"
OUT=".claude/immutable/design/${FEATURE_SLUG}.md"
echo "OUTPUT_PATH: $OUT"
```

### 4.2 Render the handoff template

The template lives at `handoff-template.md` in this skill's directory. Read
it now and render with the captured values:

- `{title}` — short feature name (or "Refactor: {area}" in refactor mode)
- `{iso_date}` — today's ISO 8601 date
- `{branch}` — current branch
- `{pitch_path}` — relative pitch path inside the spec repo, OR "(none — refactor)"
- `{pitch_domain}` — pitch frontmatter `domain:` value, OR "_internal"
- `{pitch_summary}` — 2-3 sentence summary of the pitch content
- `{files_to_touch}` — Step 2.1 list with one-line roles
- `{existing_to_reuse}` — Step 2.2 list of abstractions and patterns
- `{activation}` — Step 3.1 capture (version, hidden paths, live triggers)
- `{dependencies}` — Step 3.2 capture
- `{module_placement}` — Step 3.3 capture
- `{open_questions}` — anything Step 3 surfaced that needs user / team input
  before review. If none, write "None — proceed to plan-review."

### 4.3 Write atomically

Use the Write tool to land the rendered handoff at `$OUT`. Verify the file
exists. Render `design.step4.note_written` with the path.

After the localized confirmation, emit a single machine-parseable marker line
on its own line. The marker format is `DESIGN_NOTE_WRITTEN: <path>` — exactly
this prefix (English literal regardless of `team_language`), one space, then
the value of `$OUT` (e.g.,
`DESIGN_NOTE_WRITTEN: .claude/immutable/design/cart-checkout.md`).

Downstream consumers (auditors, follow-up skills, CI checks) grep for
`^DESIGN_NOTE_WRITTEN: ` to verify this skill (not a manual write-around)
produced the note. Absence of the marker is a tell that the note was composed
outside the skill.

### 4.4 Recommend next skill

Render `design.step4.handoff_to_plan_review_ceo` with:

- The transient note path (`$OUT`)
- The pitch path (`$PITCH_PATH`)
- The current `IMMUTABLE_PRD_REPO_MODE` (so the user knows whether
  `/immutable:plan-review-ceo` runs in this same repo or requires a switch)

---

## Strings catalog key anchors

| Key | Used in |
|-----|---------|
| `design.step1.pitch_picker_question` | Step 1.2 |
| `design.step1.pitch_confirmation` | Step 1.3 |
| `design.step1.no_pitches_found` | Step 1.1 |
| `design.step1.refactor_mode_acknowledged` | Step 1.4 |
| `design.step3.activation_question` | Step 3.1 |
| `design.step3.dependencies_question` | Step 3.2 |
| `design.step3.module_question` | Step 3.3 |
| `design.step4.note_written` | Step 4.3 |
| `design.step4.handoff_to_plan_review_ceo` | Step 4.4 |
| `design.refuse.spec_only_repo` | Preconditions |

Plus shared `common.*` keys: `common.refuse_legacy_mode`,
`common.protected_branch_warn`, `common.fallback_warning`.

---

## Log learning to project memory (mandatory final step)

Before returning control to the user (success **or** abort), append one learning entry to the project store. Best-effort — if `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is unavailable, the guard exits silently and never blocks the flow.

Pick ONE branch below based on outcome and substitute the placeholders (`<pitch-basename>`, `<N>`, `<reason>`, etc.) with concrete values before running. For refactor mode (no pitch), use the literal `internal` for `<pitch-basename>` so the KEY remains grep-stable.

```bash
LH="${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh"
[ -x "$LH" ] || exit 0
SLUG=$("$LH" slug)

# === On success (transient note written) ===
TYPE=pattern; SOURCE=observed; CONF=7
KEY="design-${SLUG}-<pitch-basename>"   # e.g. design-skills-feature-x; refactor mode → design-${SLUG}-internal
INSIGHT="<one sentence summarising app-side context decisions: activation, dependencies, module — pick what matters most; ≤200 chars, no credentials>"
FILES='[".claude/immutable/design/<feature-slug>.md"]'

# === On abort (user cancels at Step 1 pitch picker, refuses Step 3 questions, etc.) ===
# TYPE=pitfall; SOURCE=observed; CONF=6
# KEY="design-aborted-${SLUG}"
# INSIGHT="Aborted at Step <N>: <reason>"
# FILES='[]'

"$LH" log "$(jq -nc --arg skill "immutable-design" --arg type "$TYPE" --arg key "$KEY" \
  --arg insight "$INSIGHT" --arg src "$SOURCE" --argjson conf "$CONF" --argjson files "$FILES" \
  '{skill:$skill,type:$type,key:$key,insight:$insight,confidence:$conf,source:$src,files:$files}' 2>/dev/null)" || true
```

---

## Important rules

- **Pitch is the design artifact.** Do not write a `design-*.md` outside
  `.claude/immutable/design/`. The transient note is delta context, not a
  rewrite of the pitch.
- **Step 1 may exit to `/immutable:prd`.** If the user discovers the pitch is
  stale or missing, recommend pitch supersede / authoring before proceeding.
- **Step 3 is gap-filling, not duplication.** If the pitch already covers an
  area, do not re-ask. Read the pitch carefully before Step 3.
- **No code changes.** Step 2 observes, Step 3 captures, Step 4 writes one
  transient note. Implementation happens after `/immutable:plan-review-ceo`
  → `/immutable:plan-review-eng` → (`/immutable:adr` if needed) → `/immutable:ship`.

---

## Supporting files

- **`handoff-template.md`** — markdown template for Step 4 transient note.

Plugin-bundled at `${CLAUDE_PLUGIN_ROOT}/design/`.
