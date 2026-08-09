---
name: implement-front
model: gpt-sol
codex-model: gpt-sol
description: 티켓 기반 프론트엔드 전용 구현 워크플로우. docs/tickets/의 티켓을 받아 브랜치 생성 → 구현(템플릿/CSS/JS만) → 빌드 검증 → 보고서 작성 → 사용자 수동 브라우저 검증 대기 → 검증완료 반영 → 단계별 로컬 커밋까지 자동으로 수행한다. 백엔드 코드(`src/main/java/**`)와 DB 스키마, 설정 파일은 절대 수정하지 않는다. push 는 사용자 명시 지시 후에만 실행한다.
---

# /implement-front — 티켓 기반 프론트엔드 전용 구현 자동화

## 목적

BOMS 프로젝트의 **프론트엔드 전용** 구현 워크플로우를 표준화한다. API/DB 변경이 필요 없는 화면 수정, 디자인/레이아웃 변경, 정적 자원 추가 등을 다룬다. 티켓 1건을 입력받아 **브랜치 생성부터 로컬 커밋까지** 수행하고, push는 사용자 지시 후에만 실행한다.

API 수정이 동반되는 작업은 이 스킬이 아닌 `/implement-api` 를 사용한다.

## 호출 형식

```
/implement-front <티켓 경로>
```

예: `/implement-front docs/tickets/TASK_DETAIL_SIDE_PANEL.md`

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

### 1. 티켓 분석 + 스코프 검증

티켓을 읽고 다음을 추출한다.

- **Type** (FEAT / BUG / TASK / CHORE / STYLE 등)
- **제목 / 브랜치명** — 티켓 내 `핵심 규칙` 섹션에 브랜치명이 명시되어 있으면 그것을 사용. 없으면 파일명에서 유도한다.
- **Scope 허용/금지**
- **Acceptance Criteria**
- **Verification 단계**

**스코프 검증 (이 스킬 적용 가능 여부 판단)**:

티켓이 다음 중 하나라도 요구하면 **즉시 중단**하고 사용자에게 `/implement-api` 사용을 권한다:
- 신규 API 엔드포인트 추가
- 기존 컨트롤러/서비스/리포지토리 로직 변경
- 엔티티/DTO 구조 변경
- DB 스키마 변경
- `application*.yml` 설정 변경

**구현 계획 제시** — 코딩 시작 전 사용자에게 아래를 보고한다:

- 수정 대상 파일 목록 (전부 프론트 자원이어야 함)
- 구현 순서
- 잠재 위험 (기존 화면 회귀, 반응형 깨짐, 브라우저 호환성 등)

> ⚠️ 사용자는 `/implement-front <티켓>` 호출 자체가 **구현 승인**이다. 계획을 보고한 뒤 별도 승인 대기 없이 바로 다음 단계로 진행한다. 다만 티켓 범위 밖의 변경이 필요하다고 판단되면 **반드시 중단**하고 확인 요청.

### 2. 브랜치 생성

브랜치명 규칙:

| 티켓 Type | 접두사 | 예시 |
|-----------|-------|------|
| 신규 화면/UI 기능 | `feature/` | `feature/task_detail_side_panel` |
| UI 버그 수정 | `fix/` | `fix/modal_close_button` |
| 스타일 수정 (CSS/레이아웃) | `style/` | `style/button_alignment` |
| 문구 수정 | `chore/edit_text` | (고정) |

```bash
git checkout -b <접두사>/<이름> origin/dev
```

**반드시 base를 `origin/dev` 으로 명시**한다. 이래야 현재 체크아웃된 브랜치와 무관하게 원격 dev 기준으로 깔끔히 분기된다.

### 3. 구현

티켓 AC 기반으로 프론트 자원만 수정한다.

**수정 허용 디렉토리** (이 외에는 절대 수정 금지):

- `src/main/resources/templates/**` — Thymeleaf 템플릿
- `src/main/resources/static/css/**` — 스타일시트
- `src/main/resources/static/js/**` — 클라이언트 스크립트
- `src/main/resources/static/fonts/**` — 폰트 자원
- `src/main/resources/static/images/**` — 이미지 자원 (존재 시)

**수정 절대 금지 디렉토리/파일**:

- `src/main/java/**` — 모든 백엔드 Java 코드
- `src/test/**` — 모든 테스트 코드
- `database.sql` — DB 스키마
- `application*.yml` — 애플리케이션 설정
- `build.gradle`, `settings.gradle` — 빌드 설정

위 금지 항목 중 하나라도 수정해야 할 필요가 발견되면 **즉시 중단**하고 사용자에게 보고. `/implement-api` 로 전환을 권한다.

**구현 가이드라인**:

- 기존 Thymeleaf 프래그먼트(`templates/fragments/**`) 재사용 우선
- 기존 CSS 클래스/유틸리티 재사용 우선
- 기존 JS 모듈 패턴 답습
- 새 화면 추가 시 기존 페이지 구조(`global/header`, `global/sidebar` 등) 그대로 사용

### 4. 빌드 검증

```bash
./gradlew compileJava
```

- 백엔드 코드는 손대지 않았으므로 `compileJava` 만으로 충분하다 (Thymeleaf 템플릿이 클래스패스에 포함되는지 확인용)
- 빌드 실패 시 즉시 중단하고 실패 로그를 사용자에게 보고. 사용자 지시 대기.

