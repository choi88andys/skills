---
name: adr
description: Guided authoring for append-only Architecture Decision Records (ADRs) in an immutable SDD repo. Conducts a focused interview (context, decision, consequences, alternatives), runs multi-persona adversarial review, and writes the ADR only when a 90% completeness gate passes. Use when a team makes a load-bearing technical direction that future engineers must understand. Triggers - "/immutable:adr", "ADR 작성", "아키텍처 결정 기록", "architectural decision".
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
| `adr.sections[].id` / `min_items` / `description` | Stage 3 interview branches (completion criteria) |
| `adr.gate.total` / `pass_threshold` / `criteria` | Stage 5 90% completeness gate |
| `adr.gate.unresolved_tag` | Stage 3/5 unresolved-answer tag — literal value sourced from the active profile per locale |
| `adr.personas[].name` / `question` / `checks` | Stage 4 adversarial review (data SSoT; v0.5 prose stays inline) |
| `naming.filename_pattern` / `slug_case` / `forbidden_slug_patterns` | Stage 6 filename validation (shared with pitch) |
| `domain_allowlist.source` / `reserved_domains` | Stage 1 domain check (`_global` reserved here) |

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
- Glob ADR directory for existing files. Read frontmatter of each to build the supersede chain index.
- If the user's intent mentions a specific domain or feature, cross-reference with active pitches in that domain.

### 1.3 Classify intent

| Signal | Intent |
|---|---|
| No prior ADR on this topic | `new` (`supersedes: null`) |
| Existing active ADR on the same topic, but direction is being reversed or significantly revised | `update` (copy latest, revise, flip old to `deprecated: true`) |
| "This decision is no longer applicable" with no replacement | `deprecate-only` (flip only) |

### 1.4 Scope classification

Ask which scope the ADR covers by rendering `adr.stage1.scope_question` (no substitutions).

- Scope `(1)` → `domain: <name>`, `references.pitches` must include ≥1 active pitch in that domain.
- Scope `(2)` → `domain: _global`, `references.pitches` may be empty. Require a written scope statement in the body.

### 1.5 Confirmation (mandatory)

Always confirm before proceeding. Show:

- Intent (new / update / deprecate-only)
- Scope (domain or `_global`)
- Base file if superseding
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

**One question at a time, always with a recommended answer** derived from upstream pitches / prior ADR / intake summary / industry defaults.

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

- `pitches`: list of pitch filenames (MUST be non-empty unless `domain: _global`)
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
| 6 | References valid | `references.pitches` non-empty (unless `_global`), all referenced files exist and parse |

### Judgment

- **5 or 6 of 6 pass** → proceed to generation
- **Fewer than 5 pass** → refuse; loop to the relevant branch
- **Any `<profile.adr.gate.unresolved_tag>` tag anywhere** → refuse regardless of count

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
  pitches:    [<filename>, …]   # non-empty unless _global
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

### Handoff

Emit commit instructions (GitHub GUI / CLI), do NOT commit.

---

## Hard Prohibitions

1. Never write a file that fails the 90% gate.
2. Never advance with any `<profile.adr.gate.unresolved_tag>` tag.
3. Never edit body of an existing ADR. Append-only + supersede chain.
4. Never commit or push.
5. Never generate an ADR with `references.pitches` empty unless `domain: _global` AND the body includes a scope statement.
6. Never claim a decision has no negative consequences — push back until the user names ≥2.
7. Never skip Alternatives — if the user insists on "there was no alternative", question whether this needs an ADR at all.

---

## Credits

Pattern sources:

- Michael Nygard, *Documenting Architecture Decisions* (2011) — Context / Decision / Consequences template
- [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — revisit-trigger field convention
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grill-me interview pattern
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — adversarial review pattern

No source files copied. Patterns referenced only.
