---
domain: <name>
supersedes: null
deprecated: false
# Only in repos with requirement_contract enabled (v0.11+): the ticket's
# identity and version coordinate. No quotation — the tracker keeps the body.
# references:
#   tickets:
#     - tracker: github
#       repo: my-org/task-tracker
#       id: "3755"
#       version: "2026-09-08T05:25:01Z"
#       read_at: 2026-09-08
#       covers:                       # binding groups/items THIS pitch reflects (labels verbatim)
#         acceptance:
#           - group: Accrual
#       delegates:                    # reflected in substance; literal owned elsewhere
#         - { binding: qa_checklist, group: Coupon card copy, items: [2], to: Figma }
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

## Requirement Disagreements (optional)

<!--
Only in repos with requirement_contract enabled, and only when this pitch
cannot follow a binding ticket item as written — the three admissible
judgements are: not implementable / self-contradiction / conflict with a
settled requirement. One `### ` entry per item. While the outcome reads
"Provisional" this pitch's PR stays open (validator --strict-body blocks the
merge); rewrite it as "Agreed" or "Deadline passed" once settled, and keep the
section — it tells a later reader the difference from the ticket is deliberate.
-->

### <tracker repo#id · section · group ordinal>

- **Original** <the ticket's sentence, verbatim>
- **Correction** <the sentence this pitch follows>
- **Reason** <Self-contradiction | Not implementable | Conflict with a settled requirement> — <evidence>
- **Outcome** Provisional — correction requested YYYY-MM-DD

## Feature Flag (optional)

<!--
Only when used. Omit this section entirely if no flag.
-->

- **Key**: `ff_<slug>`
- **States**: `deployed`, `hidden`
- **Initial deploy state**: `hidden` (promote to `deployed` after internal validation)
- **Fallback behavior**: UX in `hidden` state (preserve existing behavior / hide UI / etc.)
