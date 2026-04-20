# immutable — Append-only SDD toolkit

Single plugin hosting four skills for Spec-Driven Development with append-only guarantees: bootstrap a starter, author pitches and ADRs through guided interviews, and migrate v0.4 repos to the v0.5 profile system.

**Status**: v0.5.0. Adds `/immutable:init`, `/immutable:migrate`, profile system, strings catalog, and six bundled starters on top of the v0.4 single-plugin layout. v0.4 repos continue to work unchanged — see `../CHANGELOG.md` for the migration paths.

## Skills

| Skill | Command | Purpose | Mutability |
|---|---|---|---|
| [`init/`](init/) | `/immutable:init` | Bootstrap a starter (six modes: spec / app / single × ko / en) | Writes only into the user's CWD; never overwrites |
| [`prd/`](prd/) | `/immutable:prd` | WHAT — product pitches (6-stage interview, 3 personas, 7-criterion gate) | Append-only + supersede |
| [`adr/`](adr/) | `/immutable:adr` | WHY — Architecture Decision Records (Nygard template, 3 personas, 6-criterion gate) | Append-only + supersede |
| [`migrate/`](migrate/) | `/immutable:migrate` | v0.4 → v0.5 config migration (idempotent, zero-data-loss) | Edits `.immutable-prd/` only; never touches pitches / ADRs |

Authoring order for a typical feature:

```
/immutable:init               — bootstrap (once per repo)
        ↓
/immutable:prd                — author the pitch (spec repo)
        ↓
/immutable:adr (when load-bearing technical direction is needed) — app repo
```

`/immutable:migrate` is a one-shot upgrade for existing v0.4 repos; new repos created via `/immutable:init` are already v3.

## Installation

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install immutable
```

One install enables all four skills.

## Repository layouts

Both authoring skills consume `.immutable-prd/config.yml` at the target repo root, resolved via walk-up from CWD. Three layouts are supported:

| `repo_mode` | Pitches | ADRs | Starter |
|---|---|---|---|
| `two-repo-spec` | this repo | sibling app repo | `spec-{ko,en}` |
| `two-repo-app` | sibling spec repo (`spec_repo_path`) | this repo | `app-{ko,en}` |
| `single-repo` | this repo (`spec/pitches/`) | this repo (`adr/`) | `single-{ko,en}` |

Standalone reference configs in [`examples/`](examples/):

- [`config.yml`](examples/config.yml) — two-repo-spec
- [`config-two-repo-app.yml`](examples/config-two-repo-app.yml) — two-repo-app
- [`config-single-repo.yml`](examples/config-single-repo.yml) — single-repo

The directory name `.immutable-prd/` is retained for back-compat with the SDD_MODE_DETECT bash snippet — it's the system-level path marker, distinct from the plugin name.

## Schema, profile, strings catalog, validator

Full reference lives in [`SCHEMA.md`](SCHEMA.md):

- Document types, frontmatter fields, naming conventions
- Reference policy (pitch → ADR direction; `_global` reserved scope)
- Mutability rules + supersede chain semantics
- `config.yml` schema (v2 + v3, repo-mode-specific fields)
- Profile system — full schema, resolution order, fork vs. override
- Strings catalog — schema, key naming, responsibility split with profiles
- Validation invariants 1–8 (validator coverage)
- Migration guide v0.2 → v0.3/v0.4 → v0.5

## Design principles (shared by all four skills)

1. **Speculation is forbidden.** Unknown answers become `[미확정]` / `[TBD]` tags (locale-specific via profile) that block file generation.
2. **Append-only is cultural, not arbitrary.** History is the audit trail; mutation is the exception (single allowed in-place change: flipping `deprecated: false → true`).
3. **The author owns the commit.** Skills generate files; humans review and commit. No skill runs `git add` / `git commit` / `git push`.
4. **Quality gates are strict.** Authoring skills enforce a 90% completeness gate before writing. The 90% gate refuses generation outright — no "almost good enough" path.
5. **Configuration is data, not code.** Section headings, personas, gate criteria, and workflow prose live in profile YAML and the strings catalog. Teams override without forking the plugin.

## What v0.5 changed (vs. v0.4)

- Two new skills: `/immutable:init` (bootstrap) and `/immutable:migrate` (config upgrade).
- Profile system + strings catalog externalize what v0.4 hardcoded in SKILL.md.
- `validate_docs.py` is profile-aware and gains an opt-in `--strict-body` flag.
- v0.4 repos keep working unchanged via the zero-action path.

Full v0.4 → v0.5 release notes in [`../CHANGELOG.md`](../CHANGELOG.md).

## License

MIT — see [LICENSE](../LICENSE) at repo root.

## Credits

Pattern sources documented inside each skill's `SKILL.md` under Credits. Common sources:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only spec framing
