---
name: init
description: Bootstrap a new immutable SDD repo by copying a starter from the plugin into the current directory. Detects empty vs existing repo, helps select mode (spec / app / single) + team language + profile handling, copies the matching starter, and emits next-step git commands. Use when starting a new immutable SDD project or adding immutable configuration to an existing project. Triggers - "/immutable:init", "immutable 시작", "SDD 부트스트랩", "새 spec 레포".
allowed-tools: Read, Write, Bash, Glob, Grep
license: MIT
---

# /immutable:init — Bootstrap an Immutable SDD Repo

Copies one of six bundled starters into the current directory and emits handoff commands. Never overwrites existing files. Never runs git operations.

## Language Directive

**User-facing prompts default to Korean.** Switch to English at any point if the user requests it. Skill instructions below are English for maintainability; every user-visible string translates consistently.

## Preconditions

- Current working directory is where the user wants the repo bootstrapped (do NOT `cd` elsewhere).
- Plugin starter files are accessible via `${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>/`. Claude Code sets `CLAUDE_PLUGIN_ROOT` when invoking plugin skills. If unset (rare), fall back to walking up from the skill's own location.

## Invocation

```
/immutable:init
```

Optional free-text initial context (mode / language hint):

```
/immutable:init spec-only Korean
/immutable:init single-repo English
```

Free-text is parsed for hints only — the skill still walks Stages 2–4 to confirm.

---

## Overall Process (7 stages)

```
Stage 1: Environment Probe        — detect CWD state, suggest mode
Stage 2: Mode Selection           — spec / app / single, with default from probe
Stage 3: Language Selection       — ko / en (default ko)
Stage 4: Profile Mode             — bundled default / repo-local override / skip
Stage 5: File Copy                — starter → CWD, no-overwrite
Stage 6: Git Init Suggestion      — only if .git absent
Stage 7: Handoff                  — next-step commands
```

**Stop on user refusal at any stage.** No partial copies on cancellation.

---

## Stage 1 — Environment Probe

Use Bash + Glob + Read to inspect the CWD. Report findings before asking anything.

### 1.1 Probe checklist

| Signal | Detection | Implies |
|---|---|---|
| `.git/` present | `[ -d .git ]` | Existing git repo — skip Stage 6 git init suggestion |
| `.immutable-prd/config.yml` present | `[ -f .immutable-prd/config.yml ]` | Already initialized — STOP (1.3) |
| `pitches/` present | `[ -d pitches ]` | Spec-side already started (suggest `two-repo-spec`) |
| `adr/` present | `[ -d adr ]` | App-side already started (suggest `two-repo-app`) |
| `lib/`, `src/`, `app/` present | any of the three | App code (suggest `two-repo-app` or `single-repo`) |
| Both `pitches/` and code dirs present | combination | Suggest `single-repo` |
| Empty (only `README.md` or none) | dir listing | Empty bootstrap (suggest `two-repo-spec`) |

Run the checks in parallel:

```bash
[ -d .git ] && echo "git: yes" || echo "git: no"
[ -f .immutable-prd/config.yml ] && echo "immutable: initialized" || echo "immutable: not initialized"
ls -lA 2>/dev/null | head -30
```

### 1.2 Report findings

Show a structured summary:

> "현재 디렉토리 상태:
> - .git: <있음 | 없음>
> - 기존 immutable 설정: <없음 | 있음 (config.yml 발견)>
> - 감지된 디렉토리: <pitches/ 있음, adr/ 없음, lib/ 없음 | …>
> - 추천 모드: <two-repo-spec | two-repo-app | single-repo>
> - 추천 근거: <empty dir이라 spec-only를 우선 추천 | pitches/와 lib/이 동시에 감지됨>"

### 1.3 Already-initialized refusal

If `.immutable-prd/config.yml` exists, STOP with this exact message (Korean):

> "이 디렉토리는 이미 immutable로 초기화되어 있습니다 (.immutable-prd/config.yml 존재).
>
> 옵션:
> - v2 → v3 업그레이드: `/immutable:migrate` (S4 deliverable, 아직 미출시 시 수동 편집)
> - 재-부트스트랩: `.immutable-prd/config.yml`을 먼저 삭제한 뒤 `/immutable:init` 재실행
> - 추가 starter 적용 (single → two-repo 분리 등): 별도 디렉토리에서 init 실행 후 수동 통합
>
> 작업을 중단합니다."

Do not proceed past Stage 1 in this case.

---

