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

## Adding a new domain

1. Agree on the domain name with the lead (avoids typos / near-duplicates)
2. Add the domain to the allowlist above
3. Create the directory `pitches/<domain>/`
4. Copy `TEMPLATE.md` → `YYYY-MM-DD-initial.md`

> Read [`../CONTRIBUTING.md`](../CONTRIBUTING.md) before authoring — it defines filename rules (subject-based slug), frontmatter, normative keywords, and PR checklist. Also review the [Forbidden in pitch body](#forbidden-in-pitch-body) and [Cross-domain feature handling](#cross-domain-feature-handling) sections below.

## Cross-domain feature handling

A feature may affect multiple domains' UX (e.g., a notification settings overhaul touches both `notification` and `settings`). When this happens:

1. **Split the pitch by domain.** The file path determines the domain, so a cross-domain feature naturally becomes multiple files.
2. In each pitch body, **cross-reference**: "this feature is composed with `pitches/<domain>/YYYY-MM-DD-<slug>.md`" near `Background and Problem` or `Out of Scope`.

Do not bundle one feature = one pitch file when the feature crosses domains.

## Forbidden in pitch body

The pitch body describes **"what the app should do"** only. The following elements have their SSoT elsewhere:

| Element | SSoT | In pitch |
|---|---|---|
| Route paths, navigator API | App code | Don't write — but do describe entry/transition/return **intent** in Given/When/Then. Use bold common-noun screen names (e.g., **Order Detail (Completed Payment)** screen) |
| Widget / class / package names | App code | Don't write |
| API endpoint, payload schema | Backend spec | Don't write |
| Design tokens (color/spacing values) | Figma | Don't write (describe semantics only) |
| Exact motion duration/easing values | App code | Describe intent only, no numbers |

Normative keywords (`[MUST]` etc.) and full body rules: see [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
