# Contributing — spec/

This directory holds the **append-only pitches (product promises)** for this app. ADRs (technical decision records) live separately in [`../adr/`](../adr/).

> **Single-repo note**: pitches and ADRs share the repo but are distinct doctypes. Updating a pitch does not require an ADR change, and vice versa. Both are append-only.

## Who edits

- **UX team**: GitHub **GUI (web)** only. Add or deprecate pitches.
- **Owner (engineer)**: GUI or PR.

No branch protection — mistakes are caught downstream by the owner during implementation.

---

## Core principle — Append-only

**Never edit an existing pitch file.** When something must change, write a new pitch file.

| Operation | Allowed |
|---|---|
| `deprecated: false` → `true` (deprecate) | **Allowed** (one-way only) |
| Body edit | **Forbidden** — write a new pitch instead |
| `domain` field edit | Forbidden — even typo fixes require a new pitch |
| `supersedes` field edit | Forbidden — frozen at creation time |
| `deprecated: true` → `false` (revive) | Forbidden — write a new pitch with `supersedes: <deprecated-file>` |

ADRs follow the same append-only principle. See [`../adr/README.md`](../adr/README.md).

---

## Workflow

### Create a new domain

1. Add the domain to `pitches/README.md` (lead approval required)
2. Create the directory `pitches/<domain>/`
3. Copy `pitches/TEMPLATE.md` → `YYYY-MM-DD-initial.md`
4. Set `supersedes: null`, fill in the body
5. PR → review → merge

### Update an existing pitch

1. **Copy the latest pitch file in full**
2. Save with new filename `YYYY-MM-DD-<slug>.md`
3. Set `supersedes` to the previous filename
4. Revise the body (full snapshot — additions, edits, removals all reflected)
5. Flip the previous file's `deprecated: false` → `deprecated: true`
6. PR → review → merge

### Deprecate without successor

1. Flip the latest pitch's `deprecated: false` → `deprecated: true` only
2. Do not touch any other field or the body
3. Commit message: `chore(pitch): deprecate <domain> - <reason>`

---

## Filename / slug / frontmatter / body / Feature Flag / PR checklist

This starter carries the core workflow only. For full rules, see the spec-en starter's `CONTRIBUTING.md` or the immutable plugin docs. Key points:

- **Filename**: `YYYY-MM-DD-<slug>.md`. Slug is English kebab-case, **subject-based** (not the diff)
- **Frontmatter**: `domain`, `supersedes`, `deprecated` — all required
- **Body language**: English
- **Normative keywords**: `[MUST]`, `[MUST NOT]`, `[SHOULD]`, `[SHOULD NOT]`, `[MAY]` (RFC 2119)
- **Forbidden in body**: code identifiers, file paths, class names, package names, API endpoints, design token values (domain language only)
- **Pitch size**: Feature scale (single-flag toggleable + completable in 2–6 weeks)

---

## Commit message convention

| Situation | Format |
|---|---|
| New pitch | `feat(pitch): add <domain> - <slug>` |
| Pitch update | `feat(pitch): update <domain> - <summary>` |
| Pitch deprecation | `chore(pitch): deprecate <domain> - <reason>` |
| New ADR | `feat(adr): add <slug>` |
| ADR update | `feat(adr): supersede <slug> - <summary>` |
| ADR deprecation | `chore(adr): deprecate <slug> - <reason>` |
| Repo meta | `chore: <description>` |
