# SDD Schema — immutable plugin (v0.5 preview)

Shared schema reference for the immutable SDD toolkit. The `/immutable:prd` skill authors pitches. The `/immutable:adr` companion authors Architecture Decision Records in the app repo.

**Status**: v0.4 base schema. v0.5 introduces **config schema v3** — an optional profile system that externalizes what v0.4 hardcoded into skill code (section headings, adversarial personas, 90% gate thresholds, identifier regex, filename conventions). Doc types, append-only semantics, and supersede chain rules are unchanged.

**Compatibility**: v2 configs (`version: 2`, no `profile:` field) continue to work without modification. The plugin auto-loads the default profile that matches `team_language` — zero action required. Teams can graduate to v3 by running `/immutable:migrate` (S4 deliverable) or by hand-editing `.immutable-prd/config.yml`.

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
- Changes require a **new file** in the same chain via `supersedes: <previous-filename>`.
- The supersede chain is strict: at most one `deprecated: false` file per chain at any time.
- Deleting an old file is forbidden — history is the audit trail.

### Cultural guidance (not mechanical)

- Both pitch and ADR expect **rare** supersession. Each new version is a load-bearing policy shift. Reviewers push back hard.
- Frequent churn on either type signals either (a) the decision wasn't load-bearing enough to warrant a file, or (b) the original framing missed something — both warrant a review conversation, not a quiet rewrite.

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
├── spec/                    # subtree housing pitches
│   ├── pitches/
│   │   ├── README.md
│   │   ├── TEMPLATE.md
│   │   └── <domain>/YYYY-MM-DD-<slug>.md
│   └── .immutable-prd/
│       └── config.yml
├── adr/                     # ADRs live at app repo root (alongside code)
│   ├── TEMPLATE.md
│   └── YYYY-MM-DD-<slug>.md
└── lib/
```

In single-repo mode a single `config.yml` declares both `pitches_path` and `adr_path`.

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
- running `/immutable:migrate` (S4) which performs the bump and seeds a default-copy profile file.

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
2. **Supersede chain integrity**: `supersedes` target exists in the same directory, has `deprecated: true`, and no cycles.
3. **At most one active per chain**: per (domain, type), exactly one file has `deprecated: false`.
4. **Reference existence**: every filename in `references.pitches` exists at the configured pitches location.
5. **Reference policy**: ADR `references.pitches` non-empty unless `domain: _global`.
6. **Domain allowlist**: pitch/ADR `domain` is in `pitches/README.md`, with `_global` reserved (allowed for ADRs only, validator special-cases and skips the allowlist lookup).
7. **Filename format**: matches `YYYY-MM-DD-<kebab-slug>\.md`.
8. **Body constraints**: type-specific (pitch forbids code identifiers; ADR requires Context / Decision / Consequences / Alternatives sections).

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
```

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

1. Run `/immutable:migrate` (S4). It bumps `version: 2 → 3` in your existing `config.yml`, copies the matching default profile into `.immutable-prd/profile.yml`, and adds a pointer `profile: .immutable-prd/profile.yml`.
2. Edit `profile.yml` — change only the fields you want to diverge from the default.
3. Commit both files in the same PR. Existing pitches and ADRs remain valid (no body changes required).

**Manual upgrade** (without `/immutable:migrate`):

1. Bump `version:` to `3` in `config.yml`.
2. (Optional) Add `profile: <path>` if you want an override; otherwise omit and the default profile is used.
3. (Optional) Copy `immutable/examples/_profiles/default-<locale>.yml` into your repo and customize.

**Compatibility window**: v0.5–v0.7 accept `version: 2` without complaint. v0.8 will warn, and a later release will drop the fallback — at which point `/immutable:migrate` becomes required.
