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
| `sections[].id` / `required` / `min_items` / `max_items` / `description` | Stage 2 interview branches + Stage 6 required-sections guard. `max_items` (v0.5.6+, user_stories only) caps `### ` sub-section count — exceeding triggers `anti_monolith` escalation. |
| `sections[id=user_stories].structure` (v0.5.3+) | Stage 2 Branch B completion criterion + Stage 6 pre-write structure guard. `per_story_grouped` (default) requires each story in a `### ` sub-section carrying a GWT triple + ≥1 bracketed normative line; `consolidated` accepts a single GWT list + single normative list under the H2 (v0.5.2 shape). |
| `anti_monolith.tiers.{L1,L2,L3}` (v0.5.6+) | Stage 1.2 pre-check tier classification of existing active PRDs; Stage 1.3 intent menu adjustment (L2 promotes split, L3 blocks `update`); Stage 5 `concern_scope` criterion fail threshold. Fallback derived from `sections[user_stories].max_items` if block omitted. |
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
1.bis. **Profile schema mismatch detection** (added v0.5.7):
   - When the loaded profile is a TEAM profile (config v3 with `profile:` pointer to a repo-local file), read its `profile_schema:` value (default `1` if absent).
   - Read the bundled default profile's `profile_schema:` value for the same `team_language`.
   - **If `team_profile_schema < bundled_profile_schema`**: render `prd.stage1.profile_schema_mismatch` with `{team_schema}`, `{bundled_schema}`, and a comma-joined list of missing top-level fields detected via direct comparison (e.g., `anti_monolith`, `vague_words`, `personas[quality_auditor]`, `gate.criteria[concern_scope]`). Recommend `/immutable:migrate`.
   - **For this run only**: when the skill needs a missing field (e.g., `anti_monolith.tiers.L3.sub_sections` for §1.2.1 anti-monolith pre-check), READ THE VALUE FROM THE BUNDLED DEFAULT and use it. Do NOT write to disk. Do NOT mutate the in-memory team profile object — fetch fallback values via a "look up in team profile, else look up in bundled default" function so the fallback path is auditable.
   - **Skill traceability**: any output that references a value sourced from the bundled default fallback (rather than the team profile) MUST annotate the source — e.g., "(from bundled default-ko v2 — your team profile is v1)".
   - This guard exists to surface silent-skip behavior immediately. Without it, teams who ran `/immutable:migrate` once on plugin v0.5.0-era and never re-migrated would see new features (anti_monolith, etc.) silently disabled.
2. Confirm `pitches/` exists in CWD (or at the configured `pitches_path`). If not, stop by rendering `prd.stage1.no_pitches_dir` (no substitutions).
3. Read `pitches/README.md` — extract domain allowlist from the allowed-domains table (rows matching `` | `<name>` | ``). Use `profile.domain_allowlist.source` if it differs from the default `pitches/README.md`.
4. **Enumerate active pitches per domain** (changed v0.5.6 — was: "find the active pitch", singular). For each allowlisted domain directory, scan `*.md` frontmatter to find **all** files with `deprecated: false` (excluding `README.md` and `TEMPLATE.md`). A domain may host multiple active PRDs, each on its own supersede chain. None is privileged as "the" baseline for the domain.

### 1.2.1 Anti-monolith pre-check (v0.5.6+)

Resolve the active anti-monolith policy via this fallback chain (v0.5.7+):

1. **Team profile `anti_monolith.tiers`** — if `profile.anti_monolith.enabled == true` and `profile.anti_monolith.tiers` exists in the team profile → use those thresholds.
2. **Team profile `sections[user_stories].max_items` derivation** — else if the team profile has `max_items` → derive: `L1.sub_sections = max_items + 1`, `L2 = max_items + 2`, `L3 = max_items × 3`, `L1/L2/L3.normative_lines = sub_sections × 5`.
3. **Bundled default fallback** (added v0.5.7) — else if Stage 1.bis flagged a profile schema mismatch and the bundled default has `anti_monolith` (or `max_items`) → repeat steps 1-2 against the bundled default profile values. Annotate the rendered tier output with "(thresholds from bundled default-<lang> v<N> — your team profile is v<M>)".
4. **Skip pre-check** — only when none of the above resolve (very old plugin + truly empty profile). Surface a one-line note: "anti-monolith pre-check skipped — profile lacks both `anti_monolith` block and `max_items` field. Run `/immutable:migrate` to enable."

