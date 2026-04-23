# Changelog — immutable plugin

All notable changes to the `immutable` plugin are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the plugin follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Version is canonically declared in `.claude-plugin/plugin.json`.

## [0.5.4] — 2026-04-23

Hygiene release for multi-plugin marketplace readiness. No user-facing feature changes — this release restructures manifests and documentation so the `skills` marketplace repo can host additional plugins alongside `immutable` without ambiguity around versioning or changelogs. Existing `/immutable:*` skills, profiles, starters, and validator behavior are unchanged from v0.5.3.

### Added

- **`immutable/.claude-plugin/plugin.json`** — canonical per-plugin manifest declaring `name`, `version`, `description`, `author`, `license`, `homepage`, `repository`, `keywords`. Claude Code's version resolution uses this file first ("plugin.json takes priority" per `plugins-reference` docs), giving each plugin a single source of truth for version independent from the marketplace manifest.

### Changed

- **`.claude-plugin/marketplace.json`** — removed `metadata.version` root field. It was effectively `immutable`'s version under a non-standard location (Anthropic's own multi-plugin marketplace does not use it). Version now lives in `immutable/.claude-plugin/plugin.json` exclusively.
- **`CHANGELOG.md` relocated** — top-level `CHANGELOG.md` moved to `immutable/CHANGELOG.md` so each future plugin can own its own changelog. The marketplace repo may keep a slim top-level CHANGELOG for marketplace-level events (plugin added / removed / renamed) going forward.
- **`README.md`** — Versioning table row updated to v0.5.4 with multi-plugin hygiene note.

### Removed

- **`marketplace.json: metadata.version`** — see Changed.

### Migration

