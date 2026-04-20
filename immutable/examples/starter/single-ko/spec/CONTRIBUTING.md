# Contributing — spec/

이 디렉토리는 본 앱의 **append-only pitch (제품 약속)** 가 저장되는 곳입니다. ADR (기술 결정 기록)은 별도로 `adr/` 디렉토리에 위치합니다.

> **Single-repo 안내**: pitch와 ADR이 같은 레포에 살지만 서로 다른 doctype입니다. pitch 변경 시 ADR을 함께 작성할 필요는 없으며, ADR 변경 시 pitch를 갱신할 필요도 없습니다. 양 doctype 모두 append-only.

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

ADR도 동일한 append-only 원칙. 상세는 [`../adr/README.md`](../adr/README.md) 참조.

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
5. 이전 파일의 `deprecated: false` → `deprecated: true`로 변경
6. PR → 리뷰 → Merge

### 기능 폐기 (승계 없음)

1. 최신 Pitch 파일의 `deprecated: false` → `deprecated: true`로만 수정
2. 다른 필드, 본문은 건드리지 않음
3. 커밋 메시지: `chore(pitch): deprecate <domain> - <사유>`

---

## 파일명 / Slug / Frontmatter / 본문 작성 / Feature Flag / PR 체크리스트

본 starter는 핵심 워크플로우만 담습니다. 전체 규칙은 spec-ko starter의 `CONTRIBUTING.md` 또는 sibling 스펙 레포 컨벤션을 참조하세요. 핵심 요점:

- **파일명**: `YYYY-MM-DD-<slug>.md`. Slug는 영어 kebab-case, **subject-based** (변경 내역 X)
- **Frontmatter**: `domain`, `supersedes`, `deprecated` 3개 필수
- **본문 언어**: 한글
- **구속력 키워드**: `[MUST]`, `[MUST NOT]`, `[SHOULD]`, `[SHOULD NOT]`, `[MAY]` (RFC 2119)
- **금지 사항**: 코드 변수명·파일 경로·클래스명·패키지명·API endpoint·디자인 토큰 수치 일절 금지 (도메인 용어만)
- **Pitch 단위**: Feature 수준 (단일 플래그로 on/off 가능 + 2~6주 완결)

---

## 커밋 메시지 컨벤션

| 상황 | 형식 |
|---|---|
| 신규 pitch | `feat(pitch): add <domain> - <slug>` |
| Pitch 버전업 | `feat(pitch): update <domain> - <요지>` |
| Pitch 폐기 | `chore(pitch): deprecate <domain> - <사유>` |
| 신규 ADR | `feat(adr): add <slug>` |
| ADR 버전업 | `feat(adr): supersede <slug> - <요지>` |
| ADR 폐기 | `chore(adr): deprecate <slug> - <사유>` |
| 레포 메타 | `chore: <내용>` |
