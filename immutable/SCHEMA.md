# SDD Schema — immutable plugin (v0.5 preview)

Shared schema reference for the immutable SDD toolkit. The `/immutable:prd` skill authors pitches. The `/immutable:adr` companion authors Architecture Decision Records in the app repo.

**Status**: v0.4 base schema. v0.5 introduces **config schema v3** — an optional profile system that externalizes what v0.4 hardcoded into skill code (section headings, adversarial personas, 90% gate thresholds, identifier regex, filename conventions). Doc types, append-only semantics, and supersede chain rules are unchanged.

**Compatibility**: v2 configs (`version: 2`, no `profile:` field) continue to work without modification. The plugin auto-loads the default profile that matches `team_language` — zero action required. Teams can graduate to v3 by running `/immutable:migrate` (v0.5 / S4) or by hand-editing `.immutable-prd/config.yml`.

**Scope of v0.5 schema changes**: config file only. Frontmatter fields, filename rules, supersede mechanics, and validation invariants are unchanged. Any v0.4 pitch or ADR remains valid under v0.5.

---

## Document types

| Type | Purpose | Primary author | Location | Change frequency |
|---|---|---|---|---|
| **pitch** | WHAT the app should do (product promise) | PM / UX | Spec repo (`pitches/`) | Low (superseded on product policy change) |
| **ADR** | WHY a load-bearing technical direction was chosen | Tech lead | App repo (`adr/`) | Low (superseded on architectural reversal) |

Both doc types follow the same **append-only + supersede** mechanics.

### What v0.3 dropped (and why)

v0.2 shipped 5 companion types (`adr`, `design`, `tech-spec`, `status`, `supersede`). v0.3 drops 4 of them:

| Dropped | Reason |
|---|---|
| `tech-spec` | Mostly SSoT-duplicated against code (API / data model / state). Legitimate areas (rollout / observability / migration / external-deps) are absorbed into ADR. |
| `design` | 6 of 8 sections duplicated against pitch / Figma / code. Genuine gaps (accessibility intent + motion intent) are absorbed into the pitch TEMPLATE as optional sections. |
| `status` | Derivable from PR state / feature flags / git tags. Mutable JSON ledger introduces drift risk. |
| `supersede` | `/immutable:prd` already handles single-pitch supersede. Cross-doc cascades are rare with only 2 doc types. |

Guiding rule: **if the source of truth lives in code or tooling, don't create a parallel prose file.**

---

## Mutability policy

Both `pitch` and `adr` are append-only:

- File body is **immutable** once committed. The only allowed in-place change is `deprecated: false → true`.
- Changes require a **new file** via `supersedes: <previous-filename>`.
- **Per-edge integrity**: when a file F has `F.supersedes = T`, the target T must be `deprecated: true`. (Changed in v0.5.6 — there is no longer a global per-(domain, type) cap on actives. Multiple chains may have active leaves in the same domain — see "Granularity" below.)
- **Fan-out is permitted**: a single predecessor may be superseded by N successors — the canonical use is a `refactor-split` that decomposes one oversized PRD into several smaller ones. The shared predecessor must still be deprecated.
- Deleting an old file is forbidden — history is the audit trail.

### Granularity (added v0.5.6)

- **1 PRD = 1 feature/policy**, not 1 PRD = 1 domain. Domain is a categorization tag; multiple PRDs naturally coexist in the same domain.
- Feature ↔ Domain is **M:N** — one feature may span multiple domains (cross-reference via `references.pitches`), and one domain hosts multiple features (each as its own PRD chain).
- A PRD that grows beyond `profile.sections[user_stories].max_items` (default 3) `### ` sub-sections triggers `anti_monolith` escalation (hint / strong-recommend / block) — see "Anti-patterns" below.

### Cultural guidance (not mechanical)

- Pitch and ADR both expect **rare** supersession on the *same* concern. Each new version of a given chain is a load-bearing policy shift on that specific scope. Reviewers push back hard.
- Adding a new chain (`supersedes: null`) for a *different* concern in the same domain is **not** supersession — it is decomposition. Encouraged when the existing chain's scope doesn't cover the new concern.
- Frequent churn on a single chain signals either (a) the decision wasn't load-bearing enough to warrant a file, or (b) the original framing was too broad and should be split.
- A single PRD attempting to cover an entire domain is the **domain-charter anti-pattern** (see "Anti-patterns" section). Use `refactor-split` to decompose without a semantic change.

---

## Repository layouts

v0.3 separates pitches (spec repo) from ADRs (app repo). Each repo has its own `.immutable-prd/config.yml`.

### Two-repo mode (default — `repo_mode: two-repo`)

```
<spec-repo>/
├── pitches/
│   ├── README.md            # domain allowlist
│   ├── TEMPLATE.md
│   └── <domain>/YYYY-MM-DD-<slug>.md
├── .immutable-prd/
│   └── config.yml           # spec repo config (pitches only)
└── CONTRIBUTING.md

<app-repo>/
├── adr/
│   ├── README.md            # ADR conventions for this repo
│   ├── TEMPLATE.md
│   └── YYYY-MM-DD-<slug>.md
├── .immutable-prd/
│   └── config.yml           # app repo config (adr only)
├── lib/                     # (or src/, app/, etc.)
└── …
```

