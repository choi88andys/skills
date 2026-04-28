# Section 1 — Data flow ASCII diagram template

This is the output format for Phase 2 Section 1's required data-flow
diagrams. Read this file just before walking Section 1.

For every new data flow surfaced by the plan, draw four scenarios:

1. **Happy** — data flows correctly through every component
2. **Nil** — input is missing entirely (null / undefined / no value provided)
3. **Empty** — input is present but zero-length (empty string, empty list, 0)
4. **Error** — an upstream call (network, DB, external service) fails

ASCII is the right format because it survives in markdown reviews, in plain
emails, and in commit messages. Don't reach for diagramming tools — the
discipline of keeping it ASCII forces you to omit detail that isn't load-
bearing.

---

## Diagram conventions

```
[Component]   — a service, function, or module
{User}        — a human actor
(Storage)     — data at rest (DB, file, cache)
->            — happy-path data direction
=>            — error / fallback direction
||            — synchronous boundary (caller waits)
~~            — asynchronous boundary (fire-and-forget or queue)
?(...)        — decision branch
```

Keep one diagram per scenario. Don't merge two scenarios into one diagram —
the point is to make divergent paths legible.

---

## Worked example (cart review-request submission)

### Happy path

```
{User}
   ||
   v
[CartScreen] -- onTapSubmitReview ------> [ReviewService.submitReview]
                                                 ||
                                                 v
                                          ?(local DB write OK)
                                              | yes
                                              v
                                          [ReviewAPI POST /reviews]
                                                 ||
                                                 v
                                          ?(HTTP 200)
                                              | yes
                                              v
                                          (LocalDB: marked synced)
                                                 ||
                                                 v
                                          [CartScreen renders success]
                                                 ||
                                                 v
                                              {User}
```

### Nil scenario (orderId missing — defensive guard)

```
{User} (somehow tapped submit on a screen without orderId)
   ||
   v
[CartScreen.onTapSubmitReview]
   ||
   v
?(orderId nil)
   | yes
   v
=> [Logger] (warn: "submit tapped without orderId")
   ||
   v
=> [CartScreen renders 'Cannot submit review' state]
   ||
   v
   {User}
```

Decision: this scenario should be impossible if the screen is built correctly.
But "impossible" doesn't mean "won't happen" — defensive logging and a
visible-but-non-blocking error state catch the regression instead of hiding it.

### Empty scenario (review text blank)

```
{User} (tapped submit with blank text)
   ||
   v
[CartScreen.onTapSubmitReview]
   ||
   v
?(reviewText.trim() == "")
   | yes
   v
=> [CartScreen renders 'Please write a review first' state]
   |
   ; no API call, no persistence — pure client-side
```

Decision: blank reviews are validated client-side before any service call.
The empty case never reaches `ReviewService`. Adding this to the diagram
makes that contract explicit.

### Error scenario (ReviewAPI 5xx)

```
{User}
   ||
   v
[CartScreen] -- onTapSubmitReview ------> [ReviewService.submitReview]
                                                 ||
                                                 v
                                          (LocalDB: write OK)
                                                 ||
                                                 v
                                          [ReviewAPI POST /reviews]
                                                 ||
                                                 X (HTTP 5xx)
                                                 ||
                                          ~~ [BackgroundRetryQueue.enqueue]
                                                 ||
                                                 v
                                          [CartScreen renders 'Saved locally,
                                           syncing' state]
                                                 ||
                                                 v
                                              {User}
```

Decision: locally-persisted state means the user keeps moving, the API call
becomes a background concern, and the user sees an honest "syncing"
indication instead of an opaque error.

---

## What each diagram must show

For every diagram, the reviewer can answer these without ambiguity:

| Question | Where the answer lives |
|----------|------------------------|
| Where does the user start? | `{User}` at top |
| What components handle this flow? | Components in `[Bracket]` form |
| Where is data persisted? | `(Storage)` markers |
| What's the user-visible outcome? | Final `{User}` arrow OR explicit terminal state |
| What's synchronous vs. asynchronous? | `||` vs. `~~` |
| Where are decision branches? | `?(condition)` with explicit yes / no edges |
| Where do errors deviate? | `=>` arrows on the failing branch |

If any of these is ambiguous, the diagram isn't done.

---

## Diagram-drift check

Section 5 (Code Quality) asks whether existing ASCII diagrams in touched
files are still accurate after this change. The diagrams produced in
Section 1 are the seeds — when the implementer lands the change, they
should commit the same diagrams (or updated versions) into the touched
files' header comments. Keeping the diagrams in source means future
reviewers see them without re-doing this work.

If a touched file already has an ASCII diagram, Section 1 evaluates whether
the existing diagram remains accurate or needs an update. "Diagram drift"
is a Section 5 finding — flag the file path and the specific lines that
no longer match the code.

---

## When NOT to draw

If the plan has zero new data flows (e.g., a refactor that preserves all
external behavior), Section 1 explicitly states "no new data flows; existing
diagrams remain valid" and skips the four-scenario draw. But the reviewer
verifies the no-change claim by spot-checking the touched files'
existing diagrams.

If the plan has many new data flows (≥ 4), draw the most important two
end-to-end. For the rest, draw only the divergent points (where they branch
from an existing flow).
