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

## 신규 도메인 추가 절차

1. 리드와 도메인 이름 합의 (오타·유사명 방지 위해)
2. 이 README의 허용 목록에 도메인 추가
3. `pitches/<domain>/` 디렉토리 생성
4. `TEMPLATE.md` 복사 → `YYYY-MM-DD-initial.md` 작성

> 작성 전 [`../CONTRIBUTING.md`](../CONTRIBUTING.md) 일독 필수 — 파일명 규칙(subject-based slug), frontmatter, 구속력 키워드, PR 체크리스트가 정의되어 있다. 본 README의 [작성 금지 영역](#작성-금지-영역)과 [Cross-domain feature 처리](#cross-domain-feature-처리) 도 함께 확인.

## Cross-domain feature 처리

하나의 feature가 여러 도메인 UX에 영향을 줄 수 있다(예: 알림 설정 개편이 `notification` + `settings` 에 동시에 보임). 이때는:

1. **도메인별로 pitch를 분리**한다. 파일 경로가 도메인을 결정하므로 cross-domain feature는 자동으로 여러 파일이 된다.
2. 각 pitch 본문에서 **cross-reference**: "본 feature는 `pitches/<도메인>/YYYY-MM-DD-<slug>.md` 와 함께 구성된다" 를 `배경과 문제` 또는 `범위 제외` 근처에 명시.

한 feature = 한 pitch 파일로 묶지 않는다.

## 작성 금지 영역

Pitch 본문은 **"앱이 무엇을 해야 하는가"** 만 기술한다. 아래 요소들의 SSoT는 이 repo가 아니다.

| 요소 | SSoT | Pitch에서 |
|---|---|---|
| Route 경로 문자열·Navigator API | 앱 코드 | 적지 않음 — 단, 진입점·전환·복귀의 **의도**는 Given/When/Then에 서술. 화면명은 bold 한글 일반명사(예: **결제 완료 주문 상세** 화면) |
| 위젯·클래스명·패키지명 | 앱 코드 | 적지 않음 |
| API endpoint·payload 스키마 | 백엔드 spec | 적지 않음 |
| 디자인 토큰 (color/spacing 수치) | Figma | 적지 않음 (의미만 서술) |
| 정확한 motion duration·easing 값 | 앱 코드 | 의도만 서술, 수치는 적지 않음 |

구속력 키워드(`[MUST]` 등) 및 본문 작성 규칙 전체는 [`../CONTRIBUTING.md`](../CONTRIBUTING.md) 참조.
