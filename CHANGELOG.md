# Changelog

All notable changes to the `skills` repository (and the bundled `immutable` plugin) are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for the marketplace plugin version.

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

[0.5.1]: https://github.com/choi88andys/skills/releases/tag/v0.5.1
[0.5.0]: https://github.com/choi88andys/skills/releases/tag/v0.5.0
[0.4.0]: https://github.com/choi88andys/skills/releases/tag/v0.4.0
[0.3.0]: https://github.com/choi88andys/skills/releases/tag/v0.3.0
