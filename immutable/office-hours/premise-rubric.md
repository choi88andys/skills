# Phase 3 Alternatives Rubric

Read this file at the start of Phase 3, before generating the 3 approaches.
It distills the authoring rules and lists worked examples so each slot
(Minimal / Ideal / Creative) does what it is supposed to do.

---

## The three slots — what each is asking for

### Approach A — Minimal viable

The smallest diff that delivers the user-visible outcome. Ugly is OK; production
quality is OK to skip; "we'll fix it later" is OK as a position. The point is
to make the *can ship today* version concrete, so the team can see the shape of
"the simplest thing that works."

Heuristics:
- ≤ 5 files touched, ideally
- No new abstractions, services, or modules
- Reuses existing patterns even when they don't fit perfectly
- Defers tests / observability / migration safety only when truly negligible

Common failure: "minimal" creeps into "minimal but with one nice thing." Resist.
The Minimal version exists as a baseline; it does not need to be the answer.

### Approach B — Ideal architecture

The version a senior engineer would design with no time pressure. Long-term
trajectory matters more than time-to-ship. Multiple modules touched is fine
if each cleans up an existing seam.

Heuristics:
- New abstractions allowed when they remove real duplication or coupling
- Distribution / migration / observability / tests treated as first-class
- Reuses existing patterns when they fit; replaces them when they don't
- Considers the next 2-3 features that will land on top of this work

Common failure: "ideal" becomes "rebuild everything." Stay scoped to the
problem under discussion. If the ideal answer is genuinely a rewrite, say so —
but explicitly justify the scope expansion.

### Approach C — Creative / lateral

A different *framing* of the problem, not just a different implementation.
The question is: "What if the user didn't have to do X at all?" or "What if
the data lived somewhere else?" or "What's the cheap eureka that makes the
hard part obvious?"

Heuristics:
- Different entry point (e.g., what if this is a build-time concern, not a
  runtime concern?)
- Different abstraction (e.g., what if this is a query, not a sync?)
- Different ownership (e.g., what if the upstream service did this?)
- "Boring is creative" — sometimes the cheapest framing is to skip the feature
  entirely and route to an existing flow

Common failure: faking C by mildly tweaking B. If C is genuinely the same
shape as B with a smaller diff or one extra knob, say so explicitly:
"No meaningfully different framing exists for this problem because {reason}."
That is honest output. Do not pad.

---

## Per-approach format (mandatory fields)

Every approach must include all six fields:

```
APPROACH {letter}: {Name}
  Summary: 1-2 sentences. State the *what*, not the *why*.
  Effort:  S | M | L | XL  (Claude-assisted scale, not human-team weeks)
  Risk:    Low | Med | High  (probability × blast radius if it goes wrong)
  Pros:    2-3 bullets, each one specific and testable
  Cons:    2-3 bullets — same standard. "It's complicated" is not a Con.
  Reuses:  Files / patterns / services from Phase 1 this approach leverages.
           Empty list is OK only if truly nothing relevant exists.
```

### Effort scale (Claude-assisted)

| Letter | Order of magnitude | Example |
|--------|---------------------|---------|
| S | < 1 hour | Add a flag, change a default, write 1-2 small tests |
| M | 1-4 hours | New feature touching ≤ 5 files, normal-sized PR |
| L | 4-16 hours | Multi-component feature, schema change with migration |
| XL | 16+ hours | Architectural change, multiple PRs, dogfood phase |

### Risk scale

| Letter | Meaning |
|--------|---------|
| Low | Localized change, easy rollback, no data implications |
| Med | Cross-cutting change OR data implications OR external integration |
| High | Migration, breaking change, security-sensitive, hard rollback |

---

## Worked examples

### Example 1 — Add review-request flow to cart

> Premise: existing cart flow has a confirmation screen with a slot for an
> in-app prompt. We want to ask for a review there.

