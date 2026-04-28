# Phase 1 review sections (Eng)

Read this file at the start of Phase 1, before Section 1 begins.

This eng-review's 4 sections complement the CEO review's 11 sections.
Where the CEO review is broad (scope, security, deployment, long-term
trajectory), the eng review is **deep on implementation seams**. Avoid
re-running CEO findings — read the CEO review note first to know what's
already been covered.

For each section: walk the listed concerns, surface findings via
`AskUserQuestion` (one issue per call, never batched), and at the end
of the section render either:

- `prc.phase2.section_no_issues` (reused from CEO catalog) — if nothing
  surfaced
- A summary of accepted recommendations + deferred items, before pausing
  for the user to signal transition to the next section

All 4 sections are mandatory.

---

## Section 1 — Architecture (Eng angle)

The CEO review's Section 1 covered system-design boundaries, scaling, and
rollback posture. The eng review focuses on the **how-it-fits-together**
angle:

### Evaluate

- **Dependency graph at the package / module level**. Is the new code
  introduced inside an existing module, or does it punch a new boundary?
  Cross-package imports added — justified?
- **Coupling concerns**. Which two components are now coupled that weren't?
  Was a previously-loose coupling tightened? Why?
- **Distribution architecture**. If this introduces a new deployable
  artifact (binary, package, container, mobile app), how does it ship?
  CI/CD pipeline part of this plan or deferred?
- **Concurrency model**. Where does this code run — main thread, background
  queue, isolate, web worker? Are the synchronization assumptions correct?
- **Resource lifecycle**. Connections, file handles, observers, listeners,
  subscriptions — opened where, closed where, leaked where?
- **API stability boundary**. If this introduces a public API (whether for
  another team or a published package), what's the version commitment?

### Required output

A "dependency-delta diagram" — ASCII graph of modules touched, with
arrows showing what depends on what. Mark new edges in `**bold**` (or with
a `*` prefix) so they stand out.

### Stop rule

AskUserQuestion per issue. One at a time.

---

## Section 2 — Code Quality

### Evaluate

- **DRY violations** — be aggressive. Duplicated logic across modules
  invites drift; flag every instance, even when the duplicate is small.
- **Error handling patterns** — Section 2 of CEO already produced a rescue
  map. Cross-check: are the rescue actions actually wired up at the right
  call sites? Are exception classes named where they're raised?
- **Framework idioms**:
  - **Swift / iOS** — Swift 6 strict concurrency? `@MainActor`,
    `Sendable` boundaries respected? Async-await preferred over completion
    handlers? Deprecated APIs avoided?
  - **Dart / Flutter** — Current widget patterns? `BuildContext`
    discipline? Provider / Riverpod / etc. used per project convention?
    `dart:async` Stream lifecycle correct?
  - **TypeScript** — Strict mode preserved? `any` introduced? Type narrowing
    over assertions? Discriminated unions where they belong?
  - **Other** — Look up the project's `CONTRIBUTING.md` or stylesheet
    references in CLAUDE.md and check.
- **Existing ASCII diagrams in touched files** — Still accurate after this
  change? If not, **diagram drift** is a quality finding (not a separate
  category). Flag the file path and the lines that no longer match.
- **Naming**. New types / functions named consistently with surrounding code?
  No abbreviations the project doesn't use? Intent-revealing names, not
  pattern names?
- **Magic values**. New constants introduced — extracted, named, documented?
- **Comment hygiene**. Are comments explaining WHY (not WHAT)? Stale comments
  on touched lines updated?

### Required output

A bullet list of code-quality findings with file:line references. Each
finding includes the engineering principle it violates (DRY, explicit >
clever, completeness > shortcut, etc.).

### Stop rule

AskUserQuestion per issue.

---

## Section 3 — Test Review

The most important eng-review section. Build a **complete Test Coverage
Diagram** — template at `templates/test-coverage-diagram.md`.

### Build the diagram

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
  [list each — cross-reference CEO Section 2 rescue map]
```

For each item:
- **Test type?** (Unit / Widget / Integration / System / E2E)
- **Does a test exist in the plan?** If not, write the test spec header.
- **Happy path test?**
- **Failure path test?** Be specific — which failure?
- **Edge case test?** (nil, empty, boundary, concurrent access)

### Test ambition check

For the riskiest items in the diagram, ask:

- What's the test that makes you confident shipping at 2am Friday?
- What's the test a hostile QA engineer would write to break this?
- What's the chaos test? (Network drop? Process kill? Cache corruption?)

### Test pyramid

Many unit, fewer integration, few E2E? Or inverted (lots of E2E, few
unit)? Inverted is a smell — flag.

### Flakiness risk

Flag any test depending on time, randomness, external services, ordering,
or shared mutable state. These need explicit isolation strategies (mocked
clock, fixed seed, hermetic harness, `.serialized` trait).

### Load / stress tests

Required for any new codepath called frequently or processing significant
data. State the SLO (e.g., "p99 < 200ms at 100 RPS") and the test that
verifies it.

### Platform-specific notes

- **Dart / Flutter** — `test/`, `test_driver/`, `integration_test/`. Widget
  tests for individual components; `integration_test/` for full flows.
  Golden tests for UI-heavy changes.
- **Swift / iOS** — XCUITest vs Swift Testing. Async tests use
  `confirmation` or `.serialized` trait. UI tests need accessibility
  identifiers on every queried element.
- **TypeScript / Node** — Vitest / Jest / Playwright per project
  convention. Mock layer (vi.mock / jest.mock) used appropriately?
- **LLM / prompt changes** — Eval suites named (which scenarios run, which
  cases to add, what baselines to compare against).

### Required output

Complete Test Coverage Diagram with per-row decisions. Include "test spec
headers" for every missing test (just the test name and one-sentence
description).

### Stop rule

AskUserQuestion per issue. Test review is the most likely place for the
"we'll add tests later" anti-pattern — push back hard.

---

## Section 4 — Performance Review

### Evaluate

- **N+1 queries / over-fetching** — DB access patterns examined?
- **Memory growth** — retention cycles, background tasks holding references,
  caches without eviction, observer / listener leaks.
- **Caching opportunities AND cache invalidation** — does the plan add a
  cache? If yes, who invalidates it, when, and is invalidation tested?
- **Slow / high-complexity code paths** — flag O(n²) or worse on user-data-
  sized inputs.
- **Mobile-specific** — cold start impact, main thread blocking, battery
  drain from background work, network efficiency on cellular, image / asset
  size delta.
- **Frontend-specific** — bundle size impact (delta in KB), hydration cost,
  layout shift, font loading.
- **Backend-specific** — query plan changes, lock contention, queue
  saturation, event-loop blocking.

### Required output

A "performance budget delta" — for each new codepath, an order-of-magnitude
estimate (e.g., "+ ~20ms p50 on cart screen render", "+ ~200KB bundle"),
with the basis (measurement / inference / no idea). "No idea" is fine for
genuinely novel code, but it must be acknowledged so the implementer knows
to measure during dev, not after ship.

### Stop rule

AskUserQuestion per issue.

---

## Cross-section reminders

- **Confidence calibration** on every recommendation: 1-10. < 7 → "Low
  confidence — verify first:" prefix.
- **Map to engineering principle**: each recommendation cites the specific
  preference (DRY, explicit > clever, completeness > shortcut, etc.).
- **Issue numbering**: section number + letter (e.g., "3A", "3B").
- **Escape hatch**: if a section has no issues, say so and move on. If an
  issue has an obvious fix with no real alternatives, state what you'll
  do and move on — don't waste an AskUserQuestion call.
