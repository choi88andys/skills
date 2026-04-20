# Architecture Decision Records

This directory holds the **append-only ADRs** for this app repo. Pitches live in [`../spec/pitches/`](../spec/pitches/) (single-repo layout).

> **Shared semantics**: ADRs follow the same append-only mechanics as `pitch`. Once committed, the body is immutable; revisions create a new file and flip the previous file's `deprecated` flag to `true`. For pitch-side rules, see [`../spec/CONTRIBUTING.md`](../spec/CONTRIBUTING.md).

## Authoring tool

Use `/immutable:adr`. The skill runs an interview, adversarial review, and 90% completeness gate before writing the file.

## File placement

- `adr/YYYY-MM-DD-<slug>.md` — flat structure. Domain is recorded in frontmatter.
- `adr/TEMPLATE.md` — ADR template. Start new ADRs here.

## Frontmatter

```yaml
---
type: adr
domain: <name | _global>
supersedes: null
deprecated: false
references:
  pitches:    [<filename>, ...]    # ≥1 unless _global
  adrs:       [<filename>, ...]
  designs:    []
  tech_specs: []
---
```

| Field | Required | Notes |
|---|---|---|
| `type` | yes | Always `adr` |
| `domain` | yes | Domain slug or `_global` |
| `supersedes` | yes | Previous ADR filename or `null` |
| `deprecated` | yes | `false` (active) or `true` (deprecated) |
| `references.pitches` | conditional | ≥1 unless `domain: _global` |

In single-repo mode, `references.pitches` filenames are validated against [`../spec/pitches/`](../spec/pitches/).

## Workflow / filename / body structure

This starter carries the core overview only. For full rules, see the app-en starter's `adr/README.md` or the immutable plugin docs. Key points:

- **New / update / deprecate** — all append-only, supersede chain preserved
- **Filename**: `YYYY-MM-DD-<slug>.md`, kebab-case **subject-based** slug
- **Body**: Nygard template — Context / Decision / Consequences / Alternatives / Revisit Triggers

## ADR vs Pitch

| Question | Tool |
|---|---|
| **What should the app do** | Pitch ([`../spec/pitches/`](../spec/pitches/)) |
| **Why is the decision made this way** | ADR (this directory) |

## Commit message convention

| Situation | Format |
|---|---|
| New | `feat(adr): add <slug>` |
| Update | `feat(adr): supersede <slug> - <summary>` |
| Deprecate | `chore(adr): deprecate <slug> - <reason>` |
