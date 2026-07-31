---
name: adr
description: Guided authoring for append-only Architecture Decision Records (ADRs) in an immutable SDD repo. Conducts a focused interview (context, decision, consequences, alternatives), runs multi-persona adversarial review, and writes the ADR only when a 90% completeness gate passes. Use when a team makes a load-bearing technical direction that future engineers must understand. In the orchestrated SDD flow, ADRs are authored reactively — only after /immutable:plan-review-eng Phase 3 surfaces an ADR-authoring trigger, never upfront right after the pitch; the skill is also callable standalone to record an out-of-flow decision. Triggers - "/immutable:adr", "ADR 작성", "아키텍처 결정 기록", "architectural decision".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch
license: MIT
---

# /immutable:adr — Guided Immutable ADR Authoring

Interactively author an append-only Architecture Decision Record. Shares the append-only mechanics of `/immutable:prd` (supersede chain, `deprecated` flag, 90% gate) but with an ADR-specific interview shape (Nygard template) and review personas tuned for technical decisions.

> **Schema reference**: see [`../SCHEMA.md`](../SCHEMA.md) for shared frontmatter, reference policy, and directory conventions.

## Strings catalog & locale (v0.5 / S3)

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml` — not embedded inline. SKILL.md refers to catalog keys via the pattern ``render `<key>` `` with single-brace `{placeholder}` substitution performed by the skill.

**Locale resolution**: `team_language` comes from `.immutable-prd/config.yml` (default: `ko`). Per-string fallback:

1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit one-line warning via `common.fallback_warning`, never silent)
3. Hardcoded last-resort English in this SKILL.md (plugin file corruption; emit warning and abort the stage)

See `../SCHEMA.md#strings-catalog-v05-s3` for the schema, responsibility split (catalog vs. profile), and key naming convention.

## Profile Resolution (v0.5+)

The skill is **profile-aware** in v0.5. ADR-specific tunables — body sections, persona checks, the 6-criterion gate — live under the `adr:` block of the active profile YAML.

### Resolution order

1. If `.immutable-prd/config.yml` declares `profile: <path>` (v3 configs only) AND the file exists → load it.
2. Else load the bundled default matching `team_language` from `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`.
3. If no matching locale profile exists → fall back to `default-en.yml` with a one-line warning.

### Backward compatibility (zero-action migration)

`version: 2` configs (without `profile:`) continue to work — the skill auto-loads the bundled default profile matching `team_language`. Behavior is identical to v0.4. Run `/immutable:migrate` (S4) when ready to graduate to v3.

### Profile fields consumed by /immutable:adr in v0.5

| Profile field | Where used |
|---|---|
| `adr.sections[].heading` | Stage 6 body assembly (rendered in ADR file) |
| `adr.sections[].id` / `required` / `min_items` / `description` | Stage 3 interview branches + Stage 6 required-sections guard |
| `adr.gate.total` / `pass_threshold` / `criteria` | Stage 5 90% completeness gate |
| `adr.gate.unresolved_tag` | Stage 3/5 unresolved-answer tag — literal value sourced from the active profile per locale |
| `adr.personas[].name` / `question` / `checks` | Stage 4 adversarial review (data SSoT; v0.5 prose stays inline) |
| `naming.filename_pattern` / `slug_case` / `forbidden_slug_patterns` | Stage 6 filename validation (shared with pitch) |
| `domain_allowlist.source` / `reserved_domains` | Stage 1 domain check (`_global` reserved here) |
| `adr.anti_monolith.tiers.{L1,L2,L3}` (v0.5.6+) | Stage 1.2 pre-check tier classification (alternatives_count / consequences_count) of existing ADRs; Stage 5 in-flight draft evaluation. Skips with a note if the block is missing in both team and bundled profile. |

Profile-owned strings (ADR section headings, persona names, gate criteria) render from the active profile. Stage prompts, refusal messages, and the consequences sub-headings (positive / negative / cost-of-adoption) are sourced from the strings catalog per the "Strings catalog & locale" section above.

## Preconditions

1. `.immutable-prd/config.yml` exists at the app repo root (or detected via walk-up). `repo_mode` must be `two-repo-app` or `single-repo`. If absent, prompt the user to create one via the skeleton in `../SCHEMA.md`. Stop if declined.
2. `adr_path` resolves to an existing directory. If the directory does not exist, offer to create it with a `TEMPLATE.md` seed.
3. A pitches allowlist is reachable: local at `pitches_path` (single-repo) or at `<spec_repo_path>/<pitches_path_in_spec>/README.md` (two-repo-app). If neither is reachable, ADR may still be authored with `domain: _global`; non-`_global` ADRs require the allowlist check.