- **End users of `immutable`**: no action required. `claude plugin list` will display `Version: 0.5.4` (previously showed the install-time commit SHA fallback, e.g., `34dae9d34574`) after the next marketplace sync. Users with auto-update disabled run `/plugin marketplace update skills` (or the Marketplaces tab's "Update marketplace" button) and then `Update now` on the Installed tab.
- **Marketplace maintainers adding a 2nd plugin later**: each new plugin owns its version via its own `<plugin>/.claude-plugin/plugin.json`. Git tags follow the official `{name}--v{version}` convention produced by `claude plugin tag`.

## [0.5.3] — 2026-04-23

Patch release: tightens pitch authoring along two independent axes — **shape** (the per-story structure of the user-stories section) and **depth** (detail level proportional to complexity). Motivated by observed drift patterns across real pitches: bottom-consolidated normative bundles divorced from their stories, inline prose-style `[MUST]` that breaks grep/CI extraction (especially in Korean output from some models), vague hedge words that push interpretation onto implementers, and shallow normative counts in complex domains.

### Added

- **`profile.sections[id=user_stories].structure` field** (`per_story_grouped` | `consolidated`; default `per_story_grouped`). Declared in `immutable/examples/_profiles/default-ko.yml` and `default-en.yml` with inline documentation of both values and the enforcement sites (Stage 2, Stage 6 guard, validator).
- **Stage 6 pre-write structure guard** in `/immutable:prd`. Runs after the required-sections guard, only when `structure == per_story_grouped`. Enforces:
  - ≥2 `### ` sub-sections under the user-stories H2 (matches `min_items = 2`);
  - each `### ` sub-section carries ≥1 **bullet-list** bracketed normative line (`- **[MUST]** …`); inline paragraph normative is flagged separately as a drift signal;
  - no bracketed normative leakage between the H2 and the first `### `.
  Aborts file generation on violation and loops back to Stage 2 Branch B. Cross-cutting normative-only sub-sections are accepted (e.g., "shared result-code handling") — the guard does not require GWT inside every sub-section.
- **Stage 3 vague-word detection** — `profile.vague_words[]` carries locale-specific hedge-word regex lists (ko: `적절히`, `자연스럽게`, `충분히`, `가능한`, `합리적`, `일반적`, `최대한`, `필요에 따라`, `상황에 맞게`, `안전하게`, `부드럽게`; en: `appropriate(ly)`, `reasonabl(e|y)`, `natural(ly)`, `sufficient(ly)`, `as needed`, `etc.`/`and so on`, `smooth(ly)`, `safe(ly)`, `general(ly)`). On hit, Stage 3 renders `prd.stage3.vague_word_warning` and loops back to the relevant Branch. Skill-side only — not enforced by `validate_docs.py` (semantic noise would break CI predictability).
- **Stage 3 inline-paragraph normative scan** — catches `[MUST]` embedded in prose (the Korean-drift pattern) during authoring, renders `prd.stage3.inline_normative_warning`, and requires re-writing in bullet form before Stage 4.
- **4th adversarial-review persona `quality_auditor`** — appended to `profile.personas[]` in both bundled profiles. Question: "Can this pitch be implemented and verified against measurable criteria, with no clauses requiring subjective judgment?" Checks cover concrete-value density, context-vague hedge phrases (semantic complement to the Stage 3 regex), Then pass/fail decidability, hidden passive-voice actors, and depth-to-complexity balance. Stage 4 header updated from "(3 Personas)" to "(4 Personas)".
- **Stage 2 Branch B authoring guidance** — elicits per-sub-section normative lines alongside the GWT triple so Stage 6 assembly has the material the guard expects.
- **Stage 4 minimum-only explicit** — existing "each persona MUST surface ≥1 gap" clarified as a minimum (not a cap); LLM continues surfacing every non-trivial gap for complex pitches.
- **`validate_docs.py --strict-body` structure check (pitch only)** — mirrors the skill-side Stage 6 guard so teams wiring the validator into pre-commit hooks or CI pipelines catch the same violations post-hoc. Still gated on `--strict-body` (opt-in); activates only when the profile sets `structure == per_story_grouped`.
- **New strings** in `strings.en.yml` and `strings.ko.yml`: `prd.stage6.missing_story_structure` (expanded to cover bullet-only + min-2 rules), `prd.stage3.vague_word_warning`, `prd.stage3.inline_normative_warning`.

### Changed

- **Starter TEMPLATE.md files** — `spec-{ko,en}/pitches/TEMPLATE.md` and `single-{ko,en}/spec/pitches/TEMPLATE.md` rewrite the user-stories section to demonstrate `per_story_grouped` layout (two `### ` sub-sections, each carrying a GWT triple + bracketed MUST list on bullet lines). Inline HTML comment documents the `consolidated` alternative.
- **`prd/SKILL.md` profile-field table** — adds rows for `sections[id=user_stories].structure` and `vague_words[].regex / hint`.
- **`SCHEMA.md` invariant 8** — widened body-constraint description to cover the v0.5.3 per-story structure check alongside the existing required-sections check.

### Migration

- **Zero-action path (recommended)** — install v0.5.3 and keep your existing config. The bundled default profiles ship `structure: per_story_grouped` and the new `vague_words[]` + `quality_auditor` persona automatically. New pitches generated through `/immutable:prd` adopt the per-story, bullet-only layout by default. Existing pitches are append-only and untouched.
- **Teams with repo-local forked profiles from v0.5.2** — the new fields (`sections[id=user_stories].structure`, `vague_words[]`, `personas[id=quality_auditor]`) are missing from your fork. Missing fields fall back to bundled defaults — no config change required. To opt out of the structure guard explicitly, add `structure: consolidated` to the `user_stories` section in your profile.
- **Teams running `--strict-body` in CI** — the new pitch structure check activates under the same `--strict-body` flag. Existing pitches authored in v0.5.2 shape (consolidated, bold-label, or inline-normative) will fail the check. Options: flip the profile to `structure: consolidated`, supersede the affected pitches with per-story-grouped versions, or stop passing `--strict-body` in CI until migration completes.

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.2] — 2026-04-22

Patch release: extends `validate_docs.py --strict-body` from ADR-only to pitch + ADR. Achieves CI/hook parity with the v0.5.1 skill-side guard for teams that wire the validator into pre-commit hooks or pipelines. Still opt-in (off by default). No config changes; no migration needed.

### Changed

