---
name: merge-impl
model: gpt-sol
description: "verify-impl(자동 검증)과 사람 검증까지 끝난 feature 브랜치를 로컬 dev 에 통합하는 파이프라인 종단 스킬. 충돌은 integrator 에이전트가 feature 브랜치 위에서 최신 origin/dev 를 병합해 해소하고(모호하면 중단), 메인 세션은 충돌이 불가능한 clean fast-forward 로만 로컬 dev 를 전진시킨 뒤 origin/dev 로 push 한다. dev 는 항상 깨끗하게만 전진하며, main PR/머지는 이 스킬 밖(수동)이다. `--no-push` 로 로컬 dev ff 까지만, `--yes` 로 확인 게이트 생략."
---

# /merge-impl — feature → 로컬 dev 통합 + push (파이프라인 종단)

## 목적

verify(자동 검증) 파이프라인과 **사람 검증**까지 끝난 feature 브랜치를 **로컬 dev 에 통합**하고 `origin/dev` 로 push 한다. dev merge 시점의 충돌을 자동화하기 위한 스킬이다.

**핵심 설계** — 충돌은 "dev 위"가 아니라 "feature 위"에서 잡는다:

1. `integrator` 에이전트가 **feature 브랜치 위에서** 최신 `origin/dev` 를 병합(`git merge`)하고 충돌을 해소 + 빌드 그린 확인.
2. 그 결과 feature 가 `origin/dev` 를 **완전히 포함**하므로, 메인 세션은 로컬 dev 를 feature 로 **`--ff-only` fast-forward** 한다 → 이 단계는 **충돌이 원천적으로 불가능**. dev 는 깨끗한 상태로만 전진.
3. 메인 세션이 `git push origin dev`.

> ⚠️ **사람 검증 이후에 호출**하는 스킬이다. 자동 verify(PASS/FAIL)와 무관하게, 사용자가 브랜치를 확인하고 "dev 에 합쳐도 된다" 고 판단한 뒤 실행한다.

## 호출 형식

```
/merge-impl <티켓 경로> [--no-push] [--yes]
```

티켓 경로가 없으면 즉시 **중단**하고 물어본다. 추측 금지.

### 플래그

| 플래그 | 효과 |
|--------|------|
| `--no-push` | 로컬 dev ff 까지만 하고 `git push` 스킵. |
| `--yes` | Step 3 확인 게이트 생략(merge+push 를 바로 진행). |

---

## Step 0. 인자 파싱 & 사전 산출 (메인 세션)

1. 티켓 존재 확인. 없으면 중단.
2. **plan.md 경로 도출**(공용 규칙: `docs/tickets/` 및 `working|done|backlog|archive` 접두 제거 → 파일명 `.md`→`_plan.md` → `docs/plans/` 접두, 더블슬래시 금지) + 존재 확인. 없으면 중단, `/plan-impl` 안내. `Read` → **브랜치명** 추출.
3. **_verify.md 경로 도출**(공용 날짜 세그먼트 규칙에 `docs/verify/` 접두 + `_verify.md` 접미사) + 존재 확인. 없으면 중단: "검증 문서가 없습니다. 먼저 `/verify-impl <티켓 경로>` 로 자동 검증을 마쳐주세요." (= 검증 전 단계 미완)
4. 브랜치 존재 확인: `git branch --list <branch>`. 없으면 중단(구현/커밋 미완 추정).

## Step 1. dev 상태 점검 (메인 세션)

```bash
git fetch origin dev
```

- 로컬 `dev` 가 `origin/dev` 와 **분기(diverge)** 했는지 확인(`git rev-list --left-right --count dev...origin/dev`).
  - 로컬 dev 가 origin/dev 보다 **앞서 있음**(left>0) → 중단·보고: 로컬 dev 에 push 안 된 커밋이 있어 자동 통합 불가. 사용자에게 로컬 dev 정리 요청.
  - 그 외(behind 또는 동일) → 정상. 이후 Step 4 에서 로컬 dev 를 `origin/dev` 로 ff 한 뒤 feature 로 ff 한다.

## Step 2. 확인 게이트 (`--yes` 면 생략)

무엇을 할지 요약해 사용자 확인을 받는다(merge+push 는 되돌리기 어려운 작업):

```
다음을 진행합니다:
  1) integrator: '<branch>' 위에서 origin/dev 병합 + 충돌 해소 + 빌드 확인
  2) 로컬 dev 를 '<branch>' 로 fast-forward
  3) git push origin dev            ← --no-push 면 생략

'진행' 이라고 응답하면 실행합니다. (검증이 끝나지 않았다면 여기서 멈춰주세요.)
```

