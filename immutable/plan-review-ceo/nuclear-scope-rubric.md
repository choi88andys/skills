# Phase 1 nuclear scope rubric (CEO)

Read this file at the start of Phase 1, before sub-phase 1A begins.

Phase 1 has six sub-phases (1A through 1F). Each pauses for user input.
Issue one AskUserQuestion call per concern; never batch.

The point of Phase 1 is to lock the scope envelope **before** running the
11 review sections. Running Section 1 (Architecture) on a plan whose scope
is wrong is wasted work — the right answer is to fix scope first.

---

## 1A — Premise Challenge

Before any approach is evaluated, list the premises the framing assumes.

Output via `prc.phase1.premise_list` (rendered with the captured premises):

```
PREMISES (assumed by the current plan):
1. {statement} — agree / disagree?
2. {statement}
3. {statement}
```

For each premise, consider:

- **Is this the right problem to solve?** Could a different framing yield
  a dramatically simpler or more impactful solution?
- **What is the actual user / business outcome?** Is the plan the most
  direct path, or is it solving a proxy?
- **What happens if we do nothing?** Real pain point or hypothetical?

If the design handoff note (or the pitch) came from `/immutable:office-hours`
and has a "Premises" section, re-confirm each premise via AskUserQuestion
**before** proceeding. A flipped premise forces scope update before the
rest of the review runs.

### Mid-session exit hatch

If the user can't articulate the problem, keeps changing the problem
statement, or is clearly exploring rather than reviewing — render
`prc.phase1.exit_to_office_hours` and offer:

> A) Yes, run /immutable:office-hours and come back
> B) No, keep going

If they keep going, proceed normally — but the review will be shallower.

---

## 1B — Existing Code Leverage

Two questions:

1. **What existing code already partially or fully solves each sub-problem?**
   Map every sub-problem in the plan to existing code (use the design handoff
   note's "Existing abstractions to reuse" list as a starting point).
2. **Is this plan rebuilding anything that already exists?** If yes,
   explain why rebuilding beats refactoring.

Output as a two-column mapping: sub-problem → existing-code reference (file
path + role). If a sub-problem has no existing solution, mark it
"genuinely new."

---

## 1C — Dream State Mapping

Describe the ideal end state of this system 12 months out. Does this plan
move toward that state or away?

Output via `prc.phase1.dream_state_template`:

```
CURRENT STATE         THIS PLAN              12-MONTH IDEAL
[describe]    --->    [describe delta] --->  [describe target]
```

If the plan moves away from the 12-month ideal, the user must explicitly
acknowledge "we are taking on debt" before proceeding.

---

## 1C-bis — Implementation Alternatives (mandatory ≥2-3)

Before mode selection (1F), produce 2-3 distinct implementation approaches.
**Not optional** — every plan must consider alternatives.

### Per-approach format

```
APPROACH {letter}: {Name}
  Summary: 1-2 sentences
  Effort:  S / M / L / XL  (Claude-assisted scale)
  Risk:    Low / Med / High
  Pros:    2-3 bullets
  Cons:    2-3 bullets
  Reuses:  existing code / patterns leveraged
```

### Composition rules

- At least 2 approaches. 3 preferred for non-trivial plans.
- One MUST be **minimal viable** (fewest files, smallest diff).
- One MUST be **ideal architecture** (best long-term trajectory).
- These have **equal weight**. Don't default to minimal viable because it's
  smaller. Recommend whichever best serves the goal. If the right answer
  is a rewrite, say so — but cross-check against 1C (dream state).
- If only one approach exists, explain concretely why alternatives were
  eliminated. "Only one approach makes sense" is itself a finding.

### Recommendation

```
RECOMMENDATION: Approach {letter} because {one-line reason mapped to an
engineering preference}.
```

### Stop rule

Do NOT proceed to mode selection (1F) without user approval of the chosen
approach. AskUserQuestion presenting the recommendation, with options:

- A) Approve recommended approach — proceed to 1D
- B) Pick a different approach — specify which
- C) Revise — regenerate alternatives
- D) None — return to /immutable:office-hours

If the user picks B, the chosen approach replaces the recommended one for
the rest of the review. If the user picks C, regenerate from 1C-bis. If D,
exit to office-hours.

---

## 1D — Mode-Specific Analysis

Run the analysis matching the user's likely mode (will be confirmed in 1F).
This sub-phase tries to pre-load the right questions so 1F is informed.

### SCOPE EXPANSION analysis

Run all three:

1. **10× check** — what's the version 10× more ambitious delivering 10× more
   value for 2× the effort? Describe concretely. Often the answer is "no
   such version exists" — say so explicitly.
2. **Platonic ideal** — if the best engineer in the world had unlimited
   time + perfect taste, what would this system look like? What would the
   user feel? Start from experience, not architecture.
3. **Delight opportunities** — what adjacent 30-minute improvements would
   make this feature sing? List at least 5 candidates.

### SELECTIVE EXPANSION analysis

Run HOLD SCOPE analysis first (below), then surface expansion candidates:

