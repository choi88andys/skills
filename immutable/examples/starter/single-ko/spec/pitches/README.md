# Pitches

프로덕트 Pitch가 저장되는 공간. 각 도메인은 별도 디렉토리로 분리.

## 도메인 허용 목록

**이 목록에 등록된 도메인만 허용**. 신규 도메인 추가 시 리드 승인 후 이 표에 추가.

| 도메인 | 설명 |
|---|---|
| `_shared` | 공통 관심사 (인증·로깅·에러 처리 등 특정 도메인에 속하지 않는 것) |

<!--
예시 추가 행 (실제 도메인으로 교체하거나 이 섹션을 지우세요):

| `search` | 검색 입력·결과·필터 |
| `checkout` | 결제 플로우·할인 적용·완료 페이지 |
-->

## 파일 배치 규칙

- `pitches/<domain>/YYYY-MM-DD-<slug>.md` — 도메인별 Pitch
- `pitches/_shared/YYYY-MM-DD-<slug>.md` — 공통 관심사
- `pitches/TEMPLATE.md` — Pitch 파일 템플릿 (여기서 복사해서 시작)

## 편집 원칙

**Append-only**. 상세는 [`../CONTRIBUTING.md`](../CONTRIBUTING.md) 참조.

## ADR과의 관계

본 single-repo 레이아웃에서는 ADR이 [`../../adr/`](../../adr/) 에 위치합니다. Pitch는 "앱이 무엇을 해야 하는가" 를, ADR은 "그 결정을 왜 그렇게 구현하는가" 를 담습니다. 둘은 서로 직접 참조하지 않으며 (ADR이 단방향으로 pitch를 references) 각자 append-only.

## 신규 도메인 추가 절차

1. 리드와 도메인 이름 합의 (오타·유사명 방지 위해)
2. 이 README의 허용 목록에 도메인 추가
3. `pitches/<domain>/` 디렉토리 생성
4. `TEMPLATE.md` 복사 → `YYYY-MM-DD-initial.md` 작성

## 작성 금지 영역

Pitch 본문은 **"앱이 무엇을 해야 하는가"** 만 기술. 아래 요소들의 SSoT는 이 디렉토리가 아닙니다.

| 요소 | SSoT | Pitch에서 |
|---|---|---|
| Route 경로 문자열·Navigator API | 앱 코드 | 적지 않음 — 의도만 GWT에 서술 |
| 위젯·클래스명·패키지명 | 앱 코드 | 적지 않음 |
| API endpoint·payload 스키마 | 백엔드 spec | 적지 않음 |
| 디자인 토큰 (color/spacing 수치) | Figma | 적지 않음 (의미만 서술) |
| 정확한 motion duration·easing 값 | 앱 코드 | 의도만 서술, 수치는 적지 않음 |

전체 본문 작성 규칙: [`../CONTRIBUTING.md`](../CONTRIBUTING.md) 참조.