The skill **writes the file only**. It never commits or pushes.

## Invocation

```
/immutable:adr
```

Optional free-text initial context:

```
/immutable:adr switch state management from Provider to Riverpod
```

---

## Overall Process (5 stages)

```
Stage 1: Intent Routing           — new / update (supersede) / deprecate + scope
Stage 2: Context Intake (opt.)    — related pitches, prior ADRs, external reference
Stage 3: Interview (Nygard)        — Context / Decision / Consequences / Alternatives
Stage 4: Adversarial Review       — 3 personas, each surfaces ≥1 gap
Stage 5: 90% Completeness Gate + File Generation
```

Stop immediately on any stage failure. Loop back to Stage 3 when Stage 4 finds issues.

---

## Stage 1 — Intent Routing

### 1.1 Initial context

If the user passed no argument, ask once using `adr.stage1.intent_question` (no substitutions).

### 1.2 Environment scan (parallel)

- Read `.immutable-prd/config.yml` → resolve ADR directory, pitches path, team language.
- **Load profile** per the resolution order in **Profile Resolution** above. Cache `profile.adr.*` for the rest of the session.
- **Profile schema mismatch detection** (added v0.5.7): when the loaded profile is a TEAM profile, read its `profile_schema:` and the bundled default's `profile_schema:`. If team < bundled, render `adr.stage1.profile_schema_mismatch` with `{team_schema}` / `{bundled_schema}` / list of missing top-level fields (e.g., `adr.anti_monolith`). Recommend `/immutable:migrate`. For this run, fetch missing fields from the bundled default with source annotation in any tier output. Mirror behavior of `/immutable:prd` §1.bis — same rationale, same fallback chain.
- **Enumerate active ADRs** (v0.10.0 — the ad-hoc Glob+frontmatter scan became a resolver call, mirroring `/immutable:prd`'s Stage 1.2 item 4). Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_docs.py" --type adr --list-active` (config auto-detected by walk-up from CWD) and build the supersede chain index from its output — deprecation judged by a real YAML frontmatter parse rather than a text grep.
- **Enumerate active ADRs per (domain, supersede chain)** (changed v0.5.6 — was: implicit "the active ADR per domain"). Multiple active ADRs may coexist in the same domain (notably in `_global`) provided each is on its own supersede chain. Cross-check the user's request against every active chain — `update` targets exactly one specific chain; `new` opens a separate chain.
- If the user's intent mentions a specific domain or feature, cross-reference with active pitches in that domain.

### 1.2.1 ADR anti-monolith pre-check (v0.5.6+)

Resolution chain (v0.5.7+ — mirrors `/immutable:prd` §1.2.1):

1. Team profile `adr.anti_monolith.tiers` → use directly.
2. Bundled default `adr.anti_monolith.tiers` → use with source annotation in tier output.
3. Skip with one-line note "ADR anti-monolith pre-check skipped — `adr.anti_monolith` block missing in both team and bundled profile. Run `/immutable:migrate` to enable."

If a tier set is resolved, compute per-ADR metrics for every active ADR in the resolved domain (or in `_global` if scope is global):

- `alternatives_count` — items in the alternatives section
- `consequences_count` — total positive + negative + cost-of-adoption lines

Classify into `pass` / `L1` / `L2` / `L3`. ADR thresholds are looser than pitch by design (the "single declarative sentence" gate already prevents most decision-bundling). Tier `L2` / `L3` on an ADR usually signals one of:

- The ADR is summarizing a survey of vendor options instead of committing to one (alternatives bloat)
- The decision actually bundles two decisions (e.g., "switch state lib AND add new persistence layer")

Surface the classification to the user during Stage 1.5 confirmation. L3 ADRs cannot be `update`d — only `new` (separate chain) or `deprecate-only`.

### 1.3 Classify intent

| Signal | Intent |
|---|---|
| Decision on a topic with no prior ADR — or a topic that has prior ADRs but yours is a distinct decision | `new` (`supersedes: null`, opens a new chain). Multiple active ADRs in the same domain are normal under v0.5.6+. |
| The exact same topic of one specific active ADR is being reversed or significantly revised | `update` (copy that chain's latest, revise, flip old to `deprecated: true`). Rare — be sure you are restating *that* decision, not making a related but distinct one. |
| "This decision is no longer applicable" with no replacement | `deprecate-only` (flip only) |

### 1.4 Scope classification

Ask which scope the ADR covers by rendering `adr.stage1.scope_question` (no substitutions).

- Scope `(1)` → `domain: <name>`, `references.pitches` must include ≥1 active pitch in that domain.
- Scope `(2)` → `domain: _global`, `references.pitches` may be empty (per `profile.domain_allowlist.reserved_domains[].adr_only`; the bundled default profiles mark only `_global` this way). Require a written scope statement in the body. **Multiple coexisting `_global` ADRs are valid (v0.5.6+)** — each captures a distinct cross-cutting decision (e.g., "use ApiResult sealed", "use Equatable+Freezed mix", "Use case mandatory") on its own supersede chain.

### 1.5 Confirmation (mandatory)

Always confirm before proceeding. Show:

- Intent (new / update / deprecate-only)
- Scope (domain or `_global`)
- Base file if superseding (the specific chain being updated, when there are multiple active chains in the same domain)
- Anti-monolith tier summary for active ADRs in this scope (when ≥1 active)
- Proceed option

If ambiguous, ask rather than guess.

### 1.6 Deprecate-only flow

Skip to Stage 5. Ask for a reason string. Flip `deprecated: false → true` on the target file (single-line change). Emit handoff with no new file.

---

## Stage 2 — Context Intake (Optional)

Opt-in. Accept curated external materials:

- **Referenced pitches**: pitch filenames to bind the ADR to. Skill auto-reads these.
- **Prior ADR chain**: for `update` intent, the latest active ADR auto-loads as baseline.
- **External docs**: RFC, benchmark report, vendor comparison. URL or local path.
- **Discussion excerpts**: paste summaries of Slack / Discord threads (5k-word cap).

Reuse the anti-dumping filters from `/immutable:prd` Stage 1.5 — for each violation render the matching `common.anti_dumping.*` key (see the prd skill for the full signal → key table).

For each accepted attachment, **summarize → confirm with user → store corrected summary only**. Discard raw dumps.

Skip path: if the user replies with a negative/empty response (e.g., `없음`, `none`, `no`, `skip`, empty line), proceed to Stage 3.

---

## Stage 3 — Interview (Nygard template)

**One question at a time, always with a recommended answer** derived from upstream pitches / prior ADR / intake summary / industry defaults. **When sourcing from a prior ADR in the same scope, respect its anti-monolith tier** (§1.2.1) exactly as `/immutable:prd` Branch B does for pitches: `pass`/`L1` ADRs may inform structure; **`L2`/`L3` ADRs are fact-source only, never a structural template** — they are anti-pattern instances retained for backward compatibility, and deriving this ADR's structure or depth from one reproduces the bundling problem it exists to prevent.

### Branch A — Context

- What problem does this decision address? What is the current state?
- What constraints exist? (business, regulatory, team skill, existing code, cost)
- What forces push toward a change? (pain point, new requirement, bug class)

**Completion criterion**: a third-party engineer can summarize "what triggered this decision" in ≤3 sentences.

### Branch B — Decision

- **State the decision as a single declarative sentence.** ("We will adopt X for Y.")
- What is included in scope? What is explicitly excluded?
- What is the minimum viable implementation path?

**Completion criterion**: the decision is one unambiguous sentence readable out of context.

### Branch C — Consequences

Enumerate trade-offs:

- **Positive** — what gets better
- **Negative** — what gets worse or what we give up
- **Neutral / cost of adoption** — migration effort, training, tooling

**Completion criterion**: at least 2 positive AND at least 2 negative consequences listed. "All positive, no negative" is a sign of un-examined decision — push back.

### Branch D — Alternatives Considered

For at least 2 alternatives, capture:

- Name of the alternative
- Why it was rejected (1–2 sentences)
- What would change our mind (revisit trigger)

"We didn't consider alternatives" is not acceptable. If truly only one option exists, the decision may not warrant an ADR.

### Branch E — Rollout & Validation

- How will we know this decision is correct? (metric, milestone, review date)
- What is the rollback story if this decision fails?
- Are there feature flags, staged migrations, or gated experiments?

**Completion criterion**: at least one explicit signal/metric OR a scheduled review date.

### Branch F — References (frontmatter assembly)

Confirm the final `references` block:

- `pitches`: list of pitch filenames (MUST be non-empty unless `domain` is declared `adr_only: true` in `profile.domain_allowlist.reserved_domains`)
- `adrs`: prior ADRs this one builds on or overrides (non-supersede dependencies)
- `designs`, `tech_specs`: usually empty for an ADR; allowed if the decision directly reacts to an existing design/tech-spec

---

## Stage 4 — Adversarial Review (3 Personas)

Each persona MUST surface ≥1 gap. Gaps raised by 2+ personas escalate one severity level.

### Persona 1 — New Engineer (onboarding next quarter)

Apply the checks from `profile.adr.personas[id=new_engineer].checks[]` (profile owns the locale-specific anti-pattern examples). The persona's central question comes from `profile.adr.personas[id=new_engineer].question`.

### Persona 2 — Maintainer (2 years from now)

Apply the checks from `profile.adr.personas[id=maintainer].checks[]`. The persona's central question comes from `profile.adr.personas[id=maintainer].question`.

### Persona 3 — Product Lead

Apply the checks from `profile.adr.personas[id=product_lead].checks[]`. The persona's central question comes from `profile.adr.personas[id=product_lead].question`.

### Output

Numbered list per persona. Format per row: `[<profile.adr.personas[i].name>] <n>. <finding text>`.

For each finding, offer three action choices rendered from the catalog:

- `common.adv_review.accept` → return to Stage 3 for revision
- `common.adv_review.move_to_no_go` → add to the ADR's scope-exclusions section
- `common.adv_review.reject` → record counter-reasoning; proceed

---

## Stage 5 — 90% Completeness Gate

### Checklist (6 criteria)

| # | Criterion | Pass Condition |
|---|---|---|
| 1 | Context is clear | Third party summarizes trigger in ≤3 lines; no `<profile.adr.gate.unresolved_tag>` remains |
| 2 | Decision is one sentence | A single declarative statement, not a paragraph of hedges |
| 3 | Consequences balanced | ≥2 positive AND ≥2 negative explicitly listed |
| 4 | Alternatives considered | ≥2 alternatives with rejection reason |
| 5 | Revisit trigger present | Metric, milestone, OR scheduled review date |
| 6 | References valid | `references.pitches` non-empty (unless domain is `adr_only: true` in `profile.domain_allowlist.reserved_domains`), all referenced files exist and parse |

### Judgment

- **5 or 6 of 6 pass** → proceed to generation
- **Fewer than 5 pass** → refuse; loop to the relevant branch
- **Any `<profile.adr.gate.unresolved_tag>` tag anywhere** → refuse regardless of count

### ADR anti-monolith check (v0.5.6+)

If `profile.adr.anti_monolith.enabled == true`, additionally evaluate the in-flight draft against `profile.adr.anti_monolith.tiers`:

- L3 violation (`alternatives_count > L3.alternatives_count` OR `consequences_count > L3.consequences_count`) → **refuse generation** regardless of gate count. ADR likely bundles ≥2 decisions or has decayed into a vendor survey. Recovery: split into 2+ ADRs (each with its own `decision` sentence), or extract the survey content into a separate non-ADR document.
- L2 violation → pass with strong warning. The user must confirm "this single ADR truly captures one decision".
- L1 violation → pass with hint. No flow change.

### Refusal format

Use the same checklist style as `/immutable:prd` Stage 5 refusal.

---

## Stage 6 — File Generation and Handoff

### Filename

- **new / update**: `<adr-dir>/YYYY-MM-DD-<slug>.md` (flat, not per-domain).
- **update**: after writing the new file, flip previous active file's `deprecated: false → true`.
- **deprecate-only**: flip only.

### Frontmatter

```yaml
---
type: adr
domain: <name | _global>
supersedes: <previous-filename | null>
deprecated: false
references:
  pitches:    [<filename>, …]   # non-empty unless domain is adr_only in reserved_domains
  adrs:       [<filename>, …]
  designs:    []
  tech_specs: []
---
```

### Body structure

Section headings are sourced from `profile.adr.sections[].heading` (looked up by `id`, not hardcoded). Order MUST follow the entries in `profile.adr.sections`.

```
# <ADR Title>

## <profile.adr.sections[id=context].heading>

(Branch A content)

## <profile.adr.sections[id=decision].heading>

(Branch B content. Single declarative sentence, then optional 1-paragraph elaboration.)

## <profile.adr.sections[id=consequences].heading>

(Branch C content. Sub-headings are sourced from the strings catalog:)

### <adr.consequences.positive_heading>
- …

### <adr.consequences.negative_heading>
- …

### <adr.consequences.cost_of_adoption_heading>
- …

## <profile.adr.sections[id=alternatives].heading>

(Branch D content)

- **<Alt A>** — <rejection reason>. <revisit trigger>.
- **<Alt B>** — …

## <profile.adr.sections[id=revisit_triggers].heading>

(Branch E content)

## <profile.adr.sections[id=scope_exclusions].heading>

(Optional — `profile.adr.sections[id=scope_exclusions].required: false`. Omit the section entirely when no exclusions exist.)
```

The Consequences sub-headings (positive / negative / cost-of-adoption) are owned by the strings catalog (`adr.consequences.*`). Section headings remain owned by the profile.

### Required-sections guard

Before writing the file, iterate `profile.adr.sections[]`. For every entry with `required: true`, verify the assembled body contains an exact `## <heading>` line (whitespace stripped, profile string matched verbatim). If any required heading is missing:

- Abort file generation — do not write, do not flip `deprecated`.
- Render `adr.stage6.missing_required_section` with `{missing_headings}` set to the ordered list of absent `## <heading>` lines (one per line, in profile order).
- Loop back to Stage 3 for the branch that owns the missing content.

The guard covers custom profile forks that introduce additional `required: true` sections beyond the default Nygard branches (A–E). Previously written ADRs are append-only and out of scope — the guard runs only on the in-flight generation.

### Handoff

Emit commit instructions (GitHub GUI / CLI), do NOT commit.

---

## Log learning to project memory (mandatory final step)

Before returning control to the user (success **or** abort), append one learning entry to the project store. Best-effort — if `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is unavailable, the guard exits silently and never blocks the flow.

Pick ONE branch below based on outcome and substitute the placeholders (`<adr-filename-stem>`, `<N>`, `<reason>`, etc.) with concrete values before running. The success-path `INSIGHT` **must inline the revisit trigger** so future "what triggers re-visiting X?" queries surface it via substring match — use the same wording from the ADR's Consequences / Revisit triggers branch, condensed.

```bash
LH="${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh"
[ -x "$LH" ] || exit 0
SLUG=$("$LH" slug)

# === On success (file written, 90% gate passed) ===
TYPE=architecture; SOURCE=user-stated; CONF=7
KEY="adr-<adr-filename-stem>-${SLUG}"   # e.g. adr-2026-05-05-auth-strategy-skills
INSIGHT="Decision: <≤80 chars>. Revisit when: <≤80 chars>."
FILES='["<adr-relative-path>"]'   # e.g. ["adr/2026-05-05-auth-strategy.md"]

# === On deprecate-only (Stage 1.6 flip-existing flow, no new ADR file) ===
# TYPE=architecture; SOURCE=user-stated; CONF=7
# KEY="adr-deprecate-<target-filename-stem>-${SLUG}"
# INSIGHT="Deprecated <target>: <reason in ≤80 chars>"
# FILES='["<target-relative-path>"]'

# === On abort (interview cancel, 90% gate fail, hard prohibition hit) ===
# TYPE=pitfall; SOURCE=observed; CONF=6
# KEY="adr-aborted-stage<N>-${SLUG}"
# INSIGHT="Aborted at Stage <N>: <reason>"
# FILES='[]'

"$LH" log "$(jq -nc --arg skill "immutable-adr" --arg type "$TYPE" --arg key "$KEY" \
  --arg insight "$INSIGHT" --arg src "$SOURCE" --argjson conf "$CONF" --argjson files "$FILES" \
  '{skill:$skill,type:$type,key:$key,insight:$insight,confidence:$conf,source:$src,files:$files}' 2>/dev/null)" || true
```

---

## Hard Prohibitions

1. Never write a file that fails the 90% gate.
2. Never advance with any `<profile.adr.gate.unresolved_tag>` tag.
3. Never edit body of an existing ADR. Append-only + supersede chain.
4. Never commit or push.
5. Never generate an ADR with `references.pitches` empty unless the ADR's `domain` is declared `adr_only: true` in `profile.domain_allowlist.reserved_domains` (the bundled default profiles mark only `_global` this way, but teams may add others) AND the body includes a scope statement.
6. Never claim a decision has no negative consequences — push back until the user names ≥2.
7. Never skip Alternatives — if the user insists on "there was no alternative", question whether this needs an ADR at all.
8. Never derive this ADR's structure/depth from an L2/L3 active ADR in the same scope (mirrors `/immutable:prd` Hard Prohibition #9) — treat it as fact-source only.

---

## Credits

Pattern sources:

- Michael Nygard, *Documenting Architecture Decisions* (2011) — Context / Decision / Consequences template
- [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — revisit-trigger field convention
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grill-me interview pattern
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — adversarial review pattern

No source files copied. Patterns referenced only.