ADR references pitches by filename. The `/immutable:adr` skill resolves pitch filenames against the sibling spec repo via `spec_repo_path` in config.yml (see below).

### Single-repo mode (`repo_mode: single-repo`)

```
<app-repo>/
├── .immutable-prd/
│   └── config.yml           # at app root so /immutable:prd and /immutable:adr both resolve via walk-up
├── spec/                    # subtree housing pitches
│   └── pitches/
│       ├── README.md
│       ├── TEMPLATE.md
│       └── <domain>/YYYY-MM-DD-<slug>.md
├── adr/                     # ADRs live at app repo root (alongside code)
│   ├── TEMPLATE.md
│   └── YYYY-MM-DD-<slug>.md
└── lib/
```

In single-repo mode a single `config.yml` at the app repo root declares both `pitches_path` and `adr_path`. Config must live at the app root (not inside `spec/`) so the walk-up resolver finds it regardless of which subtree the skill is invoked from.

---

## `.immutable-prd/config.yml` schema

### Two-repo mode — spec repo config

```yaml
# Version of this config schema. v0.3 uses version 2 (breaking change from v0.2).
version: 2

# Repository mode for THIS repo.
#   two-repo-spec: this is the spec repo (pitches only)
#   two-repo-app:  this is the app repo (adr only)
#   single-repo:   both pitches and adr live in this repo
repo_mode: two-repo-spec

# Team working language for user-facing prompts.
# - ko: Korean (default for current users)
# - en: English
team_language: ko

# Path to pitches (required when this repo hosts pitches).
pitches_path: pitches/

# Template path (optional — defaults to pitches/TEMPLATE.md).
templates:
  pitch: pitches/TEMPLATE.md
```

### Two-repo mode — app repo config

```yaml
version: 2
repo_mode: two-repo-app
team_language: ko

# Path to ADRs in this repo.
adr_path: adr/

# Sibling spec repo path (absolute or relative). /immutable:adr resolves
# pitch filenames against <spec_repo_path>/<pitches_path>.
# If null, ADRs may reference pitches only by filename (no existence check).
spec_repo_path: ../myproject-spec
pitches_path_in_spec: pitches/

templates:
  adr: adr/TEMPLATE.md
```

### Single-repo mode

```yaml
version: 2
repo_mode: single-repo
team_language: ko

pitches_path: spec/pitches/
adr_path: adr/

templates:
  pitch: spec/pitches/TEMPLATE.md
  adr: adr/TEMPLATE.md
```

### v3 additions (v0.5+)

v3 is a **superset** of v2. The only structural difference is a bumped `version:` field and a new optional `profile:` pointer:

```yaml
version: 3                       # was 2 in v0.4
repo_mode: two-repo-spec
team_language: ko
pitches_path: pitches/

# NEW in v3 (optional).
# Path to a team-specific profile file. Unset → plugin loads the default
# profile matching `team_language` (e.g., default-ko / default-en, bundled
# with the plugin under `immutable/examples/_profiles/`).
#
# Profiles declare section headings, personas, 90% gate thresholds,
# identifier regex, and filename conventions as data. See the
# "Profile system" section below for the full schema.
profile: .immutable-prd/profile.yml
```

All other v2 fields (`repo_mode`, `team_language`, `pitches_path`, `adr_path`, `spec_repo_path`, `pitches_path_in_spec`, `templates`) retain their v2 meaning in v3.

**Interop rule**: `version: 2` without `profile:` is valid in v0.5+. The plugin auto-loads the default profile matching `team_language`. Authors opt in to customization by either:

- bumping `version: 2 → 3` and adding `profile:` (explicit, recommended), or
- running `/immutable:migrate` (v0.5 / S4) which performs the bump and seeds a default-copy profile file.

### Detection & fallback

Skills detect config via this order:

1. `./.immutable-prd/config.yml` (current working directory)
2. Walk up to repo root (`.git` marker) and retry
3. If no config found: prompt the user to create one (via `/immutable:init`), or fall back to inferred defaults:
   - `repo_mode: two-repo-spec` if `pitches/` exists and no `lib/` / `src/` / `app/`
   - `repo_mode: two-repo-app` if `lib/` / `src/` / `app/` exists and no `pitches/`
   - `repo_mode: single-repo` if both `pitches/` and `lib/` exist
   - `team_language: ko`
   - `profile: <bundled default-ko>`

### Reusable helper

Shell helper (bundled at `scripts/find_config.sh`):

```bash
# Walk up from $PWD until .immutable-prd/config.yml or .git boundary.
current="$(pwd)"
while :; do
  candidate="$current/.immutable-prd/config.yml"
  [ -f "$candidate" ] && { echo "$candidate"; break; }
  [ -d "$current/.git" ] && break
  parent="$(dirname "$current")"
  [ "$parent" = "$current" ] && break
  current="$parent"
done
```

