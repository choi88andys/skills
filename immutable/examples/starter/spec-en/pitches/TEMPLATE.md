---
domain: <name>
supersedes: null
deprecated: false
---

# <Pitch title>

## Background and Problem

Why is this pitch needed (context).

## User Stories and Acceptance Criteria

<!--
Under profile.sections[user_stories].structure = per_story_grouped (default),
each story lives in its own `### <story title>` sub-section carrying the GWT
triple AND its bound RFC 2119 normative lines together — this preserves the
story ↔ criterion link and keeps the body grep-friendly.
If the profile sets `structure: consolidated`, delete this section from the
TEMPLATE and replace it with two flat lists (GWT triple + normative bullets)
directly under the H2.
-->

### <Story 1 — short imperative title>

- **Given** <state>
- **When** <user action>
- **Then** <system response>

- **[MUST]** The system …
- **[MUST NOT]** The system …

### <Story 2 — alternate / error path>

- **Given** <state>
- **When** <user action>
- **Then** <system response>

- **[MUST]** The system …

## Edge Cases

| Case | Expected handling |
|---|---|
| <case> | <expected behavior> |

## Out of Scope

- What this pitch **does not** cover (record exclusions explicitly)

## Feature Flag (optional)

<!--
Only when used. Omit this section entirely if no flag.
-->

- **Key**: `ff_<slug>`
- **States**: `deployed`, `hidden`
- **Initial deploy state**: `hidden` (promote to `deployed` after internal validation)
- **Fallback behavior**: UX in `hidden` state (preserve existing behavior / hide UI / etc.)
