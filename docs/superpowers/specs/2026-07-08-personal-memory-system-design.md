# 개인 AI 메모리 시스템 설계

날짜: 2026-07-08
상태: 사용자 리뷰 대기

## 목적

Claude Code와 나눈 대화(현재 526개 세션, 289MB JSONL)를 잃어버리지 않고:

1. **과거 대화 검색** — "저번에 어떻게 해결했더라?"를 전문 검색으로 해결
2. **인사이트 자동 축적** — 작업 중 나온 교훈·결정·선호를 자동 감지해 저장, 다음 세션의 Claude가 더 똑똑하게 시작
3. **위키/지식베이스** — 세션에서 추출한 정보를 프로젝트/토픽/의사결정 위키로 정리

수집 소스는 **Claude Code만** (1차). Codex CLI, Gemini CLI, 웹 익스포트는 seCall이 이미 지원하므로 필요 시 켜기만 하면 됨.

주 소비자는 **Claude Code 자신** (MCP 검색 + 세션 시작 시 자동 주입). 사람 열람은 Obsidian이 부수적으로 제공.

## 아키텍처

레이어 2개. 하나는 도입(seCall), 하나는 자작(memory-tick 스킬).

```
[Claude Code 세션 JSONL (~/.claude/projects)]
        │
        ▼ secall ingest / sync (launchd 일 1회)
[seCall] ── 로컬 볼트 ~/secall-vault
   ├─ raw/.sessions/   원본 세션 아카이브 (불변, dot-prefix로 Obsidian 숨김)
   ├─ wiki/            AI 생성 위키 (projects / topics / decisions)
   ├─ log/             날짜별 작업일기
   └─ SQLite FTS5      BM25 검색 (kiwi 토크나이저), DB는 파생 캐시
        │
        ▼ secall mcp (user 스코프)
[Claude Code 새 세션] ← recall / get / wiki_search / graph_query 툴

[대화 중 인사이트] ─ memory-tick 스킬 (Stop hook, 스로틀)
        ▼
[iCloud Obsidian vault/memory/]  마크다운 + frontmatter, 폰 열람 가능
        ▲
[SessionStart hook] ─ MEMORY.md 인덱스를 새 세션에 주입
```

**볼트 분리 원칙**: 무거운 원본 아카이브는 로컬(`~/secall-vault`), 가벼운 큐레이션 노트만 iCloud vault. 289MB+ 아카이브를 iCloud에 넣으면 폰 동기화·스토리지만 괴롭다. Obsidian은 두 볼트를 모두 열 수 있다.

## 컴포넌트 1: seCall (도입)

- 레포: https://github.com/hang-in/seCall (Rust, 385⭐, 활발히 유지보수 중, AGPL — 개인 사용 무관)
- 설치: 공식 `install.sh` (macOS prebuilt 바이너리)
- `secall init` 설정값:
  - 볼트: `~/secall-vault`
  - 토크나이저: **kiwi** (한국어 대화 비중 높음)
  - 임베딩 백엔드: **none** — BM25만으로 시작. 자기 대화 검색은 키워드를 기억하는 경우가 대부분이라 BM25로 충분. 검색 품질이 아쉬우면 `ort`(ONNX 내장 bge-m3) 백엔드로 전환 후 `secall reindex`
  - git remote: 생략 (멀티 기기 필요해지면 추가)
- 초기 인제스트: `secall ingest --auto` → 526개 세션
- MCP 등록: `claude mcp add --scope user secall -- secall mcp` → 모든 프로젝트에서 과거 세션 검색
- 자동화: launchd로 매일 1회 `secall sync`
- 위키/작업일기: `secall wiki update --backend claude` — LLM 토큰을 쓰므로 초기엔 수동 실행, 품질 확인 후 주 1회 자동화 검토

## 컴포넌트 2: memory-tick 스킬 (자작)

`~/.claude/skills/memory-tick/SKILL.md` 개인 스킬 하나 + hook 스크립트.

### 저장 (쓰기 경로)

- **트리거 1**: Stop hook — 스로틀 스크립트(마지막 저장 후 일정 시간/턴 경과 시에만)가 "이번 구간에 저장 가치 있는 인사이트가 있는지 판단하라"는 컨텍스트를 주입. Claude가 판단해서 있으면 조용히 저장, 없으면 무시
- **트리거 2**: 사용자의 명시 요청 ("이거 기억해", "메모리 저장해줘", "remember this")
- **저장 위치**: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/memory/` 플랫 폴더
- **파일 형식**: `{type}_{slug}.md`, YAML frontmatter (`name`, `description`, `type: user|feedback|project|reference`, `tags`, `created`)
- **인덱스**: 같은 폴더의 `MEMORY.md`에 한 줄 요약 목록 유지 (파일당 한 줄)
- 저장 기준: 코드/git이 이미 기록하는 것은 저장하지 않음. 사용자 선호, 반복되는 교훈, 프로젝트 제약, 외부 참조만

### 회상 (읽기 경로)

- SessionStart hook이 vault의 `MEMORY.md`를 읽어 새 세션 컨텍스트에 주입
- 인덱스만 주입 (전문 아님) — Claude가 관련 있다고 판단한 항목만 해당 파일을 Read
- 어느 프로젝트 디렉토리에서 작업하든 동일하게 동작 (프로젝트별 메모리가 아니라 개인 전역 메모리)

## 에러 처리

- **seCall**: 볼트(마크다운)가 원본, DB는 캐시. DB 손상 시 `secall reindex --from-vault`로 복구. `secall lint`로 정합성 점검
- **hooks**: 전부 fail-open. 스크립트 오류·타임아웃이 세션 진행을 절대 막지 않음 (exit 0 보장, 에러는 로그 파일로만)
- **iCloud 충돌**: memory 파일은 항상 파일 단위 전체 쓰기 (append 없음). 충돌 시 Obsidian/iCloud가 만드는 conflict 사본은 인덱스에 안 올라가므로 무해

## 검증 계획

1. 인제스트 후 `secall recall` 스모크 테스트 — 기억나는 과거 작업 2~3개 검색해서 실제로 나오는지
2. 세션 수가 소스 JSONL 수(526 근처)와 맞는지
3. 새 Claude Code 세션에서 MCP recall 툴이 보이고 동작하는지
4. memory-tick 왕복: 테스트 인사이트 저장 → 새 세션에서 자동 주입 확인
5. hook fail-open: 스크립트를 일부러 깨뜨려도 세션이 정상 진행되는지

## 명시적으로 뺀 것 (YAGNI)

| 뺀 것 | 다시 켜는 조건 |
| --- | --- |
| 벡터/시맨틱 검색 | BM25 recall이 아쉬울 때 — `secall config` 백엔드 변경 + reindex |
| Codex/Gemini/웹 익스포트 수집 | 해당 도구 사용량이 늘 때 — `secall ingest <경로>` 한 줄 |
| Web UI 상시 구동 | 브라우징 필요할 때 — `secall serve` 수동 실행 |
| git 멀티 기기 동기화 | 두 번째 Mac이 생길 때 |
| 위키 자동 생성 스케줄 | 수동 실행 품질 확인 후 |
