---
name: board-loop
model:
description: feature-board 큐(step_state=QUEUED)를 폴링해 처리할 board 를 1건씩 디스패치하는 워커 틱. status=START 면 /board-ticket, status=CONFIRMATION_CHECK 이고 confirmation 전부 선택됐으면 /board-plan 으로 분기한다. RUNNING 은 skip, 오래된 RUNNING 은 stale 로 보고만 한다. 매 틱이 board API 를 새로 읽는 stateless 구조라 호스트 cron + fresh `claude -p "/board-loop"` 로 무인 구동한다. 설계 SSOT=BOARD_SKILL_DESIGN.md §6.
---

# /board-loop — feature-board 큐 워커 (틱 디스패처)

## 목적

feature-board 의 **큐 신호(step_state=QUEUED)** 를 폴링해, 처리 대상 board 를 한 틱에
**1건씩** `/board-ticket` 또는 `/board-plan` 으로 분기 실행한다. 매 틱이 board API 를
새로 읽어 판단하는 **stateless** 워커라, 호스트 cron 으로 fresh `claude -p "/board-loop"`
를 주기 실행하면 무인 운영된다(컨텍스트 누적 없음).

> 설계 SSOT: 레포 루트 `BOARD_SKILL_DESIGN.md` §6. 구동(cron/flock/시크릿/체크아웃)은
> 코드 밖 배포 작업이며 이 스킬은 "한 틱의 디스패치 로직"만 정의한다.

## 호출 형식

```
/board-loop
```

인자 없음. (board id 를 받지 않는다 — 큐를 스스로 조회한다.)

## 공통 — board API 호출 규약

- **`curl` 직접 호출 금지. 반드시 `~/bin/boms-api.sh` 래퍼를 통해 호출한다.**
  (Claude Code allowlist 가 이 래퍼만 허용 — curl 전체는 막혀 있다. BOARD_SKILL_DESIGN §6.3)
  - 형식: `~/bin/boms-api.sh <METHOD> <PATH> [JSON_BODY]`
  - 래퍼가 `BOMS_BASE_URL`(기본 `http://localhost:8080`) 앞에 붙여 호출하고, 응답 본문(JSON)을
    stdout 으로 출력한다. board API(`/api/feature-board/...`) 외 경로는 래퍼가 거부한다.
- 응답은 `ApiResponse<T>`(`{status,statusCode,data}`) 래핑. 비-2xx 면 래퍼가 exit 1.
- 비-2xx 면 그 board 처리만 건너뛰고 사유를 기록(전체 틱을 중단하지 않음). 단 큐 목록
  조회 자체가 실패하면 틱 중단.

## Step 1. 큐 목록 조회

```bash
~/bin/boms-api.sh GET /api/feature-board/queued
```
- `data` = `step_state=QUEUED` board 목록(각 항목에 `id`, `status` 포함).
- 비어 있으면 **"처리할 큐 없음" 보고 후 종료**(정상).

## Step 2. 디스패치 (한 틱에 1건 권장)

큐 목록을 순회하되, **stuck 방지를 위해 한 틱에 1건만** 처리하고 종료하는 것을 기본으로
한다(다음 틱이 나머지를 집어감). board 별 분기:

| board 상태 | 조건 | 동작 |
|---|---|---|
| `status=START`, `step_state=QUEUED` | — | `Skill` 도구로 **`/board-ticket {id}`** |
| `status=CONFIRMATION_COMPLETE`, `step_state=QUEUED` | — (전부 선택돼야 COMPLETE 가 되므로 이미 충족) | `Skill` 도구로 **`/board-plan {id}`** |
| `status=CONFIRMATION_CHECK`, `step_state=QUEUED` | confirmations 모든 항목 `selected` 채워짐 | `Skill` 도구로 **`/board-plan {id}`** |
| `status=CONFIRMATION_CHECK`, `step_state=QUEUED` | 일부 `selected` 비어 있음 | **skip**(사용자 선택 미완) + 경고 로그 |
| `step_state=RUNNING` | — | **skip**(처리 중) |

> ℹ️ confirmation 을 전부 선택하면 백엔드(`selectConfirmation`)가 status 를 자동으로
> `CONFIRMATION_COMPLETE` 로 전이한다. 따라서 Run2 큐는 보통 `CONFIRMATION_COMPLETE+QUEUED`
> 로 들어온다(위 2번째 행이 주 경로). `CONFIRMATION_CHECK+QUEUED` 는 0건 선택 등 예외 경로.

- 실행 스킬(`/board-ticket`·`/board-plan`)이 시작 시 `step_state` 를 `RUNNING` 으로
  claim 하므로, 동일 board 가 다음 틱에 중복 디스패치되지 않는다(틱은 flock 으로 동시 1개).

## Step 3. stuck RUNNING 점검 (보고만)

큐 목록과 별개로, `step_state=RUNNING` 인 board 의 `dateOfUpdate` 가 **임계(기본 30분)**
보다 오래면 stale 후보로 **보고만** 한다(자동 리셋·재시도 안 함). 사용자가 웹 `retry` 로
직전 status 복귀 후 다시 큐 등록한다. (임계값·자동화 여부는 BOARD_SKILL_DESIGN §7-7.)

## Step 4. 틱 종료 보고

처리한 board(분기 결과)·skip 사유·stale 후보를 한 줄씩 요약하고 종료한다. 다음 디스패치는
다음 cron 틱이 수행한다.

---

## 금지 / 실패 처리

- 큐 조회 실패 → 틱 중단·보고. 개별 board 처리 실패 → 그 board 만 skip, 나머지 계속.
- board id 를 인자로 받지 않는다(스스로 큐 조회). 코드 직접 수정/커밋 금지(실행 스킬이
  내부에서 `/plan-impl` 등을 통해 수행).
- 한 틱에서 다건을 동시에 병렬 실행하지 않는다(verify/포트/리소스 배타성 — 순차 1건).

## 참고

- 설계: `BOARD_SKILL_DESIGN.md` §6
- 실행 스킬: `/board-ticket`, `/board-plan`

---

문서 끝.
