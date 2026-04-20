---
name: prd
description: Guided authoring for immutable, append-only PRD/pitch files. Conducts a grill-me style interview with context intake, domain-language check, multi-persona adversarial review, and a 90% completeness gate before writing any file. Use when a team needs to produce new spec/PRD content or version-update existing ones in an append-only SDD repo. Triggers - "/immutable:prd", "pitch 작성", "스펙 작성", "PRD 추가", "피치 만들어".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch
---

# /immutable:prd — Guided Immutable PRD Authoring

Interactively author an append-only pitch-style PRD file. Enforces format, structure, scope, and domain language. Generates the file only when the answer set passes a 90% completeness gate.

## Language Directive

**All user-facing prompts, questions, and messages MUST be in the team's working language (default: Korean, set by `team_language` in `.immutable-prd/config.yml`).** The skill instructions below are in English for maintainability; every message shown to the user is in the team's language. If the team works in a different language, translate all user-facing strings consistently.

## Profile Resolution (v0.5+)

The skill is **profile-aware** in v0.5: section headings, the gate threshold, persona checks, identifier-detection regex, and filename rules are sourced from a profile YAML rather than hardcoded.

### Resolution order

1. If `.immutable-prd/config.yml` declares `profile: <path>` (v3 configs only) AND the file exists → load it.
2. Else load the bundled default matching `team_language` from `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`.
3. If no matching locale profile exists → fall back to `default-en.yml` with a one-line warning.

### Backward compatibility (zero-action migration)

`version: 2` configs (without `profile:`) continue to work unchanged — the skill auto-loads the bundled default profile matching `team_language`. Behavior is identical to v0.4. Run `/immutable:migrate` (S4) when ready to graduate to v3.

### Profile fields consumed by /immutable:prd in v0.5

| Profile field | Where used |
|---|---|
| `sections[].heading` | Stage 6 body assembly (rendered in pitch file) |
| `sections[].id` / `min_items` / `description` | Stage 2 interview branches (completion criteria) |
| `normative_keywords[].token` / `meaning` | Stage 2 Branch C bracket vocabulary |
| `identifier_patterns[].regex` / `hint` | Stage 3 code-identifier detection |
| `naming.filename_pattern` / `slug_case` / `forbidden_slug_patterns` | Stage 6 filename validation |
| `feature_flag.*` | Stage 2 Branch F (key prefix, states, fallback) |
| `domain_allowlist.source` / `reserved_domains` | Stage 1 / Stage 3 domain checks |
| `gate.total` / `pass_threshold` / `criteria` | Stage 5 90% completeness gate |
| `gate.unresolved_tag` | Stage 2/5 unresolved-answer tag (e.g., `[미확정]` for ko, `[TBD]` for en) |
| `gate.reject_on_unresolved` | Stage 5 hard-block flag |

The Korean inline strings below remain as the v0.5 default rendering — they match `default-ko.yml`. When `team_language: en`, render the equivalent strings from `default-en.yml`. v0.6+ moves all inline strings to a `strings/strings.<locale>.yml` catalog (S3 deliverable).

## Preconditions

The skill assumes the working directory is the root of a pitch spec repo with the following convention:

```
<repo-root>/
├── pitches/
│   ├── README.md        # contains a "## 도메인 허용 목록" (or "## Allowed Domains") table with rows `| `<domain>` | <description> |`
│   ├── TEMPLATE.md      # pitch body template
│   └── <domain>/
│       └── YYYY-MM-DD-<kebab-slug>.md
└── CONTRIBUTING.md      # rules SSoT
```

Each pitch file requires YAML frontmatter:

```yaml
---
domain: <name>              # must match parent directory
supersedes: <filename|null> # previous active file in the same domain
deprecated: false           # flipped to true when a new version supersedes
---
```

If the repo uses a different structure, fork and adapt the SKILL.md. Config file overrides are out of scope for v0.x.

The skill only **writes** the file. It never commits or pushes. The user reviews the generated file and commits manually.

## Invocation

```
/immutable:prd
```

Optional free-text argument for initial context:
```
/immutable:prd 공지에 자동 모달 기능 추가
```

---

## Overall Process (6 Stages)

