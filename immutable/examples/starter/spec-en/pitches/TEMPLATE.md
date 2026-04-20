---
domain: <name>
supersedes: null
deprecated: false
---

# <Pitch title>

## Background and Problem

Why is this pitch needed (context).

## User Stories and Acceptance Criteria

- **Given** <state>
- **When** <user action>
- **Then** <system response>

Use RFC 2119 keywords for binding statements:

- **[MUST]** The system …
- **[MUST NOT]** The system …

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
