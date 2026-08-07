---
name: plan-impl
model:
description: "티켓(파일 경로=단건 / 디렉토리 경로=N건)을 받아, 메인 세션이 사전 문서를 직접 읽지 않고 티켓당 architect 에이전트를 병렬 spawn 해 plan.md 를 생성한 뒤, api/front 는 engineer(backend_engineer/frontend_engineer)를 병렬 batch 로·fullstack 은 순차로 직접 spawn 하고, verify 를 티켓별 순차로 체이닝하는 thin 오케스트레이터(verify 가 _verify.md 를 커밋하면 종단). 메인 세션은 티켓/plan 커밋과 worktree 관리만 직접 수행하고 코드/사전문서는 건드리지 않는다. `--no-chain` 으로 plan 생성까지만 수행한다. 사실상 부재중인 /auto-impl 라우터 역할을 plan-impl 이 담당한다."
---

# /plan-impl — 티켓 기반 계획+구현 오케스트레이터

## 목적

plan-impl 은 **thin 오케스트레이터**다. 메인 세션은 사전 문서(SSOT/ARCHITECTURE 등 7종)와 코드를 직접 읽지 않는다. 대신:

1. 티켓당 `architect` 에이전트를 spawn 해 plan.md 를 만들고 (계획),
2. 각 plan.md 의 실행 경로(route)에 따라 `backend_engineer` / `frontend_engineer` 에이전트를 spawn 해 구현까지 자동 체이닝한다.

**핵심 이점**: 사전 문서 읽기는 architect 에이전트 안에서만 일어나므로 메인 세션 컨텍스트가 가볍게 유지된다(1M context 한도 분산). 구현은 격리된 worktree 에이전트에서 수행되어 메인 워크스페이스와 분리된다.

> 이 스킬은 에이전트 생태계(architect → backend_engineer/frontend_engineer → release_manager)를 오케스트레이션한다. 설계상 `/auto-impl` 라우터가 할 일을 plan-impl 이 담당한다.

## 호출 형식

```
/plan-impl <티켓 파일 경로> [--no-chain]   # 단건 모드 (N=1)
/plan-impl <디렉토리 경로> [--no-chain]      # 디렉토리 모드 (직속 *.md N건)
```

예:
- 단건: `/plan-impl docs/tickets/working/20260514/PROJECT_MEMBER_ASSIGN.md`
- 디렉토리: `/plan-impl docs/tickets/working/20260514/`

인자가 없으면 즉시 **중단**하고 사용자에게 인자를 물어본다. 추측 금지.

### 플래그

| 플래그 | 효과 |
|--------|------|
| `--no-chain` | Step 3(구현 에이전트 체이닝)을 스킵. plan.md 생성·커밋까지만 하고 종료. |

## 디스패치

| 인자 형태 | 모드 | 티켓 목록 |
|-----------|------|-----------|
| 존재하는 `.md` 파일 | 단건 | 그 파일 1개 |
| 존재하는 디렉토리 | 디렉토리 | `<DIR>/*.md` 직속(재귀 금지). 제외: `_TEMPLATE.md`, `README.md`, `_` 로 시작하는 파일 |
| 미존재 / 그 외 | 오류 | 중단 후 인자 확인 요청 |

**단건·디렉토리는 동일 파이프라인을 탄다 (단건은 N=1).** Step 0~4 를 그대로 수행한다.

---

## 메인 세션 역할 (요약)

메인 세션은 **코드/사전 문서를 읽지 않는다.** 다음만 수행한다:

- Step 0: 티켓 목록 산출 + dirty 티켓 일괄 커밋
- Step 1: 티켓당 `architect` spawn (계획, 병렬)
- Step 2: 생성된 plan.md 일괄 커밋
- Step 3: (디폴트) api/front engineer **병렬 batch** spawn(3a) + fullstack 순차(3b) + worktree 관리 → verify **티켓별 순차** 체인(3c, verify 커밋으로 종단)
- Step 4: 결과 집계 보고

---

## Step 0. 티켓 목록 산출 & dirty 커밋

