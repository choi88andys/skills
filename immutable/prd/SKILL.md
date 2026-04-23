---
name: prd
description: Guided authoring for immutable, append-only PRD/pitch files. Conducts a grill-me style interview with context intake, domain-language check, multi-persona adversarial review, and a 90% completeness gate before writing any file. Use when a team needs to produce new spec/PRD content or version-update existing ones in an append-only SDD repo. Triggers - "/immutable:prd", "pitch 작성", "스펙 작성", "PRD 추가", "피치 만들어".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch
---

# /immutable:prd — Guided Immutable PRD Authoring

Interactively author an append-only pitch-style PRD file. Enforces format, structure, scope, and domain language. Generates the file only when the answer set passes a 90% completeness gate.

## Strings catalog & locale (v0.5 / S3)

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml` — not embedded inline. SKILL.md refers to catalog keys via the pattern ``render `<key>` `` with single-brace `{placeholder}` substitution performed by the skill.

**Locale resolution**: `team_language` comes from `.immutable-prd/config.yml` (default: `ko`). Every render follows this fallback:

1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit one-line warning via `common.fallback_warning`, never silent)
3. Hardcoded last-resort English in this SKILL.md (plugin file corruption; emit warning and abort the stage)

See `../SCHEMA.md#strings-catalog-v05-s3` for the schema, responsibility split (catalog vs. profile), and key naming convention.

## Profile Resolution (v0.5+)

The skill is **profile-aware** in v0.5: section headings, the gate threshold, persona checks, identifier-detection regex, and filename rules are sourced from a profile YAML rather than hardcoded.

### Resolution order

1. If `.immutable-prd/config.yml` declares `profile: <path>` (v3 configs only) AND the file exists → load it.
2. Else load the bundled default matching `team_language` from `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`.
3. If no matching locale profile exists → fall back to `default-en.yml` with a one-line warning.

### Backward compatibility (zero-action migration)

`version: 2` configs (without `profile:`) continue to work unchanged — the skill auto-loads the bundled default profile matching `team_language`. Behavior is identical to v0.4. Run `/immutable:migrate` (S4) when ready to graduate to v3.

### Profile fields consumed by /immutable:prd in v0.5

| Profile field | Where used |
|---|---|
| `sections[].heading` | Stage 6 body assembly (rendered in pitch file) |
| `sections[].id` / `required` / `min_items` / `description` | Stage 2 interview branches + Stage 6 required-sections guard |
| `sections[id=user_stories].structure` (v0.5.3+) | Stage 2 Branch B completion criterion + Stage 6 pre-write structure guard. `per_story_grouped` (default) requires each story in a `### ` sub-section carrying a GWT triple + ≥1 bracketed normative line; `consolidated` accepts a single GWT list + single normative list under the H2 (v0.5.2 shape). |
| `normative_keywords[].token` / `meaning` | Stage 2 Branch C bracket vocabulary |
| `identifier_patterns[].regex` / `hint` | Stage 3 code-identifier detection |
| `vague_words[].regex` / `hint` (v0.5.3+) | Stage 3 vague-word detection (skill-side only; not enforced by the CI validator) |
| `naming.filename_pattern` / `slug_case` / `forbidden_slug_patterns` | Stage 6 filename validation |
| `feature_flag.*` | Stage 2 Branch F (key prefix, states, fallback) |
| `domain_allowlist.source` / `reserved_domains` | Stage 1 / Stage 3 domain checks |
| `gate.total` / `pass_threshold` / `criteria` | Stage 5 90% completeness gate |
| `gate.unresolved_tag` | Stage 2/5 unresolved-answer tag — literal value sourced from the active profile per locale |
| `gate.reject_on_unresolved` | Stage 5 hard-block flag |

Inline profile strings (e.g., `sections[i].heading`, `personas[i].name`) remain rendered from the active profile. Stage prompts (intent questions, refusal messages, handoff blocks) are sourced from the strings catalog per the "Strings catalog & locale" section above.

## Preconditions

The skill assumes the working directory is the root of a pitch spec repo with the following convention:

```
<repo-root>/
├── pitches/
│   ├── README.md        # contains an allowed-domains table under a locale-specific "Allowed Domains" heading with rows `| `<domain>` | <description> |`
│   ├── TEMPLATE.md      # pitch body template
│   └── <domain>/
│       └── YYYY-MM-DD-<kebab-slug>.md
└── CONTRIBUTING.md      # rules SSoT
```

