---
name: verify-impl
model: gpt-sol
description: 구현(test/impl)이 커밋된 브랜치에서 verifier 에이전트를 비격리로 spawn 해 티켓 §9 Verification 을 자동 실행하고 docs/verify/<날짜>/<NAME>_verify.md 에 증거(호출/응답/DB/스크린샷)를 수집·자동 확인 행 기록·_verify.md 1커밋까지 시키는 thin wrapper. verifier 가 _verify.md 를 커밋하면 여기서 파이프라인이 종료된다(체인 없음). PASS/FAIL/INCONCLUSIVE 판정은 보고만 한다. 최종 수동 검증은 사용자 몫이며, 만족하면 사용자가 /merge-impl 을 직접 호출하고 불만족 시 새 티켓으로 재작업한다. /impl-api·/impl-front 직후 또는 그 체인에서 호출된다. 구현 코드 수정/push 는 하지 않는다(커밋은 verifier 가 _verify.md 문서 1건만).
---

# /verify-impl — verifier 호출 wrapper (§9 자동 검증)

## 목적

구현이 커밋된 브랜치에서 **`verifier` 에이전트를 비격리(메인 워크스페이스)로 spawn** 해 티켓 §9 시나리오를 자동 실행하고 `_verify.md` 증거를 수집한 뒤 **verifier 가 대상 브랜치에서 `_verify.md` 문서 1건을 바로 커밋**한다. 커밋으로 **impl 파이프라인은 종료**되며, 이후 체인은 없다(판정은 보고만).

> **왜 비격리인가**: verifier 는 `_verify.md`(증거)를 대상 브랜치에 직접 커밋해야 하므로, 격리 worktree 가 아니라 **메인 워크스페이스의 대상 브랜치 체크아웃 위에서** 동작한다. 검증 결과는 이 브랜치에 남고, 사용자가 만족하면 별도로 `/merge-impl` 을 호출한다(그 호출이 곧 검증완료 의사표시 — 파이프라인 내부에 별도 검증완료 게이트를 두지 않는다).
>
> 검증 규칙(시나리오 추출, HTTP/통합테스트 휴리스틱, 앱 수명주기, 판정, `_verify.md` 포맷)은 `~/.claude/agents/verifier.md` 가 보유한다. 이 스킬은 얇은 wrapper다.

## 호출 형식

```
/verify-impl <티켓 경로>
```

티켓 경로가 없으면 즉시 **중단**하고 물어본다.

## Step 1. 사전 산출 (메인 세션)

- 티켓 파일 존재 확인. 없으면 중단.
- **plan.md 경로 도출**(공용 규칙): `docs/tickets/` + `working/|done/|backlog/|archive/` 제거 → `.md`→`_plan.md` → `docs/plans/` 접두. 없으면 중단(`/plan-impl` 선행 안내).
- plan.md 를 `Read` 해서 **브랜치명** 추출.

## Step 2. verifier spawn (비격리)

`Agent` 도구 1회 호출:
- `subagent_type`: `verifier`
- `isolation`: **사용 안 함** (메인 워크스페이스에서 브랜치 체크아웃 후 검증 — `_verify.md` 핸드오프 위해)
- `description`: `"verify: <티켓 파일명>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "ticket_path": "<TICKET_ABS>", "plan_path": "<PLAN_ABS>", "branch": "<plan.md 브랜치명>" }
  ```

verifier 5줄 응답에서 **종합 판정(PASS/FAIL/INCONCLUSIVE)**, `_verify.md` 경로, 실패 시나리오를 수집.

## Step 3. 판정 보고 / 종료 (종단)

종합 판정과 핵심 증거를 사용자에게 **보고**하고 파이프라인을 종료한다. 후속 자동 체인은 없다:

```
🔍 자동 검증 완료 — 종합 판정: {PASS/FAIL/INCONCLUSIVE}
증거: <_verify.md 경로> (이미 커밋됨)
{실패 시나리오 요약}

여기서 impl 파이프라인이 종료됩니다. ./gradlew bootRun 등으로 직접 확인해 만족하면
'/merge-impl <티켓 경로>' 로 병합을 진행하고, 문제가 있으면 새 티켓으로 재작업하세요.
```

verifier 가 사전조건 실패(브랜치 불일치, §9 부재·모호, 앱 기동 실패 등)로 **중단**한 경우엔 그 사유를 보고 후 종료.

---

## 금지 / 실패 처리

- 이 스킬/verifier 는 구현 코드 수정·새 브랜치 생성·push 를 하지 않는다. 커밋은 verifier 가 `_verify.md` 문서 1건만 수행한다(`git add -A` 금지, 경로 명시 스테이징).
- 판정 FAIL/INCONCLUSIVE 는 별도 처리 없이 **보고만** 한다(사용자 결정 — 후행 수동 검증).
- verifier 사전조건 실패는 사유 보고 후 종료.

## 참고

- 검증 에이전트: `~/.claude/agents/verifier.md`
- 선행: `.claude/skills/impl-api/SKILL.md`, `.claude/skills/impl-front/SKILL.md`
- 후행: 없음(impl 파이프라인 종단). 사용자 검증 만족 시 수동으로 `.claude/skills/merge-impl/SKILL.md` 호출.

---

문서 끝.
