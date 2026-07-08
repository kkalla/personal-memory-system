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

- 위치: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory/memory/` (플랫 폴더, 하위 폴더 없음)
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

## 동작 규칙

1. 조용히 한다 — 저장했다고 길게 보고하지 않는다 (한 줄이면 충분).
2. 파일은 항상 전체 쓰기(Write), append 금지 (iCloud 충돌 방지).
3. 인덱스(MEMORY.md)가 100줄을 넘으면 오래되고 안 쓰이는 항목부터 정리한다.
4. 저장할 게 없으면 아무 것도 하지 않는다 — 억지로 만들지 않는다.