Stand-alone validator (`scripts/validate_docs.py`, requires PyYAML) enforces the invariants in the Validation section below. Suitable for pre-commit hooks and CI.

---

## Frontmatter — shared fields

Both pitch and ADR share this core:

```yaml
---
type: pitch | adr
domain: <name>                # pitch: required; ADR: required (may be "_global")
supersedes: <filename|null>
deprecated: false
references:
  pitches: [<filename>, …]    # ADR MUST have ≥1 unless domain == "_global"
---
```

### Rules

- `type` is explicit — lets validators distinguish docs regardless of directory. **Optional** when the doc lives in a conventional directory (validator falls back to parent-dir inference per `pitches_path` / `adr_path`).
- `domain: _global` is reserved for ADRs that cut across all domains. The validator special-cases `_global` and does **not** require it to appear in `pitches/README.md`.
- `references.pitches` filenames only (no paths). Resolved against the configured pitches location (local for spec repo, `spec_repo_path` for app repo).
- The entire `references:` block is **optional** for pitches. For ADRs it is required unless `domain: _global`.
- When present, `references.pitches` MAY be empty. Non-empty lists MUST reference files that exist at generation time — stale references are a validation error.
- A deprecated doc's references are frozen — no back-edits allowed. If the referenced pitch is superseded, the ADR stays pointing at the old filename (history snapshot) unless a new ADR is issued.

---

## Naming conventions

| Type | Path | Filename rule |
|---|---|---|
| pitch | `pitches/<domain>/…` | `YYYY-MM-DD-<slug>.md` |
| ADR | `adr/…` (flat in app repo root) | `YYYY-MM-DD-<slug>.md` |

Slug: English kebab-case, same rule as existing pitches.

---

## Reference policy

### pitch

- No required upstream. Pitches are roots.
- MAY reference earlier pitches in other domains via `references.pitches` for cross-domain coordination.

### ADR

- **MUST** reference ≥1 active pitch in `references.pitches` when the decision is scoped to a specific feature / domain.
- **MAY** set `domain: _global` and leave `references.pitches` empty for architectural decisions that cut across all features. The body must include an explicit scope statement in this case.
- An ADR without any upstream reference should explain its scope in the body. If no explanation fits, the decision may not warrant an ADR.

### ADR justification areas (cultural guidance)

ADRs absorb what v0.2's `tech-spec` legitimately captured. Four ADR-worthy justification areas — each area has its own adversarial pressure in the `/immutable:adr` interview:

| Area | Example decisions | Why ADR-worthy |
|---|---|---|
| **Rollout** | staged rollout %, feature flag strategy, kill-switch design | Choices here outlive the feature. Rollback plan is load-bearing. |
| **Observability** | metrics schema, logging cardinality, alerting thresholds | Observability shape determines what future debugging is possible. |
| **Migration** | schema migration strategy, backfill policy, double-write windows | Data migrations are one-way doors. Reversal cost is high. |
| **External-deps** | 3rd-party SDK choice, vendor lock-in boundary, API compat guarantees | External dependencies impose ongoing constraints past the initial choice. |

ADR TEMPLATE carries one worked example per area. See `adr/TEMPLATE.md`.

---

## Validation invariants

Checked at generation time by the `/immutable:adr` skill, and by CI via `scripts/validate_docs.py`:

1. **Frontmatter schema**: required fields present and typed correctly.
2. **Supersede chain integrity (per-edge)**: for each file F with non-null `F.supersedes`, the target T must (a) exist in the same doc-type set and (b) have `deprecated: true`. No cycles.
3. **No global per-(domain, type) cap on actives** (changed in v0.5.6): multiple `deprecated: false` files MAY coexist in the same domain provided each is on its own supersede chain. Fan-out (one predecessor superseded by N successors — e.g., a `refactor-split`) is permitted as long as the shared predecessor is deprecated. Rationale: 1 PRD = 1 feature/policy, and a domain naturally hosts multiple features. The previous "exactly one active per (domain, type)" cap forced domain-charter monoliths and triggered fake-domain workarounds for ADRs (see "Anti-patterns" below).
4. **Reference existence**: every filename in `references.pitches` exists at the configured pitches location.
5. **Reference policy**: ADR `references.pitches` non-empty unless the domain is declared `adr_only` in `profile.domain_allowlist.reserved_domains` (e.g., `_global`).
6. **Domain allowlist**: pitch/ADR `domain` is in `pitches/README.md`, with reserved domains special-cased (validator reads the reserved list + `adr_only` flag from the profile and skips allowlist lookup for reserved IDs).
7. **Filename format**: matches `profile.naming.filename_pattern` (default `^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$` when no profile is loaded).
8. **Body constraints**: type-specific.
   - *pitch*: forbids code identifiers (enforced by `/immutable:prd` at authoring time, not by the CI validator).
   - *pitch / ADR (skill-level guard, always on)*: at Stage 6 generation, `/immutable:prd` and `/immutable:adr` verify every `required: true` entry in `profile.(adr.)sections[]` appears as an `## <heading>` in the assembled body. Missing sections abort file generation via `(prd|adr).stage6.missing_required_section` and loop back to the interview. The guard runs only on in-flight generation — previously written files are append-only and untouched. Covers custom profile forks that add required sections beyond the default branches.
   - *pitch user-stories structure (skill-level guard, v0.5.3+)*: when `profile.sections[id=user_stories].structure == per_story_grouped` (default), `/immutable:prd` Stage 6 additionally verifies that the user-stories H2 slice contains ≥1 `### ` sub-section, each sub-section contains ≥1 bracketed normative keyword line, and no bracketed normative leaks between the H2 and the first `### `. Violations abort via `prd.stage6.missing_story_structure`. Cross-cutting sub-sections with only normative lines (no GWT) are accepted by design. For `structure: consolidated` the guard is skipped.
   - *pitch / ADR (CI validator, opt-in)*: `scripts/validate_docs.py --strict-body` scans all pitch and ADR files and flags the same missing-heading violations post-hoc. The v0.5.3+ pitch user-stories structure check activates under the same flag (profile-gated on `per_story_grouped`). Off by default for backward compatibility with v0.4 repos authored before the profile system existed.