> 풀빌드(`./gradlew clean build`)는 시간이 오래 걸리고 백엔드 테스트까지 돌리므로 이 단계에서는 생략한다. 회귀 검증은 사용자 수동 브라우저 테스트(Step 6)에서 진행.

### 5. 보고서 작성

위치: `docs/analysis/{TICKET-ID_또는_NAME}_report.md`

파일명 규칙: `docs/analysis/README.md` 의 명명 규칙 준수.

필수 섹션 (`docs/QA_AND_DONE.md` 5장 및 기존 보고서 포맷 준거):

1. **요약** — 구현 내용 + 변경 이유
2. **변경 파일** — 표 형식 (파일 경로 | 변경 내용). 모두 프론트 자원이어야 함.
3. **구현 상세**
   - 화면 동작 흐름 (사용자 액션 → DOM/스타일 변화 순서)
   - 반응형/브라우저 대응 사항 (해당 시)
4. **검증** — 빌드 결과 + 사용자 검증 칸 (Step 7에서 채움)
5. **회귀 확인** — 기존 화면 영향 없음 명시
6. **위험/참고** — 브라우저 호환성, 캐시, 접근성 등
7. **완료 상태** — 체크박스 리스트 (AC 항목 기준)

> 이 시점에서 "사용자 검증" 항목은 아직 비워둔다 (Step 7에서 채움).

### 6. 🛑 사용자 수동 브라우저 검증 대기

다음 메시지를 사용자에게 출력하고 **대화를 일시 중단**한다:

```
✅ 구현 완료. 브라우저에서 수동 검증을 진행해 주세요.

1. ./gradlew bootRun 으로 애플리케이션 실행
2. 브라우저에서 티켓의 'Verification' 섹션에 명시된 화면/시나리오 확인
3. 강력 새로고침(Ctrl+F5)으로 정적 자원 캐시 무효화 후 재확인
4. 검증 완료 시 "검증완료" 라고 응답해 주세요
5. 문제가 있다면 구체적 증상(스크린샷/콘솔 에러 등)을 알려주세요 — 해당 지점부터 수정 진행
```

**사용자의 "검증완료" 응답이 오기 전까지 Step 7 이후로 진행 금지.**

### 7. 보고서 검증완료 반영

사용자가 "검증완료"라고 응답하면 보고서의 **검증** 섹션 표에 다음 행을 추가:

```
| 사용자 검증 (YYYY-MM-DD) | 완료 |
```

날짜는 오늘 날짜 (환경에서 제공된 `currentDate` 사용).

### 8. 단계별 커밋 (push 금지)

커밋을 아래 순서로 분리한다. **각 커밋마다 사용자 확인 없이 진행**한다 (이미 검증 완료된 상태).

1. **구현 커밋** (prefix는 티켓 Type에 맞춤)
   ```
   feat: {기능 요약}    # 신규 화면/UI 기능
   fix: {수정 내용}     # UI 버그 수정
   style: {스타일 내용} # 스타일/레이아웃 수정
   chore: {문구 내용}   # 문구 수정
   ```
   대상 파일: `src/main/resources/templates/**`, `src/main/resources/static/**` 하위 변경분

2. **보고서 커밋**
   ```
   chore: add implementation report for {티켓 ID/이름}
   ```
   대상 파일: `docs/analysis/{...}_report.md`

각 커밋 전 `git add` 는 **경로를 명시**한다. `git add .` 또는 `git add -A` 금지.

Co-Authored-By 라인이나 외부 광고성 문구 추가 금지.

### 9. 완료

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

- 빌드 실패 / 예상치 못한 에러 발생 시 **즉시 중단**
- 에러 로그를 사용자에게 그대로 제시
- 자동 재시도 금지 — 사용자 지시 대기
- 이미 만든 브랜치/커밋은 건드리지 않음 (destructive action 금지)
- 백엔드 수정이 필요해진 경우 즉시 중단 후 `/implement-api` 전환 권유

## 커밋 메시지 규칙 요약

| Prefix | 용도 |
|--------|------|
| `feat:` | 신규 화면/UI 기능 |
| `fix:` | UI 버그 수정 |
| `style:` | 스타일(CSS/레이아웃) 수정 |
| `chore:` | 문구 수정, 보고서, 정적 자원 등 |

prefix 뒤에는 **콜론 + 공백 + 한국어 요약**.

## `/implement-api` 와의 차이

| 항목 | `/implement-api` | `/implement-front` |
|------|------------------|--------------------|
| 적용 대상 | 백엔드+프론트 동시 수정 | 프론트 전용 |
| TDD | Red/Green 단계 필수 | 없음 (백엔드 미변경) |
| 빌드 명령 | `./gradlew clean build` | `./gradlew compileJava` |
| 검증 방식 | 자동 테스트 + 사용자 수동 | 사용자 수동 브라우저만 |
| 커밋 분리 | 테스트 + 구현 + 보고서 (3건) | 구현 + 보고서 (2건) |
| 수정 허용 | 전체 (티켓 Scope 내) | `templates/**`, `static/**` 만 |

## 참고 문서

- 티켓 포맷 표준: `docs/tickets/_TEMPLATE.md`
- 티켓 규칙: `docs/tickets/README.md`
- 보고서 규칙: `docs/analysis/README.md`, `docs/QA_AND_DONE.md`
- AI 행동 규칙: `docs/AI_AGENT_RULES.md`
- 아키텍처: `docs/ARCHITECTURE.md`, `docs/SSOT.md`
- 풀스택 구현 스킬: `.claude/skills/implement-api/SKILL.md`

---

문서 끝.
