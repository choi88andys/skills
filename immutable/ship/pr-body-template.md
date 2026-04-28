# ship Step 5 PR-body template

This file is the markdown template the `ship` skill renders in Step 5.
Placeholders use single-brace mustache (`{name}`); the skill substitutes
them during rendering.

The `### TEMPLATE START` and `### TEMPLATE END` markers below are stripped
when the skill assembles the PR body.

---

### TEMPLATE START

## Summary

{summary_bullets}

## Test plan

{test_plan}

## Spec / decision context

- Pitch: `{pitch_path}`
- Linked ADRs:
{adr_paths}

{spec_repo_pr_placeholder}

## Deferred to spec / future ADRs

{ceo_phase3_triggers}

---

🤖 Generated with [Claude Code](https://claude.com/claude-code) via the
`immutable` plugin SDD flow (`/immutable:office-hours` →
`/immutable:prd` → `/immutable:design` → `/immutable:plan-review-ceo` →
`/immutable:plan-review-eng` → `/immutable:adr` → `/immutable:ship`).

### TEMPLATE END

---

## Section authoring notes

| Placeholder | Source | Format |
|-------------|--------|--------|
| `{summary_bullets}` | Pitch + design note + ceo note (Phase 1F scope envelope) | 3-5 bullets, each ≤ 1 line. Lead with WHAT changes, then WHY. |
| `{test_plan}` | Eng note Section 3 Test Coverage Diagram | Bulleted markdown checklist. Each row of the diagram becomes one TODO bullet. |
| `{pitch_path}` | Design note `Pitch:` line | Relative path inside the spec repo (e.g., `pitches/cart/2026-04-15-review-request.md`). For refactor mode, write `(none — internal refactor)`. |
| `{adr_paths}` | Step 5.2 grep result | Bullet list. Each bullet: `- adr/<filename>` (path relative to app repo root). If empty: `- (no linked ADRs in this PR)`. |
| `{spec_repo_pr_placeholder}` | User answer | When the sprint also produced a pitch supersede in the spec repo, render `Spec repo PR: <fill in>` so the reviewer can locate the companion. Empty otherwise. |
| `{ceo_phase3_triggers}` | CEO note Phase 3 | Bullet list of pitch-supersede or future-ADR candidates the review surfaced but were not addressed in this PR. Empty list ↔ "None — review surfaced no follow-ups." |

## PR title rules

The skill computes the PR title separately (not part of the body template):

- ≤ 70 characters total
- Starts with conventional prefix (`feat:`, `fix:`, `chore:`, etc.)
- Concise — describes WHAT changes, not the implementation detail

Examples:
- `feat(cart): add review-request flow on confirmation screen`
- `fix(auth): refresh token retry skipping rate-limit window`
- `refactor(cart): extract review submission into ReviewService`

## Worked example (cart review-request submission)

PR title: `feat(cart): add review-request flow on confirmation screen`

PR body (rendered):

```
## Summary

- Adds a "Submit review" action under the cart confirmation screen, gated
  by the `cart_review_prompt_v1` feature flag (off by default until 2026-05).
- New `ReviewService` centralizes prompt eligibility (StoreKit 3-per-365
  budget) and routes successful submissions through `BackgroundRetryQueue`
  for offline durability.
- Wires telemetry events `cart.review.shown` / `.submitted` / `.dismissed`
  for funnel measurement.

## Test plan

- [ ] Cart screen submit-tap widget test (`cart_submit_review_tap_test`)
- [ ] `ReviewService.submitReview` happy path unit test
- [ ] `ReviewService.submitReview` failure paths: timeout, 401, 5xx, malformed
- [ ] `BackgroundRetryQueue.processQueue` integration test (drain + partial)
- [ ] `ReviewAPI POST /reviews` mocked integration test (200/401/429/500)
- [ ] Rescue path tests: NetworkTimeoutError / UnauthorizedError /
      ResponseDecodingError / LocalPersistenceError
- [ ] Manual: switch flag on, submit a review, verify telemetry events fire

## Spec / decision context

- Pitch: `pitches/cart/2026-04-15-review-request-flow.md`
- Linked ADRs:
  - `adr/2026-04-22-review-prompt-eligibility-service.md`
  - `adr/2026-04-22-background-retry-queue.md`

## Deferred to spec / future ADRs

- Pitch supersede pending: motion intent for the success state was not
  in the original pitch — captured in `pitches/cart/2026-04-22-review-request-flow.md`
  (separate spec-repo PR).
- Future ADR: cross-surface prompt strategy (review prompt + NPS + email)
  is out of scope for this PR; surface in next sprint's pitch.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code) via the
`immutable` plugin SDD flow (`/immutable:office-hours` → `/immutable:prd` →
`/immutable:design` → `/immutable:plan-review-ceo` → `/immutable:plan-review-eng` →
`/immutable:adr` → `/immutable:ship`).
```