**Profile awareness** (v0.5+): the CI validator loads the profile via the same resolution order as the skills — config.yml `profile:` → bundled `default-<team_language>.yml` → hardcoded last-resort defaults. v2 configs get the bundled default automatically; no config bump required.

---

## Profile system (v0.5, config v3)

A **profile** externalizes the authoring policy baked into skill code: section headings, adversarial review personas, 90% completeness gate criteria, code-identifier regex, filename conventions, and feature-flag vocabulary. The plugin ships reference profiles (`default-ko.yml`, `default-en.yml`, …) under `immutable/examples/_profiles/`. Teams select one via `config.yml: profile:`, or fork one into their repo and customize.

### Why profiles exist

v0.4 embedded Korean section headings, 7-criterion gate, 3-persona list, and identifier regex directly in `immutable/prd/SKILL.md`. That forced forks on any team whose (a) working language wasn't Korean, (b) section taxonomy differed, or (c) gate threshold needed tuning. The 3-tier classification below motivates the split:

| Tier | Meaning | What lives here |
|---|---|---|
| **Core-Closed** | Doctype identity. Fork is the only change path. | Append-only semantics, supersede chains, doc types (pitch + ADR), 3 core frontmatter fields |
| **Guided-Default** | Strong defaults. Overridden only when explicitly set in a profile. | Section names, RFC 2119 keywords, 3 personas, 7-criterion gate, 6-stage skeleton, filename pattern |
| **Open** | Team freedom. Skill enforces format contract only. | Domain allowlist, i18n strings, identifier regex, feature-flag prefix, frontmatter team extensions |

**Profile fields correspond to Guided-Default.** Core-Closed behavior cannot be overridden from a profile file — it's baked into the skills and the schema. Open tier is per-repo (allowlist in `pitches/README.md`, strings catalog in `strings/`, team frontmatter extensions).

### Profile file schema

```yaml
# Profile schema revision. Bumped on breaking changes to the keys below.
profile_schema: 1

# Locale matching strings/strings.<locale>.yml (enabled in v0.6+ via S3).
locale: ko | en | ja | …

# User-facing label shown in /immutable:init.
display_name: "<label>"

# Pitch body sections in render order. `id` is a stable English key referenced
# by skill logic; `heading` is rendered into the pitch file.
sections:
  - id: <snake_case_id>
    heading: "<user-facing heading>"
    required: true | false
    min_items: <int>              # minimum blocks/rows for 90% gate credit
    description: "<interview hint + gate pass condition>"
  # …

# Adversarial review personas for Stage 4.
personas:
  - id: <snake_case_id>
    name: "<user-facing name>"
    question: "<persona's central challenge>"
    checks: ["<bullet>", …]
  # …

# RFC 2119 normative keywords rendered with `[KEYWORD]` bracket syntax.
normative_keywords:
  - key: <CONSTANT>
    token: "<rendered token, e.g. 'MUST NOT'>"
    meaning: "<semantics>"

# 90% completeness gate.
gate:
  total: <int>
  pass_threshold: <int>           # e.g. 6 of 7
  reject_on_unresolved: true      # any unresolved tag blocks regardless of pass count
  unresolved_tag: "[미확정]"      # locale-specific literal
  criteria:
    - id: <snake_case_id>
      label: "<short label>"
      pass_condition: "<description>"

# Code identifier detection (Stage 3).
identifier_patterns:
  - id: <name>
    regex: '<PCRE>'
    hint: "<reviewer message>"

# Filename / slug conventions.
naming:
  filename_pattern: '<regex>'
  date_format: "<strftime>"
  slug_case: kebab | snake | camel
  slug_language: en | ko | …
  forbidden_slug_patterns:
    - id: <name>
      regex: '<PCRE>'
      reason: "<why>"

# Feature flag vocabulary.
feature_flag:
  key_prefix: "ff_"
  states: [deployed, hidden, …]
  default_initial: <state>
  required_fields: [key, states, initial_state, fallback_ux]

# Domain allowlist policy (points at `pitches/README.md`).
domain_allowlist:
  source: "pitches/README.md"
  reserved_domains:
    - id: "_shared"
      description: "<purpose>"
    - id: "_global"
      description: "<purpose>"
      adr_only: true
  new_domain_review:
    near_duplicate_threshold: <int>       # Levenshtein distance
    requires_lead_approval: true | false

# ADR-specific overrides (added v0.5 / S2).
# Top-level `sections`, `personas`, `gate`, `feature_flag` apply to /immutable:prd
# only. ADR has its own body shape (Nygard template), persona set, and 6-criterion
# gate — captured under this `adr:` block so /immutable:adr can lookup section
# headings and completeness criteria from the profile instead of hardcoding them.
adr:
  sections: [ … ]                         # ADR body sections (id, heading, required, min_items, description)
  personas: [ … ]                         # 3 ADR personas for Stage 4
  gate:                                   # ADR 6-criterion completeness gate
    total: <int>
    pass_threshold: <int>                 # e.g. 5 of 6
    reject_on_unresolved: true
    unresolved_tag: "<locale literal>"
    criteria: [ … ]
```

