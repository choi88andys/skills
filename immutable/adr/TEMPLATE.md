---
type: adr
domain: <name | _global>
supersedes: null
deprecated: false
references:
  pitches: []
---

# <ADR Title>

## 맥락 (Context)

<!-- What problem does this decision address? Current state. Constraints. Forces pushing toward change. -->
<!-- A third-party engineer should be able to summarize "what triggered this decision" in ≤3 sentences after reading this section. -->

## 결정 (Decision)

<!-- State the decision as a single declarative sentence. Example: "We will adopt Riverpod for client-side state management across all feature modules." -->
<!-- Optional: one short paragraph of elaboration (scope included, scope excluded, minimum viable implementation path). -->

## 결과 (Consequences)

### 긍정적 영향
- <!-- at least 2 items -->

### 부정적 영향 / 트레이드오프
- <!-- at least 2 items; "no downsides" is a red flag — push back -->

### 채택 비용 / 중립
- <!-- migration effort, training, tooling -->

## 검토한 대안 (Alternatives Considered)

- **<대안 A>** — <기각 사유>. <재검토 조건>.
- **<대안 B>** — <기각 사유>. <재검토 조건>.

<!-- "There was no alternative" is usually a sign that this decision doesn't need an ADR. -->

## 재검토 조건 (Revisit Triggers)

<!-- At least one: metric, milestone, OR scheduled review date. -->

## 범위 제외

<!-- Optional. Things this ADR explicitly does NOT decide. Remove this section if not applicable. -->

---

<!--
================================================================================
Reference examples — delete everything below this line before committing your ADR.
================================================================================

The `/immutable:adr` skill recognizes four ADR-worthy justification areas
(per ../SCHEMA.md "ADR justification areas"):

  1. Rollout        — staged rollout %, feature flags, kill-switch design
  2. Observability  — metrics schema, logging cardinality, alerting thresholds
  3. Migration      — schema migrations, backfill policy, double-write windows
  4. External-deps  — 3rd-party SDK choice, vendor lock-in, API compat guarantees

Each example below shows the Context / Decision / Consequences shape for one area.
Use these as a pattern — do NOT copy prose verbatim.

--------------------------------------------------------------------------------
Example 1 — Rollout
--------------------------------------------------------------------------------

## 맥락 (Context)

쿠폰 적립 알림 시스템을 12M 사용자에게 배포한다. 하드 롤백은 3 단계
(data migration + service reversion + user notification cleanup) 를 거쳐야 하며,
잘못된 알림이 이미 전송된 뒤라면 각 단계의 비용이 비선형으로 증가한다.
사용자 신뢰 영향이 크므로 watch-and-pray flat-100 배포는 선택지가 아니다.

## 결정 (Decision)

Rollout 을 1% → 10% → 50% → 100% 4-step 으로 staged 배포하고, 각 step 은
error-rate + opt-out-rate threshold 를 24 시간 soak 하는 것을 조건으로 한다.

## 결과 (Consequences)

### 긍정적 영향
- Blast radius 가 각 step 에서 해당 cohort 로 한정된다. 롤백 시 잘못된 알림이
  도달하는 사용자 수가 최악의 경우에도 전체의 10% 이하로 유지된다.
- Error-rate threshold 자동 정지가 있으므로, on-call 이 매 step 마다
  watch-and-pray 할 필요가 없다.

### 부정적 영향 / 트레이드오프
- 전체 배포가 flat-100 보다 4-5 일 길어진다. 매출 영향이 있는 feature 라면
  선택을 다시 검토해야 한다.
- Feature flag 인프라가 GA 이후에도 kill-switch 목적으로 유지되어야 한다.
  기술 부채 후보.

### 채택 비용 / 중립
- 기존 feature flag 시스템 재사용 가능. 추가 인프라 필요 없음.

--------------------------------------------------------------------------------
Example 2 — Observability
--------------------------------------------------------------------------------

## 맥락 (Context)

주문 내역 페이지가 특정 필터 조합에서 느리다는 리포트가 누적되고 있다. 사용자에게
보이는 UI 를 추가하지 않고 원인을 진단해야 한다. 현재 로그는 1% 샘플링으로
찍히고 있어 필터 조합 별 coverage 가 부족하다.

## 결정 (Decision)

필터가 적용될 때마다 구조화 로그 이벤트를 emit 하며, filter signature +
render latency 를 captures 한다. 진단 기간에는 100% 샘플링, 14 일 이후
자동으로 5% 로 decay 한다.

## 결과 (Consequences)

### 긍정적 영향
- 500ms 이하 회귀가 사용자 컴플레인 도달 전에 감지 가능해진다.
- filter signature dimension 으로 slice 가능 — 새 대시보드 없이 기존 쿼리로
  원인 추적.

### 부정적 영향 / 트레이드오프
- 진단 기간에 로그 볼륨이 약 6x 증가한다. 14 일간 스토리지 비용 spike.
- filter signature 가 사용자 쿼리의 shape 를 노출한다 (값 자체는 아님).
  프라이버시 리뷰 필요.

### 채택 비용 / 중립
- 기존 structured logging 파이프라인 재사용. 별도 backend 변경 없음.

--------------------------------------------------------------------------------
Example 3 — Migration
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

--------------------------------------------------------------------------------
Example 4 — External-deps
--------------------------------------------------------------------------------

## 맥락 (Context)

긴 공지사항 요약을 위해 Apple Intelligence (Foundation Models) on-device
요약을 도입한다. 사용 불가 디바이스에서는 기존 서버 요약 엔드포인트로
fallback 한다. 서버 요약은 SoT 로 유지되며, on-device 는 latency
optimization 목적으로만 사용한다.

## 결정 (Decision)

`SystemLanguageModel.availability == .available` 을 gate 로 해서 가능한
디바이스에서는 on-device 요약을 사용하고, 아니면 기존 서버 엔드포인트를
호출한다. 서버 응답이 source of truth 이며, on-device 결과는 UI 에
먼저 표시되더라도 서버 응답 도착 시 대체될 수 있다.

## 결과 (Consequences)

### 긍정적 영향
- 지원 디바이스에서 200-400ms 단축, 오프라인 요약 가능해진다.
- 새로운 vendor lock-in 없음 — 서버 요약이 이미 있었으므로 fallback 존재.

### 부정적 영향 / 트레이드오프
- 요약 렌더링에 두 개의 code path 가 유지된다. 유닛 테스트 / 리뷰 부담.
- iOS 지원 하한이 18.1 로 상승. 구 디바이스는 서버 요약만.
- Apple Intelligence 출력 품질이 OS 버전마다 drift — 사용자 리포트 2 건
  이상 누적 시 revisit.

### 채택 비용 / 중립
- Foundation Models API 학습 1 주. 기존 summarize 모듈에 availability
  check 1 곳 추가.
-->