1. 디스패치 표대로 **대상 티켓 목록**을 만든다.
2. **디렉토리 모드 plan 스킵 필터**: 각 티켓의 대응 plan.md 경로(아래 "plan.md 경로 도출 규칙")가 이미 존재하면 그 티켓은 **이번 처리 대상에서 제외**한다(기존 plan 덮어쓰지 않음). 제외 사실은 Step 4 보고에 명시. 모든 티켓이 제외되면 "모든 티켓이 이미 plan.md 보유" 보고 후 종료.
3. **대상 티켓 dirty 일괄 커밋** — `git status --short -- <대상 티켓들>` 로 분류:
   - untracked(`??`) / unstaged-added(`A `): 신규 → `git add <신규 티켓들>` → `git commit -m "chore: add ticket(s) in <컨텍스트>"`
   - modified(`M`/`MM`): 변경 → `git add <변경 티켓들>` → `git commit -m "chore: update ticket(s) in <컨텍스트>"`
   - clean: 스킵
4. 규칙:
   - **반드시 파일 경로 명시**해서 add. `git add .` / `git add -A` / 와일드카드 금지.
   - 대상 티켓 외 다른 uncommitted 변경은 건드리지 않음 (사용자 working state 보존).
   - 커밋 실패(pre-commit hook 등) → 즉시 중단, Step 1 진행 안 함, 사유 보고.

> 왜 메인 세션이 티켓을 커밋하나: architect 를 **no-commit 모드**로 호출하므로(Step 1 참조), 티켓/plan 커밋은 오케스트레이터가 책임진다.

### plan.md 경로 도출 규칙 (공용)

1. 티켓 경로에서 `docs/tickets/` 접두 제거
2. 첫 세그먼트가 `working/`·`done/`·`backlog/`·`archive/` 중 하나면 그것도 제거
3. 남은 경로의 파일명에서 `.md` → `_plan.md`
4. `docs/plans/` 접두

예:
- `docs/tickets/working/20260514/X.md` → `docs/plans/20260514/X_plan.md`
- `docs/tickets/X.md` → `docs/plans/X_plan.md`

> ⚠️ 더블 슬래시(`docs/plans//X_plan.md`) 절대 금지.

---

## Step 1. architect spawn (티켓당 1개, 계획)

대상 티켓 N개에 대해 **단일 메시지에 `Agent` 도구 호출 N개를 병렬 배치**한다.

각 호출 파라미터:
- `subagent_type`: `architect`
- `isolation`: **사용 안 함** — architect 는 메인 워크스페이스 현재 브랜치에 plan.md 를 작성해야 한다(그래야 Step 3 의 engineer worktree 에서 plan.md 가 보인다).
- `description`: `"plan: <티켓 파일명>"`
- `prompt`: 아래. architect.md 는 첫 JSON 블록을 파싱한다.

```text
{ "ticket_path": "<TICKET_ABS_PATH>" }

[오케스트레이션 지시 — 위 JSON 외 추가 규칙]
- 당신(architect)은 plan.md 작성과 ticket frontmatter `type` 기록(Step 3.4 Edit)까지만 수행한다.
- **git add / git commit 을 하지 말 것**: architect.md 의 "Step 0 티켓 dirty 커밋" 과 "Step 4.1 plan.md/ticket 자동 커밋" 을 모두 스킵한다. Step 3.4 의 ticket frontmatter 편집분과 plan.md 커밋은 호출자(plan-impl 메인 세션)가 Step 2 에서 일괄 처리한다.
- 산출물은 plan.md 파일 1개 + (필요 시) ticket frontmatter `type` 편집. 작성 위치/섹션/트랙 판정·기록은 architect.md 규칙을 그대로 따른다.
- 응답은 architect.md "응답 포맷(정확히 7줄)" 그대로 반환한다. 7번째 줄 `비고` 에 frontmatter type 기록/정정 내역이 담긴다.
```

치환:
- `<TICKET_ABS_PATH>` → 티켓 파일 절대경로

> ⚠️ **no-commit 오버라이드 이유**: architect.md 는 기본적으로 plan.md 를 자체 커밋(Step 4.1)한다. 그러나 N개 architect 를 동일 워크스페이스에서 병렬 spawn 하면 `git commit` 들이 `index.lock` 에서 경합한다. 그래서 오케스트레이터는 architect 를 no-commit 으로 호출하고 Step 2 에서 일괄 커밋한다.

각 architect 7줄 응답에서 추출한다:
- 결과: 성공 | 실패(사유)
- plan.md 경로
- 실행 경로: `fullstack` | `/impl-api` | `/impl-front` | 판정 모호(중단)
- 브랜치명
- 비고: frontmatter type 기록/정정 내역 (Step 2 커밋 메시지 참고용)

