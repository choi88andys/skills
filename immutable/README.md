# immutable — Append-only SDD toolkit

Single plugin hosting two skills for Spec-Driven Development with append-only guarantees.

**Status**: v0.4.0. Merges the v0.3 two-plugin layout (`immutable-prd` + `immutable`) into one plugin with a unified `immutable:` namespace.

## Skills

| Skill | Command | Purpose | Mutability |
|---|---|---|---|
| [`prd/`](prd/) | `/immutable:prd` | WHAT — product pitches | Append-only + supersede |
| [`adr/`](adr/) | `/immutable:adr` | WHY — Architecture Decision Records | Append-only + supersede |

Together they form the v0.4 SDD output surface:

```
 pitch (/immutable:prd)      ADR (/immutable:adr)
       WHAT                         WHY — load-bearing technical direction
```

## Installation

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install immutable
```

One plugin install covers both `/immutable:prd` and `/immutable:adr`.

## Repository layouts

Both skills consume `.immutable-prd/config.yml` at the target repo root. Three example configs in [`examples/`](examples/):

- [`config.yml`](examples/config.yml) — two-repo mode, spec repo side (pitches)
- [`config-two-repo-app.yml`](examples/config-two-repo-app.yml) — two-repo mode, app repo side (ADRs)
- [`config-single-repo.yml`](examples/config-single-repo.yml) — single-repo mode (both in one repo)

The config directory name `.immutable-prd/` is retained for back-compat with the SDD_MODE_DETECT bash snippet — it's the system-level path marker, distinct from the plugin name.

## Authoring order

Typical feature lifecycle:

```
pitch                                        — /immutable:prd (spec repo)
  ↓
ADR (if tech direction is load-bearing)      — /immutable:adr (app repo)
```

See [`SCHEMA.md`](SCHEMA.md) for shared schema — frontmatter, reference policy, repo layouts, mutability rules, migration guide.

## Design principles (shared by both skills)

1. **Speculation is forbidden.** Unknown answers become `[미확정]` tags that block file generation.
2. **Append-only is cultural, not arbitrary.** History is the audit trail; mutation is the exception.
3. **The author owns the commit.** Skills generate files; humans review and commit.
4. **Quality gates are strict.** Every skill enforces a 90% completeness gate before writing.

## What v0.4 changed

| v0.3 | v0.4 |
|---|---|
| 2 plugins (`immutable-prd` + `immutable`) | 1 plugin (`immutable`) |
| `/immutable-prd:immutable-prd` + `/immutable:adr` | `/immutable:prd` + `/immutable:adr` |
| 2 install + 2 enable steps | 1 install + 1 enable step |

Behavior, schema, and config format are unchanged. v0.4 is a structural rename release.

## What v0.3 dropped (retained rationale)

v0.2 shipped 5 companion types (`adr`, `design`, `tech-spec`, `status`, `supersede`). v0.3 dropped 4:

| Dropped | Replacement |
|---|---|
| `tech-spec` | ADR absorbs the 4 ADR-worthy areas (rollout, observability, migration, external-deps) |
| `design` | Pitch TEMPLATE optional sections absorb genuine gaps (accessibility intent, motion intent) |
| `status` | Derive from PR state, feature flags, git tags — not prose |
| `supersede` | `/immutable:prd` handles pitch supersession; cross-doc cascades are rare with 2 doc types |

Guiding rule: **if the source of truth lives in code or tooling, don't create a parallel prose file.**

## License

MIT — see [LICENSE](../LICENSE) at repo root.

## Credits

Pattern sources documented inside each skill's `SKILL.md` under Credits. Common sources:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only spec framing
