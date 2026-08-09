---
name: auto-impl
model: gpt-sol
description: 하나의 요구사항, feature-list Markdown 파일, 또는 기존 티켓 디렉터리에서 BOMS 기능을 자동 구현한다. 티켓 생성, 계획 수립, 티켓 간 의존성 분석, 의존성 기반 병렬/순차 구현, 자동 검증, 복구 재시도, 로컬 dev 직렬 통합을 거쳐 최종 사람 리뷰까지 수행한다. 사용자가 여러 Java 프로젝트 요구사항을 티켓마다 수동 검토하거나 plan-impl을 반복 호출하지 않고 최소 개입으로 구현하고 싶을 때 사용한다. board-* 스킬은 사용하지 않는다.
---

# 자동 구현

## 목적

요구사항부터 로컬 `dev`의 최종 사람 리뷰까지, 재개 가능하고 의존성을 인지하는 구현 배치를 한 번에 실행한다. `ticket-create`, `plan-impl --no-chain`, 기존 구현 에이전트, `verify-impl`, `integrator` 에이전트를 재사용한다. `board-*`, `finalize-impl`, `commit-impl`은 이 파이프라인 밖에 둔다.

이 스킬을 명시적으로 호출한 것은 선택된 저장소 안에서 티켓, 계획, 기능 브랜치, 커밋, 검증 증거, 로컬 `dev` 통합을 생성할 권한을 준 것으로 간주한다. 사용자가 `--push`를 포함하지 않는 한 절대 push하지 않는다.

## 호출

```text
$auto-impl <requirement text | feature-list.md | ticket directory>
$auto-impl <input> [--push] [--max-repair <N>]
$auto-impl --resume <execution-manifest.json> [--push]
```

기본값:

- 통합 대상: 로컬 `dev`
- 사람 게이트: 배치가 최종 리뷰에 도달한 뒤 1회, 그리고 실제로 막는 모호점이 있을 때만 단일 통합 질문 1회
- Push: 비활성화
- 복구 재시도: `2`
- 자동 통합 허용 판정: `PASS`만 허용

## 불변 조건

1. 대상 저장소의 `AGENTS.md` 파일을 변경 전에 읽고, 적용 가능한 가장 구체적인 지시를 따른다.
2. Maven이 의존성을 관리하는 경우 Maven 빌드나 테스트를 시도하지 않는다. 생략된 증거를 기록하고, 불완전한 검증을 조용히 `PASS`로 바꾸지 않는다.
3. 관련 없는 사용자 변경을 보존한다. `git add .`, `git add -A`, 강제 checkout, 강제 push, 파괴적 reset, 광범위한 정리를 절대 사용하지 않는다.
4. 구현 에이전트는 허용된 소유 영역 안에서만 코드를 변경하게 한다. 메인 세션은 오케스트레이션, 실행 매니페스트, worktree 수명주기, 브랜치 통합을 담당한다.
5. 스케줄러가 준비됐다고 판단한 티켓만 동시에 구현한다. 같은 앱, 포트, 브라우저, 데이터베이스를 공유하는 검증은 티켓별로 한 번에 하나씩 실행한다. 통합은 반드시 티켓별로 하나씩 직렬 실행한다.
6. 병렬 에이전트가 `dev`나 같은 worktree에 직접 쓰게 하지 않는다.
7. 매니페스트 정책이 허용한 검증 판정만 통합한다. 기본값은 `PASS`이며, `FAIL`과 `INCONCLUSIVE`는 차단한다.
8. 최종 리뷰가 끝날 때까지 모든 기능 브랜치를 유지한다. 실패한 worktree를 자동으로 삭제하지 않는다.

## Phase 0: 사전 점검

1. 입력 경로나 현재 디렉터리에서 대상 Git 저장소를 결정한다. Git 저장소가 아니면 중단한다.
2. 적용 가능한 `AGENTS.md` 파일을 찾아 읽는다.
3. 로컬 `dev`가 있는지 확인한다. `dev` HEAD, 현재 브랜치, worktree 목록, `git status --short`를 기록한다.
4. 관련 없는 dirty 변경 때문에 안전한 브랜치 전환이나 통합이 불가능하면 정확한 경로를 제시하고 중단한다. 자동으로 stash하지 않는다.
5. `origin/dev`가 있으면 fetch한 뒤 로컬 `dev`와 비교한다. 로컬 `dev`가 뒤처졌으면 fast-forward하고, 의도적으로 앞서 있는 로컬 `dev`는 허용하며, diverge 상태면 중단한다. 로컬 작업을 절대 reset하지 않는다.
6. 티켓 생성과 계획 수립 전에 로컬 `dev`를 checkout한다. 해결되지 않은 dirty 변경 위에서 전환하지 말고 중단한다.
7. `--push`와 `--max-repair`를 파싱한다. 음수 재시도 값은 거부한다.
8. 이 스킬 디렉터리와 스케줄러 스크립트 경로를 결정한다. 스크립트를 호출할 때는 절대 경로를 사용한다.