실패/판정모호 티켓은 Step 2·3 대상에서 제외하고 Step 4 에 사유를 모은다.

---

## Step 2. plan.md + ticket frontmatter 일괄 커밋

성공한 architect 들이 생성한 plan.md 경로를 **명시 나열**해 한 번에 커밋한다. architect 가 Step 3.4 에서 ticket frontmatter `type` 을 기록/정정한 경우(7줄 응답의 `비고` 또는 `git status --short -- <대상 티켓들>` 로 확인) 그 ticket 들도 **같은 커밋에 명시 경로로 포함**한다:

```bash
git add <plan_1> <plan_2> ... [<type 기록된 ticket_1> ...]
git commit -m "chore: add plan(s) (+route type) for <컨텍스트>"
```

규칙:
- 실패한 architect 의 plan/ticket 은 제외. `git add .` / `-A` / 와일드카드 금지.
- 다른 uncommitted 변경 건드리지 않음. (Step 0 에서 이미 커밋된 ticket 이 architect 의 frontmatter 편집으로 다시 dirty 해진 것만 포함)
- 커밋 실패 시 즉시 중단, 사유 보고(구현 체이닝 진행 안 함).

> plan.md 는 이 시점에 **로컬 현재 브랜치(보통 dev)에 커밋**된다. Step 3 의 engineer worktree 는 현재 HEAD 기준으로 생성되므로 plan.md 가 보인다.

**`--no-chain` 이면 여기서 Step 4(보고)로 가서 종료.**

---

## Step 3. 구현 에이전트 spawn + 체이닝 (디폴트, `--no-chain` 이면 스킵)

이번 처리 성공 티켓을 route 별로 구현한다. **병렬 정책(Option A): engineer spawn 은 병렬, verify 체인은 순차.**

| 구간 | 대상 route | 병렬도 | 근거 |
|---|---|---|---|
| **3a** engineer spawn | api · front (순수) | **병렬 batch** | engineer 는 worktree 격리 + 빌드만 수행(앱/포트 미점유) → 동시 실행 안전 |
| **3b** engineer spawn | fullstack | **티켓별 순차** | backend→frontend 가 같은 worktree/브랜치를 공유해야 함 |
| **3c** verify (종단) | 전체 성공 티켓 | **티켓별 순차** | verify 가 앱 기동/포트/브라우저를 점유하는 배타 자원 |

> ⚠️ **delegation 아님 (구조 변경)**: 예전에는 티켓당 `/impl-api`·`/impl-front` 에 **순차 위임**해 engineer 가 직렬화됐다. 이제 plan-impl 이 engineer 를 **직접 병렬 spawn** 한다. 또한 위임 방식은 이미 plan 을 가진(planning 단계에서 스킵된) 티켓까지 끌어와 over-capture 하는 문제가 있었는데, 직접 spawn 으로 **이번 처리 성공 티켓만** 정확히 구현하도록 바로잡았다. (`/impl-api`·`/impl-front` 스킬은 단독 직접 호출용으로 그대로 유지 — plan-impl 체인에서는 더 이상 경유하지 않는다.)

> ✅ **plan.md 도달성**: engineer 들은 **로컬 `dev`** 에서 브랜치를 만든다(backend_engineer/frontend_engineer Step 2 = `git checkout -b <branch> dev`). plan.md 는 Step 2 에서 로컬 dev 에 커밋되므로 engineer worktree(로컬 dev 기준)에서 `plan_path` 가 보인다. 단 **로컬 dev 가 최신이어야** 하므로, plan-impl 실행 전 `git pull` 등으로 dev 를 최신화해 두는 것을 권장한다.

### 3a. api / front engineer 병렬 spawn (batch)

대상: route 가 api 또는 front 인 성공 티켓 전부.

1. **단일 메시지에 `Agent` 호출들을 병렬 배치**한다 (api·front 를 한 메시지에 섞어 띄워도 무방 — engineer 는 worktree 격리 + 빌드만, 포트/앱 미점유):
   - api 티켓 → `subagent_type: backend_engineer`, `isolation: "worktree"`
     - `prompt` JSON: `{ "ticket_path":"<TICKET_ABS>", "plan_path":"<PLAN_ABS>", "route":"api", "branch":"<plan.md 브랜치명>" }`
   - front 티켓 → `subagent_type: frontend_engineer`, `isolation: "worktree"`
     - `prompt` JSON: `{ "ticket_path":"<TICKET_ABS>", "plan_path":"<PLAN_ABS>", "route":"front", "branch":"<plan.md 브랜치명>" }`
   - `description`: `"impl: <티켓 파일명>"`
