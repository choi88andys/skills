---
domain: <도메인명>
supersedes: null
deprecated: false
---

# <Pitch 제목>

## 배경과 문제

왜 이 Pitch가 필요한가 (맥락 설명).

## 사용자 스토리 및 수용 조건

<!--
profile.sections[user_stories].structure 기본값(per_story_grouped)에선
각 스토리를 아래처럼 `### <스토리 제목>` 서브섹션으로 묶고 서브섹션 안에
GWT 블록 + 결합된 RFC 2119 normative 줄을 함께 둔다 (스토리 ↔ 수용조건
traceability 보존). `consolidated` 모드를 쓰려면 이 섹션을 TEMPLATE에서
삭제하고 GWT 목록 + normative 목록 두 개를 H2 바로 아래에 둔다.
-->

### <스토리 1 — 짧은 imperative 제목>

- **Given** <전제 상태>
- **When** <사용자 행위>
- **Then** <시스템 반응>

- **[MUST]** 시스템은 …한다.
- **[MUST NOT]** 시스템은 …하지 않는다.

### <스토리 2 — happy path 외 경로>

- **Given** <전제 상태>
- **When** <사용자 행위>
- **Then** <시스템 반응>

- **[MUST]** 시스템은 …한다.

## 엣지 케이스

| 상황 | 처리 |
|---|---|
| <케이스> | <기대 동작> |

## 범위 제외 (No-gos)

- 이 Pitch에서 **절대 다루지 않을** 것 (현재 제외 항목을 명시적으로 기록)

## Feature Flag (선택)

<!--
플래그를 사용하는 경우에만 작성. 미사용 시 이 섹션 전체 생략.
-->

- **Key**: `ff_<slug>`
- **사용 상태**: `deployed`, `hidden`
- **초기 배포 상태**: `hidden` (내부 검증 후 `deployed`로 전환)
- **Fallback 동작**: `hidden` 상태에서의 UX (기존 동작 유지 / 숨김 UI 등)
