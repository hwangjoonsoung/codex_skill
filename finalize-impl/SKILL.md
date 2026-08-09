---
name: finalize-impl
model: gpt-sol
description: (자동 파이프라인에서 제외됨 — 릴리스 노트가 별도로 필요할 때만 단독 호출) 구현(test/impl)이 커밋된 브랜치에서 release_manager 에이전트를 write phase·비격리로 spawn 해 _report.md(보고서, 검증 행 포함)를 작성까지만 시키는 thin wrapper. 작성이 끝나면 /commit-impl 로 자동 체인한다. /verify-impl 에서 체인되어 온 경우 _verify.md 의 종합 판정을 verify_verdict 로 전달(게이트 없음), 단독 호출이면 수동 검증완료 대기 후 진행. 이 스킬/agent 는 보고서 커밋을 하지 않으며(커밋은 /commit-impl), 구현 수정/브랜치 변경/push 는 하지 않는다.
---

# /finalize-impl — release_manager(write) 호출 wrapper (보고서 작성)

## 목적

> ⚠️ **이 스킬은 자동 파이프라인에서 제외되었다.** `/verify-impl` 은 `_verify.md` 커밋으로 종료되며 더 이상 `/finalize-impl` 로 체인하지 않는다. 구현 보고서(`_report.md`)가 별도로 필요할 때만 **단독 호출**한다.

구현이 커밋된 브랜치에서 **`release_manager` 에이전트를 write phase 로 비격리 spawn** 해 `_report.md` 작성(§4 검증 행 포함)까지만 시킨다. 커밋은 하지 않고 `/commit-impl` 로 체인한다.

> 비격리 이유: verify→finalize→commit 꼬리는 같은 브랜치 위에서 이어져야 한다 — `_verify.md` 는 verifier 가 이미 그 브랜치에 커밋해 두었고(참조·판독 대상), 아직 커밋 안 된 `_report.md` 를 /commit-impl 로 핸드오프하므로 같은 워크스페이스·브랜치 위에서 동작해야 한다([[verify-impl]] 와 동일 원칙). 보고서 포맷/모드 판정/검증 행 규칙은 `~/.claude/agents/release_manager.md` 가 보유한다.

## 호출 형식

```
/finalize-impl <티켓 경로>
```

티켓 경로가 없으면 즉시 **중단**하고 물어본다.

## Step 1. 사전 산출 (메인 세션)

- 티켓 존재 확인. 없으면 중단.
- **plan.md 경로 도출**(공용 규칙) + 존재 확인(없으면 중단, `/plan-impl` 안내). plan.md `Read` → **브랜치명** 추출.
- **_verify.md 경로 도출**: 같은 날짜 세그먼트 도출 규칙에 접두사 `docs/verify/` + 접미사 `_verify.md`(예: `docs/verify/20260514/X_verify.md`). ※ `_report.md` 는 `docs/analysis/`, `_verify.md` 는 `docs/verify/` 로 접두가 다르다.

## Step 1.5. 검증 인정 / 수동 대기

- `_verify.md` 가 **존재**(=`/verify-impl` 체인으로 진입): §1 종합 판정을 읽어 `verdict`(PASS/FAIL/INCONCLUSIVE) 확보. **게이트 없이** Step 2 진행. (FAIL/INCONCLUSIVE 라도 중단하지 않음 — 사용자 자동 체이닝 결정)
- `_verify.md` 가 **없음**(단독 호출): 수동 검증 대기 메시지 출력 후 사용자 **"검증완료"** 응답 대기.
  ```
  ✅ 구현 완료. ./gradlew bootRun 후 티켓 §9 시나리오를 수동 검증하고 "검증완료" 라고 응답해주세요.
     문제가 있으면 구체적 증상을 알려주세요 — 수정은 /impl-api 또는 /impl-front 재실행으로 진행합니다.
  ```
  - 사용자가 문제 제보 → **중단**, `/impl-api`/`/impl-front` 재실행 안내(이 스킬은 구현 수정 안 함).
  - "검증완료" 응답 → `verdict` 없이(=사용자 수동 검증) Step 2 진행.

## Step 2. release_manager spawn (write phase, 비격리)

`Agent` 도구 1회 호출:
- `subagent_type`: `release_manager`
- `isolation`: **사용 안 함**
- `description`: `"finalize: <티켓 파일명>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "ticket_path": "<TICKET_ABS>", "plan_path": "<PLAN_ABS>", "branch": "<plan.md 브랜치명>", "phase": "write", "verify_verdict": "<PASS|FAIL|INCONCLUSIVE 또는 생략>" }
  ```
  - `_verify.md` 가 있었으면 `verify_verdict` 채움 → release_manager 가 §4 검증 표에 `자동 검증 판정` 행을 그 verdict 로 기록.
  - 없었으면(`수동`) `verify_verdict` 생략 → release_manager 가 `사용자 검증 | 완료` 행 기록.

release_manager 응답에서 결과/보고서 경로를 수집(write phase 이므로 커밋 SHA 는 "없음").

## Step 3. /commit-impl 자동 체인

release_manager(write) 성공 시 **사용자 응답 없이 곧바로** `Skill` 도구로 `/commit-impl <티켓 경로>` 를 호출한다. 보고서 커밋·완료 보고는 `/commit-impl` 이 수행한다.

```
✅ 보고서 작성 완료. 이어서 /commit-impl 로 보고서 커밋을 진행합니다.
```

---

## 금지 / 실패 처리

- 보고서 **커밋 직접 수행 금지**(→ `/commit-impl`). 구현 수정/브랜치 변경/push 금지.
- 사용자 검증 실패 제보 → 중단, `/impl-api`·`/impl-front` 재실행 안내.
- release_manager 가 스코프 위반(프론트 모드에 백엔드 변경 등) 감지 → 중단, 사유 보고.

## 참고

- 보고 에이전트: `~/.claude/agents/release_manager.md`
- 선행: `.claude/skills/verify-impl/SKILL.md` / 후행: `.claude/skills/commit-impl/SKILL.md`

---

문서 끝.