## Phase 1: 티켓 생성

입력이 기존 티켓 파일 또는 디렉터리이면, 직속 티켓 Markdown 파일만 수집하고 티켓 생성을 건너뛴다.

그 외에는 `ticket-create/SKILL.md`를 따른다.

- feature-list 경로는 일괄 프로토콜을 사용한다.
- 자유 텍스트에 독립적으로 테스트 가능한 요구사항이 여러 개 포함되어 있으면 번호가 붙은 요구사항 항목으로 나누고, 각 분할을 사용자에게 승인받도록 강제하지 않은 채 일괄 ticket-writer 프로토콜을 실행한다.
- 요구사항이 하나이면 단일 티켓 프로토콜을 사용한다.
- `ticket_writer`가 구현 route나 의존성 순서를 선택하게 하지 않는다.

생성 후 모든 티켓의 Confirmation 섹션을 스캔한다. 미해결 항목을 분류한다.

- 적용 가능한 프로젝트 규칙이나 명시적 배치 정책이 기본값을 제공할 때만 되돌릴 수 있는 기술 선택을 해결한다. 규칙 또는 정책을 결정 출처로 기록한다.
- 누락된 비즈니스 동작, 파괴적 데이터 변경, 인가/보안 의미, 외부에 보이는 계약 선택은 blocking으로 취급한다.
- 모든 blocking 항목을 하나의 통합 질문으로 제시한다. 티켓마다 질문하지 않는다.
- blocking 항목이 없으면 사용자에게 티켓을 읽도록 요구하지 않고 계속한다.

## Phase 2: 구현 없이 계획 생성

`plan-impl <ticket directory> --no-chain`을 호출한다. 기존 계획을 재사용하고 성공한 각 티켓에서 다음을 수집한다.

- ticket path
- plan path
- route: `api`, `front`, 또는 `fullstack`
- feature branch name
- 계획된 파일, 테이블, API, 기타 공유 리소스

계획 실패 티켓은 실행에서 제외하고 정확한 사유를 기록한다. 일반 `plan-impl` 구현 체인은 호출하지 않는다. 그 체인은 티켓 간 의존성 스케줄링을 하지 않기 때문이다.

## Phase 3: 실행 매니페스트 작성

매니페스트를 만들거나 수정하기 전에 [references/execution-manifest.md](references/execution-manifest.md)를 읽는다.

선택된 모든 티켓과 계획을 하나의 배치로 읽는다. 다음을 도출한다.

- `depends_on`: 반드시 먼저 구현되어야 하는 선행 작업
- `resources`: 파일, 테이블, 엔드포인트, 설정, 포트, 기타 배타적 리소스
- `conflicts_with`: 비즈니스 의존성으로 표현되지 않은 명시적 순서 제약
- `priority`: 명시된 비즈니스 우선순위. 없으면 `0`

독립적인 `parallel: true|false` 플래그는 절대 사용하지 않는다. 모든 의존성이 통합되었고 활성 작업과 리소스 충돌이 없을 때만 티켓은 병렬 준비 상태다.

런타임 상태는 다음 위치에 저장한다.

```text
<repo>/.codex/auto-impl/<batch-id>.json
```

이 런타임 파일을 stage하거나 commit하지 않는다. 부모 디렉터리가 없으면 생성한다. 구현 전에 검증한다.

```text
python <skill-dir>/scripts/dag_scheduler.py validate <manifest>
```

알 수 없는 의존성, 중복 티켓 ID, 잘못된 상태, 의존성 cycle이 있으면 구현 전에 중단한다.

## Phase 4: 구현 스케줄링

실행 가능한 티켓이나 활성 티켓이 남지 않을 때까지 반복한다.

1. 현재 사용 가능한 worker slot 수로 제한해 다음 ready set을 스케줄러에 요청한다.

   ```text
   python <skill-dir>/scripts/dag_scheduler.py ready <manifest> --limit <available-worker-slots>
   ```

2. worker를 spawn하기 전에 티켓을 `RUNNING`으로 전환하고 현재 로컬 `dev` SHA를 `base_ref`로 기록한다.

   ```text
   python <skill-dir>/scripts/dag_scheduler.py transition <manifest> <ticket-id> RUNNING --base-ref <sha> --branch <branch>
   ```

