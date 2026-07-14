# skills

A collection of Claude Code skills and plugins for Spec-Driven Development (SDD).

The flagship plugin is [`immutable`](immutable/) — an append-only SDD toolkit covering the full 7-step flow (problem framing → pitch → app-side design → CEO-style scope review → engineering review → ADR → PR creation) using only the plugin; no external harness required.

## Plugins

| Plugin | Skills | Purpose |
|---|---|---|
| [`immutable`](immutable/) | `/immutable:init`, `/immutable:office-hours`, `/immutable:prd`, `/immutable:design`, `/immutable:plan-review-ceo`, `/immutable:plan-review-eng`, `/immutable:adr`, `/immutable:ship`, `/immutable:migrate` | Append-only SDD — bootstrap starters, run the 7-step flow from problem framing through PR creation, and migrate v0.4 repos to the v0.5 profile system. Single plugin install. |

## Quick start
```sh
# 1. Install (once per Claude Code workspace)
claude plugin marketplace add choi88andys/skills
claude plugin install immutable

# 2. Bootstrap a starter into the current directory
mkdir my-spec && cd my-spec
/immutable:init                            # 7-stage interactive bootstrap

# 3. Run the 7-step flow on your first feature

# Single-repo flow (or run steps 1-2 in spec repo, 3-7 in implementation repo):
/immutable:office-hours                    # premise + ≥3 alternatives + transient design note
/immutable:prd                             # author the pitch (WHAT)
/immutable:design                          # confirm pitch + capture app-side context
/immutable:plan-review-ceo                 # scope challenge + 11-section adversarial review
/immutable:plan-review-eng                 # 4-section engineering review + worktree analysis
/immutable:adr                             # author ADR (only when an architecture decision is surfaced)
/immutable:ship                            # pre-ship checklist + PR creation

# 4. (Existing v0.4 repos only — once, when you want to graduate)
/immutable:migrate
```

`/immutable:init` is the recommended entry for new repos; it copies one of six bundled starters (spec / app / single × ko / en) and emits the next-step git commands. Existing v0.5.x repos picked up the new flow skills immediately on install when upgrading to v0.6.0 — `/immutable:prd`, `/immutable:adr`, and `/immutable:migrate` behavior was unchanged at that point, though subsequent releases (see CHANGELOG) have since refined `/immutable:prd`'s interview and `/immutable:adr`'s description.

## Skills

### `/immutable:init` — bootstrap

Copies one of six bundled starters into the current directory. Detects empty vs existing repo, helps select mode (spec / app / single) + team language + profile handling, copies the matching starter, and emits next-step git commands. Never overwrites existing files. Never runs git operations.

```sh
/immutable:init                          # interactive
/immutable:init single-repo English      # free-text hint pre-fills mode + language
```

Six bundled starters:

| Starter | Mode | Language | Purpose |
|---|---|---|---|
| `spec-ko` / `spec-en` | two-repo-spec | ko / en | Spec repo (pitches only) |
| `app-ko` / `app-en` | two-repo-app | ko / en | App repo (ADRs only) |
| `single-ko` / `single-en` | single-repo | ko / en | Single repo (pitches + ADRs) |

Every starter carries `.github/workflows/validate-docs.yml` (v0.8.0+) — a CI gate that runs the plugin's own `scripts/validate_docs.py` over the repo's pitches and ADRs on every push and pull request, fetching it from a pinned plugin tag rather than vendoring a copy. The `app-*` workflow additionally checks out the sibling spec repo, because an app repo's ADRs reference pitches it does not itself hold; set `SPEC_REPO` at the top of the file (and, for a private spec repo, a `SPEC_REPO_TOKEN` secret). Unconfigured, it fails loudly rather than passing while checking less.

### `/immutable:office-hours` — premise challenge + 3 alternatives
Heaviest context-gather skill in the flow. Forces premise challenge then generates ≥3 implementation approaches (Minimal viable / Ideal architecture / Creative). Output is a transient design-doc note that `/immutable:prd` consumes during Stage 1.5 Context Intake. Refuses to write code; writes only the one transient note.

```sh
/immutable:office-hours                                    # interactive
/immutable:office-hours add review-request to cart         # free-text initial context
```

Output: `.claude/immutable/office-hours/{slug}.md` (gitignored).

### `/immutable:prd` — pitch authoring

Guided interview for an append-only pitch (WHAT the app should do). Walks Stage 1 intent routing → optional Stage 1.5 context intake → Stage 2 grill-me interview (Background, User Stories with Given/When/Then, normative keywords, edge cases, no-gos, optional feature flag) → Stage 3 domain-language check → Stage 4 three-persona adversarial review → Stage 5 90% completeness gate (8 criteria) → Stage 6 file generation. Refuses to write the file unless the gate passes.

```sh
/immutable:prd                              # interactive
/immutable:prd add auto-modal to notice     # free-text initial context
```