```
APPROACH A — Minimal viable: Inline button on existing confirmation
  Summary: Add a "Leave a review" button under the existing confirmation copy.
           Tap → opens system review prompt via `SKStoreReviewController`.
  Effort:  S
  Risk:    Low
  Pros:    No new screens, no new state, no analytics work
           Ships today, easy to remove if it underperforms
  Cons:    No funnel measurement
           Always asks, even from users who left a 1-star review yesterday
  Reuses:  CartConfirmationScreen.swift, AnalyticsEvent.confirmationViewed

APPROACH B — Ideal architecture: ReviewPromptManager service
  Summary: New ReviewPromptManager service decides eligibility (purchase count,
           time since last ask, recent NPS), then routes to either StoreKit
           prompt or an in-app survey. Cart confirmation calls the manager.
  Effort:  M
  Risk:    Low
  Pros:    Single source of truth for prompt eligibility — extensible to other
           surfaces (post-purchase email, settings)
           Funnel measurement out of the box (manager emits structured events)
           Honors Apple's 3-prompts-per-365-days budget without per-screen logic
  Cons:    More files
           Eligibility rules live in code — needs a profile review check
  Reuses:  AnalyticsEvent.*, FeatureFlag (for kill-switch), SKStoreReviewController

APPROACH C — Creative / lateral: skip the in-app prompt entirely
  Summary: Drop the cart-screen prompt; instead, send a transactional email
           24h post-purchase with a one-tap review link. Cart confirmation
           stays as-is.
  Effort:  M
  Risk:    Med (relies on email delivery; user cohort with email opt-out gets nothing)
  Pros:    Higher response rate (email-based asks have measured 3-4× tap-through
           compared to in-app prompts on similar flows)
           Decouples prompt timing from cart UX — fewer screens for the user
           Works for users who never reopen the app
  Cons:    Email infra dependency (existing transactional pipeline must support
           review CTA)
           Email opt-out users miss the prompt entirely — segment loss
  Reuses:  TransactionalEmail.sender, OrderConfirmedEvent (already published)

RECOMMENDATION: Approach B because the manager eliminates the per-screen
eligibility code that A would force us to add later, and Apple's 3-per-365-days
budget already requires central tracking — building it once is cheaper than
sprinkling it across 4 surfaces over the next two quarters.
```

### Example 2 — When Approach C cannot be generated

> Premise: replacing a hardcoded URL constant with a config-driven value.

```
APPROACH A — Minimal viable: Read URL from Info.plist
  ...

APPROACH B — Ideal architecture: Inject via DI container
  ...

APPROACH C — Creative / lateral: NOT GENERATED
  No meaningfully different framing exists for "make a URL configurable":
  the variable is read by exactly one caller, the value comes from one of
  the same three sources (compile-time, build-config, runtime fetch), and
  there is no abstraction layer that would change ownership. Approaches A
  and B exhaustively cover the design space.

RECOMMENDATION: Approach A because the variable has one caller and lives
behind a feature flag already; the DI container would add 30 minutes of
boilerplate without a downstream consumer.
```

---

## Pitfalls catalog

| Pitfall | Why it's bad | Fix |
|---------|--------------|-----|
| Faking Approach C with a tiny tweak of B | Burns user trust; gives the illusion of breadth without it | Explicitly state "no meaningfully different framing — {reason}" |
| Recommending the Ideal architecture by default | Bias toward B because it sounds more thoughtful | Default to whichever best serves the goal; state the trade-off |
| Listing "it's complex" as a Con | Vague; not testable | Replace with a concrete: "needs migration of 4 callers" or "new module to maintain" |
| Skipping `Reuses:` | Hides that an existing pattern would handle this | List existing files / services even when the approach extends them |
| One-paragraph Summary | Too long; obscures the *what* | 1-2 sentences; supporting detail goes in Pros / Cons |

---

## What Phase 3 must surface in the design doc

After the user picks an approach, Phase 4 renders the alternatives section
verbatim. The Phase 3 output should already be in the right format — no
rewriting between phases. If you need to revise the alternatives after the
user pushes back, regenerate them from Phase 3.1, do not patch in place.
