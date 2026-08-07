---
name: commit-impl
model:
description: (자동 파이프라인에서 제외됨 — /finalize-impl 을 단독 호출한 뒤에만 이어서 호출) /finalize-impl 이 작성한 _report.md 를 release_manager 에이전트를 commit phase·비격리로 spawn 해 보고서 1커밋만 시키는 thin wrapper(체인 종단). verify→finalize→commit 자동 체인의 끝으로 호출되거나 사용자 "검증완료" 후 단독 호출된다. 검증 행은 이미 finalize 의 write phase 에서 반영되었으므로 본 단계는 커밋만 담당한다. test/impl 은 impl-* 가 이미 커밋했고, push 는 사용자 명시 지시 후에만.
---

# /commit-impl — release_manager(commit) 호출 wrapper (보고서 커밋, 종단)

## 목적

`/finalize-impl` 이 작성한 `_report.md`(검증 행 포함)를 **`release_manager` 에이전트를 commit phase 로 비격리 spawn** 해 보고서 1커밋만 시키는 **체인 종단**이다.

> 검증 행 반영은 finalize 의 write phase 에서 이미 끝났다(release_manager 가 verify_verdict 로 §4 행 기록). 따라서 이 단계는 **커밋만** 한다. 비격리·핸드오프 원칙은 [[verify-impl]]·[[finalize-impl]] 와 동일.

## 호출 형식

```
/commit-impl <티켓 경로>
```

티켓 경로가 없으면 즉시 **중단**하고 물어본다.

## Step 1. 사전 산출 (메인 세션)

- 티켓 존재 확인.
- **plan.md / report.md 경로 도출**(공용 규칙, 접미사 `_plan.md` / `_report.md`).
- `_report.md` 없으면 **중단**: "보고서가 없습니다. 먼저 `/finalize-impl <티켓 경로>` 로 보고서를 작성해주세요."
- plan.md `Read` → **브랜치명** 추출.

## Step 2. release_manager spawn (commit phase, 비격리)

`Agent` 도구 1회 호출:
- `subagent_type`: `release_manager`
- `isolation`: **사용 안 함**
- `description`: `"commit: <티켓 파일명>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "ticket_path": "<TICKET_ABS>", "plan_path": "<PLAN_ABS>", "branch": "<plan.md 브랜치명>", "phase": "commit" }
  ```

release_manager(commit) 가 이미 작성된 `_report.md` 를 1커밋(`git add <report> && git commit`)한다. 응답에서 보고서 커밋 SHA·전체 커밋 목록 수집.

> 같은 일자 보고서가 이미 커밋되어 있으면 release_manager 가 "이미 커밋됨 — 스킵" 으로 응답한다.

## Step 3. 완료 보고 / 종료

```
🎉 전체 완료.
브랜치: {브랜치명}
커밋 목록: {release_manager 응답의 전체 커밋 목록}

push 하려면 'push 해줘' 또는 'git push -u origin <브랜치>' 로 지시해 주세요. (PR/머지는 수동)
```

**여기서 파이프라인 종료.** push 는 하지 않는다(사용자 명시 지시 시에만).

---

## 금지 / 실패 처리

- 구현 코드 수정/브랜치 변경/push 자동 실행 금지. 보고서 본문 재작성 금지(커밋만).
- `_report.md` 없음 → 중단, `/finalize-impl` 선행 안내.
- release_manager 커밋 실패(pre-commit hook 등) → 중단, 로그 보고, 자동 재시도 금지.

## 참고

- 보고 에이전트: `~/.claude/agents/release_manager.md`
- 선행: `.claude/skills/finalize-impl/SKILL.md`

---

문서 끝.
