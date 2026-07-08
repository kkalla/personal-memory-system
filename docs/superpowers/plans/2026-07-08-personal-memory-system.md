# 개인 AI 메모리 시스템 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** seCall로 Claude Code 세션 아카이브·검색·위키를 구축하고, 자작 memory-tick 스킬로 대화 인사이트를 자동 축적한다.

**Architecture:** 레이어 2개 — ① seCall(외부 도구 도입): JSONL 인제스트 → iCloud vault `96_memory` 볼트 + SQLite FTS5(BM25) + MCP 서버. ② memory-tick(자작): Stop hook(30분 스로틀)이 인사이트 저장을 지시하고, SessionStart hook이 메모리 인덱스를 새 세션에 주입.

**Tech Stack:** seCall(Rust 바이너리, 설치만), bash hook 스크립트 2개, Claude Code hooks(settings.json), launchd.

## Global Constraints

- seCall 볼트 경로: `/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory` (공백 포함 — 항상 인용)
- memory-tick 저장 폴더: 위 볼트 안 `memory/` 서브폴더, 인덱스는 `memory/MEMORY.md`
- 토크나이저 **kiwi**, 임베딩 백엔드 **none**(BM25만), seCall git sync **사용 금지**(iCloud가 동기화 담당)
- hook은 전부 fail-open: 어떤 오류에도 `exit 0`, 세션을 막지 않는다
- 스로틀 간격 30분 (스크립트 상수)
- 파일 원본은 repo `/Users/max/00_Projects/95_personal-memory/skills/memory-tick/`, `~/.claude/skills/memory-tick`은 symlink
- 스펙: `docs/superpowers/specs/2026-07-08-personal-memory-system-design.md`

## 파일 구조

```
95_personal-memory/
├── docs/superpowers/specs/…(기존 스펙)
├── docs/superpowers/plans/2026-07-08-personal-memory-system.md  (이 문서)
├── skills/memory-tick/
│   ├── SKILL.md                  # memory-tick 스킬 본문
│   ├── stop-hook-throttle.sh     # Stop hook: 30분 스로틀 + 평가 지시 주입
│   ├── session-start-memory.sh   # SessionStart hook: MEMORY.md 인덱스 주입
│   └── test_hooks.sh             # 두 스크립트의 셀프 체크 (bats 없이 bash만)
└── launchd/com.max.secall-sync.plist  # 일일 secall sync (원본, 설치는 cp)
```

---

### Task 1: seCall 설치 + init

**Files:**
- Create: 없음 (외부 바이너리 설치 + `96_memory` 볼트 초기화)

**Interfaces:**
- Produces: `secall` CLI (PATH 상), 볼트 디렉토리 `…/Obsidian/96_memory/` (raw/, wiki/, log/ 구조)

- [x] **Step 1: 설치**

```bash
curl -fsSL https://raw.githubusercontent.com/hang-in/seCall/main/install.sh | sh
```

- [x] **Step 2: 설치 확인**

```bash
which secall && secall --version
```

Expected: 바이너리 경로와 버전 출력. `which` 실패 시 셸 재로그인 또는 install.sh가 안내한 PATH 추가 후 재시도.

결과: `/Users/max/.local/bin/secall`, `secall 0.7.0`.

- [x] **Step 3: init 옵션 확인**

```bash
secall init --help
```

Expected: `--vault` 플래그 확인. 토크나이저/임베딩을 플래그로 받는지 확인 (비대화형 우선).

결과: `--vault`/`-v`, `--git`, `--format`만 존재. 토크나이저/임베딩 플래그 없음 → init 후 `secall config set`으로 보정 필요.

- [x] **Step 4: init 실행**

```bash
secall init --vault "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory"
```

대화형 프롬프트가 뜨면: 토크나이저 `kiwi`, 임베딩 백엔드 `none`, git remote 없음 선택. 플래그로 안 되고 프롬프트도 없으면 init 후 다음으로 보정:

```bash
secall config set search.tokenizer kiwi
secall config set embedding.backend none
```

(정확한 config 키 이름은 `secall config --help` 출력을 따른다)

결과: init은 비대화형으로 즉시 완료(프롬프트 없음, 기본값 tokenizer=lindera, embedding.backend=ollama로 생성). `secall config set search.tokenizer kiwi`, `secall config set embedding.backend none` 실행하여 보정 완료 (`secall config show`로 확인: tokenizer=kiwi, embedding.backend=none, git_remote=(not set)).

- [x] **Step 5: 볼트 생성 확인**

```bash
ls -la "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory"
```

Expected: seCall 볼트 구조(raw/ 또는 .sessions, wiki/, log/ 등) 생성됨.