Each pitch file requires YAML frontmatter:

```yaml
---
domain: <name>              # must match parent directory
supersedes: <filename|null> # previous active file in the same domain
deprecated: false           # flipped to true when a new version supersedes
---
```

If the repo uses a different structure, fork and adapt the SKILL.md. Config file overrides are out of scope for v0.x.

The skill only **writes** the file. It never commits or pushes. The user reviews the generated file and commits manually.

## Invocation

```
/immutable:prd
```

Optional free-text argument for initial context (the user may type in any language):
```
/immutable:prd add auto-modal to notifications
```

---

## Overall Process (6 Stages)

```
Stage 1: Intent Routing           — classify new / update / deprecate + confirm domain
Stage 1.5: Context Intake (opt.)  — accept curated external context (Figma/Notion/local/Slack)
Stage 2: Interview                 — one question at a time, with a recommended answer
Stage 3: Domain Language Check    — code identifier detection, terminology drift
Stage 4: Adversarial Review       — four personas each surface at least one gap
Stage 5: 90% Completeness Gate    — 7-criterion checklist; generate file only if passed
Stage 6: File Generation & Handoff
```

**Stop immediately on any stage failure.** Do not write the file until all stages pass. Loop back to Stage 2 when Stage 3 or 4 finds issues.

---

## Stage 1 — Intent Routing

### 1.1 Gather initial context

If the user did not pass an argument, ask exactly once using `prd.stage1.intent_question` (no substitutions).

### 1.2 Environment scan (parallel)

Use Bash + Glob + Read to collect:

1. **Resolve config + profile** (added v0.5):
   - Walk up from CWD to find `.immutable-prd/config.yml` (use `scripts/find_config.sh`).
   - If config absent: prompt the user to run `/immutable:init` first, or fall back to the inferred-defaults path documented in `../SCHEMA.md`.
   - Read `team_language`, `profile:` (if v3), and other config fields.
   - Load profile per the resolution order in **Profile Resolution** above. Cache the parsed profile for the rest of the session.
2. Confirm `pitches/` exists in CWD (or at the configured `pitches_path`). If not, stop by rendering `prd.stage1.no_pitches_dir` (no substitutions).
3. Read `pitches/README.md` — extract domain allowlist from the allowed-domains table (rows matching `` | `<name>` | ``). Use `profile.domain_allowlist.source` if it differs from the default `pitches/README.md`.
4. For each allowlisted domain directory, scan `*.md` frontmatter to find the active pitch (`deprecated: false`, not `README.md`, not `TEMPLATE.md`).

### 1.3 Classify intent

