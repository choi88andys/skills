# Section 3 — Test Coverage Diagram template

Read this file just before walking Section 3 of the eng review.

The Test Coverage Diagram is a **structured inventory** of what needs to
be tested. Each row maps a new piece of behavior to its test plan. The
purpose is not exhaustive coverage (impossible) but explicit awareness —
every new behavior has a planned test or an explicit "no test, because…"
rationale.

---

## The six categories

```
NEW UX FLOWS:
NEW DATA FLOWS:
NEW CODEPATHS:
NEW BACKGROUND JOBS / ASYNC WORK:
NEW INTEGRATIONS / EXTERNAL CALLS:
NEW ERROR / RESCUE PATHS:
```

For each category, list every distinct item the plan introduces. If a
category has no new items, write "None new" — don't omit the category.

---

## Per-item table

For every item in any of the six categories, fill the table:

```
| Item | Test type | Test exists? | Happy | Failure | Edge case |
|------|-----------|--------------|-------|---------|-----------|
| ...  | ...       | ...          | ...   | ...     | ...       |
```

| Column | What it captures |
|--------|------------------|
| Item | One-line description (e.g., "Cart submit-review button tap") |
| Test type | Unit / Widget / Integration / System / E2E |
| Test exists? | Yes (with file:line) / No (with planned test name) |
| Happy | Yes / No (with planned test name) |
| Failure | Yes / No, **specific failure mode** (timeout / 4xx / 5xx / parse error / etc.) |
| Edge case | Yes / No, **specific edge** (nil / empty / boundary / concurrent / unicode / etc.) |

Three "No" columns in a row is a critical gap — flag.

---

## Worked example (cart review-request submission)

```
NEW UX FLOWS:
- User taps "Submit review" on cart confirmation screen

NEW DATA FLOWS:
- Cart screen → ReviewService.submitReview → ReviewAPI POST → LocalDB write

NEW CODEPATHS:
- ReviewService.submitReview happy branch
- ReviewService.submitReview duplicate-submission branch (idempotent return)
- BackgroundRetryQueue.enqueue branch (when API fails)

NEW BACKGROUND JOBS / ASYNC WORK:
- BackgroundRetryQueue.processQueue (drains pending submissions on app foreground)

NEW INTEGRATIONS / EXTERNAL CALLS:
- ReviewAPI POST /reviews (new endpoint)

NEW ERROR / RESCUE PATHS:
- NetworkTimeoutError → retry 2× w/ jittered backoff
- UnauthorizedError → token refresh + retry once
- ResponseDecodingError → user-visible "Could not confirm submission"
- LocalPersistenceError → user-visible "Failed to save locally" + Sentry
```

```
| Item                                     | Test type    | Test exists? | Happy   | Failure                       | Edge case                  |
|------------------------------------------|--------------|--------------|---------|-------------------------------|----------------------------|
| User taps Submit-review                  | Widget       | No (planned: cart_submit_review_tap_test) | No (will add) | No — covered in service tests | No                         |
| ReviewService.submitReview               | Unit         | No (planned: review_service_submit_test)  | No → add     | timeout / 401 / 5xx / parse / dup / persist | empty review text          |
| ReviewService.submitReview duplicate     | Unit         | No → add                                 | -       | DuplicateSubmissionError → return success | -                          |
| BackgroundRetryQueue.enqueue             | Unit         | No → add                                 | -       | -                             | full queue / disk full     |
| BackgroundRetryQueue.processQueue        | Integration  | No → add                                 | drains 1 item | partial drain (network mid-loop) | empty queue, queue with 100+ |
| ReviewAPI POST /reviews                  | Integration (mock) | No → add                          | 200 path | 401, 429, 500, malformed body | huge payload, unicode emoji |
| NetworkTimeoutError rescue               | Unit         | No → add                                 | -       | retry 2× then re-raise        | -                          |
| UnauthorizedError rescue                 | Unit         | No → add                                 | -       | refresh OK + retry; refresh fail → re-raise | -                          |
| ResponseDecodingError rescue             | Unit         | No → add                                 | -       | user-visible toast emitted    | -                          |
| LocalPersistenceError rescue             | Unit         | No → add                                 | -       | user-visible banner emitted   | disk full mid-write        |
```

---

## Test ambition check

For the riskiest 1-2 items in the diagram, surface these via AskUserQuestion:

- **2am Friday test** — what test do you want green when paged on a Friday
  night? (e.g., "the integration test that submits a review through the
  full stack with a real local DB")
- **Hostile QA test** — what test would a hostile QA engineer write to
  break this? (e.g., "rapid-fire 100 submissions with the same orderId in
  parallel")
- **Chaos test** — what test simulates production weirdness? (e.g., "kill
  the app mid-submission, restart, verify the queue resumes")

If the user agrees these tests should land before merge, add them as
planned-test rows in the table.

---

## Test pyramid health check

Render via `pre.phase2.test_pyramid_check` (no, this lives in eng `pre.*`
namespace if needed):

```
Unit tests planned:        N
Widget / Component tests:  N
Integration tests:         N
E2E tests:                 N
```

Healthy pyramid: many unit, fewer integration, few E2E. Inverted pyramid
(lots of E2E, few unit) is a smell — flag and ask the user to invert before
merge OR justify explicitly (e.g., "this code has no testable units;
behavior emerges only in integration").

---

## Flakiness risk inventory

For each planned test, ask:

| Risk source | Mitigation |
|-------------|------------|
| Time / clock | Mocked clock injected into the system under test |
| Randomness | Seeded RNG, deterministic seed in test setup |
| External service | Recorded fixtures (vcr / nock) OR hermetic mock |
| Ordering | `.serialized` trait / explicit synchronization |
| Shared mutable state | Test isolation (fresh instance per test) |

Flag any planned test that hits a risk source without a documented mitigation.

---

## Load / stress tests

For any new codepath that will be called frequently (≥ 1 RPS at p50, or
≥ 100 RPS at peak), state the SLO and the test that verifies it:

```
ReviewService.submitReview SLO: p99 < 500ms at 50 RPS
Verifying test: integration_load_review_service_test (50 RPS for 30s, p99 measured)
```

If no SLO test is planned for a hot path, surface as a Section 3 issue.

---

## Output to the review note

After the table is populated, copy it verbatim into the eng review note's
"Test Coverage Diagram" section. The implementer reads the table during
implementation and uses it as the test checklist.
