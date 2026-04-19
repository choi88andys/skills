---
name: adr
description: Guided authoring for append-only Architecture Decision Records (ADRs) in an immutable SDD repo. Conducts a focused interview (context, decision, consequences, alternatives), runs multi-persona adversarial review, and writes the ADR only when a 90% completeness gate passes. Use when a team makes a load-bearing technical direction that future engineers must understand. Triggers - "/immutable:adr", "ADR 작성", "아키텍처 결정 기록", "architectural decision".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch
license: MIT
---

# /immutable:adr — Guided Immutable ADR Authoring

Interactively author an append-only Architecture Decision Record. Shares the append-only mechanics of `/immutable:prd` (supersede chain, `deprecated` flag, 90% gate) but with an ADR-specific interview shape (Nygard template) and review personas tuned for technical decisions.

> **Schema reference**: see [`../SCHEMA.md`](../SCHEMA.md) for shared frontmatter, reference policy, and directory conventions.

## Language Directive

User-facing prompts MUST use the team's language from `.immutable-prd/config.yml` (`team_language`, default `ko`). Skill instructions are English; user-visible strings translate consistently.

## Preconditions

1. `.immutable-prd/config.yml` exists at the app repo root (or detected via walk-up). `repo_mode` must be `two-repo-app` or `single-repo`. If absent, prompt the user to create one via the skeleton in `../SCHEMA.md`. Stop if declined.
2. `adr_path` resolves to an existing directory. If the directory does not exist, offer to create it with a `TEMPLATE.md` seed.
3. A pitches allowlist is reachable: local at `pitches_path` (single-repo) or at `<spec_repo_path>/<pitches_path_in_spec>/README.md` (two-repo-app). If neither is reachable, ADR may still be authored with `domain: _global`; non-`_global` ADRs require the allowlist check.

The skill **writes the file only**. It never commits or pushes.

## Invocation

```
/immutable:adr
```

Optional free-text initial context:

```
/immutable:adr switch state management from Provider to Riverpod
```

---

## Overall Process (5 stages)

```
Stage 1: Intent Routing           — new / update (supersede) / deprecate + scope
Stage 2: Context Intake (opt.)    — related pitches, prior ADRs, external reference
Stage 3: Interview (Nygard)        — Context / Decision / Consequences / Alternatives
Stage 4: Adversarial Review       — 3 personas, each surfaces ≥1 gap
Stage 5: 90% Completeness Gate + File Generation
```

Stop immediately on any stage failure. Loop back to Stage 3 when Stage 4 finds issues.

---

## Stage 1 — Intent Routing

### 1.1 Initial context

If the user passed no argument, ask once:

> "무엇을 결정하려고 하세요? 한두 문장으로 설명해주세요."

### 1.2 Environment scan (parallel)

- Read `.immutable-prd/config.yml` → resolve ADR directory, pitches path, team language.
- Glob ADR directory for existing files. Read frontmatter of each to build the supersede chain index.
- If the user's intent mentions a specific domain or feature, cross-reference with active pitches in that domain.

### 1.3 Classify intent

| Signal | Intent |
|---|---|
| No prior ADR on this topic | `new` (`supersedes: null`) |
| Existing active ADR on the same topic, but direction is being reversed or significantly revised | `update` (copy latest, revise, flip old to `deprecated: true`) |
| "This decision is no longer applicable" with no replacement | `deprecate-only` (flip only) |

### 1.4 Scope classification

Ask which scope the ADR covers:

> "이 결정의 범위가 어떻게 되나요?
> (1) 특정 도메인의 pitch에 종속 (도메인 이름 지정)
> (2) 여러 도메인/기능에 걸친 전역 결정 (`_global`)"

- Scope `(1)` → `domain: <name>`, `references.pitches` must include ≥1 active pitch in that domain.
- Scope `(2)` → `domain: _global`, `references.pitches` may be empty. Require a written scope statement in the body.

### 1.5 Confirmation (mandatory)

Always confirm before proceeding. Show:

- Intent (new / update / deprecate-only)
- Scope (domain or `_global`)
- Base file if superseding
- Proceed option

If ambiguous, ask rather than guess.

### 1.6 Deprecate-only flow

Skip to Stage 5. Ask for a reason string. Flip `deprecated: false → true` on the target file (single-line change). Emit handoff with no new file.

---

## Stage 2 — Context Intake (Optional)

Opt-in. Accept curated external materials:

- **Referenced pitches**: pitch filenames to bind the ADR to. Skill auto-reads these.
- **Prior ADR chain**: for `update` intent, the latest active ADR auto-loads as baseline.
- **External docs**: RFC, benchmark report, vendor comparison. URL or local path.
- **Discussion excerpts**: paste summaries of Slack / Discord threads (5k-word cap).

Reuse the anti-dumping filters from `/immutable:prd` Stage 1.5:

| Signal | Action |
|---|---|
| Document > 5,000 words | Refuse. Ask for 1–3 relevant sections only. |
| > 10 pages total | Refuse. Ask to distill. |
| Authenticated URL without integration | Ask for pasted summary. |

For each accepted attachment, **summarize → confirm with user → store corrected summary only**. Discard raw dumps.

Skip path: if user says "없음", proceed to Stage 3.

---

## Stage 3 — Interview (Nygard template)

**One question at a time, always with a recommended answer** derived from upstream pitches / prior ADR / intake summary / industry defaults.

### Branch A — Context

- What problem does this decision address? What is the current state?
- What constraints exist? (business, regulatory, team skill, existing code, cost)
- What forces push toward a change? (pain point, new requirement, bug class)

**Completion criterion**: a third-party engineer can summarize "what triggered this decision" in ≤3 sentences.

### Branch B — Decision