- **`validate_docs.py --strict-body`** now validates pitch bodies in addition to ADR bodies. Every `profile.sections[i].required == true` entry (pitch) and `profile.adr.sections[i].required == true` entry (ADR) must appear as an `##` heading. Violation message labels the doctype (`missing required pitch section` / `missing required ADR section`). Off by default — behavior unchanged for teams that don't use the flag.
- **`SCHEMA.md` invariant 8 (CI validator clause)** — scope widened from ADR to pitch + ADR; backward-compat note widened from "v0.4 ADRs" to "v0.4 repos".
- **`validate_docs.py` internal refactor** — `validate_adr_body` renamed to `validate_body_headings` (doctype-agnostic). Shared `_extract_required_headings` helper backs both `profile_required_adr_headings` and the new `profile_required_pitch_headings`.

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.1] — 2026-04-22

Patch release: adds a Stage 6 skill-side guard that verifies required section headings are present in the assembled body before `/immutable:prd` and `/immutable:adr` write the file. Complements the v0.5.0 opt-in `--strict-body` CI check by catching missing sections at generation time. No config changes; no migration needed.

### Added

- **Stage 6 required-sections guard (pitch + ADR)** — always-on, skill-side. Iterates `profile.(adr.)sections[]` and fails generation if any `required: true` entry is missing as an `## <heading>` in the body. Aborts without writing the file or flipping `deprecated`, and loops back to the interview (Stage 2 for pitch, Stage 3 for ADR). Covers custom profile forks that add required sections beyond the default branches. Skill-side complement to v0.5.0's ADR-only `--strict-body` CI check.
- **New strings** — `prd.stage6.missing_required_section` and `adr.stage6.missing_required_section` in `strings.en.yml` and `strings.ko.yml`, with `{missing_headings}` placeholder rendering the ordered list of absent `##` lines.

### Changed

- **`SCHEMA.md` invariant 8** — split into two clauses: skill-side guard (always on, both doctypes) and CI-side `--strict-body` (opt-in, ADR only).
- **`prd/SKILL.md` and `adr/SKILL.md` profile-field tables** — the `sections[].id / required / min_items / description` row now reflects that `required` is consumed at Stage 6 by the guard (in addition to the Stage 2/3 interview branches).

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.0] — 2026-04-20

The "foundation" release: extends the v0.4 two-skill toolkit into a four-skill bootstrap-able plugin with externalized configuration. v0.4 repos keep working without any change — every new surface is opt-in.

### Added

- **`/immutable:init`** — 7-stage bootstrap skill (probe → mode → language → profile → copy → git → handoff). Copies one of six bundled starters into the current directory. Never overwrites existing files. Never runs git operations.
- **`/immutable:migrate`** — 4-stage idempotent v0.4 → v0.5 config migration (probe → plan preview → execute → verify+handoff). Bumps `config.yml: version: 2 → 3`, copies the bundled default profile into `.immutable-prd/profile.yml`, and uncomments the `profile:` pointer. Re-running on an already-migrated repo aborts cleanly. Existing `profile.yml` is preserved.
- **Profile system** — `immutable/examples/_profiles/default-{ko,en}.yml` externalize section headings, adversarial personas, 90% gate criteria, RFC 2119 keywords, identifier regex, filename conventions, and feature-flag vocabulary. Teams override selected fields by copying a default profile into their repo and pointing `config.yml: profile:` at the copy. Missing fields fall back to the matching bundled default.
- **Strings catalog** — `immutable/strings/strings.{ko,en,ja}.yml` externalize user-facing workflow prose (Stage questions, refusal messages, confirmation templates, handoff blocks). Resolution order per string: `<team_language>` → `en` → hardcoded English in SKILL.md (with one-line warning at each fallback step — never silent). `strings.ja.yml` ships as an empty scaffold; every key falls back to `en` until translated.
- **Six bundled starters** — `immutable/examples/starter/{spec,app,single}-{ko,en}/` consumed by `/immutable:init`. File counts: spec = 5, app = 3, single = 7.
- **Config schema v3** — adds an optional `profile: <path>` field. v2 configs (without `profile:`) continue to work unchanged; the plugin auto-loads the bundled default matching `team_language`.
- **`validate_docs.py --strict-body`** — opt-in CI check that every `profile.adr.sections[].required == true` entry appears as an `##` heading in each ADR body. Off by default for backward compatibility with v0.4 ADRs authored before the profile system existed.