2. 각 engineer 응답에서 **결과 / 브랜치명 / test·impl 커밋 SHA / 빌드결과** 를 수집. 실패 워커는 3c verify 체인에서 제외한다.
3. **worktree 정리**: 성공 워커는 그 브랜치 worktree 를 `git worktree list` 로 식별해 `git worktree remove <path>`(브랜치가 free 돼 메인 IDE 에서 `git checkout <branch>` 가능). 실패 워커는 worktree 유지(사용자 확인용). `--force` 금지, 제거 실패 시 사유 보고.

### 3b. fullstack — plan-impl 직접 오케스트레이션 (공유 worktree, 티켓별 순차)

fullstack 은 backend·frontend 가 **같은 worktree/브랜치를 공유**해야 하므로 병렬 batch 에 넣지 않고 **티켓별 순차**로 처리한다. **브랜치는 backend_engineer 가 worktree 안에서 직접 생성**하므로, 메인 세션은 브랜치 없이 빈 공유 worktree 만 만든다.

1. 메인 세션: 공유 worktree 생성 (브랜치 미생성 — backend 가 만든다)
   ```bash
   git worktree add --detach <WT_ABS_PATH> dev   # 로컬 dev 기준 detached (plan.md 가시), 브랜치 -b 금지
   ```
   - `<WT_ABS_PATH>`: 임시 worktree 절대경로 (예: 레포 밖 `../.plan-impl-wt/<티켓명>`).
2. `backend_engineer` spawn (`isolation` 미사용, cwd 로 worktree 명시):
   - `prompt` JSON: `{ "ticket_path":..., "plan_path":..., "route":"fullstack", "branch":"<plan.md 의 브랜치명>", "cwd":"<WT_ABS_PATH>" }`
   - backend 가 cwd 안에서 `git checkout -b <branch> dev` 로 브랜치 생성 후 백엔드 구현·2커밋. 성공 응답 **대기**(순차).
3. backend 성공 시 같은 cwd 로 `frontend_engineer` spawn (`isolation` 미사용):
   - `prompt` JSON: `{ "ticket_path":..., "plan_path":..., "route":"fullstack", "existing_branch":"<backend 가 만든 브랜치명>", "cwd":"<WT_ABS_PATH>" }`
   - frontend 는 현재 worktree 브랜치가 `existing_branch` 와 일치하는지 확인 후 프론트 구현·1커밋. backend 실패면 frontend 스킵.
4. **정리**: backend·frontend 둘 다 성공 시 메인 세션이 `git worktree remove <WT_ABS_PATH>` 로 정리한다. 하나라도 실패면 worktree 유지, 이 티켓은 3c 에서 제외·보고.

> 여러 fullstack 티켓은 worktree 경로를 티켓별로 달리해 **순차** 처리한다. 한 fullstack 티켓 **내부**는 backend→frontend 순차(동일 브랜치 누적 커밋)다.

### 3c. verify 체인 (티켓별 순차, 종단)

3a·3b 가 모두 끝난 뒤, **성공한 모든 티켓**(api/front/fullstack)에 대해 `Skill` 도구로 `/verify-impl <티켓 경로>` 를 **티켓별로 하나씩(순차)** 호출한다. `/verify-impl` 이 검증하고 `_verify.md` 를 커밋하면 그 티켓의 파이프라인은 **종료**된다(이후 자동 체인 없음). 사용자가 검증 만족 시 수동으로 `/merge-impl` 을 호출한다.

> ⚠️ verify 는 앱 기동/포트/브라우저를 점유하므로 **동시 호출 절대 금지**. 반드시 직전 티켓의 체인이 끝난 뒤 다음 티켓을 호출한다. 실패/스킵 티켓(3a/3b 에서 빌드·구현 실패)은 체인하지 않는다.

---

## Step 4. 결과 보고 / 종료

- **plan 집계**: 티켓별 (plan.md 경로, route, 브랜치). 스킵(이미 plan 보유)·실패(판정 등) 사유 명시. Step 0/Step 2 커밋 SHA.
- `--no-chain` 인 경우: 위 plan 집계 + 다음 단계 안내를 덧붙이고 종료.
  - api/front: `/impl-api` 또는 `/impl-front` 수동 호출 안내
  - fullstack: 공유 worktree 수동 구현 또는 별도 라우터 안내