| Signal | Intent |
|---|---|
| New feature/flow, fits no allowlisted domain | `new-domain` (requires allowlist update) |
| New feature/flow, fits an existing domain with no prior pitch | `new` (`supersedes: null`) |
| Modification/addition/removal within an existing active pitch's scope | `update` (copy active, revise, flip old deprecated) |
| "No longer provided" with no replacement | `deprecate-only` (flip active's `deprecated` flag) |

### 1.4 Confirmation (mandatory)

Always confirm intent and target before proceeding. Render `prd.stage1.confirmation` with:

- `{domain}` — the confirmed domain name (e.g., `notice`)
- `{intent_desc}` — lookup of the matching `prd.intent_desc.<intent>` key (`new` / `new_domain` / `update` / `deprecate_only`)
- `{base_file}` — relative path to the active pitch being superseded, or `common.placeholder.none` for a new pitch

If classification is ambiguous, ask rather than guess.

### 1.5 New-domain flow

If `new-domain`:

1. Explain the gate: domain must be added to `pitches/README.md` after lead approval.
2. Ask whether lead approval is obtained. If not, stop.
3. If approved, ask for the proposed slug (English kebab-case).
4. Detect near-duplicates against existing domains (Levenshtein distance ≤ 2 → warn).
5. Add the row to the allowlist, create the directory, proceed with `supersedes: null`.

### 1.6 Deprecate-only flow

Skip the interview. Request a reason string. Flip the target file's `deprecated: false` → `true` (single-line change only). Jump directly to Stage 6.

---

## Stage 1.5 — Context Intake (Optional)

After intent is confirmed, ask whether the user has supporting materials. This stage is **opt-in** — the user can skip.

### Prompt (verbatim required)

Render `prd.stage1_5.intake_prompt_verbatim` **verbatim** — do not paraphrase, shorten, reorder, or drop guardrail lines (quantity caps, rejection notices, example URLs). The verbatim contract applies to the rendered catalog value for the active locale; each locale's catalog owns its own verbatim translation. Do NOT rewrite the value at render time.

### Filtering (anti-dumping)

Before processing, validate inputs. For each violation, render the matching catalog key:

| Signal | Refusal key |
|---|---|
| File or document > 5,000 words | `common.anti_dumping.file_too_large` |
| Figma project / file root URL (no `node-id` query param) | `common.anti_dumping.figma_root_url` |
| More than 3 Figma node URLs | `common.anti_dumping.figma_too_many` |
| Notion workspace root URL or DB view URL | `common.anti_dumping.notion_root_url` |
| > 10 pages total across attachments | `common.anti_dumping.too_many_pages` |
| Pasted text > 30 lines | `common.anti_dumping.pasted_too_long` |
| URL to authenticated service without MCP integration | `common.anti_dumping.auth_url` |

Do not proceed with raw dumps. Distillation is the user's responsibility; interpretation is the skill's.

### Summarize-and-confirm loop

For each accepted attachment:

1. Fetch/read the content (WebFetch for public URLs, Read for local files).
2. Extract 5–7 bullet points of facts relevant to the pitch under authorship.
3. Show the bullet summary to the user, then ask using `prd.stage1_5.summary_confirmation` (no substitutions).
4. Apply user corrections to the summary.
5. Store the **corrected summary only** as interview context. Discard the raw dump.

### Scope alignment

After all attachments are summarized, ask using `prd.stage1_5.scope_alignment` (no substitutions). This prevents Figma-driven or Notion-driven spec where the source dominates instead of serving.

### Skip path

If the user replies with a negative/empty response (e.g., `없음`, `none`, `no`, `skip`, empty line), proceed directly to Stage 2. Do not pressure for attachments.

---

## Stage 2 — Interview (grill-me pattern)

### Principles

- **One question at a time.** Wait for the answer before the next.
- **Always provide a recommended answer** with each question, derived from the active pitch, analogous patterns in other domains, industry defaults, or the confirmed Stage 1.5 summary. The user can accept, edit, or reject.
- **Forbid speculation.** When the user cannot answer or the answer is vague, record a tag in the format `<profile.gate.unresolved_tag> — <question summary>`. The tag literal comes from the active profile (one per locale). Never fill gaps with plausible-sounding content.
- **Prefer codebase exploration over asking** when an answer is already present.

### Question Branches (fixed order)

#### Branch A — Background and Problem

Ask about:
- Why is this pitch needed? (user request / business decision / existing bug / compliance)
- What is the current state? (nothing / partial / exists differently)
- What specific gap does this pitch close?

**Completion criterion**: a third party can understand "why this pitch is needed" in ≤3 sentences.

#### Branch B — User Stories (Given/When/Then)

Walk the user flow from start to end. For each branch point elicit:
- **Given**: user's state
- **When**: user action (tap, input, swipe, etc.)
- **Then**: system response

At least one happy path + at least one alternate/error branch. Minimum 2 GWT blocks, ideally 3.

**Structure (v0.5.3+)**: consult `profile.sections[id=user_stories].structure` (default `per_story_grouped`):

- `per_story_grouped` — each story/flow carries a short imperative title that becomes its `### ` sub-section. During authoring, collect for every sub-section: the title, a GWT triple (when the sub-section is a user flow), AND ≥1 bracketed normative keyword line from Branch C (`[MUST]` / `[MUST NOT]` / `[SHOULD]` / …) that binds requirements to that sub-section. A sub-section MAY be a cross-cutting group (e.g., "result-code handling across all registration channels") in which case the GWT triple can be omitted — but the bound normative line is still required. Do NOT defer normative elicitation to a post-hoc consolidated list; the binding must happen inside each sub-section.
- `consolidated` — collect GWT blocks and normative lines independently; Stage 6 renders them as two separate lists under the H2. Choose this mode only when the profile explicitly sets `structure: consolidated`.

**Completion criteria**:
- Every branch point expressed as a GWT triple.
- Under `per_story_grouped`: every sub-section has ≥1 bound normative line. GWT triples live inside their owning sub-section (or are omitted for cross-cutting normative-only groups). If any sub-section lacks a bound normative line, loop back and elicit before advancing.

#### Branch C — Normative Keywords

For each GWT, extract binding statements using the bracket vocabulary from `profile.normative_keywords`. The bundled defaults are RFC 2119:

- `[MUST]` — required, no exceptions
- `[MUST NOT]` — forbidden
- `[SHOULD]` — recommended; justified exceptions allowed
- `[SHOULD NOT]` — discouraged
- `[MAY]` — optional

When the profile overrides `normative_keywords`, render the team's tokens instead of these defaults. Token + meaning come from `profile.normative_keywords[].token` and `.meaning`.

**Completion criterion**: at least 3 bracketed normative statements across the body (matches `profile.gate.criteria[id=normative_minimum]`).

#### Branch D — Edge Cases

Offer a checklist of common candidates:

| Candidate | Applicable? |
|---|---|
| No network connection | Y/N |
| Empty data (empty list) | Y/N |
| Missing permission / expired auth | Y/N |
| Concurrency conflict | Y/N |
| External app missing | Y/N |
| Extreme input (max length, unicode, RTL) | Y/N |

For each applicable case, elicit the expected handling.

**Completion criterion**: at least 2 edge-case rows with explicit handling.

#### Branch E — No-gos (Out of Scope)

Elicit at least one explicit exclusion. Each no-go must be classified as:
- **Deferred** — split into a separate pitch
- **Intentionally not provided** — explain why
- **Outside this pitch's scope** — handled by another domain

**Completion criterion**: at least 1 no-go with a reason or handoff target.

#### Branch F — Feature Flag (optional)

Ask whether a feature flag is needed. If yes, capture:
- **Key**: `ff_<slug>`
- **States**: `deployed` / `hidden`
- **Initial state**: usually `hidden` → promote to `deployed` after internal validation
- **Fallback behavior**: UX in `hidden` state

Apply the **Goldilocks test**: "Can this entire feature be toggled on/off by a single flag?" If no, the pitch is too large and must be split.

---

## Stage 3 — Domain Language Check

### Checks

1. **Code identifier detection** via the regex list in `profile.identifier_patterns`. Bundled defaults (default-ko / default-en):
   - camelCase: `\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b`
   - snake_case: `\b[a-z]+_[a-z_]+\b`
   - PascalCase: `\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b`
   - file paths: `\b[a-z]+/[a-z_/]+\.(dart|swift|ts|js|py|kt)\b`

   Teams override via a custom profile (e.g., add Kotlin object literals, Swift enum cases). Use the `hint` field from `profile.identifier_patterns[]` for the warning message.

   On hit, render `prd.stage3.identifier_warning` with `{identifier}` = the matched token and `{hint}` = the profile's `identifier_patterns[].hint` for the matching pattern.

2. **Vague-word detection (v0.5.3+)** via the regex list in `profile.vague_words` (bundled default covers Korean hedge terms `적절히`, `자연스럽게`, `충분히`, `가능한`, `합리적`, `일반적`, `최대한`, `필요에 따라`, `상황에 맞게`, `안전하게`, `부드럽게`, and English `appropriate(ly)`, `reasonabl(e|y)`, `natural(ly)`, `sufficient(ly)`, `as needed`, `etc.`/`and so on`, `smooth(ly)`, `safe(ly)`, `general(ly)`).

   On hit, render `prd.stage3.vague_word_warning` with `{word}` = the matched phrase and `{line}` = the surrounding sentence (≤120 chars). The warning asks the author to replace with a concrete value or confirm the ambiguity is intentional. Loop back to the relevant Branch (B for story text, C for normative) per hit.

   This check is skill-side only — not enforced by `validate_docs.py` (semantic noise is tolerable at authoring time but would break CI predictability).

3. **Inline-paragraph normative detection (v0.5.3+, `per_story_grouped` only)** — scan the user-stories section slice. For any bracketed token from `profile.normative_keywords[].token` (`[MUST]`, `[MUST NOT]`, …) that appears on a line which is neither a bullet (`^\s*[-*]\s+`) nor a heading, render `prd.stage3.inline_normative_warning` with `{line}` = the offending line. This catches the Korean-drift pattern where some models embed `**[MUST]**` mid-sentence.

   On hit, loop back to Branch B/C with instruction to re-write as a bullet list item.

4. **Terminology consistency** against existing active pitches. If a new word is introduced for an already-named concept, call it out.

5. **Frontmatter `domain` consistency** with parent directory and allowlist.

### Failure handling

On violation, return to Stage 2 for the specific branch. Do not advance to Stage 4 until all code identifiers are removed, all vague words are resolved (replaced or user-confirmed), and the inline-normative pattern is cleaned.

---

## Stage 4 — Adversarial Review (4 Personas)

Each persona MUST surface at least one gap. "Looks good" is prohibited. Beyond the minimum of one, continue surfacing every non-trivial gap the persona identifies; do NOT artificially cap per-persona output at one finding. Gaps raised by 2+ personas are promoted one severity level.

### Persona 1 — New Engineer

Question: "Could I implement this pitch with only this document?"

Apply the checks from `profile.personas[id=new_engineer].checks[]` against the drafted body. The profile lists the specific anti-patterns (e.g., vague directives, under-specified GWT blocks, hidden cross-domain dependencies) in the active locale.

### Persona 2 — Customer Support

Question: "What does the user see in every edge case?"

Apply the checks from `profile.personas[id=customer_support].checks[]`. The profile lists coverage areas (network / permission / external-dependency failure modes, error messaging, excessive hand-wave language) in the active locale.

### Persona 3 — Product Lead

Question: "Is this pitch at Feature scale?"

Check for:
- Single-flag toggleability
- Completion within 2–6 weeks
- Epic-level content that should be split
- Overlap or conflict with existing active pitches

### Persona 4 — Quality Auditor (v0.5.3+)

Question rendered from `profile.personas[id=quality_auditor].question` (default: "Can this pitch be implemented and verified against measurable criteria, with no clauses requiring subjective judgment?").

Apply the checks from `profile.personas[id=quality_auditor].checks[]`. The bundled default covers:
- Concrete-value density — each normative carries numbers/timeouts/thresholds/UI specs rather than qualitative adjectives.
- Context-vague hedge phrases that passed the Stage 3 regex but remain ambiguous in the surrounding sentence.
- Pass/fail decidability of every GWT Then (can a test or reviewer give a binary verdict without subjective judgment?).
- Missing-subject or passive-voice sentences that hide the responsible actor.
- Depth-to-complexity balance — thin MUST/edge-case counts in a pitch that drew on substantial Stage 1.5 intake is a drift signal.

This persona complements the Stage 3 regex-based vague-word scan (which is deterministic and shallow) with semantic judgment. The two layers are expected to overlap; overlap is a feature, not redundancy.

### Output

Present findings as a numbered list labeled by persona name (from `profile.personas[i].name`). Format per row: `[<persona.name>] <n>. <finding text>`.

For each finding, offer three options (rendered in the active locale via profile values or skill-level logic — no inline Korean/English prose in this SKILL.md):
- Accept → return to Stage 2 for revision
- Move to No-go → add to Branch E explicitly
- Reject → record counter-reasoning; proceed

---

## Stage 5 — 90% Completeness Gate

### Checklist (7 criteria)

| # | Criterion | Pass Condition |
|---|---|---|
| 1 | Background is clear | Third party can summarize intent in ≤3 lines; no `<profile.gate.unresolved_tag>` tags remain |
| 2 | User stories in GWT | At least 2 GWT blocks, all structurally complete |
| 3 | Normative keywords | At least 3 bracketed statements across the body |
| 4 | Edge cases table | At least 2 rows with explicit handling |
| 5 | No-gos defined | At least 1 item with reason or handoff |
| 6 | Zero code identifiers | Stage 3 passed cleanly |
| 7 | Feature-scale scope | Passes the single-flag toggle test |

### Judgment

- **6 or 7 of 7 pass** → proceed to Stage 6
- **Fewer than 6 pass** → refuse generation; loop to the relevant branch
- **Any `<profile.gate.unresolved_tag>` tag remains anywhere** → refuse generation regardless of count

### Refusal message

Render `common.gate.refusal_template` with:

- `{criteria_rows}` — newline-joined per-criterion rows built from `common.gate.row_template` with `{n}` = 1..7, `{label}` = `profile.gate.criteria[i].label`, `{status}` = `common.gate.status_pass` or `common.gate.status_fail` (optionally appended with a short reason for failures in the active locale)
- `{next_action}` — one-line actionable next step in the active locale, derived from which criteria failed (identify the failing branches by `profile.gate.criteria[i].id` and ask the user to address them)

---

## Stage 6 — File Generation and Handoff

### Determine filename and path

- **new / new-domain / update**:
  - Path: `pitches/<domain>/YYYY-MM-DD-<slug>.md`
  - `YYYY-MM-DD`: today's date (use `date +%Y-%m-%d`)
  - `<slug>`: English kebab-case derived from the title; confirm with the user
- **update** additionally: flip the previous active file's `deprecated: false` → `true`. Only that one line.
- **deprecate-only**: flip only. No new file.

### Frontmatter

```yaml
---
domain: <name>
supersedes: <previous-filename | null>
deprecated: false
---
```

### Body assembly

Start from `pitches/TEMPLATE.md`. Populate sections from interview answers, using **section headings from `profile.sections[].heading`** (looked up by `id`, rendered from the active profile — never hardcoded):

- `# <title>` — user-confirmed title
- `## <profile.sections[id=background].heading>` — Branch A content
- `## <profile.sections[id=user_stories].heading>` — Branch B + Branch C content (internal shape controlled by `structure`, see below)
- `## <profile.sections[id=edge_cases].heading>` — Branch D content
- `## <profile.sections[id=no_gos].heading>` — Branch E content
- `## <profile.sections[id=feature_flag].heading>` — Branch F (only when used)

Section order MUST follow the order of entries in `profile.sections`. Skill consults `profile.sections[i].id` to know which interview branch's content fills each section.

#### User-stories section internal shape (v0.5.3+)

`profile.sections[id=user_stories].structure` selects the internal layout:

- **`per_story_grouped` (default)** — for each story/flow collected in Branch B, emit:

  ```
  ### <story title>

  - **Given** <state>
  - **When** <action>
  - **Then** <response>

  - **[MUST]** <binding statement 1>
  - **[MUST NOT]** <binding statement 2>
  ```

  A cross-cutting sub-section may carry only bracketed normative lines (no GWT triple) when the sub-section header itself names the shared context:

  ```
  ### <cross-cutting group title, e.g., shared result-code handling>

  - **[MUST]** <binding statement 1>
  - **[MUST]** <binding statement 2>
  ```

  Each `### ` sub-section MUST contain ≥1 bracketed normative keyword line where the token is at the **head of a bullet list item** — `- **[MUST]** …`, `- **[MUST NOT]** …`, or `- [SHOULD]  …` (optional markdown emphasis, then the bracket, then the claim text). Nested bullets are valid (`  - **[MUST]** …`). Both of the following are drift signals that the guard rejects:
    - Inline prose normative in a paragraph: `시스템은 카드를 **[MUST]** 먼저 표시한다`
    - Inline-position normative inside a bullet: `- 진행 중 주문이 있으면 카드를 **[MUST]** 먼저 표시한다` — bullet shape but the bracket is mid-sentence; breaks grep extraction and tends to surface in Korean output from some models.

  Separate sub-sections with a blank line. Do NOT add a consolidated trailing normative list under the H2 — in this mode normative lines live only inside their owning sub-section.

  The user-stories section MUST contain ≥2 `### ` sub-sections (matches `profile.sections[id=user_stories].min_items = 2`). A single-story pitch is too thin to claim "user stories" coverage.

- **`consolidated`** — emit a single GWT list followed by a single bracketed-keyword list under the H2 (v0.5.2 shape). Do NOT add `### ` sub-sections in this mode.

If the `structure` field is missing (profile predates v0.5.3), treat it as `per_story_grouped`.

### Required-sections guard

Before writing the file, iterate `profile.sections[]`. For every entry with `required: true`, verify the assembled body contains an exact `## <heading>` line (whitespace stripped, profile string matched verbatim). If any required heading is missing:

- Abort file generation — do not write, do not flip `deprecated`.
- Render `prd.stage6.missing_required_section` with `{missing_headings}` set to the ordered list of absent `## <heading>` lines (one per line, in profile order).
- Loop back to Stage 2 for the branch that owns the missing content.

The guard covers custom profile forks that introduce additional `required: true` sections beyond the default branches (A–E, plus optional F). Previously written pitches are append-only and out of scope — the guard runs only on the in-flight generation.

### Structure guard (v0.5.3+, `user_stories` per_story_grouped only)

Runs after the required-sections guard passes, and only when `profile.sections[id=user_stories].structure == per_story_grouped` (treat missing field as `per_story_grouped`). For `structure: consolidated` profiles, skip this guard.

**What the guard enforces (and what it doesn't):**

The guard binds *normative lines to sub-sections* — the core traceability property of `per_story_grouped`. It intentionally does NOT require a GWT triple in every `### ` sub-section, because a valid pitch can legitimately carry a cross-cutting group (e.g., shared result-code handling across several channels) whose sub-section header already names the shared context. Section-level "≥2 GWT blocks total" remains enforced by the Stage 5 gate criterion `gwt_minimum`, which counts across all sub-sections.

Algorithm:

1. Locate the user-stories H2 in the assembled body (`## <profile.sections[id=user_stories].heading>`). Capture the slice from that H2 up to (but not including) the next `## ` line or EOF. Strip fenced code blocks from the slice before inspection so example `### ` inside code doesn't false-match.
2. Extract every `### ` sub-section within that slice.
3. If the slice has fewer than 2 `### ` sub-sections: violation — either the section is empty of stories (0 sub-sections), or only carries one story (matches `min_items = 2` gate).
4. For each sub-section body (content between its `### ` and the next `### ` / H2):
   - Require ≥1 **bullet-head** bracketed normative — a line matching `^\s*[-*]\s+[\*_]{0,3}\[<token>\]` where `<token>` comes from `profile.normative_keywords[].token`. The bracket must be at the *head* of the bullet (optionally wrapped in `**` / `_` emphasis) — not mid-sentence inside the bullet. Nested bullets (`  - **[MUST]**`) are valid.
   - A sub-section missing this is flagged as "missing normative line (bullet-head format required)".
   - Additionally, flag any **inline-position bracketed normative** — a bracketed token on a line that is a paragraph, or a bullet line where the bracket is not at the head. Both read as prose ("시스템은 카드를 **[MUST]** 먼저 표시한다" or "- 시스템은 카드를 **[MUST]** 먼저 표시한다") and defeat grep/CI extraction. Documented in `prd.stage3.inline_normative_warning`.
5. Leakage check: any bracketed normative keyword line appearing *between* the user-stories H2 and the first `### ` sub-section is flagged as "normative line leaked outside sub-section". In `per_story_grouped` mode, normative statements must live inside their owning sub-section so the story↔criterion link is preserved.
6. If any of steps 3–5 report violations:
   - Abort file generation — do not write, do not flip `deprecated`.
   - Render `prd.stage6.missing_story_structure` with `{offending_sections}` set to the ordered list of issues (one per line). Zero-sub-sections emits `<heading> — no story sub-sections found`. Single-sub-section emits `<heading> — only 1 sub-section (need ≥2)`. Missing bullet-head emits `### <title> — missing normative line (must be bullet item beginning with the bracket, like \`- **[MUST]** …\`)`. Inline-position emits `### <title> — inline-position normative (bracket must be at the head of its bullet): <line excerpt>`. Leakage emits `(between ## <heading> and first ###) — leaked normative: <line>`.
   - Loop back to Stage 2 Branch B for re-elicitation of the missing per-story content.

Previously written pitches are append-only and out of scope — the guard runs only on the in-flight generation.

### Handoff output

After writing, emit a handoff message by rendering `prd.stage6.handoff` with:

- `{new_file_path}` — relative path of the newly generated pitch
- `{deprecated_line}` — for `update` intent, render `prd.stage6.deprecated_line` with `{old_file_path}` = the previous active file; for `new` / `new_domain`, substitute with an empty string
- `{github_web_steps}` — render `common.handoff.github_web_steps`
- `{cli_steps}` — render `common.handoff.cli_steps`

Do NOT commit or push — the user owns the commit decision.

---

## Hard Prohibitions

1. **Never write a file that fails the 90% gate.** Do not round up.
2. **Never advance past Stage 5 with any `<profile.gate.unresolved_tag>` tag remaining.**
3. **Never edit an existing pitch's body.** Append-only. The only allowed in-place change is flipping `deprecated: false` → `true`.
4. **Never commit or push.** File writes only. The user owns the commit decision.
5. **Never include code identifiers in the body.** Domain language only.
6. **Never speculate in interview answers.** Unknown → `<profile.gate.unresolved_tag>` tag.
7. **Never skip any stage.** Each stage has an explicit completion criterion.
8. **Never ingest raw dumps from context intake.** Summarize, confirm, then use the summary.

---

## Credits

Design patterns adapted from the following open-source projects:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me` interview pattern, `domain-model` terminology challenge
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria checklist
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer` multi-persona pattern

No source files copied. Patterns referenced only.