```
Stage 1: Intent Routing           — classify new / update / deprecate + confirm domain
Stage 1.5: Context Intake (opt.)  — accept curated external context (Figma/Notion/local/Slack)
Stage 2: Interview                 — one question at a time, with a recommended answer
Stage 3: Domain Language Check    — code identifier detection, terminology drift
Stage 4: Adversarial Review       — three personas each surface at least one gap
Stage 5: 90% Completeness Gate    — 7-criterion checklist; generate file only if passed
Stage 6: File Generation & Handoff
```

**Stop immediately on any stage failure.** Do not write the file until all stages pass. Loop back to Stage 2 when Stage 3 or 4 finds issues.

---

## Stage 1 — Intent Routing

### 1.1 Gather initial context

If the user did not pass an argument, ask exactly once:

> "무엇을 작성하려고 하세요? 한두 문장으로 간단히 설명해주세요."

### 1.2 Environment scan (parallel)

Use Bash + Glob + Read to collect:

1. **Resolve config + profile** (added v0.5):
   - Walk up from CWD to find `.immutable-prd/config.yml` (use `scripts/find_config.sh`).
   - If config absent: prompt the user to run `/immutable:init` first, or fall back to the inferred-defaults path documented in `../SCHEMA.md`.
   - Read `team_language`, `profile:` (if v3), and other config fields.
   - Load profile per the resolution order in **Profile Resolution** above. Cache the parsed profile for the rest of the session.
2. Confirm `pitches/` exists in CWD (or at the configured `pitches_path`). If not, stop:
   > "현재 디렉토리에 pitches/가 없습니다. 스펙 레포 루트에서 다시 실행해주세요."
3. Read `pitches/README.md` — extract domain allowlist from the allowed-domains table (rows matching `` | `<name>` | ``). Use `profile.domain_allowlist.source` if it differs from the default `pitches/README.md`.
4. For each allowlisted domain directory, scan `*.md` frontmatter to find the active pitch (`deprecated: false`, not `README.md`, not `TEMPLATE.md`).

### 1.3 Classify intent

