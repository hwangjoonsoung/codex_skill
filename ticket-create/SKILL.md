---
name: ticket-create
model: gpt-sol
description: 요구사항을 ticket_writer 에이전트로 티켓 파일로 작성하는 thin wrapper. 자유 텍스트=단건(메인 세션이 모호점만 사용자에게 질문 후 ticket_writer 1개 spawn), feature-list .md 경로=일괄(메인 세션이 미구현 항목 파싱 → 항목당 ticket_writer 병렬 spawn). 티켓은 오늘 날짜(yyyymmdd) 디렉토리(docs/tickets/<yyyymmdd>/) 밑에 저장하며, 디렉토리가 없으면 생성한다. ticket 커밋은 하지 않으며(사용자 검토 후 /plan-impl Step 0 에서 자동 커밋), 브랜치 생성/구현은 하지 않는다.
---

# /ticket-create — ticket_writer 호출 wrapper (티켓 작성)

## 목적

요구사항을 **`ticket_writer` 에이전트**로 `docs/tickets/_TEMPLATE.md` 포맷 티켓 파일로 작성한다. 사용자와의 모호점 Q&A(인터랙티브)는 메인 세션이 담당하고, 실제 티켓 본문 작성은 agent 가 한다.

> 인터랙티브 게이트(AskUserQuestion 류)는 sub-agent 에서 동작하지 않으므로, **모호점 질문은 메인 세션이** 하고 확정된 요구사항을 agent 에 전달한다. 티켓 포맷/섹션 규칙은 `~/.claude/agents/ticket_writer.md` 가 보유.

## 호출 형식

```
/ticket-create <요구사항 자유 텍스트>          # 단건
/ticket-create <feature-list .md 파일 경로>   # 일괄
```

인자가 없으면 즉시 **중단**하고 물어본다.

## 디스패치

| 인자 | 모드 | 진행 |
|------|------|------|
| 존재하는 `.md` 파일 경로 | 일괄 | "일괄 모드" 섹션 |
| 그 외 자유 텍스트 | 단건 | "단건 모드" 섹션 |
| 존재하는 디렉토리 | 오류 | 의도 모호 — 자유 텍스트인지 feature-list 파일인지 확인 |

---

## 단건 모드

### S1. 모호점 사용자 질문 (인터랙티브, 메인 세션)

요구사항에서 **Type / 현재·기대 동작 / 영향 범위 / AC 근거 / DB 스키마 변경 여부** 중 불명확한 게 있으면 사용자에게 질문한다(추측 금지 — SSOT 필수사항). 명확하면 스킵.
- 더 효율적인 방법(라이브러리/구조)이 보이면 제안. 라이브러리는 무료 라이선스(MIT/Apache 2.0/GPL 등)만.

### S2. 날짜 디렉토리 + 파일명 결정 (메인 세션)

1. **오늘 날짜 디렉토리 확보**: `<DATE>` = 오늘 날짜를 `yyyymmdd` 로 포맷(예: `20260707`). `<TICKET_DIR>` = `docs/tickets/<DATE>/`. 해당 디렉토리가 없으면 `mkdir -p docs/tickets/<DATE>` 로 **먼저 생성**한다.
2. **파일명 결정**: UPPER_SNAKE_CASE 3~5단어로 `<TICKET_DIR><NAME>.md` (= `docs/tickets/<DATE>/<NAME>.md`) 결정. 같은 날짜 디렉토리 내 동일명 존재 시 `_V2`/`_FIX` 등으로 구분하고 사용자에게 알린다.

### S3. ticket_writer spawn

`Agent` 도구 1회 호출:
- `subagent_type`: `ticket_writer`
- `isolation`: **사용 안 함** (티켓을 메인 워크스페이스에 직접 작성)
- `description`: `"ticket: <NAME>"`
- `prompt` (첫 JSON 블록):
  ```json
  { "requirement": "<원요구사항 + S1 에서 확정된 Q&A 요약>", "output_path": "<docs/tickets/<DATE>/<NAME>.md 절대경로>" }
  ```

### S4. 완료 보고 / 종료

agent 응답(티켓 경로/Type/보완 필요)을 받아 보고 + 다음 단계 안내:
```
구현 계획: /plan-impl docs/tickets/<DATE>/<NAME>.md
```
> ⚠️ ticket 은 **커밋하지 않는다**. 사용자가 검토/수정한 뒤 `/plan-impl` Step 0 에서 자동 커밋된다.

---

## 일괄 모드 (feature-list)

코디네이터 sub-agent 없이 **메인 세션이 직접** 파싱·spawn 한다.

### B1. 미구현 항목 파싱 (메인 세션)
- `test -f <인자>` 확인.
- `^##` = 도메인 헤더, `^\d+\.` = 기능 항목. 제목에 **(DONE)** 포함 시 스킵. 항목 본문(들여쓰기)을 다음 항목/헤더 직전까지 묶어 (domain, title, body) 추출.
- 미구현 항목 0개면 "처리 대상 없음" 보고 후 종료.

### B2. 파일명 + 중복 검사 (메인 세션)
- `<OUTPUT_DIR>` = `dirname(<인자>)`.
- 항목별 티켓명 UPPER_SNAKE_CASE → `<OUTPUT_DIR>/<NAME>.md`.
- `<OUTPUT_DIR>/<NAME>.md` 가 이미 존재하거나 `docs/tickets/**` 에 의미상 동일 티켓이 있으면 **스킵**(사유 명시).

### B3. ticket_writer 병렬 spawn (항목당 1개)
실행 대상 N개를 **단일 메시지에 `Agent` 호출 N개 병렬 배치**:
- `subagent_type`: `ticket_writer`, `isolation`: 사용 안 함, `description`: `"ticket: <NAME>"`
- `prompt` JSON: `{ "requirement": "<항목 body>", "output_path": "<OUTPUT_DIR>/<NAME>.md 절대경로>" }`
> 일괄 모드는 사용자 인터랙션이 불가하므로 ticket_writer 가 모호점을 §8 Confirmation 에 "미정" 으로 남겨 best-effort 작성한다.

### B4. 집계 보고 / 종료
- 생성된 티켓 목록 / 스킵(중복) / 보완 필요 항목.
- ticket 커밋 안 함. 다음 단계 안내:
  ```
  일괄 계획+구현: /plan-impl <OUTPUT_DIR>
  ```

---

## 금지 사항

- ticket 파일 `git add`/커밋 일체 금지(→ `/plan-impl` Step 0). 다른 파일 커밋도 금지.
- 브랜치 생성/구현/계획 수립 금지(각각 `/impl-*`, `/plan-impl` 책임).
- `docs/tickets/<yyyymmdd>/`(오늘 날짜 디렉토리) 외 위치 저장 금지. 기존 티켓 덮어쓰기 금지(동일명 시 중단·확인).
- 실행 경로/트랙(frontmatter `type`: fullstack/api/front) 추천·기록 금지 — `/plan-impl` 의 architect 가 코드 탐색으로 결정해 ticket frontmatter 에 채워 넣는다. ticket 작성 시 `type` 은 빈칸/생략으로 둔다.

## 참고

- 티켓 에이전트: `~/.claude/agents/ticket_writer.md`
- 다음 단계: `.claude/skills/plan-impl/SKILL.md`

---

문서 끝.