## Stage 2 — Mode Selection

Show all three options with the probe's recommendation marked. Always confirm with the user — never auto-select.

> "어떤 starter로 시작할까요?
>
> (1) two-repo-spec — 스펙 전용 레포 (pitches/만, sibling app repo와 분리 운영)
> (2) two-repo-app — 앱 전용 레포 (adr/만, sibling spec repo 참조)
> (3) single-repo — pitches + adr 합본 레포 (작은 팀 / 단일 레포 운영 시)
>
> [추천: (<번호>) — <근거 한 줄>]
>
> 번호 또는 옵션 이름으로 선택해주세요."

If the user passed a free-text hint matching one of the modes (e.g., "spec-only", "app", "single"), pre-fill the recommendation but still confirm.

If user picks an option that conflicts with the probe (e.g., picks `two-repo-spec` when `lib/` exists), warn but allow:

> "선택한 모드(two-repo-spec)는 감지된 코드 디렉토리(lib/)와 어울리지 않습니다. 보통 single-repo 또는 two-repo-app이 적합합니다. 그래도 진행하시겠습니까?"

---

## Stage 3 — Language Selection

> "팀 작업 언어를 선택해주세요:
>
> (1) Korean (ko) — 기본
> (2) English (en)
>
> [추천: (1)]
>
> 번호로 선택해주세요. (다른 언어는 v0.6+ 지원 예정.)"

This sets `team_language` in config.yml AND determines which starter is copied (`<mode>-<lang>`). The plugin loads the matching default profile (`default-ko.yml` or `default-en.yml`) at /immutable:prd / /immutable:adr invocation time.

---

## Stage 4 — Profile Mode

> "프로필 (섹션 헤딩, 적대적 리뷰 personas, 90% gate criteria 등 customization) 처리 방식:
>
> (1) bundled default 사용 — config.yml에 `profile:` 명시 안 함. 플러그인이 자동으로 default-<lang>를 로드. **권장 (가장 간단, 추후 변경 가능)**
> (2) repo-local 복사 — `.immutable-prd/profile.yml`로 default를 복사하고 config가 그것을 가리킴. 팀이 즉시 editable
> (3) skip 후 나중에 결정 — config에 주석으로만 남김 (현재는 동작 X와 동일)
>
> [추천: (1)]"

### Branch handling

- **(1) bundled default**: leave config.yml's `profile:` line as a comment (it's already commented in the starter). No additional file copy.
- **(2) repo-local copy**: copy `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml` → `<CWD>/.immutable-prd/profile.yml`, then edit the copied config.yml to uncomment the `profile: .immutable-prd/profile.yml` line. Mention to the user: "프로필 파일을 직접 편집해서 sections / personas / gate threshold를 customize할 수 있습니다."
- **(3) skip**: identical to (1) for v0.5 (the comment stays as documentation). Note to user: "나중에 (2)로 전환하려면 `cp ${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml .immutable-prd/profile.yml` 실행 후 config.yml의 `profile:` 라인 주석 해제."

---

## Stage 5 — File Copy

Source: `${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>/`
Destination: CWD (always — never `cd` elsewhere)

### 5.1 Enumerate source files

```bash
src="${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>"
[ -d "$src" ] || { echo "starter not found at $src"; exit 1; }
find "$src" -type f
```

### 5.2 Copy with no-overwrite

For each source file:

1. Compute destination = `<CWD>/<path-relative-to-src>`
2. If destination exists with non-empty content: SKIP. Append to `skipped[]` list.
3. If destination directory is missing: `mkdir -p` it.
4. Read source via Read tool, Write to destination.
5. Append to `copied[]` list.

**Implementation note**: prefer Read + Write over `cp` so the skill stays within Claude Code's tracked file operations. For empty `.gitkeep` files, run `touch <dest>` via Bash.

### 5.3 Profile-copy branch (Stage 4 = option 2)

After 5.2, additionally:

1. Read `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`
2. Write to `<CWD>/.immutable-prd/profile.yml` (skip if exists)
3. Edit `<CWD>/.immutable-prd/config.yml`:
   - Find the line `# profile: .immutable-prd/profile.yml`
   - Replace with `profile: .immutable-prd/profile.yml` (uncomment)

### 5.4 Report