### Changed

- **`validate_docs.py` is now profile-aware**. The hardcoded filename regex is replaced with `profile.naming.filename_pattern`. The hardcoded `_global` special-case is replaced with `profile.domain_allowlist.reserved_domains[].adr_only`. v2 configs auto-load the bundled `default-<team_language>.yml` profile — no config bump required.
- **`/immutable:prd` and `/immutable:adr` SKILL.md** are now profile-aware AND catalog-aware. Section headings, persona names/questions/checks, gate criteria, identifier regex, and filename rules are looked up from the active profile rather than hardcoded into the skill text. Stage questions, refusal messages, confirmation templates, and handoff blocks are looked up from the strings catalog. Inline Korean prose has been removed.
- **`marketplace.json`** registers `./init` and `./migrate` skill paths in addition to `./prd` and `./adr`. Plugin description and keywords expanded to surface the new bootstrap and migration capabilities.
- **`SCHEMA.md`** documents the v3 config field, the profile system (Profile resolution order, reference profiles, when to fork vs. override), the strings catalog (resolution order, responsibility split with profiles, key naming convention), the v0.4 → v0.5 migration paths, and the rewritten validation invariants 5–8.

### Migration (v0.4 → v0.5)

- **Zero-action path (recommended for most teams)** — install v0.5 and keep `version: 2` in your existing `.immutable-prd/config.yml`. The plugin auto-loads the bundled default profile that matches your `team_language` (`ko` → `default-ko.yml`, `en` → `default-en.yml`). Behavior is identical to v0.4.
- **Graduate to v3** — run `/immutable:migrate` to bump `version: 2 → 3`, seed `.immutable-prd/profile.yml` from the bundled default, and uncomment the `profile:` pointer. Idempotent and zero-data-loss. After migration, edit only the fields you want to diverge from the default — unedited fields continue to fall back to the bundled default.
- **Compatibility window** — v0.5–v0.7 accept `version: 2` without complaint. v0.8 will warn, and a later release will require `/immutable:migrate`. No deprecations in v0.5.

### Deprecated

None. The hardcoded `_global` special-case in the v0.4 validator is replaced by the profile-driven `domain_allowlist.reserved_domains[].adr_only` flag, but the `_global` ADR scope itself is preserved (it is now declared in the bundled default profiles).

### Removed

None.

### Fixed

None.

## [0.4.0]

Single-plugin merge: the v0.3 two-plugin layout (`immutable-prd` + `immutable`) was unified into one `immutable` plugin. One install, one enable step, consistent `/immutable:*` namespace. Behavior, schema, and config format unchanged from v0.3.

## [0.3.0]

Append-only foundation: dropped four of the v0.2 companion doc types (`design`, `tech-spec`, `status`, `supersede`) — duplicated against pitch / Figma / code or derivable from PR state and feature flags. ADRs relocated from the spec repo into the app repo. `/immutable:prd` absorbed pitch supersession; cross-doc cascades are rare with two doc types.

## [0.2.0] and earlier

Pre-public iterations — see `git log` for history.

[0.5.4]: https://github.com/choi88andys/skills/releases/tag/immutable--v0.5.4
[0.5.3]: https://github.com/choi88andys/skills/releases/tag/v0.5.3
[0.5.2]: https://github.com/choi88andys/skills/releases/tag/v0.5.2
[0.5.1]: https://github.com/choi88andys/skills/releases/tag/v0.5.1
[0.5.0]: https://github.com/choi88andys/skills/releases/tag/v0.5.0
[0.4.0]: https://github.com/choi88andys/skills/releases/tag/v0.4.0
[0.3.0]: https://github.com/choi88andys/skills/releases/tag/v0.3.0
