---
name: implement-api
model: gpt-sol
codex-model: gpt-sol
description: 티켓 기반 TDD API 구현 워크플로우. docs/tickets/의 티켓을 받아 브랜치 생성 → TDD(Red/Green) → 빌드/테스트 검증 → 보고서 작성 → 사용자 수동 검증 대기 → 검증완료 반영 → 단계별 로컬 커밋까지 자동으로 수행한다. push 는 사용자 명시 지시 후에만 실행한다.
---

# /implement-api — 티켓 기반 API 구현 자동화

## 목적

BOMS 프로젝트의 API 구현 워크플로우를 표준화한다. 티켓 1건을 입력받아 **브랜치 생성부터 로컬 커밋까지** 수행하고, push는 사용자 지시 후에만 실행한다.

## 호출 형식

```
/implement-api <티켓 경로>
```

예: `/implement-api docs/tickets/PROJECT_MEMBER_ASSIGN.md`

티켓 경로가 주어지지 않으면 즉시 **중단하고 사용자에게 티켓 경로를 물어본다**. 추측하지 않는다.

## 사전 읽기 (필수)

구현 시작 전 반드시 다음 문서를 **Read 도구로 순서대로** 읽는다. 읽지 않고 진행하면 안 된다.

1. `docs/SSOT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/AI_AGENT_RULES.md`
4. `docs/DEVELOPMENT_GUIDE.md`
5. `docs/QA_AND_DONE.md`
6. `docs/tickets/README.md`
7. `docs/analysis/README.md`
8. 입력받은 티켓 파일

---

## 워크플로우

### 0. 사전 점검

다음을 **반드시** 확인한다. 하나라도 실패하면 **즉시 중단**하고 사용자에게 상황을 보고한다.

- [ ] 티켓 파일이 존재하는가?
- [ ] 티켓 파일 커밋 여부 확인 및 자동 커밋:
  - `git status` 로 uncommitted 파일 목록을 확인한다
  - **입력받은 티켓 파일만** untracked/unstaged 상태인 경우 → 자동으로 커밋한다:
    ```bash
    git add <티켓 파일 경로>
    git commit -m "chore: add ticket <티켓 파일명>"
    ```
  - 티켓 파일 외 다른 uncommitted 변경도 존재하는 경우 → **즉시 중단**하고 사용자에게 stash/commit 안내
  - 작업 트리가 이미 clean 한 경우 → 이 단계 건너뜀
- [ ] `git fetch origin dev` 실행하여 원격 최신 상태를 가져온다

> 현재 브랜치가 어디든 상관없다. 새 브랜치는 `origin/dev` 을 base로 직접 분기하므로, 로컬 `dev` 의 상태(ahead/behind/divergent)도 무관하다. 단, 현재 브랜치의 uncommitted 변경은 `git checkout -b` 시 새 브랜치로 끌려와 오염을 유발하므로 반드시 clean 상태여야 한다.

### 1. 티켓 분석

티켓을 읽고 다음을 추출한다.

- **Type** (FEAT / BUG / TASK / CHORE / STYLE 등)
- **제목 / 브랜치명** — 티켓 내 `핵심 규칙` 섹션에 브랜치명이 명시되어 있으면 그것을 사용. 없으면 파일명에서 유도한다.
- **Scope 허용/금지**
- **Acceptance Criteria**
- **Verification 단계**

**구현 계획 제시** — 코딩 시작 전 사용자에게 아래를 보고한다:

- 근본 원인 분석
- 수정 대상 파일 목록
- 구현 순서 (TDD 계획 포함)
- 잠재 위험

> ⚠️ 사용자는 `/implement-api <티켓>` 호출 자체가 **구현 승인**이다. 계획을 보고한 뒤 별도 승인 대기 없이 바로 다음 단계로 진행한다. 다만 티켓 범위 밖의 변경이 필요하다고 판단되면 **반드시 중단**하고 확인 요청.

### 2. 브랜치 생성

브랜치명 규칙:

| 티켓 Type | 접두사 | 예시 |
|-----------|-------|------|
| 신규 기능 구현 | `feature/` | `feature/project_member_assign` |
| 기능 수정 / 오류 수정 | `fix/` | `fix/task_pin_bug` |
| 테스트 코드만 수정 | `test/` | `test/user_service_coverage` |
| 문구 수정 | `chore/edit_text` | (고정) |
| 스타일 수정 | `style/` | `style/button_alignment` |

```bash
git checkout -b <접두사>/<이름> origin/dev
```

**반드시 base를 `origin/dev` 으로 명시**한다. 이래야 현재 체크아웃된 브랜치와 무관하게 원격 dev 기준으로 깔끔히 분기된다.

### 3. TDD — Red 단계 (테스트 먼저)

티켓 AC 기반으로 **실패하는 테스트**를 먼저 작성한다.

- **Controller 통합 테스트** (`@SpringBootTest` + `MockMvc`) — API 엔드포인트 레벨
- **Service 단위 테스트** (Mockito 또는 `@SpringBootTest`) — 비즈니스 로직 레벨
- 위 두 레이어까지만 작성한다. Repository 테스트는 대상이 아니다.

테스트 위치: `src/test/java/org/cric/back_office/...`

테스트 작성 후 실행하여 **실제로 실패하는지 확인**한다 (`./gradlew test --tests "..."`). 실패하지 않으면 테스트가 의미 없으므로 재작성.

### 4. TDD — Green 단계 (구현)

테스트가 통과되도록 최소한의 코드로 구현한다. 아키텍처 계층 순서를 따른다:

