# Contributing

## 누가 편집하나

- **UX팀**: GitHub **GUI(웹 브라우저)** 만 사용. Pitch를 추가·폐기 가능.
- **Owner(개발자)**: GUI 또는 PR 둘 다 가능.

Branch protection 없음 — 실수는 앱 구현 단계에서 owner가 교차 검증.

---

## 핵심 원칙 — Append-only

**기존 Pitch 파일을 수정하지 않는다**. 변경이 필요하면 새 Pitch 파일을 만든다.

| 대상 | 허용 여부 |
|---|---|
| `deprecated: false` → `true` (폐기 처리) | **허용** (단방향만) |
| 본문 내용 수정 | **금지** — 새 Pitch 작성으로 대체 |
| `domain` 필드 수정 | 금지 — 오타라도 새 Pitch로 정정 |
| `supersedes` 필드 수정 | 금지 — 생성 시점 고정 |
| `deprecated: true` → `false` (부활) | 금지 — 새 Pitch 작성 (`supersedes`에 deprecated 파일 지정) |

---

## 워크플로우

### 신규 도메인 생성

1. `pitches/README.md`에 도메인 추가 등록 (리드 승인)
2. `pitches/<domain>/` 디렉토리 생성
3. `pitches/TEMPLATE.md` 복사 → `YYYY-MM-DD-initial.md` 생성
4. `supersedes: null`로 세팅, 내용 작성
5. PR → 리뷰 → Merge (또는 GUI 직접 커밋)

### 기존 도메인 버전 업데이트

1. **기존 최신 Pitch 파일 전체 복사**
2. 새 파일명 `YYYY-MM-DD-<slug>.md`로 저장
3. `supersedes`에 이전 파일명 기입
4. 내용 갱신 (추가·수정·제거 모두 반영된 **full snapshot**)
5. 이전 파일의 `deprecated: false` → `deprecated: true`로 변경 (본문·다른 필드는 건드리지 않음)
6. PR → 리뷰 → Merge

### 기능 폐기 (승계 없음)

1. 최신 Pitch 파일의 `deprecated: false` → `deprecated: true`로만 수정
2. 다른 필드, 본문은 건드리지 않음
3. 커밋 메시지: `chore(pitch): deprecate <domain> - <사유>`
4. PR → 리뷰 → Merge

---

## 파일명 규칙

### 형식

- `YYYY-MM-DD-<slug>.md`
- `YYYY-MM-DD`: 해당 Pitch 버전 최초 작성일
- `<slug>`: 영어 kebab-case, **주제 기반(subject-based)**
- 파일명이 곧 버전 식별자. 버전 구분은 날짜 접두사 + `supersedes` frontmatter가 담당

### Slug 작성 원칙 — Subject-based

Slug는 **"이 파일이 무엇에 관한 spec인가"** 를 담는다. 변경 내역(delta)은 담지 않는다.

**근거**: 각 Pitch는 full snapshot(추가·수정·제거 모두 반영)이므로 **그 자체로 완결된 SSoT** 여야 한다. Delta-describing slug는 파일을 "변경 이력의 조각"으로 만들어 독립 독해성을 떨어뜨린다. ADR (Nygard / MADR), IETF RFC, 주요 엔터프라이즈 design-doc 관행 모두 subject-based naming을 따른다.

**허용**

| 분류 | 예시 | 설명 |
|---|---|---|
| Baseline | `initial` | 최초 버전 — 도메인 자체가 주제인 경우 허용 |
| 주제 기반 | `order-history-and-receipts`, `partial-refund`, `push-subscription-management` | feature의 본질을 kebab-case로. 도메인명과 중복감이 있어도 무방 |
| 버전 카운터 | `rev2`, `v3` | 주제 변화 없이 완성도·맥락만 갱신되는 경우 (IETF 스타일) |

**금지**

- Delta-describing slug: "무엇이 바뀌었나"를 담는 이름 (예: `figma-alignment`, `policy-update`, `code-aligned`, `v0.3-sections`)
- 하네스/템플릿 버전 참조: `v0.3-*` 등 템플릿 세대를 slug에 노출
- 시점성 표현: `latest`, `final`, `current`

**Delta 정보의 위치** (파일명이 아닌 곳)

1. `supersedes` frontmatter — 이전 버전 파일명
2. 커밋 메시지 — `feat(pitch): update <domain> - <요지>`
3. (선택) 본문 상단 `## 변경 이력` 섹션 — 해당 버전에서 달라진 항목 bullet

## YAML Frontmatter (필수)

모든 Pitch 파일 최상단에 필수.

