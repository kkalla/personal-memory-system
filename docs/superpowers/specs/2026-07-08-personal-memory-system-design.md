# 개인 AI 메모리 시스템 설계

날짜: 2026-07-08 (rev 2 — 볼트 완전 통일)
상태: 사용자 리뷰 대기

## 목적

Claude Code와 나눈 대화(현재 526개 세션, 289MB JSONL)를 잃어버리지 않고:

1. **과거 대화 검색** — "저번에 어떻게 해결했더라?"를 전문 검색으로 해결
2. **인사이트 자동 축적** — 작업 중 나온 교훈·결정·선호를 자동 감지해 저장, 다음 세션의 Claude가 더 똑똑하게 시작
3. **위키/지식베이스** — 세션에서 추출한 정보를 프로젝트/토픽/의사결정 위키로 정리

수집 소스는 **Claude Code만** (1차). Codex CLI, Gemini CLI, 웹 익스포트는 seCall이 이미 지원하므로 필요 시 켜기만 하면 됨.

주 소비자는 **Claude Code 자신** (MCP 검색 + 세션 시작 시 자동 주입). 사람 열람은 Obsidian(맥/폰)이 제공.

프로젝트 저장소: `/Users/max/00_Projects/95_personal-memory`

## 아키텍처

레이어 2개. 하나는 도입(seCall), 하나는 자작(memory-tick 스킬). 저장소는 **iCloud Obsidian vault 안 `96_memory` 하나로 완전 통일** — 원본 아카이브까지 iCloud에 실리는 트레이드오프(스토리지·동기화 트래픽 증가)를 인지하고 선택함.

```
[Claude Code 세션 JSONL (~/.claude/projects)]
        │
        ▼ secall ingest / sync (launchd 일 1회)
[seCall 볼트] = ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory/
   ├─ raw/.sessions/   원본 세션 아카이브 (불변, dot-prefix — Obsidian 인덱싱 제외)
   ├─ wiki/            AI 생성 위키 (projects / topics / decisions)
   ├─ log/             날짜별 작업일기
   ├─ graph/           Knowledge Graph
   ├─ memory/          memory-tick 노트 + MEMORY.md 인덱스 (자작 레이어)
   └─ SQLite FTS5      BM25 검색 (kiwi 토크나이저), DB는 로컬 파생 캐시
        │
        ▼ secall mcp (user 스코프)
[Claude Code 새 세션] ← recall / get / wiki_search / graph_query 툴

[대화 중 인사이트] ─ memory-tick 스킬 (Stop hook, 스로틀)
        ▼
[96_memory/memory/] ← 마크다운 + frontmatter
        ▲
[SessionStart hook] ─ memory/MEMORY.md 인덱스를 새 세션에 주입
```

**통일의 장점**: 위키·작업일기·메모리 노트가 메인 PARA vault 안에서 바로 보이고, `[[]]` 링크가 기존 노트들과 한 vault에서 엮임. 폰에서도 열람 가능. 멀티 기기 동기화는 iCloud가 담당 (seCall git sync는 사용하지 않음 — iCloud와 충돌).

**수용한 트레이드오프**: `raw/.sessions/`(현재 기준 수십~100MB+, 계속 증가)가 iCloud를 탐. dot-prefix 폴더라 Obsidian 앱(폰 포함)은 인덱싱하지 않으므로 앱 성능 영향은 제한적일 것으로 예상. 문제가 되면 그때 로컬 볼트로 분리 후 `secall reindex --from-vault`로 이전.

## 컴포넌트 1: seCall (도입)

