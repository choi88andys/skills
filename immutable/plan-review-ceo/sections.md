# Phase 2 review sections (CEO)

Read this file at the start of Phase 2, before Section 1 begins.

For each section: evaluate the listed concerns, surface any findings via
`AskUserQuestion` (one issue per call, never batched), and at the end of
the section render either:

- `prc.phase2.section_no_issues` — if nothing surfaced
- A summary of accepted recommendations + deferred items, before pausing
  for the user's transition signal to the next section

The 11 sections run in order. Sections 1-10 are mandatory. Section 11 runs
only when `DESIGN_SCOPE=true` (set in Phase 0.4).

---

## Section 1 — Architecture Review

### Evaluate and diagram

- Overall system design and component boundaries. Draw the dependency graph
  (ASCII).
- Data flow — all four paths. For every new data flow, ASCII diagram four
  scenarios:
  - Happy (data flows correctly)
  - Nil (input missing — what happens?)
  - Empty (input present but zero-length — what happens?)
  - Error (upstream call fails — what happens?)
- State machines. ASCII for every new stateful object. Include impossible /
  invalid transitions and what prevents them.
- Coupling concerns. Which components are now coupled that weren't? Justified?
  Draw before / after dependency graph.
- Scaling characteristics. What breaks first at 10× load? At 100×?
- Single points of failure. Map them.
- Security architecture — auth boundaries, data access patterns, API surfaces.
  Each new endpoint or data mutation: who can call, what they get, what they
  can change?
- Production failure scenarios. For each new integration point, one realistic
  production failure (timeout, cascade, data corruption, auth failure) and
  whether the plan accounts for it.
- Rollback posture. If this ships and breaks, what's the rollback? Git revert?
  Feature flag? DB migration rollback? How long?

### EXPANSION / SELECTIVE EXPANSION addenda

If Phase 1F selected an EXPANSION mode, also evaluate:
- What would make this architecture *beautiful* — not just correct, elegant?
  Something a new engineer in 6 months would say "oh, that's clever and
  obvious at the same time"?
- What infrastructure would make this feature a platform other features
  build on?

If SELECTIVE EXPANSION accepted any cherry-picks affecting architecture,
evaluate each pick's fit here. Flag any creating coupling concerns or not
integrating cleanly.

### Required output

- Full system architecture ASCII diagram showing new components +
  relationships to existing ones (use `templates/data-flow-diagram.md` for
  the four-path data-flow shape)
- Rollback posture — one paragraph naming the specific revert path

### Stop rule

For each issue: AskUserQuestion individually. One issue per call. Present
options, state recommendation, explain WHY. Do NOT batch. Proceed to
Section 2 only after all Section 1 issues are resolved.

---

## Section 2 — Error & Rescue Map

The section that catches silent failures. **Not optional.**

For every new method, service, or codepath that can fail, fill out the
rescue map (template at `templates/error-rescue-map.md`).

### Rules

- Catch-all error handling (`catch Exception`, `except Exception`,
  `rescue StandardError`) is ALWAYS a smell. Name specific exceptions.
- Logging only with a generic message is insufficient. Log full context:
  what was attempted, with what arguments, for what user / request.
- Every rescued error must either: retry with backoff, degrade gracefully
  with user-visible message, or re-raise with added context. "Swallow and
  continue" is almost never acceptable.
- For each GAP (unrescued error that should be rescued): specify rescue
  action + user-visible message.
- For LLM / AI service calls: what happens when response is malformed?
  Empty? Hallucinated invalid JSON? Model refusal? Each is a distinct
  failure mode.

### Required output

