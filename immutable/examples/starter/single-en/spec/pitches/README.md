# Pitches

Where product pitches live. Each domain has its own subdirectory.

## Allowed Domains

**Only domains in this list are accepted.** Add a new domain after lead approval.

| Domain | Description |
|---|---|
| `_shared` | Cross-cutting concerns (auth, logging, error handling, etc. — not scoped to a specific domain) |

<!--
Example rows (replace with your real domains or remove this block):

| `search` | Search input, results, filters |
| `checkout` | Checkout flow, discount application, completion page |
-->

## File placement rules

- `pitches/<domain>/YYYY-MM-DD-<slug>.md` — per-domain pitches
- `pitches/_shared/YYYY-MM-DD-<slug>.md` — cross-cutting concerns
- `pitches/TEMPLATE.md` — pitch template (copy from here to start)

## Editing principle

**Append-only.** See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for full rules.

## Relationship to ADRs

In this single-repo layout, ADRs live in [`../../adr/`](../../adr/). Pitches describe "what the app should do"; ADRs capture "why we implemented the decision this way." They do not directly cross-reference (ADRs reference pitches one-way) and both follow append-only mechanics.

## Adding a new domain

1. Agree on the domain name with the lead (avoids typos / near-duplicates)
2. Add the domain to the allowlist above
3. Create the directory `pitches/<domain>/`
4. Copy `TEMPLATE.md` → `YYYY-MM-DD-initial.md`

## Forbidden in pitch body

The pitch body describes **"what the app should do"** only. The following elements have their SSoT elsewhere:

| Element | SSoT | In pitch |
|---|---|---|
| Route paths, navigator API | App code | Don't write — describe entry/transition intent in GWT only |
| Widget / class / package names | App code | Don't write |
| API endpoint, payload schema | Backend spec | Don't write |
| Design tokens (color/spacing values) | Figma | Don't write (describe semantics only) |
| Exact motion duration/easing values | App code | Describe intent only, no numbers |

Full body rules: [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