| Signal | Intent |
|---|---|
| New feature/flow, fits no allowlisted domain | `new-domain` (requires allowlist update) |
| New feature/flow, fits an existing domain with no prior pitch | `new` (`supersedes: null`) |
| Modification/addition/removal within an existing active pitch's scope | `update` (copy active, revise, flip old deprecated) |
| "No longer provided" with no replacement | `deprecate-only` (flip active's `deprecated` flag) |

### 1.4 Confirmation (mandatory)

Always confirm intent and target before proceeding. Example (Korean):

> "[notice] 도메인 업데이트로 이해했습니다.
> 기준 파일: pitches/notice/2026-04-16-initial.md
> 인터뷰를 시작할까요?
>
> (1) 맞음 — 인터뷰 시작
> (2) 다른 도메인 — 직접 지정
> (3) 신규 도메인 — 허용 목록 추가 절차 안내
> (4) 폐기만 — 인터뷰 없이 deprecated 플립"

If classification is ambiguous, ask rather than guess.

### 1.5 New-domain flow

If `new-domain`:

1. Explain the gate: domain must be added to `pitches/README.md` after lead approval.
2. Ask whether lead approval is obtained. If not, stop.
3. If approved, ask for the proposed slug (English kebab-case).
4. Detect near-duplicates against existing domains (Levenshtein distance ≤ 2 → warn).
5. Add the row to the allowlist, create the directory, proceed with `supersedes: null`.

### 1.6 Deprecate-only flow

Skip the interview. Request a reason string. Flip the target file's `deprecated: false` → `true` (single-line change only). Jump directly to Stage 6.

---

## Stage 1.5 — Context Intake (Optional)

After intent is confirmed, ask whether the user has supporting materials. This stage is **opt-in** — the user can skip.

### Prompt (verbatim required)

The block between `>>> BEGIN VERBATIM` and `<<< END VERBATIM` MUST be displayed to the user **verbatim**. Do not paraphrase, shorten, reorder, or drop guardrail lines (quantity caps, "거절됩니다", "금지", example URLs). Translate to the team's working language only when language is not Korean — preserve every cap and example when translating.

```
>>> BEGIN VERBATIM
참고 자료가 있으면 첨부해주세요 (없으면 '없음'). 다음 중 해당되는 것만:

(a) Figma — 단일 프레임 노드 URL, 1~3개
    예: figma.com/design/.../?node-id=123-456
    ※ 파일 전체 URL은 거절됩니다

(b) Notion/Docs — feature 요약 페이지 1개
    ※ 워크스페이스 루트 URL 금지

(c) 로컬 파일 — .md/.txt, 5페이지 이내

(d) 텍스트 붙여넣기 — 정리된 요지, 30줄 이내
    채팅 로그 전체 X, 결정/요구사항 위주
<<< END VERBATIM
```

### Filtering (anti-dumping)

Before processing, validate inputs:

| Signal | Action |
|---|---|
| File or document > 5,000 words | Refuse. Ask user to specify 1–3 relevant sections only. |
| Figma project / file root URL (no `node-id` query param) | Refuse. Ask for a single frame/node URL with `node-id`. |
| More than 3 Figma node URLs | Refuse. Ask user to keep to 1–3 core screens. |
| Notion workspace root URL or DB view URL | Refuse. Ask for a single feature-related page URL. |
| > 10 pages total across attachments | Refuse. Ask user to distill to essentials first. |
| Pasted text > 30 lines | Refuse. Ask user to distill to key decisions/requirements. |
| URL to authenticated service without MCP integration | Note that content can't be fetched; ask user to paste the summary as text instead. |

Do not proceed with raw dumps. Distillation is the user's responsibility; interpretation is the skill's.

### Summarize-and-confirm loop

For each accepted attachment:

1. Fetch/read the content (WebFetch for public URLs, Read for local files).
2. Extract 5–7 bullet points of facts relevant to the pitch under authorship.
3. Show the bullet summary to the user and ask:
   > "이 자료에서 다음을 읽었습니다. 해석이 맞습니까? 틀린 부분이나 이 pitch 범위 밖 내용이 있으면 지적해주세요."
4. Apply user corrections to the summary.
5. Store the **corrected summary only** as interview context. Discard the raw dump.

### Scope alignment

After all attachments are summarized, ask:

> "이 자료들 중 이번 pitch에 담겨야 할 내용은 무엇이고, 자료에 없지만 pitch에 추가되어야 할 동작은 무엇입니까?"

This prevents Figma-driven or Notion-driven spec where the source dominates instead of serving.

### Skip path

If the user says "없음" or equivalent, skip to Stage 2. Do not pressure for attachments.

---

## Stage 2 — Interview (grill-me pattern)

### Principles

- **One question at a time.** Wait for the answer before the next.
- **Always provide a recommended answer** with each question, derived from the active pitch, analogous patterns in other domains, industry defaults, or the confirmed Stage 1.5 summary. The user can accept, edit, or reject.
- **Forbid speculation.** When the user cannot answer or the answer is vague, record a `[미확정 — {question}]` tag. Never fill gaps with plausible-sounding content.
- **Prefer codebase exploration over asking** when an answer is already present.

### Question Branches (fixed order)

#### Branch A — Background and Problem

Ask about:
- Why is this pitch needed? (user request / business decision / existing bug / compliance)
- What is the current state? (nothing / partial / exists differently)
- What specific gap does this pitch close?

**Completion criterion**: a third party can understand "why this pitch is needed" in ≤3 sentences.

#### Branch B — User Stories (Given/When/Then)

Walk the user flow from start to end. For each branch point elicit:
- **Given**: user's state
- **When**: user action (tap, input, swipe, etc.)
- **Then**: system response

At least one happy path + at least one alternate/error branch. Minimum 2 GWT blocks, ideally 3.

**Completion criterion**: every branch point expressed as a GWT triple.

#### Branch C — Normative Keywords

For each GWT, extract binding statements using the bracket vocabulary from `profile.normative_keywords`. The bundled defaults are RFC 2119:

- `[MUST]` — required, no exceptions
- `[MUST NOT]` — forbidden
- `[SHOULD]` — recommended; justified exceptions allowed
- `[SHOULD NOT]` — discouraged
- `[MAY]` — optional

When the profile overrides `normative_keywords`, render the team's tokens instead of these defaults. Token + meaning come from `profile.normative_keywords[].token` and `.meaning`.

**Completion criterion**: at least 3 bracketed normative statements across the body (matches `profile.gate.criteria[id=normative_minimum]`).

#### Branch D — Edge Cases

Offer a checklist of common candidates:

| Candidate | Applicable? |
|---|---|
| No network connection | Y/N |
| Empty data (empty list) | Y/N |
| Missing permission / expired auth | Y/N |
| Concurrency conflict | Y/N |
| External app missing | Y/N |
| Extreme input (max length, unicode, RTL) | Y/N |

For each applicable case, elicit the expected handling.

**Completion criterion**: at least 2 edge-case rows with explicit handling.

#### Branch E — No-gos (Out of Scope)

Elicit at least one explicit exclusion. Each no-go must be classified as:
- **Deferred** — split into a separate pitch
- **Intentionally not provided** — explain why
- **Outside this pitch's scope** — handled by another domain

**Completion criterion**: at least 1 no-go with a reason or handoff target.

#### Branch F — Feature Flag (optional)

Ask whether a feature flag is needed. If yes, capture:
- **Key**: `ff_<slug>`
- **States**: `deployed` / `hidden`
- **Initial state**: usually `hidden` → promote to `deployed` after internal validation
- **Fallback behavior**: UX in `hidden` state

Apply the **Goldilocks test**: "Can this entire feature be toggled on/off by a single flag?" If no, the pitch is too large and must be split.

---

## Stage 3 — Domain Language Check

### Checks

1. **Code identifier detection** via the regex list in `profile.identifier_patterns`. Bundled defaults (default-ko / default-en):
   - camelCase: `\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b`
   - snake_case: `\b[a-z]+_[a-z_]+\b`
   - PascalCase: `\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b`
   - file paths: `\b[a-z]+/[a-z_/]+\.(dart|swift|ts|js|py|kt)\b`

   Teams override via a custom profile (e.g., add Kotlin object literals, Swift enum cases). Use the `hint` field from `profile.identifier_patterns[]` for the warning message.

   On hit:
   > "본문에 코드 식별자 '`XYZ`'가 있습니다. 도메인 용어로 바꿔주세요. (감지 패턴: <hint>)"

2. **Terminology consistency** against existing active pitches. If a new word is introduced for an already-named concept, call it out.

3. **Frontmatter `domain` consistency** with parent directory and allowlist.

### Failure handling

On violation, return to Stage 2 for the specific branch. Do not advance to Stage 4 until all identifiers are removed.

---

## Stage 4 — Adversarial Review (3 Personas)

Each persona MUST surface at least one gap. "Looks good" is prohibited. Gaps raised by 2+ personas are promoted one severity level.

### Persona 1 — New Engineer

Question: "Could I implement this pitch with only this document?"

Check for:
- Vague directives ("적절히", "보기 좋게", "자연스럽게")
- GWT blocks that are not concrete enough to implement
- Unstated dependencies on other domains

### Persona 2 — Customer Support

Question: "What does the user see in every edge case?"

Check for:
- Coverage of network/permission/external-dependency failure modes
- Defined error messaging or explicit no-go placement
- Hand-wave phrases ("라이브러리 기본 동작에 위임") used excessively

### Persona 3 — Product Lead

Question: "Is this pitch at Feature scale?"

Check for:
- Single-flag toggleability
- Completion within 2–6 weeks
- Epic-level content that should be split
- Overlap or conflict with existing active pitches

### Output

Present findings as a numbered list labeled by persona. Example:

> [신입 개발자] 1. Branch B의 "적절히 조정"이 모호합니다. 수치 또는 판정 조건 필요.
> [고객지원] 1. 네트워크 오류 처리는 있으나 서버 5xx 처리 누락.
> [제품 책임자] 1. "주문하기 탭 초기화"가 플래그 범위 밖으로 보임. 분리 검토 필요.

For each finding, offer three options:
- **반영** → return to Stage 2 for revision
- **No-go로 이동** → add to Branch E explicitly
- **반려** → record counter-reasoning; proceed

---

## Stage 5 — 90% Completeness Gate

### Checklist (7 criteria)

| # | Criterion | Pass Condition |
|---|---|---|
| 1 | Background is clear | Third party can summarize intent in ≤3 lines; no `[미확정]` tags remain |
| 2 | User stories in GWT | At least 2 GWT blocks, all structurally complete |
| 3 | Normative keywords | At least 3 bracketed statements across the body |
| 4 | Edge cases table | At least 2 rows with explicit handling |
| 5 | No-gos defined | At least 1 item with reason or handoff |
| 6 | Zero code identifiers | Stage 3 passed cleanly |
| 7 | Feature-scale scope | Passes the single-flag toggle test |

### Judgment

- **6 or 7 of 7 pass** → proceed to Stage 6
- **Fewer than 6 pass** → refuse generation; loop to the relevant branch
- **Any `[미확정]` tag remains anywhere** → refuse generation regardless of count

### Refusal message (example)

> "아직 생성 기준에 미달합니다:
>
> □ [1] 배경 — 통과
> □ [2] GWT 2개 — 통과
> □ [3] Normative 3개 — 통과
> □ [4] 엣지 2행 — 1행만 작성됨 (미통과)
> □ [5] No-go 1개 — 통과
> □ [6] 코드 식별자 0개 — 통과
> □ [7] Feature 크기 — 범위 초과 판정 (미통과)
>
> Branch D에서 엣지 케이스를 1개 더 추가하고, Branch E에서 범위 축소 결정을 내려주세요."

---

## Stage 6 — File Generation and Handoff

### Determine filename and path

- **new / new-domain / update**:
  - Path: `pitches/<domain>/YYYY-MM-DD-<slug>.md`
  - `YYYY-MM-DD`: today's date (use `date +%Y-%m-%d`)
  - `<slug>`: English kebab-case derived from the title; confirm with the user
- **update** additionally: flip the previous active file's `deprecated: false` → `true`. Only that one line.
- **deprecate-only**: flip only. No new file.

### Frontmatter

```yaml
---
domain: <name>
supersedes: <previous-filename | null>
deprecated: false
---
```

### Body assembly

Start from `pitches/TEMPLATE.md`. Populate sections from interview answers, using **section headings from `profile.sections[].heading`** (looked up by `id`, not hardcoded):

- `# <title>` — user-confirmed title
- `## <profile.sections[id=background].heading>` — Branch A (default-ko: `배경과 문제`; default-en: `Background and Problem`)
- `## <profile.sections[id=user_stories].heading>` — Branch B + Branch C (default-ko: `사용자 스토리 및 수용 조건`; default-en: `User Stories and Acceptance Criteria`)
- `## <profile.sections[id=edge_cases].heading>` — Branch D (default-ko: `엣지 케이스`; default-en: `Edge Cases`)
- `## <profile.sections[id=no_gos].heading>` — Branch E (default-ko: `범위 제외 (No-gos)`; default-en: `Out of Scope`)
- `## <profile.sections[id=feature_flag].heading>` — Branch F (only when used; default-ko/en: `Feature Flag`)

Section order MUST follow the order of entries in `profile.sections`. Skill consults `profile.sections[i].id` to know which interview branch's content fills each section.

### Handoff output

After writing, emit a handoff message. Do NOT commit or push. Example:

> 생성된 파일:
> - `pitches/notice/2026-04-18-auto-modal.md`
> - (update인 경우) `pitches/notice/2026-04-16-initial.md` — deprecated: true로 플립됨
>
> 등록 방법 (두 가지 중 택 1)
>
> [A] GitHub 웹 — 권장
>   1. 스펙 레포의 GitHub 페이지 접속
>   2. 위 경로에 파일 업로드 또는 직접 생성
>   3. 커밋 메시지 컨벤션 (CONTRIBUTING.md 참조):
>      - 신규: `feat(pitch): add <domain> - <slug>`
>      - 업데이트: `feat(pitch): update <domain> - <요지>`
>      - 폐기: `chore(pitch): deprecate <domain> - <사유>`
>   4. "Commit directly to main" 선택
>
> [B] CLI
>   git add pitches/<경로>
>   git commit -m "<메시지>"
>   git push origin main

---

## Hard Prohibitions

1. **Never write a file that fails the 90% gate.** Do not round up.
2. **Never advance past Stage 5 with any `[미확정]` tag remaining.**
3. **Never edit an existing pitch's body.** Append-only. The only allowed in-place change is flipping `deprecated: false` → `true`.
4. **Never commit or push.** File writes only. The user owns the commit decision.
5. **Never include code identifiers in the body.** Domain language only.
6. **Never speculate in interview answers.** Unknown → `[미확정]` tag.
7. **Never skip any stage.** Each stage has an explicit completion criterion.
8. **Never ingest raw dumps from context intake.** Summarize, confirm, then use the summary.

---

## Credits

Design patterns adapted from the following open-source projects:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me` interview pattern, `domain-model` terminology challenge
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria checklist
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer` multi-persona pattern

No source files copied. Patterns referenced only.
