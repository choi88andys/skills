# Architecture Decision Records

This directory holds the **append-only ADRs (Architecture Decision Records)** for this app repo. ADRs capture load-bearing technical directions that future engineers must understand.

> **Shared semantics**: ADRs follow the same append-only mechanics as `pitch`. Once committed, the body is immutable; revisions create a new file and flip the previous file's `deprecated` flag to `true`. For pitch-side rules, see the sibling spec repo's `CONTRIBUTING.md`.

## Authoring tool

Use `/immutable:adr`. The skill runs an interview, adversarial review, and 90% completeness gate before writing the file.

## File placement

- `adr/YYYY-MM-DD-<slug>.md` — flat structure (no per-domain subdirectories). Domain is recorded in frontmatter.
- `adr/TEMPLATE.md` — ADR template. Start new ADRs here.

## Frontmatter

```yaml
---
type: adr
domain: <name | _global>           # specific domain or _global (cross-cutting decision)
supersedes: null                    # previous filename if superseding
deprecated: false
references:
  pitches:    [<filename>, ...]    # ≥1 unless _global
  adrs:       [<filename>, ...]    # other ADR dependencies (optional)
  designs:    []
  tech_specs: []
---
```

| Field | Required | Notes |
|---|---|---|
| `type` | yes | Always `adr` |
| `domain` | yes | Domain slug or `_global` (decision crossing domain boundaries) |
| `supersedes` | yes | Previous ADR filename or `null` |
| `deprecated` | yes | `false` (active) or `true` (deprecated) |
| `references.pitches` | conditional | ≥1 unless `domain: _global` |

## Workflow

### New ADR

1. Run `/immutable:adr` → walk through the interview
2. On 90% gate pass, file is created at `adr/YYYY-MM-DD-<slug>.md`
3. PR → review → merge

### Update an ADR (direction reversal)

1. Copy the active ADR to a new filename (handled by `/immutable:adr`)
2. Set `supersedes` to the previous filename
3. Revise the body (full snapshot)
4. Flip the previous file's `deprecated: false` → `true` (one-line change only)
5. PR → review → merge

### Deprecate an ADR (no successor)

1. Flip the active ADR's `deprecated: false` → `true` only
2. Do not touch any other field or the body
3. Commit message: `chore(adr): deprecate <slug> - <reason>`

## Filename rules

- `YYYY-MM-DD-<slug>.md`
- `<slug>`: English kebab-case, **subject-based** (capture the decision subject, not the diff)
- Forbidden: `latest`, `final`, `current`, template versions (`v0.3-*`)

## Body structure (Nygard template)

See `adr/TEMPLATE.md`. Required sections:

- **Context** — the problem triggering the decision, current state, constraints
- **Decision** — a single declarative sentence
- **Consequences** — ≥2 positive AND ≥2 negative impacts
- **Alternatives Considered** — ≥2 alternatives with rejection reasons
- **Revisit Triggers** — metric / milestone / scheduled review date (≥1)

## ADR vs Pitch

| Question | Tool |
|---|---|
| **What should the app do** (user-facing promise) | Pitch (sibling spec repo) |
| **Why is the decision made this way** (load-bearing technical direction) | ADR (this repo) |

## Commit message convention

| Situation | Format |
|---|---|
| New | `feat(adr): add <slug>` |
| Update | `feat(adr): supersede <slug> - <summary>` |
| Deprecate | `chore(adr): deprecate <slug> - <reason>` |
