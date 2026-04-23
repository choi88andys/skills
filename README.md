# skills

A collection of Claude Code skills and plugins for Spec-Driven Development (SDD).

The flagship plugin is [`immutable`](immutable/) — an append-only SDD toolkit that bootstraps a starter, interviews authors for pitches and ADRs, and validates the result. v0.5 adds a `/immutable:init` bootstrap, a `/immutable:migrate` upgrade path, six bundled starters, a profile system, and a multi-locale strings catalog.

## Plugins

| Plugin | Skills | Purpose |
|---|---|---|
| [`immutable`](immutable/) | `/immutable:init`, `/immutable:prd`, `/immutable:adr`, `/immutable:migrate` | Append-only SDD — bootstrap starters, author pitches (WHAT) + Architecture Decision Records (WHY), and migrate v0.4 repos to the v0.5 profile system. Single plugin install. |

## Quick start (v0.5)

```sh
# 1. Install (once per Claude Code workspace)
claude plugin marketplace add choi88andys/skills
claude plugin install immutable

# 2. Bootstrap a starter into the current directory
mkdir my-spec && cd my-spec
/immutable:init                    # walks 7 stages: probe → mode → language → profile → copy → git → handoff

# 3. Author your first pitch
/immutable:prd                      # interview → adversarial review → 90% gate → write file

# 4. (When a load-bearing technical decision arises, in the app repo)
/immutable:adr

# 5. (Existing v0.4 repos only — once, when you want to graduate)
/immutable:migrate
```