Step 4 was the silent-skip behavior in v0.5.6 — replaced in v0.5.7 by the bundled-default fallback in step 3 plus the explicit note when even that fails.

Once the user has hinted at a target domain (from Stage 1.1 free-text or from the implicit domain in the request), compute metrics for every active PRD in that domain:

- `sub_sections` — count of `### ` headers within the user_stories H2 slice (strip fenced code blocks first to avoid false matches)
- `normative_lines` — count of lines whose first non-whitespace bracket token matches a `profile.normative_keywords[].token` (`[MUST]`, `[MUST NOT]`, `[SHOULD]`, `[SHOULD NOT]`, `[MAY]`)

Classify each active PRD into the highest tier it triggers (L3 > L2 > L1 > none). Surface the result as part of the Stage 1.4 confirmation block:

```
도메인 `<domain>` 의 active PRDs:
  - 2026-04-20-foo.md          [L3 — 8 sub-sections, 50+ normatives]
  - 2026-04-22-bar.md          [pass]
  - 2026-04-23-baz.md          [L1 — 4 sub-sections]
```

When the user's request appears to touch an L2/L3 PRD, this classification drives the Stage 1.3 intent menu.

### 1.3 Classify intent (5-way, v0.5.6+)

| Signal | Intent |
|---|---|
| New feature/flow, fits no allowlisted domain | `new-domain` (requires allowlist update) |
| New feature/flow in an existing domain — distinct concern from any active PRD | **`new`** ← most common (`supersedes: null`, joins the domain as another active chain) |
| The exact scope of one specific active PRD is being re-declared (the PRD's stated promise is wrong/incomplete and you are restating it) | `update` (copy active, revise, flip old deprecated). **Rare** — most "I want to change X" cases are actually `new` (separate concern) or `split-from` (X is one slice of a too-broad PRD) |
| Existing PRD is too large (anti-monolith tier ≥ L1) and you want to reorganize it without semantic change | **`refactor-split`** ← Stage 1 only. Decomposes one PRD into N smaller ones preserving all behavior |
| Existing PRD is too large AND you have a new semantic change targeting one of its sub-scopes | **`split-from`** ← Stage 1 (refactor) + Stage 2 (semantic change in the relevant new sub-PRD). Two-stage flow described below. |
| "No longer provided" with no replacement | `deprecate-only` (flip target's `deprecated` flag) |

#### Anti-monolith driven menu adjustment

When the user's request maps onto an existing active PRD, consult that PRD's tier from §1.2.1:

- **L1 (hint)**: keep the menu as listed. Show a one-line note: "기존 PRD `<file>` 가 약간 큼 (sub-sections N). 신규 작업이 별도 concern 이라면 `new` 권장."
- **L2 (strong_recommend)**: reorder the menu so `refactor-split` and `split-from` precede `update`. If the user picks `update`, ask for an explicit reason (recorded in interview transcript only — not written to frontmatter or body).
- **L3 (block)**: remove `update` from the menu entirely. Only `refactor-split`, `split-from`, `new` (separate small PRD) remain offerable.

### 1.4 Confirmation (mandatory)

Always confirm intent and target before proceeding. Render `prd.stage1.confirmation` with:

- `{domain}` — the confirmed domain name (e.g., `notice`)
- `{intent_desc}` — lookup of the matching `prd.intent_desc.<intent>` key (`new` / `new_domain` / `update` / `refactor_split` / `split_from` / `deprecate_only`)
- `{base_file}` — for `update` / `refactor-split` / `split-from` / `deprecate-only`: the active file being acted on. For `new` / `new-domain`: `common.placeholder.none`.
- `{anti_monolith_summary}` — the per-PRD tier summary from §1.2.1 (rendered when the domain has ≥1 active PRD)

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

### 1.7 Refactor-split flow (v0.5.6+, Stage 1 only)

Decomposes an oversized active PRD into N smaller PRDs **without semantic change**. Pure structural refactor.

#### 1.7.1 Sub-section enumeration

Read the target PRD. Parse the user_stories H2 slice. Extract every `### ` sub-section as a candidate split unit. Each candidate carries:

- Sub-section title (the `### ` text)
- The sub-section's GWT triple (if present)
- Bullet-head normative lines bound to that sub-section
- Edge case rows that name only entities from this sub-section (heuristic match against sub-section title nouns)
- No-go items that name only entities from this sub-section

Cross-cutting content (RFC 2119 declaration, edge cases or no-gos that touch multiple sub-sections, normatives that live between the H2 and the first `### `) is held aside for §1.7.3.

#### 1.7.2 Boundary confirmation

Present the proposed split to the user:

```
기존 PRD: 2026-04-20-foo.md (8 sub-sections, 50 normatives)

분할 후보 (N = 8):
  1. <title-1>  — 4 GWT 라인, 5 normatives, 2 edge cases, 1 no-go
  2. <title-2>  — 3 GWT 라인, 7 normatives, 1 edge case, 0 no-gos
  ...

Cross-cutting (특정 sub-section 에 귀속되지 않음):
  - RFC 2119 declaration → 모든 split PRD 에 자동 복사
  - "모든 화면에 닫기 affordance 제공" [MUST] → 어느 sub-section 의 책임?
  - edge case "환불 완료 주문의 영수증 아이콘" → sub-section 6, 7 둘 다에 해당하는데 어디 둘까?

진행: (a) 제안대로 분할 (b) 경계 조정 (c) 합쳐야 할 후보 지정 (d) 취소
```

If user picks (b) or (c), iterate until boundary is confirmed.

#### 1.7.3 Cross-cutting handling

- **형식 선언** (RFC 2119, 라이센스, glossary 헤더 등 — 1-line declarations) → 모든 split PRD 의 top 에 자동 복사. 중복은 해롭지 않음.
- **Behavioral cross-cutting MUSTs**: ask the user per item which sub-section owns it. If truly cross-section (no single owner), offer to extract into a separate small PRD (`<domain>-<concern>-shared.md` — same domain, separate chain).

#### 1.7.4 Mechanical write-out

For each accepted sub-section, generate a small PRD file:

```yaml
---
domain: <same as original>
supersedes: <original filename>
deprecated: false
---

# <derived title from sub-section>

## <profile.sections[id=background].heading>

(상속: 원본 Background 에서 본 sub-scope 와 무관한 단락은 생략. scope 명시
한 줄 추가: "본 PRD 는 원본 `<original>.md` 의 `<sub-section title>` 부분을
분리하여 다룬다.")

## <profile.sections[id=user_stories].heading>

### <sub-section title>

(원본의 GWT + bullet-head normatives 그대로 복사)

## <profile.sections[id=edge_cases].heading>

(이 sub-scope 와 관련된 edge case 행만 복사)

## <profile.sections[id=no_gos].heading>

(이 sub-scope 와 관련된 no-go 항목만 복사 + cross-domain 항목은 그대로 상속)
```

Filename: `YYYY-MM-DD-<sub-section-slug>.md` (date = today, slug = kebab-cased sub-section title or user-chosen).

#### 1.7.5 Sanity check (instead of full 90% gate)

Skip the standard Stage 5 gate (this is a refactor, not new content). Run instead:

- Each split file has valid frontmatter
- Every original [MUST] / [MUST NOT] / [SHOULD] line appears in exactly one split file (no duplicates, no losses) — except cross-cutting form declarations (allowed to duplicate)
- Every original edge case row appears in at least one split file
- Every original no-go appears in at least one split file

On any failure: do NOT write any file, report the missing/duplicated items, return to §1.7.2 for re-mapping.

#### 1.7.6 Atomic write

When sanity check passes, perform in this order:

1. Write all N split files (`supersedes: <original>`, `deprecated: false`)
2. Flip original file's `deprecated: false` → `true` (single-line edit)

If the user wants to abort after seeing the proposed write list, halt without changing any file.

#### 1.7.7 Handoff

Render `prd.refactor_split.handoff` with the list of new files + the deprecated original. Recommend committing this as a single commit titled `refactor(<domain>): split <original> into N sub-pitches`. Skill does not commit.

### 1.8 Split-from flow (v0.5.6+, Stage 1 + Stage 2)

When the user has both a structural refactor need AND a semantic change targeting one of the new sub-scopes.

1. Run §1.7 (refactor-split) end to end. Confirm completion.
2. Ask: "Stage 2 진행 (신규 변경) 하시겠습니까? Y → 다음 단계 / N → 별도 commit 가시성 확보를 위해 여기서 종료, 나중에 `/immutable:prd` 다시 호출하여 update."
3. If Y: re-enter Stage 1.3 with intent locked to `update`, target = the specific split-out PRD that owns the user's semantic change. Proceed through Stage 2 → Stage 5 → Stage 6 normally (full 90% gate applies to this step — it IS a semantic change).
4. If N: end. The refactor-split commit stands alone.

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
- **Always provide a recommended answer** with each question. Derivation priority (v0.5.6+):
  1. **Confirmed Stage 1.5 summary** (the user explicitly curated context — most reliable).
  2. **Industry defaults** / Apple HIG / cited vendor docs.
  3. **Analogous active pitches in other domains** — preferred sources are small PRDs (sub-section count ≤ `profile.sections[user_stories].max_items`). Use as structural template.
  4. **Active pitches in the same domain** — but with tier-aware handling:
     - Tier `pass` (under L1) — usable as both fact-source and structural template.
     - Tier `L1` — usable as fact-source. Avoid copying its structure (it is borderline oversized).
     - Tier `L2` / `L3` — **fact-source only, never a structural template.** Read for "this PRD says [MUST] X, ensure no contradiction" only. Do not derive sub-section count, ordering, normative density, or scope breadth from these. They are anti-pattern instances retained for backward compatibility.
- **Forbid speculation.** When the user cannot answer or the answer is vague, record a tag in the format `<profile.gate.unresolved_tag> — <question summary>`. The tag literal comes from the active profile (one per locale). Never fill gaps with plausible-sounding content.
- **Prefer codebase exploration over asking** when an answer is already present.

### Question Branches (fixed order)

#### Branch A — Background and Problem

This section captures the **product/service-level** problem the requirement solves — NOT the document's own creation rationale.

Ask about:
- What user or business problem does this requirement solve? (user pain, business goal, policy/compliance need)
- For whom, and what are they trying to accomplish? (user role, scenario, current friction)
- Why is this the right product-level approach to that problem? (decision basis, key trade-offs)

**Reject signals (loop back, do not advance)**:
- Answer describes the document's own existence — "PRD didn't exist", "aligning spec with code", "v1 → v2 changelog", "this is the retro-spec for current behavior". These are document meta, not product problems. Re-ask: "Set the document framing aside — what user or business pain does the underlying requirement address, and why this answer?"
- Answer is only sub-pitch positioning — "this is sub-pitch 1 of 4 in domain X, sibling pitches are Y/Z". Positioning may appear as a single scope-setting clause inside the answer, but not as the whole answer.
- Answer is generic restatement of the title — restating "this pitch defines the checkout screen" without naming a problem.

**Completion criterion**: a third party can summarize the **user/business problem** this requirement solves in ≤3 sentences. Document-existence rationale alone fails this branch.

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

### Checklist (8 criteria, v0.5.6+)

The criteria list is sourced from `profile.gate.criteria[]` (id-keyed). Defaults below.

| # | Criterion id | Pass Condition |
|---|---|---|
| 1 | `background_clear` | Third party can summarize the **user/business problem** this requirement solves in ≤3 lines; no `<profile.gate.unresolved_tag>` tags remain. Answers covering only document-existence rationale (PRD missing / code-spec alignment / changelog) fail this criterion. |
| 2 | `gwt_minimum` | happy path GWT ≥1 AND alternate/error GWT ≥1 (kind check, not count) |
| 3 | `normative_minimum` | At least 3 bracketed statements across the body |
| 4 | `edge_cases_minimum` | At least 1 row with explicit handling |
| 5 | `no_gos_minimum` | At least 1 item with reason or handoff |
| 6 | `no_code_identifiers` | Stage 3 passed cleanly |
| 7 | `feature_scope` | Passes the single-flag toggle test |
| 8 | `concern_scope` | Anti-monolith — see below |

### `concern_scope` evaluation (v0.5.6+)

Compute the in-flight draft's metrics before evaluating:

- `sub_sections` — count of `### ` headers under the user_stories H2 slice
- `normative_lines` — count of bracketed-keyword lines across the entire body

Compare against `profile.anti_monolith.tiers` (or derived fallback per §1.2.1):

- `sub_sections > L3.sub_sections` OR `normative_lines > L3.normative_lines` → **fail** (block file generation, force `refactor-split`)
- `sub_sections > L2.sub_sections` OR `normative_lines > L2.normative_lines` → **pass with strong-recommend warning** (criterion counts as pass; surface `prd.stage5.l2_warning` to the user)
- `sub_sections > L1.sub_sections` OR `normative_lines > L1.normative_lines` → **pass with hint** (criterion counts as pass; surface `prd.stage5.l1_hint`)
- otherwise → pass

The criterion only fails on L3 violation. L1/L2 are warnings that do not block but are visible.

### Judgment

- Use `profile.gate.pass_threshold` (default 7 of 8 in default-ko / default-en since v0.5.6) → proceed to Stage 6
- Below threshold → refuse generation; loop to the relevant branch
- **Any `<profile.gate.unresolved_tag>` tag remains anywhere** → refuse generation regardless of count
- **`concern_scope` failed (L3)** → refuse generation regardless of count, AND offer `refactor-split` of the in-flight draft as the recovery action

### Refusal message

Render `common.gate.refusal_template` with:

- `{criteria_rows}` — newline-joined per-criterion rows built from `common.gate.row_template` with `{n}` = 1..N (N = `profile.gate.total`), `{label}` = `profile.gate.criteria[i].label`, `{status}` = `common.gate.status_pass` or `common.gate.status_fail` (optionally appended with a short reason for failures in the active locale)
- `{next_action}` — one-line actionable next step in the active locale, derived from which criteria failed (identify the failing branches by `profile.gate.criteria[i].id` and ask the user to address them). For `concern_scope` failure specifically, the next_action MUST recommend `refactor-split` (the failed draft is too large to ship as one PRD).

---

## Stage 6 — File Generation and Handoff

### Determine filename and path

- **new / new-domain / update**:
  - Path: `pitches/<domain>/YYYY-MM-DD-<slug>.md`
  - `YYYY-MM-DD`: today's date (use `date +%Y-%m-%d`)
  - `<slug>`: English kebab-case derived from the title; confirm with the user
- **update** additionally: flip the previous active file's `deprecated: false` → `true`. Only that one line.
- **deprecate-only**: flip only. No new file.
- **refactor-split** (v0.5.6+): handled by §1.7 — N new files + flip original. Bypasses standard Stage 6 (no 90% gate, sanity check only).
- **split-from** (v0.5.6+): Stage 1 phase = §1.7 / §1.8; Stage 2 phase enters this section as an ordinary `update` against the relevant split-out PRD.

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

The rendered `prd.stage6.handoff` includes a **Next step** block pointing to `/immutable:design <slug>` plus a one-paragraph clarifier stating that ADR authoring is reactive (surfaced by `/immutable:plan-review-eng` Phase 3 as an OUTPUT, not authored upfront after the pitch). This anchor exists because the canonical pitch → design transition has no orchestrator-level enforcement — without it, callers reading only nearby signals (init handoffs that surface ADR as a peer entry point, CHANGELOG mentions of standalone ADR usage) tend to infer prd → adr as the next step. v0.6.5 already corrected the receiving end (`/immutable:plan-review-ceo` description); v0.7.3 closes the emitting end by adding the next-step anchor here.

Do NOT commit or push — the user owns the commit decision.

---

## Log learning to project memory (mandatory final step)

Before returning control to the user (success **or** abort), append one learning entry to the project store. Best-effort — if `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is unavailable, the guard exits silently and never blocks the flow.

Pick ONE branch below based on outcome and substitute the placeholders (`<intent>`, `<target-filename-stem>`, `<N>`, `<reason>`, etc.) with concrete values before running.

```bash
LH="${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh"
[ -x "$LH" ] || exit 0
SLUG=$("$LH" slug)

# === On success (file written, 90% gate passed) ===
TYPE=pattern; SOURCE=user-stated; CONF=7
KEY="pitch-<intent>-${SLUG}"   # <intent> ∈ {new, update, refactor-split, split-from, new-domain}
INSIGHT="<one sentence summarising what the pitch establishes or changes; ≤200 chars, no credentials, no instruction-like phrasing>"
FILES='["<pitch-relative-path>"]'   # e.g. ["pitches/state/use-riverpod.md"]

# === On deprecate-only (Stage 1.6 flip-existing flow, no new pitch file) ===
# TYPE=pattern; SOURCE=user-stated; CONF=7
# KEY="pitch-deprecate-<target-filename-stem>-${SLUG}"
# INSIGHT="Deprecated <target>: <reason in ≤80 chars>"
# FILES='["<target-pitch-relative-path>"]'

# === On abort (interview cancel, 90% gate fail, hard prohibition hit) ===
# TYPE=pitfall; SOURCE=observed; CONF=6
# KEY="prd-aborted-${SLUG}"
# INSIGHT="Aborted at Stage <N>: <reason in one sentence>"
# FILES='[]'

"$LH" log "$(jq -nc --arg skill "immutable-prd" --arg type "$TYPE" --arg key "$KEY" \
  --arg insight "$INSIGHT" --arg src "$SOURCE" --argjson conf "$CONF" --argjson files "$FILES" \
  '{skill:$skill,type:$type,key:$key,insight:$insight,confidence:$conf,source:$src,files:$files}' 2>/dev/null)" || true
```

---

## Hard Prohibitions

1. **Never write a file that fails the 90% gate.** Do not round up.
2. **Never advance past Stage 5 with any `<profile.gate.unresolved_tag>` tag remaining.**
3. **Never edit an existing pitch's body.** Append-only. The only allowed in-place change is flipping `deprecated: false` → `true`.
4. **Never commit or push.** File writes only. The user owns the commit decision.
5. **Never include code identifiers in the body.** Domain language only.
6. **Never speculate in interview answers.** Unknown → `<profile.gate.unresolved_tag>` tag.
7. **Never skip any stage.** Each stage has an explicit completion criterion. (Exception: §1.7 `refactor-split` is a structural refactor and bypasses Stage 2-5; it runs its own §1.7.5 sanity check instead.)
8. **Never ingest raw dumps from context intake.** Summarize, confirm, then use the summary.
9. **Never derive PRD structure from an L2/L3 active pitch** (v0.5.6+). Oversized PRDs are anti-pattern instances; treat them as fact-source only when answering individual interview questions, never as templates for the new draft's shape, scope, or normative density.
10. **Never let `update` intent target an L3 PRD** (v0.5.6+). The intent menu must remove `update` when the target is L3; only `refactor-split`, `split-from`, or `new` (separate small PRD) are offerable. Bypassing this rule perpetuates the domain-charter anti-pattern.

---

## Credits

Design patterns adapted from the following open-source projects:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me` interview pattern, `domain-model` terminology challenge
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria checklist
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer` multi-persona pattern

No source files copied. Patterns referenced only.
