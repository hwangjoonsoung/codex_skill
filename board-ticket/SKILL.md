---
name: board-ticket
model:
description: feature-board(웹/DB) 게시글 id 를 받아 Run 1(워크플로우 1→3단계)을 수행하는 board 연동 래퍼. board 상세를 읽어 requirement 로 ticket_writer 를 spawn 해 티켓을 만들고, status 를 TICKET_CREATE→CONFIRMATION_CHECK 로 PATCH 하며, 생성 티켓 §8 확인사항을 board confirmation 으로 POST 한다. confirmation 이 0개면 CONFIRMATION_COMPLETE 까지 전이 후 /board-plan 으로 자동 연속한다. 기존 ticket-create/plan-impl 은 고치지 않고 감싼다(wrap). 설계 SSOT=BOARD_SKILL_DESIGN.md.
---

# /board-ticket — feature-board Run 1 (티켓 생성 + 확인사항 표시)

## 목적

feature-board 게시글 하나(`id`)를 받아 **워크플로우 1→3단계**를 수행한다:
board 의 `requirement` 로 티켓을 만들고, 그 티켓의 §8 확인사항을 board 에 표시한 뒤
`CONFIRMATION_CHECK` 에서 정지한다. 진행 상태는 board REST API 를 PATCH 해 보고한다.

> 설계 SSOT: 레포 루트 `BOARD_SKILL_DESIGN.md`. 데이터 설계: `FEATURE_BOARD_DESIGN.md`.
> 이 스킬은 **wrap 래퍼**다 — `ticket-create` 의 인터랙티브 Q&A 대신 `ticket_writer`
> 에이전트를 직접 spawn 해(모호점은 §8 "미정"으로 best-effort) 헤드리스 실행에 맞춘다.
>
> **트리거**: 보통 `/board-loop` 워커가 `step_state=QUEUED` + `status=START` board 를
> 발견해 호출한다(수동 직접 호출도 가능). 시작 시 Step 2 의 `RUNNING` 전이가 큐 claim
> 역할을 해 중복 디스패치를 막는다.

## 호출 형식

```
/board-ticket <board id>
```

인자(board id)가 없으면 즉시 **중단**하고 물어본다. 추측 금지.

## 공통 — board API 호출 규약

- **`curl` 직접 호출 금지. 반드시 `~/bin/boms-api.sh` 래퍼를 통해 호출한다.**
  (allowlist 가 래퍼만 허용 — curl 전체는 막혀 있다. BOARD_SKILL_DESIGN §6.3)
  - 형식: `~/bin/boms-api.sh <METHOD> <PATH> [JSON_BODY]` → 응답 본문(JSON) stdout 출력.
- 응답은 `ApiResponse<T>`(`{status,statusCode,data}`) 래핑.
- board 갱신 호출의 **actor 는 항상 `AI`** (BOARD_SKILL_DESIGN §7.1).
- 어떤 호출이든 비-2xx(래퍼 exit 1) 면 **중단**하고 응답 본문을 보고한다(자동 재시도 금지).

## Step 1. board 상세 조회 & 사전 검증

```bash
~/bin/boms-api.sh GET /api/feature-board/<id>
```
- `data.status` 가 `START` 가 아니면 **중단**(이미 진행된 글). 사유 보고.
- `data.title`, `data.requirement`, `data.parentId`(재작업 컨텍스트용) 추출.

## Step 2. TICKET_CREATE 진입 표시

```bash
~/bin/boms-api.sh PATCH /api/feature-board/<id>/status \
  '{"targetStatus":"TICKET_CREATE","stepState":"RUNNING","actor":"AI"}'
```

## Step 3. 티켓 파일명 결정

- `<NAME>` = title 을 UPPER_SNAKE_CASE 3~5단어로 축약.
- ⚠️ 이 레포는 docs 가 **`task_management_system/` 모듈 하위**에 있다(레포 루트 아님).
  출력 경로 `<TICKET_ABS>` = **`<레포루트>/task_management_system/docs/tickets/working/<오늘 YYYYMMDD>/<NAME>.md`**
  (절대경로). `git rev-parse --show-toplevel` 로 레포 루트를 구해 앞에 붙인다.
  (cwd 기준 상대경로 `docs/tickets/...` 로 만들면 cwd 가 레포 루트일 때 엉뚱한 곳에 생기므로 금지.)
- 동일명 존재 시 `_V2` 등으로 구분.

## Step 4. ticket_writer spawn (티켓 본문 작성)

`Agent` 도구 1회 호출:
- `subagent_type`: `ticket_writer`, `isolation`: 사용 안 함
- `description`: `"ticket: <NAME>"`
- `prompt` 첫 JSON: `{ "requirement": "<board requirement>", "output_path": "<TICKET_ABS>" }`
  - 재작업(`parentId` 존재) 시 requirement 뒤에 "이전 시도 참조: board parentId=<n>" 를 덧붙여
    ticket_writer 가 부모 맥락을 인지하게 한다.
- ticket_writer 는 모호점을 §8 Confirmation 에 "미정/질문+선택지"로 남긴다(best-effort).

실패 시: `PATCH .../status` 로 `FAILED`(`stepState:"FAILED"`, `message:"<원인>"`) 기록 후 중단.

## Step 5. ticket_path 저장

```bash
~/bin/boms-api.sh PATCH /api/feature-board/<id>/artifacts \
  '{"ticketPath":"task_management_system/docs/tickets/working/<YYYYMMDD>/<NAME>.md"}'
```

## Step 6. §8 확인사항 추출 → board 표시

- 생성된 티켓을 `Read` 해 **§8(Confirmation/확인사항)** 의 각 항목을
  `{seq, question, options[], rationale?}` 로 변환.
  - 질문만 있고 선택지가 불명확하면 `options` 에 합리적 후보(예: ["예","아니오"]) 구성.
- confirmation 이 **1개 이상**이면:
  ```bash
  ~/bin/boms-api.sh POST /api/feature-board/<id>/confirmations \
    '{"confirmations":[{"seq":1,"question":"...","options":["A","B"],"rationale":"..."}],"actor":"AI"}'
  ```
  이어서 `PATCH .../status` → `CONFIRMATION_CHECK`(`stepState:"SUCCESS"`,`actor:"AI"`).
  **여기서 정지.** 사용자에게 "웹에서 확인사항 선택 후 /board-plan <id> 를 실행" 안내.

## Step 7. confirmation 0개 → 자동 연속 (BOARD_SKILL_DESIGN §7-2=B)

추출된 확인사항이 **0개**면 선택할 게 없으므로 정지하지 않는다:
```bash
~/bin/boms-api.sh PATCH /api/feature-board/<id>/status \
  '{"targetStatus":"CONFIRMATION_COMPLETE","stepState":"SUCCESS","actor":"AI"}'
```
→ 곧바로 `Skill` 도구로 `/board-plan <id>` 를 호출해 Run 2 로 연속한다.

---

## 금지 / 실패 처리

- board API 비-2xx → 중단·본문 보고, 자동 재시도 금지.
- `status != START` → 중단. 코드 수정/브랜치 생성/커밋 금지(티켓 커밋도 안 함 — /board-plan 의 /plan-impl 이 담당).
- ticket_writer 외 다른 구현 작업 금지.

## 참고

- 설계: `BOARD_SKILL_DESIGN.md`, `FEATURE_BOARD_DESIGN.md`
- 티켓 에이전트: `~/.claude/agents/ticket_writer.md`
- 후행: `/board-plan`

---

문서 끝.
