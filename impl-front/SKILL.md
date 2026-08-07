---
name: impl-front
model:
description: plan.md 가 준비된 티켓(파일=단건 / 디렉토리=N건)에 대해 티켓당 frontend_engineer 에이전트를 격리 worktree 로 spawn 해 templates/static 구현 + compileJava + 1커밋을 시키는 thin wrapper. 구현이 끝나면 성공 티켓마다 /verify-impl 로 자동 체인하며, verify 가 _verify.md 를 커밋하면 파이프라인이 종료된다(이후 체인 없음). route 가 front 인 티켓만 처리하며 /impl-api·fullstack 은 안내 후 스킵. 신규 API 가 필요하면 frontend_engineer 가 즉시 중단하고 /impl-api 를 안내한다. 메인 세션은 코드/브랜치를 직접 건드리지 않고 agent spawn·worktree 정리·체인만 담당한다.
---

# /impl-front — frontend_engineer 호출 wrapper (프론트 구현)

## 목적

`/plan-impl` 이 만든 plan.md 를 입력으로, **티켓당 `frontend_engineer` 에이전트를 격리 worktree 로 spawn** 해 프론트(Thymeleaf/CSS/JS) 구현을 시킨다. 메인 세션은 사전 문서/코드를 읽지 않고 오케스트레이션만 한다. 구현 완료 후 `/verify-impl` 로 체인한다.

> 실제 구현 규칙(범위 한정 `templates/**`·`static/**`, compileJava 검증, 1커밋, 신규 API 필요 시 중단 등)은 `~/.claude/agents/frontend_engineer.md` 가 보유한다. 이 스킬은 얇은 wrapper다.

## 호출 형식

```
/impl-front <티켓 파일 경로>    # 단건 (N=1)
/impl-front <디렉토리 경로>     # 디렉토리 (직속 *.md N건)
```

인자가 없으면 즉시 **중단**하고 인자를 물어본다.

## 디스패치

| 인자 | 모드 | 대상 |
|------|------|------|
| 존재하는 `.md` 파일 | 단건 | 그 파일 1개 |
| 존재하는 디렉토리 | 디렉토리 | `<DIR>/*.md` 직속(재귀 금지). 제외: `_TEMPLATE.md`, `README.md`, `_` 시작 |
| 그 외 | 오류 | 중단 |

---

## Step 1. 티켓별 사전 산출 (메인 세션)

각 대상 티켓에 대해:

1. **plan.md 경로 도출**: 티켓 경로에서 `docs/tickets/` + `working/|done/|backlog/|archive/` 첫 세그먼트 제거 → 파일명 `.md`→`_plan.md` → `docs/plans/` 접두. (더블 슬래시 금지)
2. plan.md 없으면 → 그 티켓 **스킵**(사유: plan 없음, `/plan-impl` 선행 안내). 단건이면 중단.
3. plan.md 를 `Read` 해서 메타에서 **실행 경로(route)** 추출. (브랜치명은 frontend_engineer 가 plan.md 에서 직접 읽어 생성하므로 JSON 에 전달 안 함)
4. **route 검증**:
   - `/impl-front` → 진행(`route:"front"`)
   - `/impl-api` → 스킵(`/impl-api` 안내)
   - `fullstack` → 스킵: "fullstack 은 공유 worktree 가 필요하므로 `/plan-impl` 오케스트레이션에서 처리됩니다."
   - 실행 경로 누락 → 스킵(사유 명시)

처리 대상 0개면 스킵 사유 보고 후 종료.

## Step 2. frontend_engineer spawn (티켓당 1개)

처리 대상 N개를 **단일 메시지에 `Agent` 호출 N개 병렬 배치**.

각 호출:
- `subagent_type`: `frontend_engineer`
- `isolation`: `"worktree"` (필수 — 각 워커 독립 worktree)
- `description`: `"impl-front: <티켓 파일명>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "ticket_path": "<TICKET_ABS>", "plan_path": "<PLAN_ABS>", "route": "front" }
  ```

각 agent 응답에서 결과/브랜치명/구현 커밋 SHA/compileJava 결과를 수집.

> frontend_engineer 가 **신규 API 필요**를 감지하면 즉시 중단하고 `/impl-api` 전환을 안내한다. 그 티켓은 실패로 처리하고, 사용자에게 `/impl-api` 선행을 안내한다.

## Step 3. worktree 정리 (메인 세션)

- **성공** 워커: 해당 브랜치 worktree 를 `git worktree list` 로 식별해 `git worktree remove <path>`.
- **실패** 워커: worktree 유지(사용자 확인용).
- 강제 제거(`--force`) 금지. 제거 실패 시 사유 보고.

## Step 4. /verify-impl 자동 체인 (성공 티켓마다)

성공한 각 티켓에 대해 `Skill` 도구로 `/verify-impl <티켓 경로>` 를 호출한다. `/verify-impl` 이 검증하고 `_verify.md` 를 커밋하면 **파이프라인이 종료**된다(이후 자동 체인 없음). 사용자가 검증 만족 시 수동으로 `/merge-impl` 을 호출한다.

> 실패/스킵 티켓은 체인하지 않는다. 디렉토리 모드에서 성공 티켓이 여럿이면 티켓별로 순차 체인한다(verify 는 앱 기동/브라우저를 쓰므로 병렬 금지).

## Step 5. 완료 보고 / 종료

- 성공: 티켓별 (브랜치명, 구현 커밋 SHA), 그리고 체인된 `/verify-impl` 결과 요약
- 실패: 티켓별 (사유 — 신규 API 필요 등, 유지된 worktree 경로)
- 스킵: 티켓별 (사유 — plan 없음 / route 불일치 / fullstack)

---

## 금지 / 실패 처리

- 메인 세션은 코드 수정·브랜치 생성·커밋 금지(전부 agent worktree 안에서). `git worktree add/remove` 만 허용.
- 사전 문서 재읽기 금지(필요한 메타는 plan.md 에서만).
- agent 가 신규 API 필요로 중단 → 그 티켓 실패, `/impl-api` 선행 안내.
- agent compileJava 실패 → 그 티켓 worktree 유지, 체인 안 함, 사유 보고.
- plan.md 없음/route 불일치 → 해당 티켓 스킵(단건은 중단).

## 참고

- 구현 에이전트: `~/.claude/agents/frontend_engineer.md`
- 선행 스킬: `.claude/skills/plan-impl/SKILL.md` / 후행: `.claude/skills/verify-impl/SKILL.md`
- 백엔드: `.claude/skills/impl-api/SKILL.md`

---

문서 끝.