A populated rescue-map table for the new codepaths surfaced in Section 1
(or, when Section 1 concluded "no new codepaths," explicit "Section 2:
N/A — no new failure surfaces.").

### Stop rule

AskUserQuestion per issue. Do NOT batch. Review-only — do not write code.

---

## Section 3 — Security & Threat Model

### Evaluate

- New auth / authz surfaces. Who can call? What can they read / mutate?
- Data classification. Does this work touch PII, payment data, secrets,
  health data, or user-generated content? If yes, where do those values
  live (memory / disk / network / logs)?
- Logging. Does any log line capture sensitive data? Logs are forever; treat
  them like an external API.
- Injection surfaces. SQL, command, prompt injection (for LLM features),
  template injection, deserialization. Each input boundary mapped.
- Cross-tenant or cross-user leakage. If multi-tenant, does this preserve
  isolation? If cached, is the cache key tenant-scoped?
- Denial of service. New unauthenticated endpoints? Resource limits?
- Token / credential rotation. Does this introduce a long-lived secret?
  How does it rotate?

### Required output

A short threat model — actor, asset, attack, mitigation — for the highest-
leverage threats this plan introduces.

### Stop rule

AskUserQuestion per issue.

---

## Section 4 — Data Flow & Interaction Edge Cases

### Evaluate

- Race conditions. Concurrent writes? Concurrent reads of being-mutated state?
- Idempotency. Is each new operation safe to retry? If not, why not, and how
  do we know callers won't retry?
- Ordering. Does this assume an ordering (e.g., events arrive in publish
  order)? Is that assumption valid for the queue / network?
- Partial failure. What state do we leave behind when the operation fails
  midway? Is "stuck" possible?
- Time. Clock drift, timezone bugs, daylight savings, leap seconds (if
  scheduling). Do we handle dates that don't exist (Feb 30) or times that
  don't (DST gap)?
- Empty / boundary inputs. Empty list, max-int, single-element, exactly-at-
  limit. Each tested or each explicitly skipped?
- Duplicate inputs. The same event arrives twice — does the system tolerate
  it (de-dup or idempotent)?

### Required output

Edge case ledger — table with columns: edge case / behavior expected /
behavior tested / risk if untested.

### Stop rule

AskUserQuestion per issue.

---

## Section 5 — Code Quality

### Evaluate

- Code organization and module structure. Does the new code respect existing
  module boundaries? Or does it punch through them?
- DRY violations — be aggressive. Duplicated logic invites drift.
- Error handling patterns and missing edge cases (call these out explicitly,
  cross-reference Section 2's rescue map).
- Technical debt hotspots — what does this add? What does this remove?
- Areas over-engineered or under-engineered relative to engineering
  preferences. State the preference each finding violates.
- Existing ASCII diagrams in touched files — still accurate after this
  change? If not, flag as "diagram drift" — it's a code quality issue.
- Framework idioms. For Swift: Swift 6 strict concurrency? For Dart / Flutter:
  current widget patterns, no deprecated APIs? For TypeScript: strict mode
  preserved?

### Required output

A "What already exists" subsection — list existing code / flows that
partially solve the new sub-problems and whether the plan reuses them or
unnecessarily rebuilds them.

### Stop rule

AskUserQuestion per issue.

---

## Section 6 — Test Review

**Build a complete Test Coverage Diagram.** This is not optional.

```
NEW UX FLOWS:
  [list each new user-visible interaction]

NEW DATA FLOWS:
  [list each new path data takes through the system]

NEW CODEPATHS:
  [list each new branch, condition, or execution path]

NEW BACKGROUND JOBS / ASYNC WORK:
  [list each]

NEW INTEGRATIONS / EXTERNAL CALLS:
  [list each]

NEW ERROR / RESCUE PATHS:
  [list each — cross-reference Section 2]
```

For each item in the diagram:
- Test type? (Unit / Widget / Integration / System / E2E)
- Does a test exist in the plan? If not, write the test spec header.
- Happy path test?
- Failure path test? Be specific — which failure?
- Edge case test? (nil, empty, boundary values, concurrent access)

### Test ambition check

- What's the test that makes you confident shipping at 2am Friday?
- What's the test a hostile QA engineer would write to break this?
- What's the chaos test?

### Test pyramid

Many unit, fewer integration, few E2E? Or inverted? Inverted is a smell.

### Flakiness risk

Flag tests depending on time, randomness, external services, ordering.

### Load / stress tests

Required for any new codepath called frequently or processing significant
data.

### Platform-specific notes

- **Dart / Flutter**: `test/`, `test_driver/`, `integration_test/`. Widget
  tests cover individual components; `integration_test/` covers full flows.
  Golden tests for UI-heavy changes.
- **Swift / iOS**: choose XCUITest vs Swift Testing. Async tests use
  `confirmation` or `.serialized` trait. UI tests need accessibility identifiers.
- **LLM / prompt changes**: which eval suites must run, which cases to add,
  what baselines to compare against.

### Required output

Complete Test Coverage Diagram with per-row decisions.

### Stop rule

AskUserQuestion per issue.

---

## Section 7 — Performance Review

### Evaluate

- N+1 queries and database access patterns.
- Memory-usage concerns — growth patterns, retention cycles, background tasks.
- Caching opportunities — and cache invalidation correctness.
- Slow or high-complexity code paths.
- **Mobile-specific**: cold start impact, main thread blocking, battery drain
  from background work, network efficiency on cellular.
- **Frontend-specific**: bundle size impact, hydration cost, layout shift.

### Required output

Performance budget delta — for each new codepath, an order-of-magnitude
estimate (e.g., "+ ~20ms p50 on cart screen render", "+ ~200KB bundle"),
with the basis for the estimate (measurement / inference / no idea).

### Stop rule

AskUserQuestion per issue.

---

## Section 8 — Observability & Debuggability

### Evaluate

- Logs. Do we know when this code runs in production? Are key decision
  points logged at INFO or above?
- Metrics. Are there counters / histograms for the new operation? Cardinality
  budget respected (no per-user labels)?
- Traces. Distributed-tracing context propagated across the new boundary?
- Errors. Exception classes named (cross-ref Section 2). Stack traces preserved.
- Debug story. If a user reports "it didn't work" after this ships, what's
  the 5-minute path to root cause?

### Required output

Observability plan — bullet list of new logs / metrics / traces with their
labels. If "none added," state explicitly.

### Stop rule

AskUserQuestion per issue.

---

## Section 9 — Deployment & Rollout

### Evaluate

- Rollout strategy. All-at-once? Feature flag with cohort? Staged
  percentage? Canary?
- Rollback plan. If we ship and it breaks, what's the rollback path?
  How long? Who triggers it?
- Migration strategy (if data layer changes). Offline migration vs. live?
  Dual-write window? Forward-compatibility window for old clients?
- Backwards compatibility. Old clients still work? For how long?
- Dependency upgrades. Any new dependencies? Pinned to a specific version?
  Audit trail?

### Required output

Rollout-and-rollback section — three lines: rollout strategy, rollback
trigger, rollback time-to-restore.

### Stop rule

AskUserQuestion per issue.

---

## Section 10 — Long-Term Trajectory

### Evaluate

- Tech debt added vs. tech debt removed. Net delta — surface it explicitly.
- Maintenance footprint. Who is on call for this code? Is the on-call
  team capable of debugging it?
- Replacement cost. If we built this wrong, how much would we lose by
  ripping it out in 6 months? 12 months?
- Platform potential. Does this enable other features the team has on the
  roadmap? Or is it a one-off?
- Sunset planning. If this feature is killed in 18 months, what's left
  behind?

### Required output

Trajectory note — one paragraph. Cover net-debt direction, on-call viability,
and platform potential (yes / no with reason).

### Stop rule

AskUserQuestion per issue.

---

## Section 11 — Design & UX Review (skip unless DESIGN_SCOPE=true)

Run only when Phase 0.4 set `DESIGN_SCOPE=true`.

### Evaluate

- Accessibility. Screen reader labels? Color contrast? Keyboard / switch
  control navigation? Cross-reference the pitch's optional Accessibility
  intent section. If the pitch is silent and this work touches a11y,
  Section 11 surfaces a pitch-supersede candidate.
- Motion. Respects prefers-reduced-motion? Cross-reference the pitch's
  optional Motion intent section. Silent pitch + new motion = supersede
  candidate.
- Empty / loading / error states. Each present and visually consistent?
- Internationalization. New strings? RTL support? Pluralization? Long-text
  truncation?
- Consistency with existing design system. New tokens (color, spacing,
  typography) — justified? Or accidental drift?
- Open UX questions. Cross-reference the pitch's optional Open UX questions
  section. Has any been answered or invalidated by this plan? If yes,
  surface for pitch supersede.

### Required output

UX delta summary — bullet list of new screens / states / interactions
with one-line a11y and motion notes per item.

### Stop rule

AskUserQuestion per issue. After Section 11, Phase 2 is complete.

---

## Cross-section reminders

- **Confidence calibration** on every recommendation: 1-10. < 7 → "Low
  confidence — verify first:" prefix.
- **Map to engineering principle**: each recommendation cites the specific
  preference (DRY, explicit > clever, completeness > shortcut, etc.).
- **Issue numbering**: label issues with section number + letter
  (e.g., "3A", "3B"). Easy to reference later.
- **Escape hatch**: if a section has no issues, say so and move on. If an
  issue has an obvious fix with no real alternatives, state what you'll do
  and move on — don't waste an AskUserQuestion call.