1. **10× check** (concrete, single answer)
2. **Delight opportunities** (at least 5 candidates)
3. **Platform potential** — would any expansion turn this feature into
   infrastructure other features build on?

### HOLD SCOPE analysis

1. **Complexity check** — if the plan touches more than 8 files OR introduces
   more than 2 new classes / services, treat as smell; challenge whether the
   same goal is achievable with fewer parts.
2. **Minimum set of changes** that achieves the goal. Flag deferrable work.

### SCOPE REDUCTION analysis

1. **Ruthless cut** — what is the absolute minimum that ships value to a
   user? Everything else is deferred. No exceptions.
2. **What can be a follow-up PR?** Separate "must ship together" from
   "nice to ship together."

---

## 1E — Temporal Interrogation (only for EXPANSION / SELECTIVE / HOLD)

Think ahead to implementation. Decisions resolved NOW, not during work:

```
HOUR 1 (foundations):    What does the implementer need to know?
HOUR 2-3 (core logic):   What ambiguities will they hit?
HOUR 4-5 (integration):  What will surprise them?
HOUR 6+ (polish/tests):  What will they wish they'd planned for?
```

Note: these are human-team hours. With AI assistance, 6h compresses to
~30-60min. Present both scales when discussing effort.

Surface these as questions NOW, not as "figure it out later."

---

## 1F — Mode Selection

Present four options via AskUserQuestion using `prc.phase1.mode_selection`:

1. **SCOPE EXPANSION** — plan is good but could be great. Dream big. Every
   expansion opted in individually via cherry-pick ceremony in 1D output.
2. **SELECTIVE EXPANSION** — scope is baseline, but show me what else is
   possible. Cherry-pick. Neutral recommendations.
3. **HOLD SCOPE** — scope is right. Review with maximum rigor. Make it
   bulletproof. No expansions surfaced.
4. **SCOPE REDUCTION** — plan is overbuilt or wrong-headed. Propose a
   minimal version, then review that.

### Context-dependent defaults

| Situation | Default mode |
|-----------|--------------|
| Greenfield feature | EXPANSION |
| Feature enhancement / iteration | SELECTIVE EXPANSION |
| Bug fix / hotfix | HOLD SCOPE |
| Refactor | HOLD SCOPE |
| Plan touching > 15 files | suggest REDUCTION unless pushed back |
| User says "go big" / "ambitious" / "cathedral" | EXPANSION (no question) |
| User says "hold scope but tempt me" / "cherry-pick" | SELECTIVE EXPANSION |

After mode is selected:

1. Confirm which 1C-bis approach applies under the chosen mode. EXPANSION
   may favor ideal architecture; REDUCTION may favor minimal viable.
2. If EXPANSION / SELECTIVE EXPANSION, run the **opt-in ceremony**:
   - Describe the vision first.
   - Distill concrete proposals from 1D's output.
   - Present each as its own AskUserQuestion. Recommend enthusiastically.
     User decides per item.
   - Options: A) Add to scope, B) Defer to TODOS.md, C) Skip.
   - Accepted items become plan scope for the remaining sections. Rejected
     items go to "NOT in scope."
3. Once selected, **commit fully**. Do not silently drift. Do not re-argue
   for smaller scope during Section 1-11. Do not silently reduce scope or
   skip planned components.

### Render `prc.phase1.scope_locked`

Once 1F is complete, render the scope-locked summary:

```
Phase 1F decision:
  Mode:      {EXPANSION / SELECTIVE / HOLD / REDUCTION}
  Approach:  {1C-bis letter} ({approach name})

Confirmed scope:
{bullet list of in-scope items}

Out of scope (deferred or rejected):
{bullet list, each with one-line rationale}

Triggers for downstream phases:
- Pitch supersede candidate: {yes/no, why}
- ADR-authoring candidate:    {yes/no, scope}
```

---

## Pitfalls catalog

| Pitfall | Why it's bad | Fix |
|---------|--------------|-----|
| Skipping 1A premise re-confirmation when the design note has Premises | Carries forward an unchallenged framing | Re-confirm each premise; flipped → forces scope update |
| Generating only 1 alternative in 1C-bis | Skips the most important step | Force ≥2; explain when only 1 exists |
| Defaulting recommendation to minimal viable | Bias toward smaller diff regardless of trajectory | Recommend whichever serves goal best; cross-check 1C |
| Picking mode before alternatives are evaluated | Mode is downstream of approach | Always run 1C-bis before 1F |
| EXPANSION without cherry-pick ceremony | Scope creeps without user opt-in | Each expansion is its own AskUserQuestion |
| Silent scope drift during Section 1-11 | Erodes Phase 1F's commitment | Anti-skip rule + re-statement of `prc.phase1.scope_locked` summary |

---

## Cross-references

- Mode-selection defaults table: also referenced by Phase 0.5 (landscape
  check runs only when expansion is on the table).
- "Approaches considered" output is rendered into the transient review note
  in Phase 4.2 — keep the format consistent with `oh.phase3.approach_template`
  (office-hours skill) so the same approach can be carried across skills
  without reformatting.
