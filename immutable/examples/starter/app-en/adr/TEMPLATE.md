---
type: adr
domain: <name | _global>
supersedes: null
deprecated: false
references:
  pitches: []
---

# <ADR Title>

## Context

<!-- What problem does this decision address? Current state. Constraints. Forces pushing toward change. -->
<!-- A third-party engineer should be able to summarize "what triggered this decision" in ≤3 sentences after reading this section. -->

## Decision

<!-- A single declarative sentence. Example: "We will adopt Riverpod for client-side state management across all feature modules." -->
<!-- Optional: one short paragraph of elaboration (scope included, scope excluded, minimum viable implementation path). -->

## Consequences

### Positive
- <!-- at least 2 items -->

### Negative / Trade-offs
- <!-- at least 2 items; "no downsides" is a red flag — push back -->

### Cost of adoption / Neutral
- <!-- migration effort, training, tooling -->

## Alternatives Considered

- **<Alternative A>** — <rejection reason>. <revisit trigger>.
- **<Alternative B>** — <rejection reason>. <revisit trigger>.

<!-- "There was no alternative" usually signals this decision doesn't need an ADR. -->

## Revisit Triggers

<!-- At least one: metric, milestone, OR scheduled review date. -->

## Out of Scope

<!-- Optional. Things this ADR explicitly does NOT decide. Remove this section if not applicable. -->

---

<!--
================================================================================
Reference example — delete everything below this line before committing.
================================================================================

The /immutable:adr skill recognizes 4 ADR-worthy justification areas:

  1. Rollout        — staged rollout %, feature flags, kill-switch design
  2. Observability  — metrics schema, logging cardinality, alerting thresholds
  3. Migration      — schema migrations, backfill policy, double-write windows
  4. External-deps  — 3rd-party SDK choice, vendor lock-in, API compat guarantees

Below is a worked Migration example. Use as a pattern — do NOT copy verbatim.

--------------------------------------------------------------------------------
Example — Migration
--------------------------------------------------------------------------------

## Context

We are migrating notification preferences from a single boolean to per-channel
tri-state (on / off / digest). 3.2M user records have active schedules
depending on the current value. Downtime is not acceptable, and we need
≥30 days of rollback capability.

## Decision

Add the new column, run dual-writes for 2 weeks, backfill from the existing
boolean, flip reads to the new column, and retain the old column for 90 days
before a follow-up ADR decides on dropping it.

## Consequences

### Positive
- Zero downtime, zero user-visible disruption.
- 90-day rollback capability (read-flag flip is sufficient).

### Negative / Trade-offs
- 8–12ms added latency on the preference update path during dual-writes.
- Both columns active for 90 days — every code path touching preferences
  must handle both states. Code-complexity cost.
- The old-column drop requires a follow-up ADR — this ADR doesn't complete
  the migration.

### Cost of adoption / Neutral
- 1 DBA review session, ~8–12 PRs for dual-write changes.
-->