결과: `raw/.sessions/`, `wiki/{projects,topics,decisions,overview.md}`, `index.md`, `log.md`, `SCHEMA.md` 생성 확인. `secall status`: Sessions 0, Embedded 0 (예상대로, ingest는 Task 2). `secall lint`: 0 errors, 1 warning(overview.md sources 누락, 무해).

- [x] **Step 6: 커밋 (plan 체크박스 갱신)**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add -A && git commit -m "chore: seCall 설치 및 96_memory 볼트 init 완료 기록"
```

---

### Task 2: 초기 인제스트 + 검색 스모크 테스트

**Files:**
- Create: 없음 (seCall 데이터 작업)

**Interfaces:**
- Consumes: Task 1의 `secall` CLI, init된 볼트
- Produces: 526개 세션이 인제스트된 검색 가능한 볼트

- [x] **Step 1: 소스 세션 수 기록**

```bash
find ~/.claude/projects -name "*.jsonl" | wc -l
```

Expected: 526 근처 (이후 검증 기준값).

결과: 531개. 단, 이 수치는 `subagents/` 하위에 중첩된 서브에이전트 세션 파일(depth 9/11, 총 303개)을 포함한 값. 최상위(depth 7) 세션 파일만 세면 228개 — 이게 `secall ingest --auto`가 실제로 스캔하는 후보 모수임 (Step 3 결과 참고).

- [x] **Step 2: 인제스트**

```bash
secall ingest --auto
```

Expected: Claude Code 세션 자동 감지 및 인제스트 진행 로그. 수 분 소요 가능.

결과: 완료 (약 2분 소요, 타임아웃 없음). `216 ingested, 24 skipped (duplicate), 6 errors`. 에이전트별: claude-code 202, codex 5, gemini-cli 9 (— `--auto`는 Claude Code 전용이 아니라 `~/.claude/projects` 외에 `~/.gemini/tmp` 등 다른 에이전트 세션 디렉터리도 함께 스캔함, 스펙 범위상 문제 없음). 에러 6건 중 2건은 `~/.claude/projects`의 "no parseable turns"(빈/손상 세션), 4건은 `~/.gemini/tmp` 세션. ⚠️ 런타임 경고: `kiwi-rs failed, falling back to lindera` — `KIWI_LIBRARY_PATH` 미설정 + 자동 다운로드도 실패(`release asset not found for current tag: kiwi_mac_arm64_v0.23.2.tgz`)로 config상 tokenizer=kiwi이지만 실제로는 lindera로 폴백 중. Step 4에서 한글 검색 기능 자체는 정상 동작 확인했으나, Task 1에서 설정한 kiwi가 실제로 적용되지 않고 있다는 점은 후속 조치 필요 (아래 "이슈" 참고).

- [x] **Step 3: 세션 수 검증**

```bash
secall status
```

Expected: 인제스트된 세션 수가 Step 1 값 근처 (서브에이전트/빈 세션 제외로 다소 적을 수 있음 — 절반 이하로 크게 다르면 원인 조사).

결과: Sessions 216, Turns 31897, Embedded 0(예상대로 — embedding.backend=none), Vault Files 216. 216은 Step 1의 raw 531 대비 절반 이하라 원인 조사 수행: raw 531 중 303개는 `subagents/` 하위 세션(서브에이전트, 예상대로 제외 대상)이고, 최상위 세션은 228개. 228개 중 202개 claude-code로 정상 인제스트 + 2개 파싱 에러 + 24개 중복 스킵 = 228 정확히 일치. 즉 실질 모수(228) 대비 인제스트율은 ~95%로 정상. Step 1의 "526 근처" 기준값은 서브에이전트 중첩 파일을 감안하지 않은 수치였던 것으로 판단.

- [x] **Step 4: 검색 스모크 테스트**

```bash
secall recall "메모리 시스템"
secall recall "seCall"
```

Expected: 이 프로젝트 세션 포함, 관련 세션·턴이 결과로 나옴. 한글 키워드가 안 나오면 kiwi 토크나이저 설정 재확인.

결과: 두 쿼리 모두 정상 동작. "메모리 시스템" → 10건, 1위가 이 프로젝트(00_Projects) 세션(`d2445a81`, `9b2b4509`, score 1.00, "개인 메모리 시스템 구축" 매치). "seCall" → 2건, 모두 이 프로젝트 세션(`9b2b4509`, "secall 볼트 obsidian memory..." 매치). 한글 키워드 정상 인식 확인 — 단, 위 kiwi→lindera 폴백 경고가 매 호출마다 출력됨. lindera로도 형태소 분석 자체는 동작하고 있어 기능적으로 스모크 테스트는 통과하나, 설정된 토크나이저가 아닌 폴백 엔진으로 동작 중이라는 점은 기록.

- [x] **Step 5: 정합성 + 용량 실측**

```bash
secall lint
du -sh "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory"
```

Expected: lint 통과. 용량 수치 기록 (스펙 검증 항목 7 — iCloud 부하 판단 근거).

결과: lint 통과 — `216 sessions, 0 errors, 1 warnings, 432 info`. 유일한 warning은 Task 1 때부터 있던 `wiki/overview.md`의 `sources` frontmatter 누락(무해, 위키 작업은 이후 태스크). info 432건은 전부 `no vector embeddings`(embedding=none 설정에 따른 예상된 결과) + `session not referenced in any wiki page`(위키 미생성 상태의 예상된 결과). 용량: 볼트 전체 `17M` (raw/ 세션 마크다운 17M, wiki/ 4.0K, index.md 36K, log.md 40K, SCHEMA.md 4.0K). 참고로 로컬 SQLite 인덱스(`~/Library/Caches/secall/index.sqlite`, iCloud 동기화 대상 아님)는 24M. 세션 216개/턴 31897개 기준 볼트 17M → iCloud 동기화 부하는 낮은 수준으로 판단.

- [x] **Step 6: 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add -A && git commit -m "chore: 초기 인제스트 완료 — 세션 수/용량 실측 기록"
```