```yaml
---
domain: <도메인명>                  # 디렉토리 slug와 일치
supersedes: null                    # 대체 대상 없으면 null, 있으면 이전 파일명
deprecated: false                   # 폐기 여부 (기본 false)
---
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `domain` | string | ✅ | 도메인 slug (디렉토리명과 동일) |
| `supersedes` | string 또는 null | ✅ | 이전 파일명 (예: `2026-04-16-initial.md`) 또는 `null` (대체 대상 없음) |
| `deprecated` | boolean | ✅ | `false`(활성) 또는 `true`(폐기). 기본값 `false` |

---

## Pitch 단위 (Goldilocks)

**Feature 수준**: 유저에게 독립적 가치 + 한 번의 배포 사이클(2~6주) 내 완결 가능.

| 수준 | 예시 | 판정 |
|---|---|---|
| Epic (너무 큼) | "결제 시스템 개편" | 금지. 쪼개야 함 |
| **Feature** | "장바구니 부분 환불" | **이상적 단위** |
| Task (너무 작음) | "환불 버튼 색상 변경" | Pitch 아님 |

**쪼개기 테스트**: "이 기능 전체를 Feature Flag 1개로 켜고 끌 수 있는가?" → 아니오면 쪼개야 할 신호.

---

## Feature Flag

### 상태 vocabulary

| 상태 | 의미 |
|---|---|
| `deployed` | 전체 사용자에게 기능 노출 (기본값) |
| `hidden` | 전체 비노출 (킬스위치 / 개발 중 숨김 / 긴급 롤백) |

### Pitch 본문의 Feature Flag 섹션

플래그를 사용하는 Pitch만 본문에 `## Feature Flag` 섹션 포함. 미사용 Pitch는 섹션 전체 생략.

---

## 본문 작성 규칙

### 언어

- 본문: **한글**
- 구속력 있는 표현은 **아래 5개 키워드**를 대괄호와 함께 사용. 나머지 표현("해야 한다" 등)은 참고 사항으로 간주.

### 구속력 키워드 가이드

| 키워드 | 뜻 | 사용 예시 |
|---|---|---|
| **[MUST]** | 반드시 해야 함 (예외 없음) | **[MUST]** 시스템은 공지 목록을 최신순으로 표시해야 한다. |
| **[MUST NOT]** | 절대 해서는 안 됨 | **[MUST NOT]** 시스템은 비활성 공지를 목록에 표시해서는 안 된다. |
| **[SHOULD]** | 가능하면 해야 하지만, 정당한 이유가 있으면 예외 허용 | **[SHOULD]** 시스템은 22자 초과 질문에 줄바꿈을 삽입한다. |
| **[SHOULD NOT]** | 가능하면 하지 말아야 함 | **[SHOULD NOT]** 시스템은 사용자에게 기술 오류 메시지를 그대로 노출하지 않는다. |
| **[MAY]** | 해도 되고 안 해도 됨 (선택) | **[MAY]** 시스템은 빈 목록에 일러스트를 표시할 수 있다. |

키워드 정의는 본 문서(CONTRIBUTING.md)가 SSoT이며, 개별 Pitch 파일에는 반복하지 않는다.

### 금지 사항

- **코드 변수명·파일 경로·클래스명·패키지명 일절 금지** (도메인 용어만)
- Pitch는 플랫폼 중립. 다른 기술 스택으로 재구현 가능한 수준으로 기술
- 구현 방법(HOW) 적지 말 것 — Pitch는 "무엇을 해야 하는가"만
- API endpoint·디자인 토큰 수치·정확한 motion duration/easing 값도 적지 않음. 각 요소의 SSoT는 별도(백엔드 spec / Figma / 앱 코드). 상세 목록은 [`pitches/README.md` 작성 금지 영역](pitches/README.md#작성-금지-영역) 참조.

### 권장 섹션 ([`pitches/TEMPLATE.md`](pitches/TEMPLATE.md) 참조)

- 배경과 문제
- 사용자 스토리 및 수용 조건 (Given/When/Then)
- 엣지 케이스
- 범위 제외 (No-gos)
- Feature Flag (사용 시만)

Cross-domain feature 처리는 [`pitches/README.md`](pitches/README.md) 참조.

---

## PR 체크리스트

PR 템플릿(`.github/PULL_REQUEST_TEMPLATE.md`)에 내장되어 있음. 요약:

- [ ] `domain` 값이 `pitches/README.md` 허용 목록에 등록됨
- [ ] 파일 경로 slug = frontmatter `domain` 일치
- [ ] 이전 버전이 있다면 `supersedes`에 명시
- [ ] 폐기 PR이면 diff가 `deprecated` 한 줄만 있는지 확인
- [ ] Feature Flag 섹션이 있다면 Key·사용 상태·초기 상태·Fallback 4개 기입
- [ ] Pitch 범위가 Feature 수준인지 확인 (플래그 1개로 제어 가능?)

---

## 커밋 메시지 컨벤션

| 상황 | 형식 |
|---|---|
| 신규 | `feat(pitch): add <domain> - <slug>` |
| 버전업 | `feat(pitch): update <domain> - <요지>` |
| 폐기 | `chore(pitch): deprecate <domain> - <사유>` |
| 레포 메타 | `chore: <내용>` |

---

## 이해관계자 간 충돌 시

- **기획팀 간 이견**: 새 Pitch로 해결 (이전 Pitch는 그대로 두고 새 버전으로 덮음)
- **기획팀 ↔ 개발자 이견 (구현 불가·제약 충돌)**: owner가 새 Pitch 또는 구현 조정 PR 제안
