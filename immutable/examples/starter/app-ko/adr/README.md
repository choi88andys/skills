# Architecture Decision Records

이 디렉토리는 본 앱 레포의 **append-only ADR (Architecture Decision Record)** 가 저장되는 곳입니다. ADR은 향후 엔지니어가 이해해야 할 load-bearing 기술 방향을 기록합니다.

> **공통 규칙**: ADR은 `pitch`와 동일한 append-only 메커니즘을 따릅니다. 본문은 한 번 커밋된 뒤 변경 불가, 변경이 필요하면 새 파일을 작성하고 이전 파일의 `deprecated` 플래그만 `true`로 플립합니다. Pitch 측 규칙 전체는 sibling 스펙 레포의 `CONTRIBUTING.md`를 참조하세요.

## 작성 도구

`/immutable:adr` 슬래시 커맨드를 통해 작성합니다. 인터뷰 → 적대적 리뷰 → 90% 게이트 통과 시에만 파일이 생성됩니다.

## 파일 배치

- `adr/YYYY-MM-DD-<slug>.md` — flat 구조 (도메인별 디렉토리 없음). 도메인은 frontmatter `domain` 필드로 표기.
- `adr/TEMPLATE.md` — ADR 템플릿. 새 ADR은 여기서 출발.

## Frontmatter

```yaml
---
type: adr
domain: <name | _global>           # 특정 도메인 또는 _global (전역 결정)
supersedes: null                    # 대체 대상이 있으면 이전 파일명
deprecated: false
references:
  pitches:    [<filename>, ...]    # _global이 아니면 ≥1개 필수
  adrs:       [<filename>, ...]    # 다른 ADR 의존성 (선택)
  designs:    []
  tech_specs: []
---
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `type` | yes | 항상 `adr` |
| `domain` | yes | 도메인 slug 또는 `_global` (도메인 경계를 넘는 결정) |
| `supersedes` | yes | 이전 ADR 파일명 또는 `null` |
| `deprecated` | yes | `false` (활성) 또는 `true` (폐기) |
| `references.pitches` | conditional | `_global` ADR 외에는 ≥1개 필수 |

## 워크플로우

### 신규 ADR

1. `/immutable:adr` 실행 → 인터뷰 진행
2. 90% 게이트 통과 시 `adr/YYYY-MM-DD-<slug>.md` 생성
3. PR → 리뷰 → merge

### ADR 업데이트 (방향 전환)

1. 기존 활성 ADR 파일을 새 파일명으로 복사 (`/immutable:adr`가 자동화)
2. `supersedes`에 이전 파일명 기재
3. 본문 갱신 (full snapshot)
4. 이전 파일의 `deprecated: false` → `true` (한 줄만)
5. PR → 리뷰 → merge

### ADR 폐기 (대체 없음)

1. 활성 ADR의 `deprecated: false` → `true`만 변경
2. 본문 / 다른 필드 건드리지 않음
3. 커밋 메시지: `chore(adr): deprecate <slug> - <사유>`

## 파일명 규칙

- `YYYY-MM-DD-<slug>.md`
- `<slug>`: 영어 kebab-case, **subject-based** (변경 내역이 아닌 결정 주제를 담음)
- 금지: `latest`, `final`, `current`, 템플릿 버전 (`v0.3-*`)

## 본문 구조 (Nygard 템플릿)

`adr/TEMPLATE.md` 참조. 필수 섹션:

- **맥락 (Context)** — 결정을 촉발한 문제 / 현재 상태 / 제약
- **결정 (Decision)** — 단일 선언문 1개
- **결과 (Consequences)** — 긍정적 영향 ≥2 + 부정적 영향 ≥2
- **검토한 대안 (Alternatives Considered)** — ≥2개 대안 + 기각 사유
- **재검토 조건 (Revisit Triggers)** — metric / milestone / 리뷰 일자 ≥1

## ADR vs Pitch 구분

| 질문 | 도구 |
|---|---|
| **앱이 무엇을 해야 하는가** (사용자 약속) | Pitch (sibling 스펙 레포) |
| **그 결정을 왜 그렇게 구현하는가** (load-bearing 기술 방향) | ADR (이 레포) |

## 커밋 메시지 컨벤션

| 상황 | 형식 |
|---|---|
| 신규 | `feat(adr): add <slug>` |
| 업데이트 | `feat(adr): supersede <slug> - <요지>` |
| 폐기 | `chore(adr): deprecate <slug> - <사유>` |