3. 준비된 티켓을 사용 가능한 slot 수까지 동시에 spawn하되, 티켓마다 격리된 worktree 하나를 사용한다. 명시적인 파일 소유권을 전달하고, 모든 worker에게 다른 에이전트도 활성 상태이므로 그들의 변경을 되돌리지 말라고 알린다.
4. 계획 route를 사용한다.
   - `api`: `backend_engineer`를 spawn한다.
   - `front`: `frontend_engineer`를 spawn한다.
   - `fullstack`: 하나의 공유 티켓 worktree를 사용한다. `backend_engineer`를 실행해 성공을 기다린 뒤 같은 브랜치에서 `frontend_engineer`를 실행한다. 서로 다른 fullstack 티켓은 스케줄러가 ready로 판단하고 리소스 충돌이 없으면 동시에 실행할 수 있다.
5. 결과, 브랜치, 커밋 SHA, 검증 상태, 메모를 포함한 구조화된 결과를 요구한다.
6. 성공하면 `RUNNING -> IMPLEMENTED`로 전환한다. 실패하면 재시도가 남아 있을 때 `REPAIR`로 전환하고, 그렇지 않으면 `FAILED`로 전환한다.
7. 비격리 검증 전에 성공한 구현 worktree를 제거해 기능 브랜치를 checkout할 수 있게 한다. 실패한 worktree는 점검을 위해 유지한다.

선택된 ready set 하나를 구현 wave 하나로 취급한다. 해당 wave의 모든 worker가 끝나고 각 기능 브랜치가 기록된 SHA에서 파생됐음이 증명될 때까지 로컬 `dev`를 기록된 `base_ref`에 고정한다. wave 안에 활성 구현 worker가 남아 있는 동안 `dev`를 검증, 통합 또는 그 밖의 방식으로 전진시키지 않는다. 이렇게 해야 로컬 `dev`에서 브랜치를 만드는 기존 engineer 계약이 유지된다.

wave가 끝난 뒤 성공한 티켓을 직렬로 검증하고 통합한다. 같은 wave의 나중 티켓은 더 오래된 wave base에서 시작했을 수 있다. integrator는 로컬 `dev`를 fast-forward하기 전에 최신 로컬 `dev`를 해당 기능 브랜치에 merge해야 한다.

## Phase 5: 검증과 복구

구현된 티켓을 하나씩 검증한다.

1. `IMPLEMENTED -> VERIFYING`으로 전환한다.
2. `verify-impl <ticket path>`를 호출하고 `PASS`, `FAIL`, `INCONCLUSIVE` 판정과 보고서 경로를 파싱한다.
3. `PASS`이면 `VERIFIED`로 전환하고 검증 커밋을 기록한다.
4. `FAIL`이면 복구 재시도가 남아 있을 때 `REPAIR`로 전환한다. 기존 기능 브랜치에 격리 worktree를 다시 만들고, 적용 가능한 구현 에이전트에게 티켓, 계획, 검증 보고서, 기존 브랜치, `mode: repair`를 보낸다. 새 repair 커밋을 요구한 뒤 다시 검증한다.
5. `INCONCLUSIVE`이면 명확히 일시적인 검증 실패일 때만 한 번 재시도한다. 그렇지 않으면 `BLOCKED`로 전환한다. 기본 정책에서는 절대 통합하지 않는다.
6. 기존 구현 에이전트가 기존 브랜치를 재개할 수 없으면 관련 없는 대체 브랜치를 만들지 말고 `REPAIR_UNSUPPORTED` 사유로 티켓을 `BLOCKED` 처리한다.
7. 각 verifier 실행 후 기능 브랜치가 clean인지 요구하고, repair 또는 integrator worktree가 해당 기능 브랜치를 사용할 수 있도록 로컬 `dev`를 checkout한다. 예상치 못한 dirty 파일이 남으면 해당 티켓을 중단하고 정확한 경로를 보고한다.

`FAILED` 또는 `BLOCKED` 티켓의 하위 티켓이 계속 사용할 수 없는 상태여도, 관련 없는 ready 티켓은 계속 진행한다.

## Phase 6: 검증된 티켓을 로컬 dev에 통합

통합 큐를 직렬 처리한다.

1. `VERIFIED -> INTEGRATING`으로 전환한다.
2. 메인 workspace가 clean이고 로컬 `dev`가 checkout되어 있는지 확인한다.
3. 기능 브랜치가 현재 로컬 `dev`를 포함하도록, 다음 입력으로 격리 worktree에서 `integrator`를 spawn한다.

   ```json
   {
     "ticket_path": "<absolute-ticket-path>",
     "plan_path": "<absolute-plan-path>",
     "branch": "<feature-branch>",
     "base_ref": "dev"
   }
   ```