- 레포: https://github.com/hang-in/seCall (Rust, 385⭐, 활발히 유지보수 중, AGPL — 개인 사용 무관)
- 설치: 공식 `install.sh` (macOS prebuilt 바이너리)
- `secall init` 설정값:
  - 볼트: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory`
  - 토크나이저: **kiwi** (한국어 대화 비중 높음) — [Task 2 후속] 설치된 secall v0.7.0의 kiwi 자동 다운로드는 upstream 버그(잘못된 libkiwi 버전 핀 + asset 파서 버그)로 실패해 lindera로 폴백했었음. libkiwi v0.22.2 dylib+model을 `~/.local/share/secall/kiwi/`에 수동 배치하고 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 환경변수로 지정해 실제 kiwi 로딩 확인, 한국어 검색 정상 동작 확인(`.superpowers/sdd/task-2-report.md` "Fix: kiwi tokenizer" 참고). 기존 인제스트된 세션의 FTS 인덱스는 재토큰화되지 않았고(reindex는 zero-turn 세션만 healing), 환경변수도 아직 셸 프로필에 영속화되지 않아 MCP/hook/launchd 실행 환경마다 별도 전달 필요.
  - 임베딩 백엔드: **none** — BM25만으로 시작. 자기 대화 검색은 키워드를 기억하는 경우가 대부분이라 BM25로 충분. 검색 품질이 아쉬우면 `ort`(ONNX 내장 bge-m3) 백엔드로 전환 후 `secall reindex`
  - git remote: 사용 안 함 (동기화는 iCloud)
- 초기 인제스트: `secall ingest --auto` → 526개 세션
- MCP 등록: `claude mcp add --scope user secall -- secall mcp` → 모든 프로젝트에서 과거 세션 검색
- 자동화: launchd로 매일 1회 `secall sync`
- 위키/작업일기: `secall wiki update --backend claude` — LLM 토큰을 쓰므로 초기엔 수동 실행, 품질 확인 후 주 1회 자동화 검토

## 컴포넌트 2: memory-tick 스킬 (자작)

`~/.claude/skills/memory-tick/SKILL.md` 개인 스킬 하나 + hook 스크립트.

### 저장 (쓰기 경로)

- **트리거 1**: Stop hook — 스로틀 스크립트(마지막 평가 후 30분 경과 시에만, 값은 스크립트 상수로 조정 가능)가 "이번 구간에 저장 가치 있는 인사이트가 있는지 판단하라"는 컨텍스트를 주입. Claude가 판단해서 있으면 조용히 저장, 없으면 무시
- **트리거 2**: 사용자의 명시 요청 ("이거 기억해", "메모리 저장해줘", "remember this")
- **저장 위치**: `96_memory/memory/` 플랫 폴더 (seCall 볼트 내 자작 서브폴더)
- **파일 형식**: `{type}_{slug}.md`, YAML frontmatter (`name`, `description`, `type: user|feedback|project|reference`, `tags`, `created`)
- **인덱스**: 같은 폴더의 `MEMORY.md`에 한 줄 요약 목록 유지 (파일당 한 줄)
- 저장 기준: 코드/git이 이미 기록하는 것은 저장하지 않음. 사용자 선호, 반복되는 교훈, 프로젝트 제약, 외부 참조만

### 회상 (읽기 경로)

- SessionStart hook이 `96_memory/memory/MEMORY.md`를 읽어 새 세션 컨텍스트에 주입
- 인덱스만 주입 (전문 아님) — Claude가 관련 있다고 판단한 항목만 해당 파일을 Read
- 어느 프로젝트 디렉토리에서 작업하든 동일하게 동작 (프로젝트별 메모리가 아니라 개인 전역 메모리)

## 에러 처리

- **seCall**: 볼트(마크다운)가 원본, DB는 로컬 캐시. DB 손상 시 `secall reindex --from-vault`로 복구. `secall lint`로 정합성 점검
- **hooks**: 전부 fail-open. 스크립트 오류·타임아웃이 세션 진행을 절대 막지 않음 (exit 0 보장, 에러는 로그 파일로만)
- **iCloud 충돌**: memory 파일은 항상 파일 단위 전체 쓰기 (append 없음). 충돌 시 iCloud가 만드는 conflict 사본은 인덱스에 안 올라가므로 무해. seCall 원본(raw/)은 불변 파일이라 충돌 소지 낮음

## 검증 계획

1. 인제스트 후 `secall recall` 스모크 테스트 — 기억나는 과거 작업 2~3개 검색해서 실제로 나오는지
2. 세션 수가 소스 JSONL 수(526 근처)와 맞는지
3. 새 Claude Code 세션에서 MCP recall 툴이 보이고 동작하는지
4. memory-tick 왕복: 테스트 인사이트 저장 → 새 세션에서 자동 주입 확인
5. hook fail-open: 스크립트를 일부러 깨뜨려도 세션이 정상 진행되는지
6. **볼트 동거 확인**: 자작 `memory/` 폴더가 seCall `lint`/`reindex`에서 문제를 일으키지 않는지 (문제 시 memory 폴더를 `96_memory` 밖 `95_memory` 등 형제 폴더로 이동 — 스킬의 경로 상수만 변경)
7. **iCloud 부하 확인**: 초기 인제스트 후 `96_memory` 실측 용량 확인, 폰 Obsidian 열어서 체감 확인

## 명시적으로 뺀 것 (YAGNI)

| 뺀 것 | 다시 켜는 조건 |
| --- | --- |
| 벡터/시맨틱 검색 | BM25 recall이 아쉬울 때 — `secall config` 백엔드 변경 + reindex |
| Codex/Gemini/웹 익스포트 수집 | 해당 도구 사용량이 늘 때 — `secall ingest <경로>` 한 줄 |
| Web UI 상시 구동 | 브라우징 필요할 때 — `secall serve` 수동 실행 |
| seCall git 동기화 | 사용 안 함 — iCloud가 동기화 담당 (둘 다 켜면 충돌) |
| 위키 자동 생성 스케줄 | 수동 실행 품질 확인 후 |
