---
name: force-finalize-impl
model: gpt-sol
description: 현재 브랜치에서 정식 finalize-impl 사전조건(브랜치명 불일치, 이미 커밋된 worktree 변경분, 자동 빌드 실패 등)을 일부 만족하지 못하지만, 사용자가 수동 검증 완료를 명시했고 강제 마무리를 요청한 경우 보고서 작성과 보고서 커밋만 수행한다. 구현 수정, 브랜치 변경, push는 금지한다.
---

# /force-finalize-impl — 강제 보고서 마무리

## 목적

`/finalize-impl` 의 엄격한 사전조건을 만족하지 못하는 예외 상황에서, 사용자가 명시적으로 강제 finalize를 승인한 경우에만 현재 브랜치 기준으로 구현 보고서를 작성하고 보고서 커밋까지 수행한다.

대표 상황:
- worktree 변경분을 `_worktree` 브랜치로 옮겨 plan.md의 브랜치명과 현재 브랜치명이 다르다.
- 구현 변경이 이미 보존 커밋으로 들어가 있어 테스트/구현 분리 커밋이 불가능하다.
- `./gradlew clean build` 는 기존 공통 테스트/DB 환경 문제로 실패하지만, focused test 또는 수동 검증은 완료됐다.

## 호출 형식

```
/force-finalize-impl <티켓 경로>
```

## 필수 조건

- 사용자가 명시적으로 강제 finalize를 요청해야 한다.
- 현재 브랜치에서 작업한다. 브랜치 변경/재분기 금지.
- 티켓 파일과 대응 plan.md가 존재해야 한다.
- 현재 브랜치에 origin/dev 대비 구현 변경이 있어야 한다.
- 사용자가 수동 검증 완료를 명시했거나, 대화에서 동등한 의미로 확인되어야 한다.

## 워크플로우

1. 현재 브랜치, `git status --short`, `git diff --name-only origin/dev...HEAD` 를 확인한다.
2. 티켓 파일과 대응 plan.md (`/plan-impl` 의 경로 도출 규칙: 티켓 경로의 `docs/tickets/[working|done|...]/` 접두 제거 → `docs/plans/` 를 접두로 + `_plan.md` 접미) 를 읽어 실행 경로와 요구사항을 확인한다. 예: `docs/tickets/working/20260514/X.md` → `docs/plans/20260514/X_plan.md`.
3. 검증 상태를 확인한다.
   - 가능한 경우 focused test 또는 `compileJava` 등 낮은 비용 검증을 실행한다.
   - 전체 빌드가 실패한 경우 실패 원인을 보고서에 명확히 적는다.
4. 보고서 파일을 작성한다. 경로 도출 규칙은 `/finalize-impl` 과 동일: 티켓 경로의 `docs/tickets/[working|done|...]/` 접두 제거 → `docs/analysis/` 접두 + `_report.md` 접미. 예: `docs/tickets/working/20260514/X.md` → `docs/analysis/20260514/X_report.md`. 작성 전 `mkdir -p` 로 상위 디렉토리 보장.
   - 정식 `/finalize-impl` 보고서 섹션을 최대한 따른다.
   - 자동 검증 실패가 있으면 성공으로 쓰지 않는다.
   - 사용자 검증 완료 날짜를 기록한다.
   - 이미 구현 커밋이 존재하면 커밋 구조 예외를 위험/참고에 명시한다.
5. 보고서 파일만 명시 경로로 add/commit 한다.

## 커밋 규칙

보고서만 커밋한다.

```
git add <Step 4 에서 작성한 _report.md 경로>   # 예: docs/analysis/20260514/X_report.md
git commit -m "chore: add implementation report for <티켓명>"
```

## 금지 사항

- 구현 코드 수정 금지.
- 브랜치 변경, 재분기, rebase, amend, reset 금지.
- push 금지.
- `git add .`, `git add -A` 금지.
- 자동 빌드 실패를 성공으로 기록 금지.
- 사용자 검증 완료가 확인되지 않았는데 검증 완료로 기록 금지.

## 완료 보고

최종 응답에는 다음을 포함한다.

- 현재 브랜치
- 생성/커밋한 보고서 경로
- 검증 결과 요약
- `git log --oneline origin/dev..HEAD` 요약
- push는 하지 않았다는 사실
