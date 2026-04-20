# Contributing

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

---

## Workflow

### Create a new domain

1. Add the domain to `pitches/README.md` (lead approval required)
2. Create the directory `pitches/<domain>/`
3. Copy `pitches/TEMPLATE.md` → `YYYY-MM-DD-initial.md`
4. Set `supersedes: null`, fill in the body
5. PR → review → merge (or commit directly via GUI)

### Update an existing pitch

1. **Copy the latest pitch file in full**
2. Save with new filename `YYYY-MM-DD-<slug>.md`
3. Set `supersedes` to the previous filename
4. Revise the body (the new file is a **full snapshot** — additions, edits, removals all reflected)
5. Flip the previous file's `deprecated: false` → `deprecated: true` (do not touch body or other fields)
6. PR → review → merge

### Deprecate without successor

1. Flip the latest pitch's `deprecated: false` → `deprecated: true` only
2. Do not touch any other field or the body
3. Commit message: `chore(pitch): deprecate <domain> - <reason>`
4. PR → review → merge

---

## Filename rules

### Format

- `YYYY-MM-DD-<slug>.md`
- `YYYY-MM-DD`: the date this pitch version was first authored
- `<slug>`: English kebab-case, **subject-based**
- The filename IS the version identifier. Versioning is carried by the date prefix + `supersedes` frontmatter

### Slug — Subject-based naming

The slug captures **"what is this file a spec of"** — never the diff (delta) from the previous version.

**Rationale**: each pitch is a full snapshot (additions, edits, removals all reflected), so it must be a **self-contained SSoT**. Delta-describing slugs reduce a file to "a fragment of change history" and undermine standalone readability. ADR (Nygard / MADR), IETF RFC, and major enterprise design-doc conventions all use subject-based naming.

**Allowed**

| Class | Example | Notes |
|---|---|---|
| Baseline | `initial` | First version — fine when the domain itself is the subject |
| Subject-based | `order-history-and-receipts`, `partial-refund`, `push-subscription-management` | Capture the feature in kebab-case. Some redundancy with the domain name is OK |
| Version counter | `rev2`, `v3` | When the subject is unchanged but the document is being refined (IETF style) |

**Forbidden**

- Delta-describing slugs: `figma-alignment`, `policy-update`, `code-aligned`, `v0.3-sections`
- Harness/template version references: `v0.3-*`
- Timeliness-bound terms: `latest`, `final`, `current`

**Where delta information lives** (not in the filename)

1. `supersedes` frontmatter — the previous filename
2. Commit message — `feat(pitch): update <domain> - <summary>`
3. (Optional) `## Change log` section at the top of the body

## YAML frontmatter (required)

Required at the top of every pitch file.

```yaml
---
domain: <name>                      # must match parent directory
supersedes: null                    # null if no predecessor; else previous filename
deprecated: false                   # default false
---
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `domain` | string | yes | Domain slug (matches parent directory) |
| `supersedes` | string or null | yes | Previous filename (e.g., `2026-04-16-initial.md`) or `null` |
| `deprecated` | boolean | yes | `false` (active) or `true` (deprecated). Default `false` |

---

## Pitch size (Goldilocks)

**Feature scale**: independent user value + completable in one release cycle (2–6 weeks).

| Scale | Example | Verdict |
|---|---|---|
| Epic (too big) | "Payments overhaul" | Forbidden — split required |
| **Feature** | "Cart partial refund" | **Ideal unit** |
| Task (too small) | "Refund button color change" | Not a pitch |

**Splitting test**: "Can this entire feature be toggled on/off by a single feature flag?" If no, split.

---

## Feature flags

### State vocabulary

| State | Meaning |
|---|---|
| `deployed` | Feature exposed to all users (default) |
| `hidden` | Hidden from all users (kill switch / in-development / emergency rollback) |

### Pitch body Feature Flag section

Only pitches that use a flag include the `## Feature Flag` section. Pitches without flags omit the section entirely.

---

## Body conventions

### Language

- Body: **English**
- Binding statements use **the 5 RFC 2119 keywords** with bracket syntax. Other phrasing is non-binding.

### Normative keyword guide

| Keyword | Meaning | Example |
|---|---|---|
| **[MUST]** | Required, no exceptions | **[MUST]** The system shows the notice list newest-first. |
| **[MUST NOT]** | Forbidden | **[MUST NOT]** The system shows deprecated notices in the list. |
| **[SHOULD]** | Recommended; justified exceptions allowed | **[SHOULD]** The system inserts a line break in questions over 22 chars. |
| **[SHOULD NOT]** | Discouraged | **[SHOULD NOT]** The system surfaces raw technical errors to users. |
| **[MAY]** | Optional | **[MAY]** The system displays an illustration when the list is empty. |

This document (CONTRIBUTING.md) is the SSoT for the keyword definitions; individual pitch files do not repeat them.

### Forbidden in pitch body

- **No code identifiers** — variable names, file paths, class names, package names. Domain language only.
- Pitches are platform-neutral. Phrase at a level reimplementable on a different stack.
- Don't write HOW (implementation) — pitches describe WHAT.
- Don't include API endpoints, design token values, or exact motion durations/easing. Each has its own SSoT (backend spec / Figma / app code). See [`pitches/README.md` Forbidden in pitch body](pitches/README.md#forbidden-in-pitch-body).

### Recommended sections (see [`pitches/TEMPLATE.md`](pitches/TEMPLATE.md))

- Background and Problem
- User Stories and Acceptance Criteria (Given/When/Then)
- Edge Cases
- Out of Scope
- Feature Flag (only when used)

Cross-domain feature handling: see [`pitches/README.md`](pitches/README.md).

---

## PR checklist

Built into `.github/PULL_REQUEST_TEMPLATE.md`. Summary:

- [ ] `domain` value is registered in `pitches/README.md` allowlist
- [ ] File path slug = frontmatter `domain` match
- [ ] `supersedes` set if there's a predecessor
- [ ] Deprecation PR diff is exactly the `deprecated` flag flip
- [ ] If a Feature Flag section is present: Key, states, initial state, fallback all filled
- [ ] Pitch is at Feature scale (single-flag toggleable?)

---

## Commit message convention

| Situation | Format |
|---|---|
| New | `feat(pitch): add <domain> - <slug>` |
| Update | `feat(pitch): update <domain> - <summary>` |
| Deprecation | `chore(pitch): deprecate <domain> - <reason>` |
| Repo meta | `chore: <description>` |

---

## Stakeholder conflicts

- **Within the product team**: resolve via a new pitch (the previous pitch stays put; the new version supersedes)
- **Product ↔ engineering disagreement (cannot implement / constraint conflict)**: owner proposes a new pitch or an implementation-adjustment PR