결과: 커밋 완료 (plan 문서 체크박스 갱신만 대상 — 볼트 데이터는 `/Users/max/00_Projects/95_personal-memory` 밖의 iCloud 경로에 있어 이 저장소 커밋에 포함되지 않음).

**이슈 (후속 조치 권고, 이번 태스크 범위 밖):** kiwi-rs 네이티브 라이브러리 로드 실패 + 자동 다운로드도 실패(`kiwi_mac_arm64_v0.23.2` 릴리스 에셋 없음)로 매 ingest/recall 호출 시 lindera로 폴백. 한글 검색 기능 자체는 lindera로도 정상 동작했지만, Task 1에서 명시적으로 `tokenizer=kiwi`로 설정한 의도와 실제 런타임이 불일치. `KIWI_LIBRARY_PATH` 수동 설정 또는 secall 버전 확인이 필요해 보임 — Task 8 왕복 검증 또는 별도 후속 작업에서 다룰 것을 제안.

**후속 수정 (kiwi 토크나이저 실제 동작화, 상세는 `.superpowers/sdd/task-2-report.md`의 "Fix: kiwi tokenizer" 참고):** 원인은 두 가지 독립된 upstream 버그 — (1) secall v0.7.0이 핀한 libkiwi v0.23.2는 kiwi-rs 0.1.4 바인딩의 init 경로에서 SIGSEGV(upstream이 이미 v0.22.2로 재핀했으나 v0.7.0 릴리스에는 미반영), (2) secall의 release-asset 자동 다운로더 자체에 파싱 버그가 있어 어떤 태그든 다운로드 실패. bab2min/Kiwi 릴리스에서 **v0.22.2**(안전 버전) dylib+model을 직접 받아 `~/.local/share/secall/kiwi/`에 배치하고 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 환경변수로 지정하여 우회 — kiwi-fallback 경고 사라짐, `secall recall` 정상 동작 확인. 단, `secall reindex`는 이미 turns가 있는 기존 216개 세션을 재토큰화하지 않는다(소스 코드 확인: zero-turn 세션만 healing 대상) — 기존 세션의 FTS 인덱스는 Task 2 인제스트 당시의 lindera 토큰을 그대로 유지하며, 완전한 재토큰화는 `--force` 재인제스트(FTS5 중복 버그 #23 있음, 이번 범위에서 미실행)가 필요. **환경변수는 아직 `~/.zshrc`에 영속화되지 않음**(harness 권한 정책상 자동 편집 차단) — 사용자가 직접 추가하거나, Task 3/4/5/7에서 MCP·hook·launchd가 secall을 실행하는 각 환경에 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH`를 명시적으로 전달해야 함.

---

### Task 3: MCP 등록

**Files:**
- Modify: `~/.claude.json` (claude CLI가 수정 — 직접 편집 금지)

**Interfaces:**
- Consumes: Task 1의 `secall` CLI
- Produces: 모든 프로젝트에서 사용 가능한 `secall` MCP 서버 (recall/get/status/wiki_search/graph_query 툴)

- [x] **Step 1: user 스코프로 등록**

```bash
claude mcp add --scope user secall -- secall mcp
```

주의: `secall`이 로그인 셸 PATH에만 있으면 MCP 실행이 못 찾을 수 있음 — 그 경우 `which secall`의 절대경로로 등록.

결과: 브리핑 원안 대신 아래 augmented 커맨드로 등록 — Task 2에서 발견된 이슈(179번째 줄 참고)대로, `claude mcp add`는 로그인 셸(`~/.zshenv`)을 거치지 않고 커맨드를 직접 spawn하므로 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH`를 상속하지 못함. 두 값을 `--env`로 명시 전달:

```bash
claude mcp add secall --scope user \
  --env KIWI_LIBRARY_PATH="$HOME/.local/share/secall/kiwi/libkiwi.dylib" \
  --env KIWI_MODEL_PATH="$HOME/.local/share/secall/kiwi/model/models/cong/base" \
  -- secall mcp
```

등록 전 두 경로 실존 확인(`libkiwi.dylib` 15M, `model/models/cong/base/` 하위 `cong.mdl` 76M 등 정상 존재). `secall`은 절대경로(`which secall` → `/Users/max/.local/bin/secall`) 없이 bare 이름으로도 정상 연결됨(등록 시점에 PATH가 이미 해석되어 저장되는 것으로 보임) — 별도 재등록 불필요.

- [x] **Step 2: 등록 확인**

```bash
claude mcp list
```

Expected: `secall` 항목이 connected 상태.

결과: `secall: secall mcp - ✔ Connected`. `claude mcp get secall` 상세: Scope User config, Command `secall`, Args `mcp`, Environment에 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 정상 반영 확인.

- [x] **Step 3: 검증 기록 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add -A && git commit -m "chore: secall MCP user 스코프 등록"
```

결과: 커밋 완료 (plan 문서 체크박스 갱신 + `.superpowers/sdd/task-3-report.md` 대상 — `~/.claude.json`은 claude CLI가 관리하며 이 저장소 밖에 있어 커밋 대상 아님).

---

### Task 4: memory-tick — Stop hook 스로틀 스크립트 (TDD)

**Files:**
- Create: `skills/memory-tick/stop-hook-throttle.sh`
- Test: `skills/memory-tick/test_hooks.sh` (이 태스크에서 throttle 파트 작성, Task 5에서 session-start 파트 추가)

**Interfaces:**
- Produces: Stop hook 커맨드로 등록될 실행 파일. stdin으로 hook JSON을 받고, 스로틀 조건 충족 시 `{"decision":"block","reason":"…"}` JSON을 stdout에 출력, 그 외엔 무출력. 항상 exit 0. env `MEMORY_TICK_MARKER`로 마커 경로 오버라이드 가능(테스트용).

- [x] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p /Users/max/00_Projects/95_personal-memory/skills/memory-tick
```

`skills/memory-tick/test_hooks.sh`:

```bash
#!/bin/bash
# memory-tick hook 스크립트 셀프 체크. bats 없이 bash만 사용.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $1"; exit 1; }

# --- stop-hook-throttle.sh ---
tmpdir=$(mktemp -d)
export MEMORY_TICK_MARKER="$tmpdir/marker"

# 1) 마커 없으면(=첫 실행) block JSON 출력
out=$(echo '{}' | "$DIR/stop-hook-throttle.sh")
echo "$out" | grep -q '"decision":"block"' || fail "첫 실행은 block을 출력해야 함"

# 2) 직후 재실행은 스로틀에 걸려 무출력
out=$(echo '{}' | "$DIR/stop-hook-throttle.sh")
[ -z "$out" ] || fail "스로틀 구간 재실행은 무출력이어야 함"

# 3) stop_hook_active=true면 마커 없어도 무출력 (무한루프 방지)
rm -f "$MEMORY_TICK_MARKER"
out=$(echo '{"stop_hook_active": true}' | "$DIR/stop-hook-throttle.sh")
[ -z "$out" ] || fail "stop_hook_active면 무출력이어야 함"

# 4) 어떤 경우에도 exit 0 (fail-open)
echo 'not-json' | "$DIR/stop-hook-throttle.sh" >/dev/null
[ $? -eq 0 ] || fail "비정상 입력에도 exit 0이어야 함"

rm -rf "$tmpdir"
echo "PASS: stop-hook-throttle"
```

```bash
chmod +x skills/memory-tick/test_hooks.sh
```

결과: 테스트 파일 생성 완료.

- [x] **Step 2: 테스트가 실패하는지 확인**

Run: `skills/memory-tick/test_hooks.sh`
Expected: FAIL (stop-hook-throttle.sh 없음 — "No such file" 에러)

결과: 예상대로 실패 — `skills/memory-tick/test_hooks.sh: line 12: /Users/max/00_Projects/95_personal-memory/skills/memory-tick/stop-hook-throttle.sh: No such file or directory FAIL: 첫 실행은 block을 출력해야 함`

- [x] **Step 3: 구현**

`skills/memory-tick/stop-hook-throttle.sh`:

```bash
#!/bin/bash
# memory-tick Stop hook: 30분에 한 번, 턴 종료 직전에 메모리 저장 가치 평가를 지시한다.
# fail-open: 어떤 오류도 세션을 막지 않는다 (항상 exit 0).
MARKER="${MEMORY_TICK_MARKER:-$HOME/.claude/memory-tick-last-check}"
INTERVAL_SEC=$((30 * 60))  # ponytail: 고정 30분, 조정은 이 상수만

input=$(cat)

# stop hook 지시로 이미 한 번 이어진 턴이면 재차 지시하지 않는다 (무한루프 방지)
if printf '%s' "$input" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

now=$(date +%s)
if [ -f "$MARKER" ]; then
  last=$(stat -f %m "$MARKER" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$INTERVAL_SEC" ]; then
    exit 0
  fi
fi

touch "$MARKER" 2>/dev/null

cat <<'EOF'
{"decision":"block","reason":"[memory-tick] 이번 대화 구간에 저장 가치가 있는 인사이트(사용자 선호, 반복되는 교훈, 프로젝트 제약, 외부 참조)가 있는지 판단하라. 있으면 ~/.claude/skills/memory-tick/SKILL.md 규칙대로 저장하고 종료하라. 없으면 아무 것도 하지 말고 그대로 종료하라."}
EOF
exit 0
```

```bash
chmod +x skills/memory-tick/stop-hook-throttle.sh
```

결과: 구현 파일 생성 완료.

- [x] **Step 4: 테스트 통과 확인**

Run: `skills/memory-tick/test_hooks.sh`
Expected: `PASS: stop-hook-throttle`

결과: 예상대로 통과 — `PASS: stop-hook-throttle`

- [x] **Step 5: 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add skills/memory-tick/
git commit -m "feat: memory-tick Stop hook 스로틀 스크립트 (30분, fail-open)"
```

결과: 예정됨 (아래 참고)

---

### Task 5: memory-tick — SessionStart 주입 스크립트 (TDD)

**Files:**
- Create: `skills/memory-tick/session-start-memory.sh`
- Modify: `skills/memory-tick/test_hooks.sh` (session-start 테스트 추가)

**Interfaces:**
- Consumes: `96_memory/memory/MEMORY.md` (없어도 동작 — 무출력)
- Produces: SessionStart hook 커맨드. MEMORY.md가 있으면 라벨 한 줄 + 파일 내용을 stdout으로 출력(→ Claude Code가 세션 컨텍스트에 추가), 없으면 무출력. 항상 exit 0. env `MEMORY_TICK_INDEX`로 인덱스 경로 오버라이드 가능(테스트용).

- [x] **Step 1: 실패하는 테스트 추가**

`skills/memory-tick/test_hooks.sh`의 마지막 `echo "PASS: stop-hook-throttle"` 뒤에 추가:

```bash
# --- session-start-memory.sh ---
tmpdir2=$(mktemp -d)

# 1) 인덱스 파일이 없으면 무출력, exit 0
export MEMORY_TICK_INDEX="$tmpdir2/none/MEMORY.md"
out=$("$DIR/session-start-memory.sh")
[ $? -eq 0 ] || fail "인덱스 없어도 exit 0이어야 함"
[ -z "$out" ] || fail "인덱스 없으면 무출력이어야 함"

# 2) 인덱스가 있으면 라벨 + 내용 출력
export MEMORY_TICK_INDEX="$tmpdir2/MEMORY.md"
echo "- [테스트 항목](feedback_test.md) — 후크" > "$MEMORY_TICK_INDEX"
out=$("$DIR/session-start-memory.sh")
echo "$out" | grep -q '\[personal-memory\]' || fail "라벨이 출력되어야 함"
echo "$out" | grep -q '테스트 항목' || fail "인덱스 내용이 출력되어야 함"

rm -rf "$tmpdir2"
echo "PASS: session-start-memory"
```

- [x] **Step 2: 테스트가 실패하는지 확인**

Run: `skills/memory-tick/test_hooks.sh`
Expected: throttle은 PASS, session-start에서 FAIL ("No such file")

- [x] **Step 3: 구현**

`skills/memory-tick/session-start-memory.sh`:

```bash
#!/bin/bash
# memory-tick SessionStart hook: 개인 메모리 인덱스를 새 세션 컨텍스트에 주입한다.
# fail-open: 항상 exit 0.
MEMORY_MD="${MEMORY_TICK_INDEX:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory/memory/MEMORY.md}"

if [ -f "$MEMORY_MD" ]; then
  echo "[personal-memory] 저장된 개인 메모리 인덱스. 관련 항목은 같은 폴더의 해당 파일을 Read해서 참고하라:"
  cat "$MEMORY_MD" 2>/dev/null
fi
exit 0
```

```bash
chmod +x skills/memory-tick/session-start-memory.sh
```

- [x] **Step 4: 테스트 통과 확인**

Run: `skills/memory-tick/test_hooks.sh`
Expected: `PASS: stop-hook-throttle` 와 `PASS: session-start-memory` 둘 다 출력

- [x] **Step 5: 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add skills/memory-tick/
git commit -m "feat: memory-tick SessionStart 인덱스 주입 스크립트"
```

---

### Task 6: SKILL.md 작성 + symlink + hooks 등록

**Files:**
- Create: `skills/memory-tick/SKILL.md`
- Create: symlink `~/.claude/skills/memory-tick` → `/Users/max/00_Projects/95_personal-memory/skills/memory-tick`
- Modify: `~/.claude/settings.json` (hooks에 SessionStart/Stop 항목 추가)

**Interfaces:**
- Consumes: Task 4·5의 스크립트 절대경로
- Produces: Claude Code가 발견 가능한 memory-tick 스킬 + 활성화된 hook 2개

- [x] **Step 1: SKILL.md 작성**

`skills/memory-tick/SKILL.md`:

```markdown
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
```

결과: 브리핑 원문 그대로 전사 완료. 파일 생성 확인 (`skills/memory-tick/SKILL.md`, 2.1K).

- [x] **Step 2: symlink 생성**

```bash
ln -sfn /Users/max/00_Projects/95_personal-memory/skills/memory-tick ~/.claude/skills/memory-tick
ls -la ~/.claude/skills/memory-tick/
```

Expected: SKILL.md 등 4개 파일 보임.

결과: 예상대로 4개 파일(SKILL.md, session-start-memory.sh, stop-hook-throttle.sh, test_hooks.sh) 확인. `readlink ~/.claude/skills/memory-tick` → repo 경로 정상 해석. 심볼릭 링크 생성 직후 스킬 목록에 `memory-tick`이 자동 노출됨(discovery 정상 동작 확인).

- [x] **Step 3: memory 폴더 + 빈 인덱스 생성**

```bash
mkdir -p "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory/memory"
touch "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory/memory/MEMORY.md"
```

결과: 폴더 + 빈 `MEMORY.md`(0바이트) 생성 확인.

- [x] **Step 4: settings.json에 hooks 등록**

`~/.claude/settings.json`을 Read로 열어 기존 `hooks` 구조 확인 후, `SessionStart`와 `Stop` 배열에 아래 항목을 **append** (기존 항목 보존):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/max/00_Projects/95_personal-memory/skills/memory-tick/session-start-memory.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/Users/max/00_Projects/95_personal-memory/skills/memory-tick/stop-hook-throttle.sh"
          }
        ]
      }
    ]
  }
}
```

수정 후 JSON 유효성 확인:

```bash
python3 -c "import json; json.load(open('/Users/max/.claude/settings.json')); print('OK')"
```

Expected: `OK`

결과: `~/.claude/settings.json`은 기존에 `PostToolUse`만 있고 `SessionStart`/`Stop` 키는 없었음(브리핑의 "기존 SessionStart 항목 존재" 가정과 달랐음) — python3 스크립트로 `hooks.setdefault("SessionStart", [])`/`hooks.setdefault("Stop", [])` 후 append하는 방식으로 두 키를 새로 생성해 안전하게 추가. 쓰기 전 `~/.claude/settings.json.bak-task6`로 백업. `python3 -c "import json; json.load(...)"` → `OK`. `diff`로 백업과 대조해 기존 `PostToolUse` 블록 등 다른 내용은 전혀 변경되지 않고, `SessionStart`/`Stop` 두 키만 순수 추가됐음을 확인 (상세 diff는 task-6-report.md 참고).

- [x] **Step 5: hook 스모크 테스트 (수동 실행)**

```bash
echo '{}' | /Users/max/00_Projects/95_personal-memory/skills/memory-tick/stop-hook-throttle.sh
/Users/max/00_Projects/95_personal-memory/skills/memory-tick/session-start-memory.sh
```

Expected: 첫 커맨드는 block JSON 또는 무출력(30분 스로틀 상태에 따라), 둘째는 라벨+빈 인덱스 출력. 둘 다 exit 0.

결과: 기본 마커 경로(`~/.claude/memory-tick-last-check`)에 마커가 없는 상태(Task 4 테스트는 자체 tmpdir 마커만 사용해 기본 경로에 흔적을 남기지 않음)라 첫 실제 실행에서 block JSON 정상 출력, exit 0. 직후 재실행은 스로틀에 걸려 무출력 확인(정상 동작). `session-start-memory.sh`는 라벨 한 줄 출력, exit 0(MEMORY.md가 빈 파일이라 본문은 없음 — 예상대로). `skills/memory-tick/test_hooks.sh` 재실행해 `PASS: stop-hook-throttle`, `PASS: session-start-memory` 둘 다 확인 — 스모크 테스트가 기존 TDD 테스트에 영향 없음.

- [x] **Step 6: 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add skills/memory-tick/SKILL.md
git commit -m "feat: memory-tick SKILL.md + hooks 등록"
```

---

### Task 7: launchd 일일 sync

**Files:**
- Create: `launchd/com.max.secall-sync.plist` (repo 원본)
- Create: `~/Library/LaunchAgents/com.max.secall-sync.plist` (cp로 설치)

**Interfaces:**
- Consumes: Task 1의 `secall` CLI
- Produces: 매일 09:00 `secall sync` 자동 실행

- [x] **Step 1: plist 작성**

`launchd/com.max.secall-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.max.secall-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>secall sync</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/secall-sync.log</string>
  <key>StandardErrorPath</key><string>/tmp/secall-sync.err</string>
</dict>
</plist>
```

`/bin/zsh -lc` 사용 이유: 로그인 셸 PATH를 태워 secall 설치 경로에 의존하지 않기 위함.

결과: 위 스펙대로 작성했으나 kickstart 검증에서 두 가지 문제가 드러나 **최종 plist는 스펙과 다르다** (상세는 task-7-report.md). (1) `zsh -lc`는 비대화형 로그인 셸이라 `~/.zshrc`를 읽지 않아 `secall`이 PATH에 없음(`command not found`) → 절대경로로 교체. (2) launchd가 띄운 잡의 TCC 권한은 실행 바이너리(zsh)에 귀속되므로 iCloud vault 접근이 차단됨 → zsh 래퍼 제거, `secall sync` 직접 실행 + `EnvironmentVariables`로 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH`/`PATH`(git·codex용) 직접 지정. `plutil -lint` OK.

- [x] **Step 2: 설치 + 로드**

```bash
cp /Users/max/00_Projects/95_personal-memory/launchd/com.max.secall-sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.max.secall-sync.plist
```

Expected: 에러 없음. 이미 로드돼 있다는 에러면 `launchctl bootout gui/$(id -u)/com.max.secall-sync` 후 재시도.

결과: bootstrap 에러 없이 성공(stale job 없었음, 수정 재설치 시에는 bootout 후 재로드). `launchctl print gui/501/com.max.secall-sync`로 로드 상태 + `StartCalendarInterval Hour=9 Minute=0` calendarinterval 트리거 등록 확인.

- [x] **Step 3: 즉시 실행으로 동작 확인**

```bash
launchctl kickstart gui/$(id -u)/com.max.secall-sync
sleep 10 && tail -5 /tmp/secall-sync.log /tmp/secall-sync.err
```

Expected: sync 실행 로그, 에러 없음.

결과: kickstart 자체는 성공하나 **launchd 컨텍스트에서는 macOS TCC가 iCloud Drive(vault) 접근을 차단**해 sync가 vault opendir에서 무기한 블록됨(진짜 행 근본 원인 — 테스트 잡의 `ls`는 즉시 "Operation not permitted", secall은 CPU ~0으로 43분+ 행). 진단 과정에서 ollama_cloud 오설정도 발견·수정: `graph.semantic_backend=ollama_cloud` + `log.backend=ollama_cloud`인데 `OLLAMA_CLOUD_API_KEY` 미설정 → `graph.semantic_backend=disabled`(공식 off 값)로 변경, `log.backend` 키 제거(tokenizer/embedding/vault 설정은 미변경). **백업 정오**: 최초 config 백업은 백업 전에 실행한 config 프로빙(`__probe__` 값)으로 오염돼 롤백 지점으로 쓸 수 없었음 → 오염본은 `config.toml.bak-task7-corrupted`로 감사용 보존, `config.toml.bak-task7`은 Task 1 리뷰 기록의 원본 값(graph/log = ollama_cloud)을 근거로 만든 **재구성본**(파일 첫 줄 주석 명기; 알려진 값 vs 재구성 구분은 task-7-report.md 정오 절 참고). plist와 동일한 커맨드+env를 터미널 컨텍스트(TCC 허용)에서 실행한 시뮬레이션은 **~30초 만에 "Sync complete." exit 0** — kiwi 정상(lindera fallback 없음), 216 sessions/31,897 turns(claude-code 202/codex 5/gemini-cli 9, Task 2와 동일), `secall lint` 0 errors. **사용자 1회 조치 필요**: 시스템 설정 → 개인정보 보호 및 보안 → 전체 디스크 접근 권한에 `~/.local/bin/secall` 추가 후 `launchctl kickstart gui/501/com.max.secall-sync`로 최종 확인. **수용된 제약(FDA 등록 전)**: 등록 전 09:00 발화 시 잡이 vault opendir에서 블록되지만, launchd는 동일 Label 잡을 이중 기동하지 않으므로 영향은 유휴에 가까운 stuck 프로세스 1개에 그침(sqlite WAL이라 데이터 안전) — 복구는 `pkill -f "secall sync"`, 탐지 힌트는 09:00 이후 `/tmp/secall-sync.err`가 조용하면 아직 블록 상태, FDA 등록(근본 해결) 즉시 리스크 완전 소멸. timeout 셸 래퍼는 직접 실행으로 해결한 TCC 책임 프로세스 문제를 재발시키므로 의도적으로 미채택(macOS에 /usr/bin/timeout도 없음). 부수 발견: wiki codex 백엔드가 기본 모델 `gpt-5.4`로 호출돼 ChatGPT 계정에서 400 에러(비치명·즉시 실패, sync는 계속 진행) — 후속 조치 대상.

- [x] **Step 4: 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add launchd/
git commit -m "feat: launchd 일일 secall sync (09:00)"
```

결과: `launchd/` + 본 계획 문서 갱신 + task-7-report.md를 묶어 커밋 — 메시지는 행 수정을 반영해 "feat: launchd 일일 secall sync (09:00) — ollama_cloud 행 수정 포함".

---

### Task 8: 왕복 검증 + 마무리

**Files:**
- Create: `README.md` (repo 루트 — 시스템 개요·운영법 한 장)

**Interfaces:**
- Consumes: 앞선 모든 태스크

- [ ] **Step 1: 스펙 검증 항목 실행** (spec의 "검증 계획" 1~7)

```bash
# 6) 볼트 동거: 자작 memory/ 폴더가 seCall과 안 싸우는지
secall lint
# 7) 용량 재확인
du -sh "/Users/max/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/96_memory"
```

Expected: lint가 memory/ 폴더 때문에 실패하지 않음. 실패 시 memory/를 `…/Obsidian/95_memory`로 이동하고 두 스크립트와 SKILL.md의 경로 상수만 수정.

- [ ] **Step 2: memory-tick 왕복 테스트 (수동)**

새 Claude Code 세션을 열고:
1. "이거 기억해: 테스트용 메모리 항목이야" 라고 요청 → `96_memory/memory/`에 파일 생성 + MEMORY.md 갱신 확인
2. 세션 종료 후 또 새 세션 시작 → 시작 컨텍스트에 `[personal-memory]` 인덱스가 주입됐는지 확인
3. MCP 확인: 새 세션에서 secall recall 툴 호출이 되는지

- [ ] **Step 3: fail-open 확인**

```bash
chmod -x /Users/max/00_Projects/95_personal-memory/skills/memory-tick/stop-hook-throttle.sh
```

새 세션에서 짧은 대화 → 세션이 정상 진행되는지 확인 후 원복:

```bash
chmod +x /Users/max/00_Projects/95_personal-memory/skills/memory-tick/stop-hook-throttle.sh
```

- [ ] **Step 4: 위키 생성 1회 수동 실행 + 품질 확인**

```bash
secall wiki update --backend claude --session <아무 세션 id 하나>
```

Expected: `96_memory/wiki/`에 문서 생성. 품질 보고 전체 실행(`secall wiki update`) 여부는 사용자가 결정.

- [ ] **Step 5: README 작성**

`README.md`:

```markdown
# personal-memory

개인 AI 메모리 시스템. 스펙: docs/superpowers/specs/, 계획: docs/superpowers/plans/

## 구성

- **seCall** — Claude Code 세션 아카이브·검색·위키. 볼트: iCloud Obsidian vault `96_memory/`
- **memory-tick** (skills/memory-tick/) — Stop hook 30분 스로틀로 인사이트 자동 저장, SessionStart hook으로 인덱스 주입. `~/.claude/skills/memory-tick`은 여기로 symlink
- **launchd** — 매일 09:00 `secall sync` (launchd/com.max.secall-sync.plist)

## 자주 쓰는 명령

- 검색: `secall recall "키워드"` / 벡터 켜기: config에서 백엔드 ort로 + `secall reindex`
- 위키 갱신: `secall wiki update --backend claude`
- 정합성: `secall lint`, DB 복구: `secall reindex --from-vault`
- hook 테스트: `skills/memory-tick/test_hooks.sh`

## 주의

- seCall git sync 사용 금지 — 동기화는 iCloud가 담당
- memory 파일은 항상 전체 쓰기, append 금지 (iCloud 충돌 방지)
```

- [ ] **Step 6: 최종 커밋**

```bash
cd /Users/max/00_Projects/95_personal-memory
git add -A && git commit -m "docs: README + 검증 결과 기록"
```