- 체이닝을 수행한 경우: 각 성공 티켓은 plan-impl 의 직접 engineer spawn(3a 병렬 / 3b 순차) → 티켓별 `/verify-impl` 체인(3c)을 통해 **구현→검증까지 자동으로 진행**되고 verify 커밋으로 종료된다. plan 집계 + 티켓별 최종 결과(브랜치명, 구현 커밋 SHA, `_verify.md` 커밋 SHA, 검증 판정)를 모아 보고하고, 각 성공 티켓에 "메인 IDE 에서 `git checkout <branch>` 로 커밋된 결과를 직접 최종 확인하고, 만족하면 `/merge-impl` 로 병합" 을 안내한다.

> plan-impl 이 직접 spawn 하는 것은 **구현 engineer(backend_engineer/frontend_engineer)** 이고, 직접 트리거하는 마지막 스킬은 **티켓별 `/verify-impl`** 이다. verify 가 `_verify.md` 를 커밋하면 파이프라인은 종단이며 이후 자동 체인은 없다. (`/impl-api`·`/impl-front` 는 단독 호출용으로 유지되며 plan-impl 체인에서는 더 이상 경유하지 않는다.)

---

## 커밋 / 코드 수정 정책

- **메인 세션 커밋 허용은 2건뿐**: Step 0(티켓 dirty), Step 2(plan.md). 둘 다 **경로 명시** 필수. `git add .` / `-A` 금지.
- 메인 세션은 **코드 수정·브랜치 생성 금지**. 구현은 engineer 에이전트 worktree 안에서만.
  - 예외(코드 수정 아님, 메인 세션 수행 허용):
    - 3a: api/front engineer(`isolation:"worktree"`) 완료 후 `git worktree list` 식별 + `git worktree remove`.
    - 3b: fullstack 의 `git worktree add --detach <WT> dev`(빈 detached worktree 생성, 브랜치는 backend 가 생성)와 `git worktree remove`.
- architect / engineer 에이전트는 각자 SKILL/agent 규칙(사전문서 읽기 정책, TDD, 2커밋 등)을 준수한다. 메인 세션은 그 내부를 재현하지 않는다.

## 실패 처리

- 인자 누락 / 경로 미존재 → 즉시 중단, 사용자 확인.
- Step 0 티켓 커밋 실패 → 중단, 사유 보고.
- architect 가 "판정 모호(중단)"/"실패" 응답 → 해당 티켓만 제외하고 나머지 진행. 전부 실패면 Step 4 에서 사유 집계 후 종료.
- Step 2 plan 커밋 실패 → 중단(구현 체이닝 안 함).
- engineer 빌드/테스트 실패 → 해당 worktree 유지, Step 4 에 실패 사유.

## 설계 노트 — plan.md 도달성 (해결됨, Option A)

plan.md 는 Step 2 에서 **로컬 dev** 에만 커밋된다(architect 는 push 안 함). 따라서 engineer 들이 origin/dev 에서 분기하면 plan.md 를 못 본다. 이를 해결하기 위해 **engineer 의 브랜치 base 를 로컬 `dev` 로 변경**했다:

- `~/.claude/agents/backend_engineer.md` Step 2: `git checkout -b <branch> dev`
- `~/.claude/agents/frontend_engineer.md` Step 2(단일 front): `git checkout -b <branch> dev`

**전제**: plan-impl 실행 시점에 **로컬 dev 가 최신**이어야 한다(engineer 가 로컬 dev 기준으로 구현을 쌓으므로). 실행 전 `git pull` 권장. push 는 사용자가 명시 지시할 때만.

## 참고 문서 / 에이전트

- 계획 에이전트: `~/.claude/agents/architect.md` (입력 `{ticket_path}`, route 3트랙 판정)
- 구현 에이전트: `~/.claude/agents/backend_engineer.md`, `~/.claude/agents/frontend_engineer.md` (입력 `{ticket_path, plan_path, route, branch, cwd?}`)
- 보고 에이전트: `~/.claude/agents/release_manager.md`
- 티켓 포맷: `docs/tickets/_TEMPLATE.md` / `docs/tickets/README.md`

---

문서 끝.