**v0.5 consumption scope**: `/immutable:adr` reads `adr.sections[].heading` for body assembly. `adr.personas` and `adr.gate` are populated for forward compatibility — skill text still references them inline in v0.5 to keep the diff minimal. S3+ shifts the inline strings into a strings catalog and lets profiles fully drive personas/gate.

### Profile resolution order

When a skill needs a profile, it resolves in this order:

1. `config.yml: profile:` (absolute or repo-relative path). If set and exists → load.
2. Bundled default matching `team_language` (e.g., `team_language: ko` → `immutable/examples/_profiles/default-ko.yml`).
3. Fallback to `default-en` when no matching locale profile exists (non-fatal warning).

Missing fields in a team profile fall back to the corresponding field in the matching default profile, not to hardcoded skill values. Adding new Guided-Default fields in future plugin versions is non-breaking because the skill can always fall back.

### Reference profiles

| Profile | Location | Purpose |
|---|---|---|
| `default-ko` | `immutable/examples/_profiles/default-ko.yml` | Korean working language — mirrors v0.4 hardcoded values |
| `default-en` | `immutable/examples/_profiles/default-en.yml` | English canonical — section names match the ISO baseline ("Background and Problem", "User Stories and Acceptance Criteria", …) |

Additional locales (e.g., `default-ja`) may be added without schema change.

### When to fork vs. override

- **Override (recommended)**: tweaking min_items, gate.pass_threshold, persona checks, adding a section, adjusting identifier regex. Done via a team-specific profile referenced from `config.yml`.
- **Fork**: changing Core-Closed behavior (e.g., allowing body edits, adding a third doc type, removing supersede). This requires forking the `immutable` plugin itself — profiles cannot express it.

---

## Anti-monolith escalation (v0.5.6, profile_schema 2)

A 3-tier guard that detects PRDs and ADRs which bundle multiple decisions into a single file. Operates as a profile-driven block (`anti_monolith` for pitches, `adr.anti_monolith` for ADRs).

### Why

The previous "single active per (domain, type)" cap forced a domain-charter pattern — one PRD per domain, every change requires copy-pasting the full PRD into a supersede file. Symptoms observed in dogfood: 197-line `order-history` PRD with 8 sub-sections, `settings` chain superseded 4 times in a single day, 8 cross-cutting ADRs unable to coexist because all needed `_global` (which had a single-active cap). v0.5.6 drops the cap and adds this guard so the new flexibility doesn't regress into multi-feature dumping.

### Tier semantics

| Tier | Action | Skill behavior |
|---|---|---|
| **L1** | `hint` | One-line warning at Stage 1.2 environment scan. No flow change. |
| **L2** | `strong_recommend` | Stage 1.3 intent classification surfaces `refactor-split` / `split-from` as the default option. Choosing `update` requires an explicit reason (recorded in interview transcript, not frontmatter). |
| **L3** | `block` | `update` intent is removed from the menu. Only `refactor-split` (Stage 1 only), `split-from` (Stage 1 + Stage 2), or `new` (separate small PRD) are offered. Stage 5 `concern_scope` criterion fails for in-flight drafts that exceed L3. |

### Metrics (pitch)

OR semantics — exceeding either trips the tier:

- `sub_sections` — count of `### ` headers under the user_stories H2 slice
- `normative_lines` — count of bracketed-keyword lines (`[MUST]`, `[MUST NOT]`, `[SHOULD]`, …) across the entire body

### Metrics (ADR)

OR semantics:

- `alternatives_count` — items in the alternatives section
- `consequences_count` — total positive + negative + cost-of-adoption lines

### Fallback (block omitted)

If the `anti_monolith` block is absent or `enabled: false`, thresholds are derived from `sections[user_stories].max_items`:

```
L1.sub_sections = max_items + 1
L2.sub_sections = max_items + 2
L3.sub_sections = max_items × 3
L1/L2/L3.normative_lines = sub_sections × 5    (assumes ~5 normatives per feature)
```