```
복사 완료 (<N>개):
  - .immutable-prd/config.yml
  - CONTRIBUTING.md
  - pitches/README.md
  - pitches/TEMPLATE.md
  - pitches/_shared/.gitkeep

건너뜀 (이미 존재, <M>개):
  - (해당 없음 또는 목록)

(profile-mode가 (2)였다면 추가:)
  - .immutable-prd/profile.yml (편집 가능)
  - .immutable-prd/config.yml에 profile: 라인 활성화됨
```

If any file was skipped, suggest the user diff the bundled starter against their existing copy to decide whether to merge changes manually.

---

## Stage 6 — Git Init Suggestion

If `.git/` was absent in Stage 1:

> "이 디렉토리는 git 레포가 아닙니다. 다음 명령으로 초기화할 수 있습니다:
>
> ```bash
> git init
> git add .
> git commit -m \"feat: bootstrap immutable SDD\"
> ```
>
> (스킬은 git 명령을 실행하지 않습니다. 위 명령을 직접 실행해주세요.)"

If `.git/` was present:

> "기존 git 레포가 감지되었습니다. 다음 명령으로 변경사항을 커밋할 수 있습니다:
>
> ```bash
> git add .
> git commit -m \"feat: bootstrap immutable SDD\"
> ```"

---

## Stage 7 — Handoff

Mode-specific next-step output.

### two-repo-spec

> "Bootstrap 완료 (mode: two-repo-spec, lang: <ko|en>).
>
> 다음 단계:
> 1. 위 Stage 6의 git 명령 실행
> 2. `pitches/README.md`의 도메인 허용 목록 편집 — 예시 행을 실제 팀 도메인으로 교체
> 3. 첫 pitch 작성: `/immutable:prd`
>
> 참고:
> - Pitch 컨벤션 전체: `CONTRIBUTING.md`
> - ADR은 sibling app repo에서 따로 운영 (`/immutable:init` for app starter)"

### two-repo-app

> "Bootstrap 완료 (mode: two-repo-app, lang: <ko|en>).
>
> 다음 단계:
> 1. 위 Stage 6의 git 명령 실행
> 2. `.immutable-prd/config.yml`의 `spec_repo_path: ../<your-spec-repo>` 수정 — placeholder를 실제 sibling spec repo 경로로 교체
> 3. 첫 ADR 작성: `/immutable:adr`
>
> 참고:
> - ADR 컨벤션: `adr/README.md`
> - Pitches는 sibling spec repo에서 따로 작성"

### single-repo

> "Bootstrap 완료 (mode: single-repo, lang: <ko|en>).
>
> 다음 단계:
> 1. 위 Stage 6의 git 명령 실행
> 2. `spec/pitches/README.md`의 도메인 허용 목록 편집
> 3. 첫 pitch 작성: `/immutable:prd` (또는 첫 ADR: `/immutable:adr`)
>
> 참고:
> - Pitch 컨벤션: `spec/CONTRIBUTING.md`
> - ADR 컨벤션: `adr/README.md`"

---

## Hard Prohibitions

1. **Never overwrite existing files.** If a file exists at the destination, skip + report. The user's existing content is sacred.
2. **Never run git operations.** `git init`, `git add`, `git commit` are user-only. Only suggest commands.
3. **Never commit or push.**
4. **Never write outside CWD.** All copies are to the user's current directory.
5. **Never proceed with already-initialized repos.** If `.immutable-prd/config.yml` exists, refuse and explain (Stage 1.3).
6. **Always confirm mode/language with the user before copying.** No auto-selection without explicit user agreement.
7. **Never modify the bundled starter files.** They live in the plugin (read-only).

---

## Available Starters

Six starters ship with the plugin (S2). Each is a self-contained tree the skill copies into CWD.

| Starter | Mode | Language | File count | Purpose |
|---|---|---|---|---|
| `spec-ko` | two-repo-spec | ko | 5 | Korean spec repo |
| `spec-en` | two-repo-spec | en | 5 | English spec repo |
| `app-ko` | two-repo-app | ko | 3 | Korean app repo (ADRs only) |
| `app-en` | two-repo-app | en | 3 | English app repo (ADRs only) |
| `single-ko` | single-repo | ko | 7 | Korean single repo (pitches + ADRs) |
| `single-en` | single-repo | en | 7 | English single repo (pitches + ADRs) |

Additional locales (`ja`, etc.) added without schema changes — drop a new starter directory and a new `default-<locale>.yml` profile.

---

## Credits

- Design pattern: marketplace-bundled starter directories, common in modern CLI tooling (e.g., `npm init`, `cargo new`, `poetry new`).
- No source files copied. Patterns referenced only.