사용자 "진행" 응답 시 Step 3. 그 외/이의 제기 → 중단.

## Step 3. integrator spawn (feature 위 충돌 해소)

`Agent` 도구 1회 호출:
- `subagent_type`: `integrator`
- `isolation`: **`"worktree"`** (feature 브랜치를 격리 worktree 로 체크아웃해 병합·빌드; 메인 워크스페이스 오염 없음)
- `description`: `"merge: <티켓 파일명>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "ticket_path": "<TICKET_ABS>", "plan_path": "<PLAN_ABS>", "branch": "<plan.md 브랜치명>", "base_ref": "origin/dev" }
  ```

integrator 6줄 응답에서 수집: 결과 / dev merge 방식 / merge 커밋 SHA / 빌드 / 비고.

- **결과=충돌-중단(모호)** → 중단. integrator 비고의 모호 충돌 파일/헝크를 사용자에게 그대로 보고하고, 수동 해소 또는 티켓 재작업을 안내. dev 는 건드리지 않았으므로 안전.
- **결과=실패(빌드 등)** → 중단, 로그 보고. worktree 유지(사용자 확인용).
- **결과=성공** → Step 4.

## Step 4. 로컬 dev fast-forward (메인 세션)

integrator 성공(= feature 가 origin/dev 를 포함) 후, 충돌 불가능한 clean ff 로만 dev 를 전진:

```bash
git checkout dev
git merge --ff-only origin/dev     # 로컬 dev 를 origin/dev 로 정렬 (behind 였다면 전진; 실패=분기이므로 Step 1 에서 이미 걸러짐)
git merge --ff-only <branch>       # feature 로 ff (feature 가 origin/dev 포함 → clean ff 보장)
```

- 어느 `--ff-only` 든 **실패하면 즉시 중단**(비-ff 상황). dev 를 건드린 게 없으므로(체크아웃만) 안전, 사유 보고. `--force`/비-ff 병합 절대 금지.
- ff 성공 시 새 dev HEAD SHA 수집.

> integrator 가 격리 worktree 에서 만든 병합 커밋은 **같은 로컬 저장소의 브랜치 ref(`<branch>`)에 반영**되므로 메인 세션에서 `<branch>` 가 보인다(공유 `.git`). 따라서 위 ff 가 성립한다.

## Step 5. push (`--no-push` 면 생략)

```bash
git push origin dev
```

- push 거부(원격 dev 가 그새 전진 등) → 중단, 사유 보고. 강제 push 절대 금지. 사용자에게 재실행 안내.
- `--no-push` → push 생략하고 "로컬 dev 통합 완료, push 는 수동" 안내.

## Step 6. worktree 정리 & 완료 보고 (메인 세션)

- integrator worktree 를 `git worktree list` 로 식별해 `git worktree remove <path>`(성공 시에만; 실패/중단 시 유지). `--force` 금지, 제거 실패 시 사유 보고.
- 완료 보고:

```
🎉 dev 통합 완료.
브랜치: <branch>
dev merge 방식: <clean 병합 | 충돌해소(N파일) | 최신(병합 불필요)>
새 dev HEAD: <SHA>
push: <origin/dev 로 push 완료 | 생략(--no-push)>

다음: main 반영은 dev → main PR 로 별도 진행하세요. (이 스킬 범위 밖)
```

---

## 커밋 / 코드 수정 정책

- **메인 세션은 코드/충돌을 직접 수정하지 않는다.** 충돌 해소(코드 변경)는 integrator 에이전트 worktree 안에서만.
  - 메인 세션 허용 git 작업(코드 판단 없는 오케스트레이션): `git fetch`, `git checkout dev`, `git merge --ff-only`, `git push origin dev`, `git worktree remove`.
- `git add .` / `-A` / 강제 push / 비-ff 병합 / rebase 금지.

## 실패 처리 (요약)

- 인자/티켓/plan/_verify.md/브랜치 누락 → 중단, 사유·선행 스킬 안내.
- 로컬 dev 가 origin/dev 보다 앞섬(분기) → 중단(Step 1).
- integrator 모호 충돌 → 중단, 충돌 파일 보고(dev 무손상).
- integrator 빌드 실패 → 중단, 로그 보고, worktree 유지.
- `--ff-only` 실패 / push 거부 → 중단, 사유 보고. 강제 조작 금지.

## 참고

- 통합 에이전트: `~/.claude/agents/integrator.md` (입력 `{ticket_path, plan_path, branch, base_ref, cwd?}`, feature 위 병합·충돌해소·빌드까지만)
- 선행: `.claude/skills/verify-impl/SKILL.md` + 사람 검증
- 후행(스킬 밖): dev → main PR (수동)

---

문서 끝.
