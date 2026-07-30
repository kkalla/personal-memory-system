---
name: memory-tick
description: |
  대화에서 저장 가치가 있는 인사이트를 감지해 개인 메모리(Obsidian vault)에 조용히 저장하는 스킬.
  Stop hook(stop-hook-throttle.sh)이 30분마다 한 번 평가를 지시하면 이 스킬 규칙대로 판단·저장한다.
  사용자가 "이거 기억해", "메모리 저장해줘", "remember this"라고 명시 요청할 때도 발동한다.
---

# memory-tick: 대화에서 자동으로 배우기

## 목적

대화에서 가치 있는 인사이트를 감지해 저장하고, 다음 세션의 Claude가 더 똑똑하게 시작하도록 한다.

## 저장소

- 위치: `~/99_memory/memory/` (플랫 폴더, 하위 폴더 없음). 2026-07-30에 iCloud Obsidian 볼트에서 로컬로 이전 — iCloud 쓰기 충돌(`Resource deadlock avoided`) 때문
- 파일명: `{type}_{slug}.md` (예: `feedback_pdf-conversion.md`)
- 형식: 마크다운 + YAML frontmatter

```markdown
---
name: <kebab-case-slug>
description: <한 줄 요약 — 회상 시 관련성 판단에 사용>
type: user | feedback | project | reference
tags: [<태그>]
created: <YYYY-MM-DD>
---

<본문. feedback/project는 **Why:** 와 **How to apply:** 줄 포함.
관련 메모리는 [[슬러그]]로 링크.>
```

- 인덱스: 같은 폴더 `MEMORY.md`에 파일당 한 줄 — `- [제목](파일명.md) — 한 줄 훅`. 인덱스에 본문을 넣지 않는다.

## 저장 기준

저장한다: 사용자 선호·정정 피드백, 반복되는 교훈, 코드로 알 수 없는 프로젝트 제약, 외부 참조(URL·티켓).
저장하지 않는다: 코드/git 히스토리가 이미 기록하는 것, 이 대화에서만 유효한 것.
저장 전 기존 파일 확인 — 중복이면 새 파일 대신 기존 파일 갱신. 틀린 메모리는 삭제.

## 근거 표기

관찰한 사실과 추론을 섞어 쓰지 않는다. 직접 확인한 것(명령 출력·파일 내용·에러 로그)은 근거를 같이 남기고,
확인하지 못한 추측은 "미확인:" 으로 표시하거나 아예 쓰지 않는다.
확인할 도구가 없으면(예: Bash 없는 서브에이전트) "확인 불가"라고 쓴다 — 그럴듯한 원인을 지어내지 않는다.
(실측 사례: 위키 에이전트가 iCloud 쓰기 충돌을 두고 존재하지 않는 경쟁 프로세스의 PID·시각까지 지어냄)

## 시크릿 규칙

시크릿 값(API 키·토큰·비밀번호)은 절대 저장하지 않는다 — 필요하면 `[REDACTED:VAR명]`으로 마스킹해 문맥만 남긴다.
사용자가 `<private>...</private>`로 감싼 내용은 저장 대상에서 제외한다 (claude-mem의 private 태그 컨벤션).
아카이브 쪽 자동 마스킹은 `scrub/scrub_secrets.py`(launchd 08:45)가 담당하지만, 메모리 파일은 이 스킬이 직접 쓰므로 여기서 지켜야 한다.

## 동작 규칙

1. 조용히 한다 — 저장했다고 길게 보고하지 않는다 (한 줄이면 충분).
2. 파일은 항상 전체 쓰기(Write), append 금지 (iCloud 충돌 방지).
3. 인덱스(MEMORY.md)가 100줄을 넘으면 오래되고 안 쓰이는 항목부터 정리한다.
4. 저장할 게 없으면 아무 것도 하지 않는다 — 억지로 만들지 않는다.
