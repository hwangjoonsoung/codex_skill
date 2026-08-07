---
name: board-plan
model:
description: feature-board 게시글 id 를 받아 Run 2(워크플로우 4→9단계)를 수행하는 board 연동 래퍼. 선택된 confirmation 을 티켓 §8 에 반영하고 CONFIRMATION_COMPLETE 로 전이한 뒤, ticket_path 로 /plan-impl 체인을 실행하며 PLANNING→IMPLEMENT→VERIFY→USER_VERIFY 각 phase 를 board status 로 PATCH 한다(verify 커밋이 체인 종단, 보고서/FINALIZE 없음. COMMIT 은 승인 후 수동 /merge-impl). 기존 plan-impl 은 고치지 않고 감싼다(wrap). 설계 SSOT=BOARD_SKILL_DESIGN.md.
---

# /board-plan — feature-board Run 2 (확인사항 반영 + 계획·구현)

## 목적

confirmation 선택이 끝난 feature-board 게시글(`id`)을 받아 **워크플로우 4→9단계**를
수행한다: 선택값을 티켓에 반영하고, `ticket_path` 로 `/plan-impl` 체인을 실행하며
각 phase 마다 board `status` 를 갱신한다.

> 설계 SSOT: `BOARD_SKILL_DESIGN.md`. 이 스킬은 **wrap 래퍼**다 — `/plan-impl` 내부를
> 고치지 않고, 그 앞뒤에 board 읽기/상태 PATCH 만 끼운다.
>
> **트리거**: 보통 `/board-loop` 워커가 `step_state=QUEUED` + `status=CONFIRMATION_CHECK`
> (confirmation 전부 선택됨) board 를 발견해 호출한다(수동 직접 호출도 가능). Step 2 의
> `RUNNING` 전이가 큐 claim 역할을 한다. confirmation 0개 자동연속 경로에서는
> `/board-ticket` 이 직접 이 스킬을 호출한다.

## 호출 형식

```
/board-plan <board id>
```

인자가 없으면 즉시 **중단**하고 물어본다.

## 공통 — board API 호출 규약

`/board-ticket` 과 동일: **`curl` 금지, `~/bin/boms-api.sh <METHOD> <PATH> [JSON_BODY]` 래퍼만
사용**(allowlist 가 래퍼만 허용). `ApiResponse`(`{status,statusCode,data}`) 래핑,
**actor=`AI`**, 비-2xx(래퍼 exit 1) 면 중단·보고.

## Step 1. board + confirmation 조회

```bash
~/bin/boms-api.sh GET /api/feature-board/<id>                 # ticketPath, status, parentId
~/bin/boms-api.sh GET /api/feature-board/<id>/confirmations   # 선택된 확인사항 목록
```
- `data.ticketPath` 없으면 **중단**("먼저 /board-ticket <id> 실행").
- `status` 가 `CONFIRMATION_CHECK` 또는 `CONFIRMATION_COMPLETE` 가 아니면 **중단**.
- confirmation 중 `selected` 가 비어 있는 항목이 있으면 **중단**(사용자 선택 미완료).

## Step 2. 선택값 티켓 반영 + CONFIRMATION_COMPLETE

- 각 confirmation 의 `{question, selected}` 를 티켓 `ticketPath` §8 의 해당 항목에
  **결정값으로 Edit 반영**(미정 → 선택된 값).
- 이미 `/board-ticket` 의 §7 자동연속 경로로 `CONFIRMATION_COMPLETE` 면 이 전이는 생략:
  ```bash
  ~/bin/boms-api.sh PATCH /api/feature-board/<id>/status \
    '{"targetStatus":"CONFIRMATION_COMPLETE","stepState":"SUCCESS","actor":"AI"}'
  ```

## Step 3. /plan-impl 체인 — phase ↔ status PATCH

`Skill` 도구로 `/plan-impl <ticketPath>` 를 호출한다. plan-impl 의 진행에 맞춰 board
`status` 를 단계별로 PATCH 한다(각 phase 진입 `RUNNING`, 성공 `SUCCESS`, actor `AI`):

| plan-impl phase | board status | 추가 artifacts PATCH |
|---|---|---|
| architect(plan.md) | `PLANNING` | 성공 시 `planPath`, `track`, `branchName` |
| engineer(구현) | `IMPLEMENT` | — |
| verifier(검증, 종단) | `VERIFY` | 성공 시 `verifyPath` |
| 사용자 검증 대기 | `USER_VERIFY` | — (이후 사람이 웹에서 승인/반려) |
| (승인 후 수동) merge·push | `COMMIT` | `prNumber`, `prUrl` |

> ⚠️ verify 가 `_verify.md` 를 커밋하면 `/plan-impl` 체인은 **종단**이다(보고서/FINALIZE 단계 없음). 이후 `COMMIT`(merge·push)은 사람 승인 뒤 `/merge-impl` 로 수동 수행된다.

- artifacts 갱신 예:
  ```bash
  ~/bin/boms-api.sh PATCH /api/feature-board/<id>/artifacts \
    '{"planPath":"...","track":"FULLSTACK","branchName":"feature/..."}'
  ```
- 단계 실패 시 `PATCH .../status` 로 `FAILED`(`stepState:"FAILED"`,`message:"<원인>"`) 후 중단.
  사용자가 웹 `retry` 로 직전 status 복귀 후 재실행 가능.

## Step 4. USER_VERIFY 에서 정지

`/plan-impl` 체인이 구현·검증(`_verify.md` 커밋)까지 마치면 `USER_VERIFY` 로 전이하고 **정지**한다.
이후 승인/반려는 사람이 웹에서 수행:
- **승인** → 사람이 `COMMIT` 전이(또는 이미 커밋됐으면 완료 확인).
- **반려** → 웹이 `POST .../{id}/reject`(reject_reason + 새 변경점 requirement) 호출 →
  현재 행 `REJECTED` 종료 + 새 `REVISION` 행 spawn. 새 행은 다시 `/board-ticket <새 id>`
  부터 2-phase 재진입(BOARD_SKILL_DESIGN §1.1, FEATURE_BOARD_DESIGN §3).

> COMMIT 까지 자동 수행할지(승인 게이트 없이)·USER_VERIFY 에서 멈출지는 /plan-impl 의
> 커밋 정책을 따른다. push/PR 은 사용자 명시 지시가 있을 때만.

---

## 금지 / 실패 처리

- board API 비-2xx → 중단·본문 보고, 자동 재시도 금지.
- `ticketPath` 부재·confirmation 미선택·부적합 status → 중단.
- /plan-impl 내부 로직 재구현 금지(호출만). 코드 수정은 plan-impl 의 engineer 가 수행.

## 참고

- 설계: `BOARD_SKILL_DESIGN.md`, `FEATURE_BOARD_DESIGN.md`
- 오케스트레이터: `~/.claude/skills/plan-impl/SKILL.md`
- 선행: `/board-ticket`

---

문서 끝.