So a profile with only `max_items: 3` (no anti_monolith block) gets L1/L2/L3 sub_sections of 4/5/9 and normative_lines of 20/25/45 automatically.

### Skill integration

`/immutable:prd` and `/immutable:adr` consult the active profile's anti_monolith block at:

1. **Stage 1.2 environment scan** — compute metrics for every active PRD in the domain; classify into tier; surface in the pre-check message.
2. **Stage 1.3 intent classification** — when `update` would target an L2/L3 PRD, inject `refactor-split` / `split-from` ahead of `update` in the menu (L2) or remove `update` entirely (L3).
3. **Stage 5 gate** — `concern_scope` criterion checks the in-flight draft against L3; failure blocks file generation.

### Override examples

```yaml
# Strict team (single happy path features only):
anti_monolith:
  enabled: true
  tiers:
    L1: { action: hint,             sub_sections: 3, normative_lines: 15 }
    L2: { action: strong_recommend, sub_sections: 4, normative_lines: 20 }
    L3: { action: block,            sub_sections: 6, normative_lines: 30 }

# Lenient team (4-step linear flows are common, e.g., checkout/onboarding):
sections:
  - id: user_stories
    max_items: 4    # bumped from 3
# anti_monolith block omitted → derived: L1=5, L2=6, L3=12
```

---

## Anti-patterns (v0.5.6)

### Domain-charter

**Symptom**: 1 domain = 1 active PRD, treated as the domain's "constitution". Every new spec change requires a supersede that copy-pastes the entire PRD body.

**Why it's wrong**: (a) any partial change produces a 100+ line diff dominated by copy-paste noise, (b) volatile sub-scopes (e.g., a marketing-policy-driven section) drag stable sub-scopes into every supersede, (c) adversarial review effectiveness degrades on large drafts, (d) supersede frequency explodes (`settings` superseded 4× in one day during dogfood), (e) creates pressure for fake sub-domain workarounds (`_arch_layering`, `_arch_state`, …).

**Fix**: 1 PRD = 1 feature/policy. Same domain hosts multiple active PRDs, each on its own supersede chain. `refactor-split` decomposes legacy charters without semantic change.

### Fake reserved domains

**Symptom**: Adding `_arch_*`, `_concern_*`, etc. to `profile.domain_allowlist.reserved_domains` to work around a too-tight active-uniqueness cap.

**Why it's wrong**: Reserved domains were originally for system-level cross-cutting (`_global`, `_shared`); using them as decision-topic buckets bloats the profile, blurs the original meaning, and doesn't scale (every new architectural area needs a profile edit).

**Fix**: With the v0.5.6 per-edge invariant, multiple coexisting decisions in `_global` (or any domain) are valid out of the box. Add new reserved domains only when a system-level boundary truly justifies it.

### Dumping intake

**Symptom**: A single PRD that absorbs an entire Stage 1.5 intake bundle (Figma file with 30 nodes, Notion page covering 6 features, etc.).

**Why it's wrong**: The `quality_auditor` persona's "intake-volume vs output-volume" check used to flag this as "PRD too thin for the intake". Under the new model, the right action is to split the intake into multiple PRDs, not to inflate a single PRD to match.

**Fix**: When intake is broad, plan the PRD boundaries first ("intake X covers feature A + B + C → 3 PRDs"). Each PRD takes only its slice of the intake.

---

## Strings catalog (v0.5, S3)

A **strings catalog** externalizes every user-facing workflow prompt (Stage questions, refusal messages, confirmation templates, handoff blocks) that v0.4 embedded inline as Korean literals in `prd/SKILL.md`, `adr/SKILL.md`, and `init/SKILL.md`. Catalogs live at `immutable/strings/strings.<locale>.yml`. The plugin bundles `strings.ko.yml` + `strings.en.yml` (and a Japanese scaffold `strings.ja.yml`); additional locales drop in without schema changes.

### Why a catalog (separate from profiles)

Profiles (v0.5 / S1–S2) already externalized **id-bound data** — section headings, persona names/questions/checks, gate criteria labels, domain allowlist descriptions. But the prose around those data items (Stage 1 intent question, Stage 4 refusal template, Stage 7 handoff block) stayed inline Korean, which forced any non-Korean team to fork the skill. S3 lifts that remaining prose into a catalog so:

1. Adding a locale is a file addition, not a SKILL.md edit.
2. Teams can override team-specific vocabulary without forking the plugin (future `strings_path:` config field, post-S3).
3. v0.5 release polishing is scoped cleanly — SKILL.md changes ship separately from translation additions.

### 3-tier positioning

| Tier | Examples | Home |
|---|---|---|
| Core-Closed | append-only, supersede chain, doctype identity, 3 core frontmatter fields | SKILL.md + SCHEMA.md |
| Guided-Default | section names, personas, gate criteria, RFC 2119 keywords, filename patterns | **Profile YAML** |
| Open | domain allowlist, identifier regex, feature-flag prefix, **i18n strings (this catalog)**, frontmatter team extensions | Per-repo / **strings catalog** |