`/immutable:init` is the recommended entry for new repos; it copies one of six bundled starters (spec / app / single × ko / en) and emits the next-step git commands. Existing v0.4 repos keep working unchanged — see [Migration (v0.4 → v0.5)](#migration-v04--v05).

## Skills

### `/immutable:init` — bootstrap

Copies one of six bundled starters into the current directory. Detects empty vs existing repo, helps select mode (spec / app / single) + team language + profile handling, copies the matching starter, and emits next-step git commands. Never overwrites existing files. Never runs git operations.

```sh
/immutable:init                          # interactive
/immutable:init single-repo English      # free-text hint pre-fills mode + language
```

Six bundled starters:

| Starter | Mode | Language | Files | Purpose |
|---|---|---|---|---|
| `spec-ko` / `spec-en` | two-repo-spec | ko / en | 5 | Spec repo (pitches only) |
| `app-ko` / `app-en` | two-repo-app | ko / en | 3 | App repo (ADRs only) |
| `single-ko` / `single-en` | single-repo | ko / en | 7 | Single repo (pitches + ADRs) |

### `/immutable:prd` — pitch authoring

Guided interview for an append-only pitch (WHAT the app should do). Walks Stage 1 intent routing → optional Stage 1.5 context intake → Stage 2 grill-me interview (Background, User Stories with Given/When/Then, normative keywords, edge cases, no-gos, optional feature flag) → Stage 3 domain-language check → Stage 4 three-persona adversarial review → Stage 5 90% completeness gate (7 criteria) → Stage 6 file generation. Refuses to write the file unless the gate passes.

```sh
/immutable:prd                              # interactive
/immutable:prd add auto-modal to notice     # free-text initial context
```

Output: `pitches/<domain>/YYYY-MM-DD-<slug>.md` in the spec repo (or `spec/pitches/...` in single-repo mode).

### `/immutable:adr` — Architecture Decision Record authoring

Guided interview for an append-only ADR (WHY a load-bearing technical direction was chosen). Uses the Nygard Context / Decision / Consequences / Alternatives template, plus revisit triggers. Three personas (new engineer, maintainer, product lead) each surface ≥1 gap. 6-criterion 90% gate refuses to write incomplete ADRs.

```sh
/immutable:adr                                          # interactive
/immutable:adr switch state management to Riverpod      # free-text initial context
```

Output: `adr/YYYY-MM-DD-<slug>.md` in the app repo. Each ADR MUST reference ≥1 active pitch unless `domain: _global`.

### `/immutable:migrate` — v0.4 → v0.5 config upgrade

Idempotent, zero-data-loss migration from config schema v2 to v3. Bumps `version: 2 → 3`, copies the bundled default profile into `.immutable-prd/profile.yml`, and uncomments the `profile:` pointer. Walks 4 stages: probe → plan preview → execute → verify+handoff. Never runs git. Never modifies pitches, ADRs, READMEs, or templates. Re-running on an already-migrated repo aborts cleanly.

```sh
/immutable:migrate                          # auto-detects config via walk-up
```

Most teams do **not** need to run this — see [Migration (v0.4 → v0.5)](#migration-v04--v05) for the zero-action path.

## Architecture

The plugin separates concerns into three layers — Core-Closed (fork-only), Guided-Default (profile YAML), and Open (per-repo + strings catalog). Authoring policy is data, not code, so teams override sections / personas / gate without forking the skill.

### Config (`.immutable-prd/config.yml`)

Lives at the target repo root, resolved via walk-up from CWD. Declares `repo_mode`, `team_language`, paths (`pitches_path`, `adr_path`, `spec_repo_path`), and an optional `profile:` pointer. v2 (v0.4) and v3 (v0.5) are both accepted; v2 auto-loads the bundled default profile matching `team_language`.

### Profiles (`immutable/examples/_profiles/default-<lang>.yml`)

Externalize section headings, adversarial personas, 90% gate criteria, RFC 2119 keywords, identifier regex, filename conventions, and feature-flag vocabulary. Bundled defaults: `default-ko.yml` (Korean) + `default-en.yml` (English). Teams override by copying a default into their repo and pointing `config.yml: profile:` at the copy. Missing profile fields fall back to the matching bundled default — adding new fields in future plugin versions is non-breaking.

### Strings catalog (`immutable/strings/strings.<locale>.yml`)

Externalizes user-facing workflow prose (Stage questions, refusal messages, confirmation templates, handoff blocks) that v0.4 embedded inline as Korean literals. Bundled catalogs: `strings.ko.yml` (canonical), `strings.en.yml` (canonical + fallback target), `strings.ja.yml` (scaffold — every key falls back to `en` until translated).

Per-string resolution: `strings.<team_language>.yml` (primary) → `strings.en.yml` (fallback, emits one-line warning) → hardcoded English in SKILL.md (last resort, never silent). Catalog and profile responsibilities never overlap — section headings stay in the profile (bound to a structural `id`), free-form prose stays in the catalog.

### Validator (`immutable/scripts/validate_docs.py`)

Stand-alone validator for pre-commit hooks and CI. Profile-aware: reads `naming.filename_pattern` and `domain_allowlist.reserved_domains` from the active profile (with bundled defaults when no profile is loaded). Exits 1 on any violation.

```sh
python3 immutable/scripts/validate_docs.py                    # auto-detect config via walk-up
python3 immutable/scripts/validate_docs.py --config <path>    # explicit config path
python3 immutable/scripts/validate_docs.py --json             # machine-readable output
python3 immutable/scripts/validate_docs.py --strict-body      # also check pitch + ADR H2 sections vs. profile, plus pitch user-stories per-story structure (off by default)
```

Coverage: frontmatter schema, supersede chain integrity, single-active-per-chain, reference existence, reference policy, domain allowlist, filename format, and (opt-in) pitch + ADR body section presence. See [`immutable/SCHEMA.md`](immutable/SCHEMA.md) for the full invariant list.

## Structure

```
skills/
├── LICENSE                                 # MIT
├── README.md                               # this file — marketplace overview + plugin index
├── .claude-plugin/
│   └── marketplace.json                    # plugin marketplace manifest (v0.5.4 — 1 plugin, 4 skills)
└── immutable/                              # the immutable plugin
    ├── .claude-plugin/
    │   └── plugin.json                     # per-plugin manifest (name, version, author, keywords) — v0.5.4+
    ├── CHANGELOG.md                        # plugin release history (Keep a Changelog)
    ├── README.md                           # plugin overview
    ├── SCHEMA.md                           # shared schema (config v2/v3, frontmatter, references, invariants, profile, strings catalog, migration)
    ├── init/SKILL.md                       # /immutable:init  — 7-stage bootstrap
    ├── prd/SKILL.md                        # /immutable:prd   — pitch authoring (6 stages)
    ├── adr/                                # /immutable:adr   — ADR authoring (5 stages)
    │   ├── SKILL.md
    │   ├── README.md
    │   └── TEMPLATE.md
    ├── migrate/SKILL.md                    # /immutable:migrate — v2 → v3 config migration (4 stages)
    ├── strings/                            # i18n workflow prose (resolution: <locale> → en → hardcoded)
    │   ├── strings.ko.yml                  # canonical Korean
    │   ├── strings.en.yml                  # canonical English + fallback target
    │   └── strings.ja.yml                  # scaffold (falls back to en)
    ├── examples/
    │   ├── _profiles/                      # bundled default profiles (Guided-Default tier)
    │   │   ├── default-ko.yml
    │   │   └── default-en.yml
    │   ├── starter/                        # six bootstrap starters consumed by /immutable:init
    │   │   ├── spec-{ko,en}/               # two-repo-spec
    │   │   ├── app-{ko,en}/                # two-repo-app
    │   │   └── single-{ko,en}/             # single-repo
    │   ├── config.yml                      # standalone reference: two-repo-spec
    │   ├── config-two-repo-app.yml         # standalone reference: two-repo-app
    │   └── config-single-repo.yml          # standalone reference: single-repo
    └── scripts/
        ├── find_config.sh                  # walk-up config detection helper
        └── validate_docs.py                # stand-alone validator (PR check / CI)
```

## Migration (v0.4 → v0.5)

**Zero-action path (recommended for most teams)**: install v0.5 and keep `version: 2` in your existing `.immutable-prd/config.yml`. The plugin auto-loads the default profile matching `team_language` (Korean → `default-ko.yml`, English → `default-en.yml`). Behavior is identical to v0.4. No file changes required.

**Graduate to v3** when you want to override section headings, gate thresholds, personas, or identifier regex:

```sh
/immutable:migrate
```

This bumps `version: 2 → 3`, seeds `.immutable-prd/profile.yml` from the bundled default, and uncomments the `profile:` pointer. Idempotent and zero-data-loss — re-running on an already-migrated repo aborts cleanly, and an existing `profile.yml` is preserved. After migration, edit only the fields you want to diverge from the default; unedited fields continue to fall back to the bundled default.

**Compatibility window**: v0.5–v0.7 accept `version: 2` without complaint. v0.8 will warn, and a later release will require `/immutable:migrate`. Full migration mechanics in [`immutable/SCHEMA.md`](immutable/SCHEMA.md#migration).

## Pre-commit / CI validation

Wire `immutable/scripts/validate_docs.py` into a pre-commit hook or CI step to catch frontmatter drift, stale references, and single-active-invariant violations before they reach main. Exits 1 on any violation. Requires `pyyaml`.

```sh
python3 immutable/scripts/validate_docs.py
```

## Local install

Clone the repo and reference the plugin directory directly, or copy `immutable/` into your Claude Code skills path. The plugin auto-resolves bundled assets (profiles, strings catalogs, starters) via `${CLAUDE_PLUGIN_ROOT}`.

## Versioning

| Release | Highlights |
|---|---|
| v0.5.4 | Multi-plugin marketplace hygiene — per-plugin manifest at `immutable/.claude-plugin/plugin.json` owns version; `marketplace.json: metadata.version` removed; CHANGELOG relocated to `immutable/CHANGELOG.md`. No user-facing feature changes. |
| v0.5.3 | Pitch authoring tightened on two axes — **shape** (`sections[user_stories].structure: per_story_grouped` default; each `### ` sub-section carries its own bullet-list normative line; ≥2 sub-sections required; enforced at Stage 6 + `--strict-body` CI) and **depth** (Stage 3 vague-word regex + inline-normative scan; 4th adversarial-review persona `quality_auditor` focused on measurable/testable criteria). Bundled profiles ship the new fields; forked v0.5.2 profiles fall back to defaults. `consolidated` preserves the v0.5.2 shape. |
| v0.5.2 | `validate_docs.py --strict-body` extended from ADR-only to pitch + ADR. CI/hook parity with the v0.5.1 skill-side guard for teams that wire the validator into pre-commit or pipelines. Still opt-in, off by default. |
| v0.5.1 | Stage 6 required-sections guard: `/immutable:prd` and `/immutable:adr` verify every `required: true` profile section appears as an `##` heading before writing. Skill-side, always on, covers pitch + ADR. Complements v0.5.0's opt-in `--strict-body` CI check. |
| v0.5.0 | `/immutable:init` + `/immutable:migrate` skills, profile system, strings catalog (ko/en/ja), 6 bundled starters, profile-aware validator with `--strict-body`. v2 configs continue to work unchanged. |
| v0.4.0 | Two-plugin layout (`immutable-prd` + `immutable`) merged into single `immutable` plugin. |
| v0.3.0 | Dropped `design`, `tech-spec`, `status`, `supersede` companion types; ADRs relocated to app repo. |

Full release history per plugin: [`immutable/CHANGELOG.md`](immutable/CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Individual skills cite their design-pattern sources. Common references:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only spec framing