- **State the decision as a single declarative sentence.** ("We will adopt X for Y.")
- What is included in scope? What is explicitly excluded?
- What is the minimum viable implementation path?

**Completion criterion**: the decision is one unambiguous sentence readable out of context.

### Branch C — Consequences

Enumerate trade-offs:

- **Positive** — what gets better
- **Negative** — what gets worse or what we give up
- **Neutral / cost of adoption** — migration effort, training, tooling

**Completion criterion**: at least 2 positive AND at least 2 negative consequences listed. "All positive, no negative" is a sign of un-examined decision — push back.

### Branch D — Alternatives Considered

For at least 2 alternatives, capture:

- Name of the alternative
- Why it was rejected (1–2 sentences)
- What would change our mind (revisit trigger)

"We didn't consider alternatives" is not acceptable. If truly only one option exists, the decision may not warrant an ADR.

### Branch E — Rollout & Validation

- How will we know this decision is correct? (metric, milestone, review date)
- What is the rollback story if this decision fails?
- Are there feature flags, staged migrations, or gated experiments?

**Completion criterion**: at least one explicit signal/metric OR a scheduled review date.

### Branch F — References (frontmatter assembly)

Confirm the final `references` block:

- `pitches`: list of pitch filenames (MUST be non-empty unless `domain: _global`)
- `adrs`: prior ADRs this one builds on or overrides (non-supersede dependencies)
- `designs`, `tech_specs`: usually empty for an ADR; allowed if the decision directly reacts to an existing design/tech-spec

---

## Stage 4 — Adversarial Review (3 Personas)

Each persona MUST surface ≥1 gap. Gaps raised by 2+ personas escalate one severity level.

### Persona 1 — New Engineer (onboarding next quarter)

Question: "Can I understand this decision and apply it consistently from this document alone?"

Check for:
- Vague decision statements ("적절한 방향으로")
- Missing rollback or escape hatch
- Unstated prerequisites (e.g., tooling, infra, SDK version)

### Persona 2 — Maintainer (2 years from now)

Question: "Will I know whether this decision still applies when I inherit this codebase?"

Check for:
- Absent revisit triggers — "decide X; never look back"
- Undocumented assumptions that will silently become false
- Missing link to the pitch(es) that justify the decision

### Persona 3 — Product Lead

Question: "Does this decision respect the product promise in the referenced pitches?"

Check for:
- Trade-offs that quietly break a referenced pitch's `[MUST]` requirement
- Scope creep (ADR decides more than it claims)
- Missing linkage when the decision obviously affects a feature currently in progress

### Output

Numbered list per persona. For each finding, offer:

- **반영** → return to Stage 3 for revision
- **No-go로 이동** → add to "Explicitly out of scope" in the body
- **반려** → record counter-reasoning; proceed

---

## Stage 5 — 90% Completeness Gate

### Checklist (6 criteria)

| # | Criterion | Pass Condition |
|---|---|---|
| 1 | Context is clear | Third party summarizes trigger in ≤3 lines; no `[미확정]` remains |
| 2 | Decision is one sentence | A single declarative statement, not a paragraph of hedges |
| 3 | Consequences balanced | ≥2 positive AND ≥2 negative explicitly listed |
| 4 | Alternatives considered | ≥2 alternatives with rejection reason |
| 5 | Revisit trigger present | Metric, milestone, OR scheduled review date |
| 6 | References valid | `references.pitches` non-empty (unless `_global`), all referenced files exist and parse |

### Judgment

- **5 or 6 of 6 pass** → proceed to generation
- **Fewer than 5 pass** → refuse; loop to the relevant branch
- **Any `[미확정]` tag anywhere** → refuse regardless of count

### Refusal format

Use the same checklist style as `/immutable:prd` Stage 5 refusal.

---

## Stage 6 — File Generation and Handoff

### Filename

- **new / update**: `<adr-dir>/YYYY-MM-DD-<slug>.md` (flat, not per-domain).
- **update**: after writing the new file, flip previous active file's `deprecated: false → true`.
- **deprecate-only**: flip only.

### Frontmatter

```yaml
---
type: adr
domain: <name | _global>
supersedes: <previous-filename | null>
deprecated: false
references:
  pitches:    [<filename>, …]   # non-empty unless _global
  adrs:       [<filename>, …]
  designs:    []
  tech_specs: []
---
```

### Body structure

```
# <ADR Title>

## 맥락 (Context)

(Branch A)

## 결정 (Decision)

(Branch B — single declarative sentence, then optional 1-paragraph elaboration)

## 결과 (Consequences)

### 긍정적 영향
- …

### 부정적 영향 / 트레이드오프
- …

### 채택 비용 / 중립
- …

## 검토한 대안 (Alternatives Considered)

- **<대안 A>** — <기각 사유>. <재검토 조건>.
- **<대안 B>** — …

## 재검토 조건 (Revisit Triggers)

(Branch E)

## 범위 제외

(Optional — things this ADR explicitly does NOT decide)
```

### Handoff

Emit commit instructions (GitHub GUI / CLI), do NOT commit.

---

## Hard Prohibitions

1. Never write a file that fails the 90% gate.
2. Never advance with any `[미확정]` tag.
3. Never edit body of an existing ADR. Append-only + supersede chain.
4. Never commit or push.
5. Never generate an ADR with `references.pitches` empty unless `domain: _global` AND the body includes a scope statement.
6. Never claim a decision has no negative consequences — push back until the user names ≥2.
7. Never skip Alternatives — if the user insists on "there was no alternative", question whether this needs an ADR at all.

---

## Credits

Pattern sources:

- Michael Nygard, *Documenting Architecture Decisions* (2011) — Context / Decision / Consequences template
- [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — revisit-trigger field convention
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — grill-me interview pattern
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — adversarial review pattern

No source files copied. Patterns referenced only.