Output: `pitches/<domain>/YYYY-MM-DD-<slug>.md` in the spec repo (or `spec/pitches/...` in single-repo mode).

### `/immutable:design` — app-side context handoff
Lightweight bridge between pitch authoring and review. Confirms which pitch the implementation work targets, captures the app-side context the pitch couldn't include (activation status, dependent features, module placement), and writes a transient handoff note. Does NOT generate a design artifact — the pitch is the design artifact.

```sh
/immutable:design                                          # interactive
/immutable:design implementing review-request flow         # free-text initial context
```

Output: `.claude/immutable/design/{slug}.md` (gitignored).

### `/immutable:plan-review-ceo` — scope challenge + 11-section review
Adversarial CEO-style review of the implementation plan grounded in the pitch + linked ADRs + design handoff. Phase 0 nuclear scope challenge (premise / existing-code leverage / dream-state / **mandatory alternatives** / mode selection EXPANSION/SELECTIVE/HOLD/REDUCTION). Phase 2 walks 11 sections (Architecture, Error & Rescue Map, Security, Data Flow, Code Quality, Test, Performance, Observability, Deployment, Long-Term, UX). Phase 3 surfaces pitch-supersede candidates (route to spec repo) and ADR-authoring candidates.

```sh
/immutable:plan-review-ceo
```

Output: `.claude/immutable/plan-review/{slug}-ceo.md` (gitignored) with verdict APPROVE / REVISE / REJECT.

### `/immutable:plan-review-eng` — engineering review
Runs engineering rigor on the agreed scope in one of two modes: "ceo-grounded" (after CEO APPROVE, using the CEO scope envelope) or "standalone" (no prior CEO review; reviews the pitch directly with a built-in lightweight scope check). Walks 4 sections (Architecture-eng / Code Quality / Test Coverage Diagram / Performance) plus a worktree parallelization analysis (dependency table + parallel lanes + execution order + conflict flags). Surfaces ADR-authoring candidates.

```sh
/immutable:plan-review-eng
```

Output: `.claude/immutable/plan-review/{slug}-eng.md` (gitignored).

### `/immutable:adr` — Architecture Decision Record authoring

Guided interview for an append-only ADR (WHY a load-bearing technical direction was chosen). Uses the Nygard Context / Decision / Consequences / Alternatives template, plus revisit triggers. Three personas (new engineer, maintainer, product lead) each surface ≥1 gap. 6-criterion 90% gate refuses to write incomplete ADRs.

```sh
/immutable:adr                                          # interactive
/immutable:adr switch state management to Riverpod      # free-text initial context
```

Output: `adr/YYYY-MM-DD-<slug>.md` in the app repo. Each ADR MUST reference ≥1 active pitch unless `domain: _global`.

### `/immutable:ship` — pre-ship verification + PR creation
Final step in the 7-step flow. Runs pre-ship checklist (branch sanity, commit hygiene), verifies review artifacts (eng note must be APPROVE), runs build + test for the auto-detected project type (Flutter / iOS / Node / Python / Rust / Go), and composes a PR body that auto-includes the pitch path + linked ADR paths + Test Coverage Diagram + deferred items from CEO Phase 3. Calls `gh pr create` only after explicit user confirmation.

```sh
/immutable:ship
```

Refuses with structured options when: tests fail, eng review didn't APPROVE, working tree is dirty, or the current branch is `main`/`master`/`develop`.

### `/immutable:migrate` — v0.4 → v0.5 config upgrade

Idempotent, zero-data-loss migration covering both config schema (v2 → v3) and team profile field schema. Bumps `version: 2 → 3`, copies the bundled default profile into `.immutable-prd/profile.yml`, uncomments the `profile:` pointer, and structurally diffs team profile against bundled default to add only missing fields (override-preserving — existing values never modified). Walks the stages probe → plan preview → config execute → verify → profile field migration → handoff. Never runs git. Never modifies pitches, ADRs, READMEs, or templates. Re-running on an already-migrated repo aborts cleanly.

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

The plugin follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Version is canonically declared in [`immutable/.claude-plugin/plugin.json`](immutable/.claude-plugin/plugin.json). Full release history with migration notes lives in [`immutable/CHANGELOG.md`](immutable/CHANGELOG.md) — single source of truth, no duplicate version table here.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

`immutable` is built from two layered fusions: the **`immutable-prd` lineage** that reconciles append-only pitches with mutable-PRD accuracy via supersede chains (the active artifact reflects current understanding while the chain preserves full revision history), and the **gstack lineage** that contributed a transient → artifact flow pipeline (working notes feed permanent decisions; uncertainty is absorbed before promotion). The plugin README documents the full heritage at [`immutable/README.md` Design heritage](immutable/README.md#design-heritage).

Individual skills cite their design-pattern sources. Common references:

- gstack (internal harness) — flow shape, multi-persona adversarial review, 90% completeness gate
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only pitch framing
