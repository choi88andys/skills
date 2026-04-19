# /immutable:adr

Guided authoring skill for append-only Architecture Decision Records (ADRs) in an `immutable` Spec-Driven Development repo.

## What this skill does

- Walks the author through a focused ADR interview (Nygard template — Context / Decision / Consequences / Alternatives / Revisit Triggers).
- Runs three-persona adversarial review (New Engineer / Maintainer / Product Lead) and a 90% completeness gate.
- Writes the ADR only when the gate passes. Never commits.
- Preserves the append-only invariant — revisions create a new file in the supersede chain; the old file's `deprecated` flag flips.

## Expected repo structure

```
<repo-root>/
├── .immutable-prd/
│   └── config.yml          # plugin config (see ../SCHEMA.md)
├── pitches/
│   ├── README.md           # domain allowlist (shared with ADRs)
│   └── <domain>/…
└── adr/
    ├── TEMPLATE.md         # seed body template
    └── YYYY-MM-DD-<slug>.md
```

ADRs live flat (no per-domain subdirectories). Domain is tagged in frontmatter, with `_global` reserved for cross-cutting decisions.

## Installation

Bundled with the `immutable` plugin in the `choi88andys/skills` marketplace. See the [top-level README](../../README.md) for marketplace installation.

## Usage

```
/immutable:adr
```

Or with initial context:

```
/immutable:adr switch state management from Provider to Riverpod
```

## Stages

1. **Intent Routing** — new / update / deprecate; scope (domain or `_global`).
2. **Context Intake** (optional) — related pitches, prior ADR chain, external docs, discussion excerpts.
3. **Interview (Nygard)** — Context / Decision / Consequences / Alternatives / Revisit Triggers / References.
4. **Adversarial Review** — three personas each surface at least one gap.
5. **90% Completeness Gate** — 6-criterion checklist. Refusal loops back to the relevant interview branch.
6. **File Generation & Handoff** — writes the file; emits commit instructions.

## Core principles

- **Speculation is forbidden.** Unknown answers become `[미확정]` tags that block file generation.
- **Alternatives are mandatory.** At least two alternatives with rejection reasons, or the decision probably doesn't need an ADR.
- **Consequences must be balanced.** At least two positive AND at least two negative — "all upside" signals an un-examined decision.

## License

MIT — see [LICENSE](../../LICENSE) at repo root.

## Credits

- Michael Nygard, *Documenting Architecture Decisions* (2011) — Context / Decision / Consequences template.
- Pattern sources documented in [SKILL.md](SKILL.md) Credits.