```
DTO → Repository → Service → Controller
```

- 기존 패턴 재사용 (`ApiResponse<T>`, `EditorEntity` 상속, 팩토리 메서드, QueryDSL)
- 티켓 Scope 허용 목록만 수정. 금지 목록(DB 스키마, 인프라 등) 절대 건드리지 않음.
- QueryDSL 엔티티 변경이 있다면 빌드 중 QClass 재생성 필요

### 5. 빌드 / 테스트 확인

```bash
./gradlew clean build
```

- 빌드 성공 + 방금 추가한 테스트 모두 통과 → 다음 단계
- **실패하면 즉시 중단**하고 실패 로그를 사용자에게 보고. 사용자 지시 대기.

### 6. 보고서 작성

위치: `docs/analysis/{TICKET-ID_또는_NAME}_report.md`

파일명 규칙: `docs/analysis/README.md` 의 명명 규칙 준수.

필수 섹션 (`docs/QA_AND_DONE.md` 5장 및 기존 보고서 포맷 준거):

1. **요약** — 구현 내용 + 변경 이유
2. **변경 파일** — 표 형식 (파일 경로 | 변경 내용), 테스트 파일은 별도 서브섹션
3. **구현 상세**
   - 프로세스 동작 과정 (API 호출부터 내부 함수 호출 순서까지 번호로 기술)
   - 권한 검증 흐름 (해당 시)
4. **검증** — 빌드/테스트 결과 표
5. **회귀 확인** — 기존 기능 영향 없음 명시
6. **위험/참고** — 동시성, 엣지 케이스 등
7. **완료 상태** — 체크박스 리스트 (AC 항목 기준)

> 이 시점에서 "사용자 검증" 항목은 아직 비워둔다 (Step 8에서 채움).

### 7. 🛑 사용자 수동 검증 대기

다음 메시지를 사용자에게 출력하고 **대화를 일시 중단**한다:

```
✅ 구현 완료. 수동 검증을 진행해 주세요.

1. ./gradlew bootRun 으로 애플리케이션 실행
2. 티켓의 'Verification' 섹션에 명시된 시나리오 수행
3. 검증 완료 시 "검증완료" 라고 응답해 주세요
4. 문제가 있다면 구체적 증상을 알려주세요 — 해당 지점부터 수정 진행
```

**사용자의 "검증완료" 응답이 오기 전까지 Step 8 이후로 진행 금지.**

### 8. 보고서 검증완료 반영

사용자가 "검증완료"라고 응답하면 보고서의 **검증** 섹션 표에 다음 행을 추가:

```
| 사용자 검증 (YYYY-MM-DD) | 완료 |
```

날짜는 오늘 날짜 (환경에서 제공된 `currentDate` 사용).

### 9. 단계별 커밋 (push 금지)

커밋을 아래 순서로 분리한다. **각 커밋마다 사용자 확인 없이 진행**한다 (이미 검증 완료된 상태).

1. **테스트 커밋**
   ```
   test: {티켓 제목 요약}
   ```
   대상 파일: `src/test/**` 하위 변경분만

2. **구현 커밋** (prefix는 티켓 Type에 맞춤)
   ```
   feat: {기능 요약}    # 신규 기능
   fix: {수정 내용}     # 버그 수정
   style: {스타일 내용} # 스타일 수정
   ```
   대상 파일: `src/main/**` 하위 변경분

3. **보고서 커밋**
   ```
   chore: add implementation report for {티켓 ID/이름}
   ```
   대상 파일: `docs/analysis/{...}_report.md`

각 커밋 전 `git add` 는 **경로를 명시**한다. `git add .` 또는 `git add -A` 금지.

Co-Authored-By 라인이나 외부 광고성 문구 추가 금지.

### 10. 완료

마지막으로 사용자에게 다음을 보고:

- 생성된 브랜치명
- 커밋 목록 (`git log --oneline dev..HEAD`)
- 다음 단계 안내:
  ```
  push 하려면 'push 해줘' 또는 'git push -u origin <브랜치>' 로 지시해 주세요.
  이후 GitHub에서 PR 생성 → dev 머지는 수동으로 진행.
  ```

**여기서 Skill 실행 종료.** push 는 하지 않는다.

---

## 실패 처리

모든 단계에서 아래 원칙을 따른다:

- 빌드 실패 / 테스트 실패 / 예상치 못한 에러 발생 시 **즉시 중단**
- 에러 로그를 사용자에게 그대로 제시
- 자동 재시도 금지 — 사용자 지시 대기
- 이미 만든 브랜치/커밋은 건드리지 않음 (destructive action 금지)

## 커밋 메시지 규칙 요약

| Prefix | 용도 |
|--------|------|
| `feat:` | 신규 기능 구현 |
| `fix:` | 기능 수정 / 버그 수정 |
| `test:` | 테스트 코드 작성/수정 |
| `chore:` | 보고서, 문서, 설정 등 |
| `style:` | 스타일(CSS/템플릿) 수정 |

prefix 뒤에는 **콜론 + 공백 + 한국어 요약**.

## 참고 문서

- 티켓 포맷 표준: `docs/tickets/_TEMPLATE.md`
- 티켓 규칙: `docs/tickets/README.md`
- 보고서 규칙: `docs/analysis/README.md`, `docs/QA_AND_DONE.md`
- AI 행동 규칙: `docs/AI_AGENT_RULES.md`
- 아키텍처: `docs/ARCHITECTURE.md`, `docs/SSOT.md`

---

문서 끝.