4. `integrator`는 모호하지 않은 충돌만 해결하고 `AGENTS.md`가 허용한 검증을 실행하게 한다. 모호한 충돌이나 잘못된 결과가 있으면 해당 티켓을 중단한다.
5. integrator 성공 후 현재 `dev`가 기능 브랜치의 ancestor인지 확인한다.
6. `git merge --ff-only <feature-branch>`로만 로컬 `dev`를 전진시킨다. `dev`에 merge commit을 만들지 말고 절대 강제하지 않는다.
7. 새 `dev` SHA를 기록하고 `INTEGRATING -> INTEGRATED`로 전환한다.
8. 이 전환 이후에만 스케줄러가 하위 티켓을 unlock하게 한다.

통합에 실패하면 로컬 `dev`를 이전 SHA에 그대로 두고 티켓을 `REPAIR` 또는 `FAILED`로 이동한다. 관련 없는 티켓은 계속 진행한다.

## Phase 7: 완료 또는 일시 중지

스케줄러 요약을 실행한다.

```text
python <skill-dir>/scripts/dag_scheduler.py summary <manifest>
```

- ready 작업이 남아 있으면 Phase 4를 계속한다.
- 실패했거나 차단된 선행 티켓만 남아 있으면 해당 티켓과 차단된 하위 티켓을 한 번 보고하고 사용자 입력을 기다린다.
- 모든 티켓이 `INTEGRATED`가 되면 프로젝트 규칙이 허용하는 집계 검증을 선택적으로 실행한다.
- `--push`가 제공되었으면 `origin/dev`를 fetch하고, 로컬 `dev`가 diverge 없이 `origin/dev`를 포함해야 하며, 배치 끝에 로컬 `dev`를 한 번 push한다. 절대 force-push하지 않는다.
- 로컬 dev SHA, push 상태, 티켓 결과, 가정, 생략된 Maven 증거, 검증 보고서 경로를 포함한 최종 리뷰 하나를 제시한다.

사람의 결정 하나를 기다린다.

- 승인: 모든 `INTEGRATED` 티켓을 `DONE`으로 전환하고 완료한다.
- 수정 피드백: 필요한 수정 티켓만 만들고, 계획을 세우며, 영향을 받은 통합 티켓에 의존하도록 같은 매니페스트에 추가하고, 그래프를 검증한 뒤 Phase 4를 재개한다. 기존 작업을 되돌리기보다 fix-forward를 선호한다. 명시적으로 요청받지 않는 한 revert하지 않는다.

## 재개

`--resume`의 경우:

1. 매니페스트를 검증한다.
2. 기록된 브랜치와 커밋 SHA를 실제 Git ref와 비교한다.
3. 커밋과 검증 보고서로 증명할 수 있는 사실만 조정한다.
4. 중단된 `RUNNING`, `VERIFYING`, `INTEGRATING` 작업이 성공했다고 추론하지 않는다. 해당 브랜치/worktree를 검사하고 증거로 상태 전환을 완료하거나 사유와 함께 `BLOCKED`로 표시한다.
5. 스케줄러의 ready set부터 계속한다.

## 기존 스킬 경계

- 티켓 작성 규칙에는 `ticket-create`를 사용한다.
- 티켓 계획과 route에는 `plan-impl --no-chain`만 사용한다.
- 이 파이프라인에서 `impl-api` 또는 `impl-front` wrapper를 호출하지 않는다. 스케줄러가 readiness와 worktree를 제어할 수 있도록 하위 engineer role을 직접 spawn한다.
- 티켓 검증에는 `verify-impl`을 사용하되, 그 판정을 터미널 보고서가 아니라 이 파이프라인의 입력으로 취급한다.
- 티켓별로 `merge-impl`을 호출하지 않는다. 그 계약은 사전 사람 승인을 요구하며 최종 독립 통합을 대상으로 한다.
- `finalize-impl`과 `commit-impl`은 선택 사항이며 자동 파이프라인 밖에 둔다.

## 결정론적 스케줄러

검증, ready 선택, 상태 전환, 요약에는 `scripts/dag_scheduler.py`를 사용한다. 거부된 전환을 수동으로 우회하지 않는다. 이 스크립트는 명시적 priority와 더 긴 dependency chain을 우선시하고, 순환 그래프를 방지하며, 충돌하는 리소스가 같은 ready set에 포함되지 않게 한다.
