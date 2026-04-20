# Architecture Decision Records

이 디렉토리는 본 앱 레포의 **append-only ADR** 가 저장되는 곳입니다. Pitch는 [`../spec/pitches/`](../spec/pitches/) 에 위치 (single-repo 레이아웃).

> **공통 규칙**: ADR은 `pitch`와 동일한 append-only 메커니즘을 따릅니다. 본문은 한 번 커밋된 뒤 변경 불가, 변경이 필요하면 새 파일을 작성하고 이전 파일의 `deprecated` 플래그만 `true`로 플립합니다. Pitch 측 규칙 전체는 [`../spec/CONTRIBUTING.md`](../spec/CONTRIBUTING.md) 참조.

## 작성 도구

`/immutable:adr` 슬래시 커맨드를 통해 작성. 인터뷰 → 적대적 리뷰 → 90% 게이트 통과 시에만 파일이 생성됩니다.

## 파일 배치

- `adr/YYYY-MM-DD-<slug>.md` — flat 구조. 도메인은 frontmatter `domain` 필드로 표기.
- `adr/TEMPLATE.md` — ADR 템플릿. 새 ADR은 여기서 출발.

## Frontmatter

```yaml
---
type: adr
domain: <name | _global>
supersedes: null
deprecated: false
references:
  pitches:    [<filename>, ...]    # _global이 아니면 ≥1개 필수
  adrs:       [<filename>, ...]
  designs:    []
  tech_specs: []
---
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `type` | yes | 항상 `adr` |
| `domain` | yes | 도메인 slug 또는 `_global` |
| `supersedes` | yes | 이전 ADR 파일명 또는 `null` |
| `deprecated` | yes | `false` (활성) 또는 `true` (폐기) |
| `references.pitches` | conditional | `_global` ADR 외에는 ≥1개 필수 |

Single-repo 모드에서 `references.pitches` 파일명은 [`../spec/pitches/`](../spec/pitches/) 하위에서 검증됩니다.

## 워크플로우 / 파일명 / 본문 구조

상세는 별도 spec 레포 starter (`app-ko`)의 `adr/README.md` 또는 immutable plugin 문서 참조. 핵심 요점:

- **신규 / 업데이트 / 폐기** — 모두 append-only, supersede 체인 유지
- **파일명**: `YYYY-MM-DD-<slug>.md`, kebab-case **subject-based** slug
- **본문**: Nygard 템플릿 — Context / Decision / Consequences / Alternatives / Revisit Triggers

## ADR vs Pitch

| 질문 | 도구 |
|---|---|
| **앱이 무엇을 해야 하는가** | Pitch ([`../spec/pitches/`](../spec/pitches/)) |
| **그 결정을 왜 그렇게 구현하는가** | ADR (이 디렉토리) |

## 커밋 메시지 컨벤션

| 상황 | 형식 |
|---|---|
| 신규 | `feat(adr): add <slug>` |
| 업데이트 | `feat(adr): supersede <slug> - <요지>` |
| 폐기 | `chore(adr): deprecate <slug> - <사유>` |
