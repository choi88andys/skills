---
type: adr
domain: <name | _global>
supersedes: null
deprecated: false
references:
  pitches: []
---

# <ADR 제목>

## 맥락 (Context)

<!-- 어떤 문제를 다루는 결정인가. 현재 상태. 제약. 변경을 압박하는 force. -->
<!-- 제3자 엔지니어가 이 섹션만 보고 "무엇이 이 결정을 촉발했는지"를 ≤3 문장으로 요약 가능해야 한다. -->

## 결정 (Decision)

<!-- 단일 선언문. 예: "client-side 상태 관리는 모든 feature 모듈에서 Riverpod을 채택한다." -->
<!-- 선택: 한 단락의 보충 설명 (포함 / 제외 범위, 최소 구현 경로). -->

## 결과 (Consequences)

### 긍정적 영향
- <!-- 최소 2개 -->

### 부정적 영향 / 트레이드오프
- <!-- 최소 2개; "단점 없음"은 red flag — 다시 검토할 것 -->

### 채택 비용 / 중립
- <!-- 마이그레이션 노력, 학습, tooling -->

## 검토한 대안 (Alternatives Considered)

- **<대안 A>** — <기각 사유>. <재검토 조건>.
- **<대안 B>** — <기각 사유>. <재검토 조건>.

<!-- "대안이 없었다"는 보통 ADR이 필요없다는 신호다. -->

## 재검토 조건 (Revisit Triggers)

<!-- 최소 1개: metric / milestone / 예정된 리뷰 일자. -->

## 범위 제외

<!-- 선택. 이 ADR이 명시적으로 결정하지 않는 항목. 해당 없으면 섹션 통째로 삭제. -->

---

<!--
================================================================================
참고 예시 — 본 ADR 작성 전 아래 줄 포함 모두 삭제하세요.
================================================================================

ADR-worthy 4 영역 (각 영역마다 적대적 리뷰가 별도로 동작):

  1. Rollout        — staged rollout %, feature flags, kill-switch 설계
  2. Observability  — metrics 스키마, 로그 cardinality, alerting 임계
  3. Migration      — 스키마 마이그레이션, backfill 정책, dual-write 윈도우
  4. External-deps  — 3rd-party SDK 선택, vendor lock-in, API compat 보장

아래는 Migration 영역의 worked example. 패턴으로만 참고 — 본문 그대로 복사 X.

--------------------------------------------------------------------------------
Example — Migration
--------------------------------------------------------------------------------

## 맥락 (Context)

알림 설정을 단일 boolean 에서 per-channel tri-state (on / off / digest) 로
전환한다. 3.2M 사용자 레코드가 현재 값에 의존하는 활성 스케줄을 가진다.
downtime 이 허용되지 않으며, 롤백 옵션도 최소 30 일 이상 유지되어야 한다.

## 결정 (Decision)

신규 컬럼을 추가하고 2 주간 dual-write, 기존 boolean 에서 backfill, 이후
read 를 신규 컬럼으로 flip, 구 컬럼은 90 일간 보존한 뒤 후속 ADR 에서
drop 을 결정한다.

## 결과 (Consequences)

### 긍정적 영향
- Zero downtime, zero 사용자 가시 disruption.
- 90 일간 rollback 가능 (read-flag flip 만으로 복구).

### 부정적 영향 / 트레이드오프
- dual-write 기간에 preference update path 에 8-12ms 추가 latency.
- 90 일간 2 컬럼이 active — preference 를 건드리는 모든 코드가 두 상태를
  처리해야 한다. 코드 복잡도 비용.
- 구 컬럼 drop 은 후속 ADR 가 필요 — 이 ADR 가 migration 을 완료하지 않는다.

### 채택 비용 / 중립
- DBA 리뷰 1 회, dual-write 코드 변경 8-12 PR 예상.
-->