Strings catalog is Open: plugin-bundled defaults cover the common case; teams override by extending or forking later.

### Catalog vs. profile responsibility split

To prevent drift from duplication, each string lives in exactly one place:

| Content | Owner | Why |
|---|---|---|
| Section headings (`배경과 문제`, `Background and Problem`) | **Profile** (`sections[i].heading`) | Bound to the section `id`. Team overrides by forking a profile. |
| Persona name / question / checks[] | **Profile** (`personas[i].*`) | Bound to persona `id`. |
| Gate criterion label + pass_condition | **Profile** (`gate.criteria[i].*`) | Bound to criterion `id`. |
| Unresolved tag (`[미확정]` / `[TBD]`) | **Profile** (`gate.unresolved_tag`) | Locale-specific literal wired into gate logic. |
| Reserved domain description | **Profile** (`domain_allowlist.reserved_domains[i].description`) | Bound to domain `id`. |
| `display_name`, forbidden slug `reason` | **Profile** | Bound to their structural item's `id`. |
| Stage interview questions ("무엇을 작성...") | **Catalog** | No `id` — pure workflow prompt. |
| Refusal messages (Stage 1, Stage 5, anti-dumping) | **Catalog** | Workflow scaffolding, not data. |
| Confirmation templates (Stage 1.4, Stage 1.5 summary check) | **Catalog** | Workflow scaffolding. |
| Handoff messages (Stage 6, Stage 7) | **Catalog** | Workflow scaffolding. |
| Stage 1.5 VERBATIM context-intake block | **Catalog** | The whole block is a prompt; the verbatim contract applies to the rendered value per locale. |

**Never duplicate**: if a string is in the profile (e.g., `personas[0].name = "신입 개발자"`), SKILL.md reads it through the profile — never through the catalog. The catalog holds only SKILL.md prose.

### Schema (`strings.<locale>.yml`)

```yaml
# Schema revision — bumped on breaking changes to key layout.
schema: 1

# Locale key. Matches `team_language` in config.yml. The file's basename
# (`strings.<locale>.yml`) must match this value.
locale: ko  # | en | ja | …

# Flat, dot-notated hierarchical keys.
strings:
  <skill>.<stage>.<purpose>: |
    Multi-line value with {placeholder} interpolation.
  <skill>.<stage>.<atom>: "Single-line value."
```

### Key naming convention

`<skill>.<stage>.<purpose>` — all snake_case English.

| Segment | Values |
|---|---|
| `<skill>` | `init` / `prd` / `adr` / `common` (shared across skills) |
| `<stage>` | `stage1`..`stage6`, OR a functional group: `intake`, `gate`, `handoff`, `anti_dumping`, `probe`, `intent_desc`, `placeholder`, `consequences` |
| `<purpose>` | descriptive snake_case (e.g., `intent_question`, `refusal_template`, `summary_confirmation`) |

Rationale for flat dot-notation over nested YAML maps:
- `grep`-friendly (one key per line in usage sites)
- single-level lookup in skills (no path traversal)
- locale drift is trivially detectable by key-diffing two catalogs

### Interpolation grammar

Single-brace mustache: `{placeholder}` where `placeholder` is snake_case. The skill performs **simple dict substitution** — no conditionals, no loops.

Branching is expressed by separate keys, not by conditionals inside a value:

```yaml
# Good — two keys
prd.intent_desc.new: "새 pitch 생성으로 이해했습니다"
prd.intent_desc.update: "도메인 업데이트로 이해했습니다"

# Bad — conditional inside value (DO NOT DO)
# prd.intent_desc: "{if new}새 pitch...{else}도메인 업데이트...{/if}"
```

Literal `{` or `}` is not needed in current prompts; future need would introduce `{{` / `}}` escaping (not specified here).

### Resolution order (3-tier fallback)

When a skill needs a string, it resolves the catalog in this order:

1. **Primary catalog** — `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml` (where `team_language` comes from `.immutable-prd/config.yml`). Look up the key.
2. **English fallback** — if key missing in primary, look up in `strings.en.yml`. Emit a one-line warning (`common.fallback_warning`) to the user stream (never silent).
3. **Hardcoded fallback** — if key missing in both catalogs (only possible via plugin file corruption), the skill emits a warning and aborts the stage with a generic English message. This path should never fire in a correctly installed plugin.

The warning on step 2 is visible — missing translations surface immediately instead of degrading silently. Teams catch drift the first time a stage runs.

### Zero-action migration

v2 and v3 `config.yml` users both get strings catalog for free: the plugin resolves `${CLAUDE_PLUGIN_ROOT}/strings/strings.<team_language>.yml` regardless of config version. No config bump is required to benefit from S3. Teams wanting team-specific strings catalogs (e.g., organization-wide terminology override) are handled by a future `strings_path:` config field (post-S3, when a real use case materializes).

### Bundled catalogs

