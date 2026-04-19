# SDD Schema — immutable plugin (v0.4)

Shared schema reference for the immutable SDD toolkit. The `/immutable:prd` skill authors pitches. The `/immutable:adr` companion authors Architecture Decision Records in the app repo.

**Status**: v0.4.0. Single-plugin release — both `prd` and `adr` skills ship in the `immutable` plugin. Schema otherwise unchanged from v0.3: 2 doc types (pitch + adr) with append-only + supersede mechanics. The `.immutable-prd/config.yml` path marker is retained for SDD_MODE_DETECT back-compat.

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

### Detection & fallback

Skills detect config via this order:

1. `./.immutable-prd/config.yml` (current working directory)
2. Walk up to repo root (`.git` marker) and retry
3. If no config found: prompt the user to create one, or fall back to inferred defaults:
   - `repo_mode: two-repo-spec` if `pitches/` exists and no `lib/` / `src/` / `app/`
   - `repo_mode: two-repo-app` if `lib/` / `src/` / `app/` exists and no `pitches/`
   - `repo_mode: single-repo` if both `pitches/` and `lib/` exist
   - `team_language: ko`

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

## Migration from v0.2

Existing v0.2 repos migrate with these steps:

1. **Pitches** — unchanged. v0.3 pitch frontmatter is a superset of v0.2 (both accept the v0.2 schema).
2. **ADRs** — move `adr/` from spec repo into the app repo's root. Update `references.pitches` to remain valid via new `spec_repo_path` config.
3. **Drop 4 companion directories** — `design/`, `tech-spec/`, `status/`, `.immutable-prd/supersede-log/`. Preserve history by archiving to a `_archive/` branch if audit is needed; otherwise `git rm -r`.
4. **Config bump** — set `version: 2`, update `repo_mode` to `two-repo-spec` / `two-repo-app` / `single-repo`.
5. **Validator** — `validate_docs.py` v0.3 only knows about `pitch` and `adr`. v0.2 files for dropped types will trigger "unknown doc type" warnings (one-shot, ignorable during migration).

v0.3 makes no promise of backward compatibility for the dropped doc types. They are not "deprecated" — they are gone.