| Catalog | Location | Status |
|---|---|---|
| `strings.ko` | `immutable/strings/strings.ko.yml` | Canonical — Korean workflow prompts (SSoT for the Korean UX) |
| `strings.en` | `immutable/strings/strings.en.yml` | Canonical — English workflow prompts (also serves as fallback target) |
| `strings.ja` | `immutable/strings/strings.ja.yml` | Scaffold only — empty `strings: {}` map; every key falls back to `en` |

Add a new locale without any schema change: drop `strings.<locale>.yml` next to the existing files and (optionally) ship a matching `default-<locale>.yml` profile.

### Catalog authoring checklist

When adding or changing a catalog entry:

1. Key follows `<skill>.<stage>.<purpose>` naming.
2. Placeholders are snake_case and documented at the substitution site in SKILL.md.
3. Value does NOT duplicate a profile field (see the responsibility split table above).
4. Multi-line values use YAML block scalar (`|`) with 2-space indentation inside `strings:`.
5. For every key added to `strings.ko.yml`, a corresponding key exists in `strings.en.yml` (otherwise the primary → fallback diff produces a warning on first use).
6. SKILL.md is updated to reference the key (no inline Korean prose remains).

---

## Migration

### From v0.2 → v0.3/v0.4

Existing v0.2 repos migrate with these steps:

1. **Pitches** — unchanged. v0.3 pitch frontmatter is a superset of v0.2 (both accept the v0.2 schema).
2. **ADRs** — move `adr/` from spec repo into the app repo's root. Update `references.pitches` to remain valid via new `spec_repo_path` config.
3. **Drop 4 companion directories** — `design/`, `tech-spec/`, `status/`, `.immutable-prd/supersede-log/`. Preserve history by archiving to a `_archive/` branch if audit is needed; otherwise `git rm -r`.
4. **Config bump** — set `version: 2`, update `repo_mode` to `two-repo-spec` / `two-repo-app` / `single-repo`.
5. **Validator** — `validate_docs.py` v0.3 only knows about `pitch` and `adr`. v0.2 files for dropped types will trigger "unknown doc type" warnings (one-shot, ignorable during migration).

v0.3 makes no promise of backward compatibility for the dropped doc types. They are not "deprecated" — they are gone.

### From v0.4 → v0.5

**Zero-action path** (recommended for most teams): install v0.5 and keep `version: 2` in `config.yml`. The plugin auto-loads the default profile matching `team_language`. Behavior is identical to v0.4.

**Graduate to v3** when you want to override section headings, gate thresholds, personas, or identifier regex:

1. Run `/immutable:migrate` (available in v0.5). It bumps `version: 2 → 3` in your existing `config.yml`, copies the matching default profile into `.immutable-prd/profile.yml`, and uncomments the `profile: .immutable-prd/profile.yml` pointer. The operation is idempotent and zero-data-loss — re-running on an already-migrated repo aborts cleanly, and an existing `profile.yml` is preserved.
2. Edit `profile.yml` — change only the fields you want to diverge from the default. Unedited fields continue to fall back to the bundled default.
3. Commit both files in the same PR. Existing pitches and ADRs remain valid (no body changes required).

**Manual upgrade** (without `/immutable:migrate`):

1. Bump `version:` to `3` in `config.yml`.
2. (Optional) Add `profile: <path>` if you want an override; otherwise omit and the default profile is used.
3. (Optional) Copy `immutable/examples/_profiles/default-<locale>.yml` into your repo and customize.

**Compatibility window**: v0.5–v0.7 accept `version: 2` without complaint. v0.8 will warn, and a later release will drop the fallback — at which point `/immutable:migrate` becomes required.

### Profile field migration (v0.5.7+)

Plugin updates may add new fields to `profile_schema`. v0.5.6 introduced `profile_schema: 2` (added `sections[].max_items`, top-level `anti_monolith` block, `gate.criteria[concern_scope]`, `personas[quality_auditor]`, `adr.anti_monolith`). Teams who ran `/immutable:migrate` before this update have a frozen v1 team profile that does not benefit from the new defaults — until they re-run `/immutable:migrate` v0.5.7+.

`/immutable:migrate` v0.5.7+ has two responsibilities:

1. **Config migration** (`v2 → v3`) — unchanged from prior releases.
2. **Profile field migration** — reads the team's `profile_schema:`, compares to the bundled default, and inserts only **missing** fields. Never modifies values the team already has. Bumps `profile_schema:` to match the bundled version on success.

Idempotent. Safe to re-run after every plugin update. Override-preserving by design — explicit team choices on `min_items`, gate thresholds, persona checks, etc. survive the migration unchanged.

**Detection at authoring time**: `/immutable:prd` and `/immutable:adr` Stage 1.2 also detect `team_profile_schema < bundled_profile_schema` and surface a one-line warning recommending `/immutable:migrate`. For the in-flight authoring run, missing fields fall back to the bundled default values **with explicit source annotation in the rendered output** ("from bundled default-ko v2 — your team profile is v1") — never silent. No disk write happens at authoring time; the team profile remains the source of truth.

**Compatibility**: this is an additive change — v0.5.6 and earlier behave correctly when team profile is fully current. The v0.5.7 detection only fires when the team profile is genuinely behind.
