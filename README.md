# personal-memory

개인 AI 메모리 시스템. 스펙: `docs/superpowers/specs/`, 계획: `docs/superpowers/plans/`, 검증 기록: `.superpowers/sdd/task-8-report.md`

## 구성

- **seCall** (v0.7.0) — Claude Code 세션 아카이브·검색·위키. 볼트: **`/Users/max/99_memory`(로컬)**. 2026-07-30에 iCloud Obsidian 볼트(`96_memory/`)에서 이전했다 — `/tmp/secall-sync.err`에 `Resource deadlock avoided (os error 11)`가 **479건** 쌓여 있었고, 하나하나가 인덱스에서 조용히 누락된 세션이다. 이전의 대가로 **다기기 동기화를 포기**했다(맥 전용). 이전 볼트는 삭제하지 않고 `96_memory.migrated-20260730`으로 남겨뒀다
- **업무용 세션 수집** (`~/.claude-work`, `CLAUDE_CONFIG_DIR` 분리) — seCall이 자동으로 보게 하려면 `~/.claude/projects/_work--<프로젝트디렉토리명>` 심링크가 필요하다. `scripts/link_work_projects.sh`(매일 08:40 launchd)가 갱신하고 끊어진 링크도 정리한다. 상세 제약은 아래 「주의」 참고. **⚠️ 한시적 — 2026-08-11에 설정을 `~/.claude`로 통일하면 스크립트·plist·`_work--*` 링크를 전부 제거할 것**(제거 절차는 스크립트 헤더 주석). 현재 링크 확인: `command ls -l ~/.claude/projects | grep _work--`
- **memory-tick** (`skills/memory-tick/`) — Stop hook 30분 스로틀로 인사이트 자동 저장, SessionStart hook으로 인덱스 주입.
  - **스킬 배치 경로가 2단이다**: `~/.claude/skills`와 `~/.claude-work/skills`가 둘 다 `~/.agents/skills`로 symlink돼 있고, 그 안의 `memory-tick`이 이 레포로 symlink된다. 즉 레포 = 유일한 원본이고 개인용·업무용이 같은 실체를 본다.
  - ⚠️ **2026-07-30까지 이게 symlink가 아니라 07-09에 멈춘 복사본이었다.** 그래서 레포의 스킬 개선(`근거 표기` 섹션 등)이 실제 세션에는 한 번도 반영되지 않았고, 볼트 이전 때 구 경로가 남아 다음 세션이 마이그레이션된 폴더에 쓸 위험이 있었다. 옛 복사본은 `~/.agents/archive/skills-memory-tick-20260730`에 보관. **교훈 — 훅 커맨드가 레포 절대경로를 가리키는 것과 스킬 본문(SKILL.md)이 레포를 가리키는 것은 별개다.** 훅이 정상 동작하는 것만 보고 스킬 본문도 최신이라고 가정하면 안 된다. 검증: `readlink -f ~/.claude/skills/memory-tick/SKILL.md`
- **MCP 레이어** (`scripts/`) — 훅이 없는 CLI(agy·codex 등)를 메모리에 붙이는 CLI 독립 배선. 셋 다 표준 라이브러리만 쓰고 `--selftest`가 내장돼 있다.
  - `memory_mcp.py` — 볼트 읽기/쓰기 MCP 서버. `memory_get()`(인자 없으면 인덱스, 이름 주면 노트 전문) + `memory_save(kind, slug, description, body, tags)`. 쓰기는 memory-tick 포맷을 고정하고 `scrub/scrub_secrets.py`의 패턴을 **import해서** 쓰기 직전에 마스킹한다(import 실패 시 서버가 안 뜬다 — 평문으로 쓰는 것보다 시끄럽게 죽는 게 낫다). **읽기 툴이 필요한 이유**: secall이 인덱싱하는 건 `raw/.sessions/`뿐이고 `memory/*.md`는 대상이 아니다. 저장 트리거는 훅이 없으니 `~/.claude/CLAUDE.md`(=`~/.gemini/GEMINI.md` 심링크)의 「개인 메모리」 절이 담당한다
  - `mcp_shim.py` — agy가 `initialize` 전에 보내는 비표준 `server/discover`를 가로채 `-32601`로 답하는 stdio 프록시. 엄격한 서버(secall이 쓰는 rmcp)는 이 요청에 연결을 끊는다. **직접 만드는 MCP 서버는 모르는 메서드에 에러만 돌려주고 연결은 유지하도록 짜면** 이 방언에 무료로 면역이 된다
  - `mcp_http_bridge.py` — stdio만 받는 클라이언트(Claude 데스크톱 앱)를 공유 HTTP 서버에 붙이는 브릿지. 모델을 로드하지 않아 RSS 6MB
- **launchd** — 아래 「적용 중인 launchd 잡」 참고
- **시크릿 마스킹** (`scrub/`) — 3중 방어: ① PreToolUse 훅 `block_env_dump.py`가 `.env` 값 덤프를 세션에서 차단 (`~/.claude/settings.json` 등록) ② `scrub_secrets.py`가 매일 08:45(sync 15분 전) 로컬 세션 JSONL에서 시크릿 패턴·`<private>` 스팬을 마스킹 — 로컬 파일만 만지므로 FDA 불필요. 스캔 루트는 `DEFAULT_ROOTS` 2개(`~/.claude/projects` + `~/.claude-work/projects`)로, 업무용이 빠지면 `GITLAB_TOKEN` 류가 마스킹 없이 볼트로 올라간다(2026-07-30 실측: 업무용 34파일 중 4파일에 시크릿 14건). `_work--` 심링크 때문에 같은 inode를 두 번 스캔하지만 마스킹은 멱등이라 무해하며, 심링크가 사라져도 커버리지가 유지되도록 두 루트를 일부러 남겨둔다 ③ memory-tick 스킬에 시크릿 저장 금지 규칙. 수동 점검: `python3 scrub/scrub_secrets.py --report`, vault 백필: `--paths <vault>/raw <vault>` (값 미출력, 룰명×개수만 로그). 셀프테스트: `python3 scrub/test_scrub.py`

## 적용 중인 launchd 잡

레포 `launchd/*.plist`가 원본이고, `~/Library/LaunchAgents/`로 **복사**해서 쓴다(심링크 아님). 2026-08-03 기준 5개 + 상주 1개가 로드돼 있고 레포 원본과 내용이 일치한다(전수 점검: 모든 잡 마지막 종료 코드 0, `job-monitor`도 `0 failing`).

| 시각 | Label | 실행 | 로그 |
|---|---|---|---|
| 매일 08:40 | `com.max.claude-work-links` | `/bin/sh scripts/link_work_projects.sh` | `/tmp/claude-work-links.{log,err}` |
| 매일 08:45 | `com.max.secall-scrub` | `/usr/bin/python3 scrub/scrub_secrets.py` | `/tmp/secall-scrub.{log,err}` |
| 매일 09:00 | `com.max.secall-sync` | `secall sync --no-embed --no-wiki` | `/tmp/secall-sync.{log,err}` |
| 매주 화 13:00 | `com.max.secall-wiki` | `secall wiki update --backend claude --no-pull` (+`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`) | `/tmp/secall-wiki.{log,err}` |
| 매일 09:30·13:30 | `com.max.job-monitor` | `/usr/bin/python3 scripts/check_job_failures.py` | `/tmp/job-monitor.{out,err,log}` |
| 상주 | `com.max.secall-mcp` | `secall mcp --http 127.0.0.1:8971` | `/tmp/secall-mcp.{log,err}` |
| ~~매주 월 09:10~~ | ~~`com.max.secall-reindex`~~ | **비활성 (2026-07-30)** — 임베딩을 매주 지웠다 | — |

**`com.max.secall-mcp`는 공유 MCP 서버다.** stdio로 `secall mcp`를 띄우면 클라이언트마다 프로세스가 하나씩 생기고 각각 bge-m3 ONNX를 2.1GB씩 로드한다 — 2026-07-30에 6개(Claude Code CLI 3 + 데스크톱 앱 2 + agy 1)가 동시에 떠서 스왑이 28.6GB 중 27.2GB까지 차고 agy의 MCP 연결이 5분 8초 걸렸다. 이 잡 하나로 모델 로드를 1회로 줄이고 각 클라이언트는 HTTP로 붙인다(`RunAtLoad`+`KeepAlive`, 10초 내 listen).

| 클라이언트 | 등록 방법 |
|---|---|
| Claude Code | `claude mcp add --scope user --transport http secall http://127.0.0.1:8971/mcp` |
| agy | `~/.gemini/config/mcp_config.json`에 `{"serverUrl": "http://127.0.0.1:8971/mcp"}` |
| Claude 데스크톱 앱 | `claude_desktop_config.json`은 **stdio만** 유효한 설정으로 인정하므로(`{"type":"http",...}`은 "not valid MCP server configurations"로 건너뜀) `scripts/mcp_http_bridge.py`를 `command`로 끼운다 — 모델을 안 물어서 브릿지 RSS는 6MB |

**`com.max.secall-reindex`를 끈 이유**: `reindex --from-vault`는 전 세션을 재수집하고 재수집 경로엔 `DELETE FROM turn_vectors WHERE session_id = ?1`이 있다. 벡터는 볼트에 없고 DB에만 있는 파생물이라 "볼트에서 재구축"이 곧 벡터 파괴다(실측: 38,300턴 중 32개만 생존 — 10시간짜리 embed 결과가 사라졌다). 게다가 이 잡의 존재 이유였던 iCloud fileprovider 드리프트는 볼트를 로컬로 옮기며 사라졌다. plist는 `~/Library/LaunchAgents/archive/`에 보관. 드리프트가 의심되면 수동 실행하고 **직후 `secall embed`를 반드시 이어 붙일 것**.

**`com.max.secall-wiki`의 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`**: 위키 에이전트는 무거운 페이지를 서브에이전트에 위임하는데, `claude -p`가 기본 600초에서 `Background tasks still running after 600s; terminating.`을 찍고 결과를 못 받은 채 끝난다. 그런데도 secall은 `✓ Wiki update complete.` + **exit 0**이라 종료 코드로는 절대 안 보인다. 이 env로 절단을 해제하면 완주한다(07-31 실측: 10분 절단 → 16분 완주, `ags-watchtower.md` 17KB→42KB).
- ⚠️ **정기 실행으로는 아직 검증되지 않았다 (2026-08-03 기준).** `/tmp/secall-wiki.err`의 마지막 실행 블록(07-31 13:18)엔 여전히 600초 절단이 찍혀 있다 — plist 수정 시각이 13:50이라 그 실행보다 나중이기 때문. **다음 화요일 13:00 로그로 확인할 것.** 산출물은 07-31자로 10개가 갱신돼 있어 `WIKI_STALE_DAYS=8` 감시엔 안 걸린다(= mtime 감시만 믿으면 이 미검증 상태는 못 본다).

**아침 3연쇄의 순서에 의미가 있다** — 08:40 링크 갱신(새 업무 프로젝트를 그날 수집에 포함) → 08:45 스크럽(시크릿 마스킹) → 09:00 sync(볼트/iCloud에 반영). 앞의 둘이 sync보다 뒤로 가면 평문이 볼트로 새거나 새 업무 세션이 하루 늦게 들어온다.

**`secall sync`의 플래그 두 개는 둘 다 필수다** (`--no-embed --no-wiki`). 빼면 조용히 다른 일을 시작한다:
- `--no-embed` (2026-07-31) — ingest 단계 임베딩이 이 맥(RAM 16GB)에서 스래싱한다. 07-30 실행은 11세션 중 3개만 하고 9시간 뒤 SIGTERM으로 죽었다. 게다가 재수집 경로가 `DELETE FROM turn_vectors WHERE session_id=?`를 타서 있던 벡터를 깎는다(실측 4089→3901). 붙이면 40초에 exit 0.
- `--no-wiki` (2026-08-03) — 없으면 **새로 들어온 세션 하나하나마다** `wiki update --session <id>`로 claude를 부른다. 하루 30세션이면 30번이고, 09:00은 구독 쿼터 경쟁 시간대다. 위키는 주간 잡이 전체 모드로 한 번에 하는 게 맞다 — 세션 단위 증분은 맥락이 세션 하나로 좁아 페이지 품질도 떨어진다.
  - 이전엔 config `wiki.default_backend = "disabled"`가 이 역할을 대신하고 있었는데, **`disabled`는 wiki의 허용값이 아니라서**(`claude|codex|haiku|ollama|ollama_cloud|lmstudio`) 파싱 실패로 "우연히" 꺼져 있던 것이다. 대가로 세션마다 `⚠ wiki failed for <id>: Unknown backend 'disabled'` 경고가 쌓였다(`/tmp/secall-sync.err`에 33건). 지금은 플래그로 정식으로 끄고 config는 `claude`로 되돌렸다.
  - ⚠️ **그래서 이제 수동으로 `secall sync`를 돌릴 때도 `--no-wiki`를 챙겨야 한다** — config가 유효값이 된 만큼 플래그가 없으면 실제로 호출된다. `default_backend` 줄을 지우는 건 답이 아니다(폴백이 `codex`).

**실행 방식이 두 부류로 갈린다:**
- **볼트를 만지는 잡**(sync·wiki)은 `~/.local/bin/secall`을 **직접 exec**해야 한다. launchd 잡의 TCC 권한은 실행 바이너리에 귀속되므로 `/bin/zsh -c` 래퍼를 쓰면 zsh에 전체 디스크 접근(FDA)을 줘야 한다. `~/.local/bin/secall`에 FDA 1회 등록으로 해결돼 있다. `~/.zshenv`를 안 거치므로 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH`/`ORT_DYLIB_PATH`를 plist의 `EnvironmentVariables`에 직접 넣는다 — 특히 `ORT_DYLIB_PATH`가 없으면 `embedding.backend=ort` 상태에서 sync가 패닉으로 죽는다.
- **로컬 파일만 만지는 잡**(scrub·claude-work-links)은 FDA가 필요 없어 `/usr/bin/python3`·`/bin/sh` 래퍼를 써도 된다.

**상태 확인**: `launchctl list | grep com.max` — 두 번째 컬럼이 마지막 종료 코드다(`0`이 정상, `-9`는 SIGKILL). 1회 강제 실행은 `launchctl kickstart -k gui/$(id -u)/<Label>`. plist를 고친 뒤엔 `~/Library/LaunchAgents/`로 다시 복사하고 `launchctl bootout` → `bootstrap` 해야 반영된다.

**실패 알림**: `com.max.job-monitor`(09:30·13:30 + 로드 시)가 `launchctl list`의 마지막 종료 코드를 읽어 0이 아니면 macOS 배너를 띄운다. 상세는 `/tmp/job-monitor.log`(실패 사유 + 해당 잡 `.err` 꼬리 300자), 현황만 보려면 `python3 scripts/check_job_failures.py --report`.
- **각 잡을 `sh -c 'cmd || osascript ...'`로 감싸지 않았다.** 잘 돌고 있는 잡을 전부 고쳐야 하고, TCC 권한이 실행 바이너리에 귀속되므로 래퍼를 끼우면 권한 주체가 `secall`에서 `/bin/sh`로 바뀐다. 바깥에서 종료 코드만 읽으면 기존 잡을 안 건드리고 앞으로 추가되는 `com.max.*` 잡도 자동으로 커버된다. 대가는 즉시성(최대 다음 점검까지 지연).
- **같은 실패를 반복 알리지 않는다** — 상태가 바뀔 때만 띄운다(`~/.claude/job_monitor_state.json`). 매일 같은 배너가 뜨면 결국 무시하게 되고, 그게 원래 문제였던 "아무도 안 읽는 로그"의 재발이다. 복구되면 복구 알림이 한 번 뜬다.
- ⚠️ **`gui/$(id -u)`로 bootstrap해야 한다** — `osascript` 알림은 GUI 세션에 붙어야 배너가 뜬다. `system/`으로 올리면 조용히 아무 것도 안 보인다.

## 자주 쓰는 명령

- 검색: `secall recall "키워드"` (토크나이저 kiwi, 임베딩 없음 — BM25만)
- 벡터 검색 켜기: config에서 `embedding.backend`를 `ort`로 바꾸고 **`secall embed --concurrency 1 --batch-size 8`** (`reindex`가 아니다 — 그건 벡터를 지운다). 10시간짜리 작업이라 데몬으로 띄울 것. 진행: `sqlite3 ~/Library/Caches/secall/index.sqlite "SELECT COUNT(*) FROM turn_vectors;"`
- 위키 갱신: `secall wiki update --backend claude --session <id>`. config 기본값(`wiki.default_backend`)이 2026-08-03부터 `claude`라 `--backend`는 이제 선택이지만, 명시하는 습관은 유지할 것(설정이 바뀌어도 의도가 커맨드에 남는다). 세션 전체 일괄 갱신(`secall wiki update`, `--session` 없이)은 18분+/sonnet 토큰이 드므로 품질 확인 후 수동 판단
- 정합성: `secall lint` (memory/ 서브폴더와 공존 확인됨, 0 errors)
- DB 복구: `secall reindex --from-vault` (볼트=원본, DB=로컬 파생 캐시) — ⚠️ 임베딩은 볼트에 없어서 같이 지워진다. 실행했으면 직후 `secall embed` 필수
- hook 셀프테스트: `skills/memory-tick/test_hooks.sh`
- kiwi 토크나이저 env: `~/.zshenv`에 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 영속화됨 (config.toml엔 해당 키 없음). MCP 서버는 `claude mcp add`가 zshenv를 거치지 않으므로 등록 시 `--env`로 동일하게 전달했음 — 이미 완료, 재등록 시에만 신경 쓰면 됨
- MCP 상태 확인: `claude mcp list` → `secall: http://127.0.0.1:8971/mcp (HTTP) - ✔ Connected`. 2026-07-30에 stdio에서 공유 HTTP 서버로 옮겼다(모델 중복 로드 제거) — 안 붙으면 `launchctl list | grep secall-mcp`부터. stdio로 등록할 때의 교훈은 그대로 유효하다: bare 커맨드명 대신 절대경로 + env는 `--env`로 명시

## 업데이트

- secall엔 내장 update 커맨드 없음 — install.sh 재실행이 곧 업데이트
  ```bash
  secall config show > /tmp/secall-config-backup.toml   # 1. 설정 백업
  curl -fsSL https://raw.githubusercontent.com/hang-in/seCall/main/install.sh | sh  # 2. 재설치
  secall lint && secall status                            # 3. 검증
  ```
- 자동 업데이트는 하지 않기로 함 — 바이너리 교체 리스크 때문에 수동 실행만

## 주의

- seCall git sync 사용 금지 — 동기화는 iCloud가 담당 (둘 다 켜면 충돌)
- memory 파일은 항상 전체 쓰기, append 금지 (iCloud 충돌 방지)
- **launchd FDA 필요**: `~/.local/bin/secall`에 macOS 전체 디스크 접근 권한(시스템 설정 > 개인정보 보호 및 보안)을 등록하기 전까지, launchd가 새벽 09:00에 띄우는 `secall sync`는 iCloud(TCC) 접근에서 행(hang)한다. 증상: `/tmp/secall-sync.err`가 "Reindexing vault..." 이후 조용함. 복구: `pkill -f "secall sync"` 한 번. FDA 등록 후에는 재발하지 않음 (자세한 내용: `.superpowers/sdd/task-7-report.md`)
- **`disabled`가 유효한 섹션과 아닌 섹션이 갈린다 (2026-08-03, `--help` 전수 대조)** — 이걸 모르면 "설정으로 껐다"고 믿은 게 실은 파싱 실패인 상황이 생긴다.

  | config 키 | 허용값 | `disabled` | 현재 값 |
  |---|---|---|---|
  | `wiki.default_backend` | `claude\|codex\|haiku\|ollama\|ollama_cloud\|lmstudio` | ❌ 에러 | `claude` |
  | `log.backend` | `claude\|codex\|haiku\|ollama\|lmstudio` | ❌ (미확인 — log 잡이 없어 실제 호출 관측 못 함) | `disabled` |
  | `graph.semantic_backend` | `ollama\|ollama_cloud\|anthropic\|lmstudio\|disabled` | ✅ 정식값 | `disabled` |
  | `embedding.backend` | `ollama\|ort\|openai\|openvino\|none` | ❌ (여긴 `none`이 정답) | `none` |

  `[graph] semantic_backend = "disabled"`는 정상 설정이다 — 구조적 엣지는 LLM 없이도 계속 추출된다(sync 로그의 `✓ graph: N nodes / M edges added`). 시맨틱 엣지만 스킵되므로, 아쉬우면 `secall graph semantic --limit N`으로 가끔 수동으로 채우면 된다. 켜려면 로컬 ollama(`gemma4:e4b`)나 `anthropic`(haiku, `ANTHROPIC_API_KEY` 필요 — 지금은 구독만 쓰므로 미설정)인데, 임베딩까지 끈 16GB 램에서 상시 LLM은 무리라 껐다.
- **`secall log`는 안 쓴다** — `secall log [YYYY-MM-DD]`는 그날 세션들을 LLM에 넣어 **일일 작업일기**를 산문으로 생성하는 기능이다. wiki/recall과 기능이 겹치고 매일 토큰을 태울 가치가 없다고 판단해 자동화하지 않았다(launchd 잡 없음). `log.backend = "disabled"`는 허용값이 아닐 가능성이 높지만 자동 호출 경로가 없어 무해하다 — 언젠가 손으로 쓸 일이 생기면 `--backend claude`를 주면 된다.
  - ⚠️ **볼트 최상위 `log.md`와 헷갈리지 말 것.** 그건 이 기능의 산출물이 아니라 seCall이 ingest할 때마다 자동으로 쌓는 수집 기록(`type: log`, "seCall Ingest Log", 세션 ID·turns·tokens·파일경로)이고 LLM을 쓰지 않는다. `secall log` 산출물이 어디로 떨어지는지는 **미확인**(한 번도 실행한 적 없어 흔적이 없다).
- 토크나이저는 kiwi로 설정되어 있으나 기존 216세션 인덱스는 upstream 버그로 인한 재구축 리스크(git_branch 유실) 때문에 lindera 톤화 상태로 남아있음 — 신규 질의는 kiwi, 기존 인덱스는 lindera 혼용. 기능엔 지장 없음 (자세한 내용: `.superpowers/sdd/task-2-report.md`)
- **업무용(`~/.claude-work`) 세션 수집 — 경로 제약 3종 (2026-07-30 실측)**: 업무용 config dir 세션은 그냥은 절대 수집되지 않는다. 원인이 셋이고 전부 seCall 바이너리에 하드코딩돼 있어 config.toml로는 못 바꾼다.
  1. **포맷 감지가 경로 문자열 기반이다.** 동일 파일을 `~/.claude-work/projects/…`에 두면 `unknown session format`으로 실패하고, `~/.claude/projects/…`로 복사하면 정상 ingest된다(내용은 무관). 감지 앵커는 `/.claude/projects/`, `/.codex/sessions/`, `/.gemini/`.
  2. **`--auto` 스캔 깊이는 `projects/<프로젝트디렉토리>/*.jsonl` 딱 한 단계다.** 그래서 `projects/_work/<프로젝트디렉토리>/x.jsonl`처럼 한 단계 깊으면 못 본다. 부수적으로 발견된 사실 — `projects/<projdir>/<uuid>/subagents/*.jsonl`(개인용 256개)도 같은 이유로 **한 번도 인덱스된 적 없다**. 서브에이전트 트랜스크립트는 사실상 수집 대상 밖(파생 노이즈라 의도적 방치로 두는 중).
  3. **심링크는 depth 1에서만 따라간다.** `projects/_work → ~/.claude-work/projects` 같은 상위 심링크는 `--auto`가 무시하지만, `projects/_work--<projdir> → ~/.claude-work/projects/<projdir>`처럼 **프로젝트 디렉토리 자체를 depth 1 형제로** 걸면 정상 수집된다. 디렉토리명은 겉치레일 뿐 — seCall은 프로젝트명을 jsonl 안의 `cwd`에서 뽑는다.

  채택한 형태: `~/.claude-work/projects`는 실체로 그대로 두고(`projects/`는 심링크 금지 대상), `~/.claude/projects/_work--<projdir>` 심링크만 건다. 링크 갱신은 `scripts/link_work_projects.sh`(매일 08:40, `com.max.claude-work-links`)가 맡는다 — 새 업무 프로젝트 디렉토리를 링크하고 사라진 것의 끊어진 링크를 지운다. **대안으로 검토했다 기각한 것 둘**: ① 별도 `secall ingest <dir>` launchd 잡 — `ingest`는 **새로 넣은 게 0이면 에러가 없어도 항상 exit 1**이라 조용한 날마다 실패로 보여 진짜 실패를 가린다 ② 레이아웃 스왑(`~/.claude-work/projects` 실체를 `~/.claude/projects/_work`로 옮기고 심링크 역방향) — 위 ②번 깊이 제약에 걸려 **작동하지 않는다**(실제로 해보고 되돌림).

  스크립트 자체의 함정 하나: `"$linked개"`처럼 변수 바로 뒤에 한글이 붙으면 bash가 멀티바이트를 변수명의 일부로 먹어 `unbound variable`이 난다 — `${linked}개`로 중괄호를 쓸 것. `set -u`가 없었으면 빈 문자열로 조용히 넘어갔다.
- **임베딩은 메모리 제약이 병목이다 (2026-07-30 실측)**: 이 맥은 RAM 16GB인데 bge-m3 ONNX 모델이 **2.1GB**다. Slack·Notion·Podman VM·Hermes·Claude Code가 올라간 상태에서 임베딩을 돌리면 스왑이 포화되고(실측: 33.8GB 중 **32.9GB 사용**, pageouts 319,606) 프로세스가 `U`(중단 불가 I/O 대기) 상태로 CPU 12%만 쓰며 사실상 멈춘다. **5턴짜리 세션이 4분 넘게 진행되지 않는 것**을 관측했다 — 정체가 아니라 `model.onnx_data` mmap 페이지인이 스왑을 때리는 것이다.
  - **iCloud와 무관하다.** 임베딩 쓰기 경로는 `~/Library/Caches/secall/index.sqlite`(로컬)라 볼트 이전으로 해결되지 않는다. 볼트 이전이 고친 것은 sync/lint/reindex의 vault **읽기** 지연이다(lint 2분 타임아웃 → 0초).
  - **secall 프로세스를 둘 이상 동시에 돌리지 말 것** — 각각 모델을 따로 로드해 2.1GB씩 먹는다. `secall sync`(ingest 단계에서 임베딩함)와 `secall embed`를 겹쳐 돌리면 확실히 스래싱한다.
  - 운영 방침: 임베딩은 **맥이 유휴일 때 단독으로** `secall embed --concurrency 1`. 급하지 않으면 BM25만으로도 검색은 동작하니 미뤄도 된다(벡터 없는 세션은 `secall recall`에서 키워드 매칭으로만 잡힘).
  - **미해결**: `ort 2.0.0-rc.10`이 ONNX Runtime `1.22.x`를 기대하는데 brew에 설치된 건 `1.28.0`이다(경고만 뜨고 동작은 함). 성능/정확도 영향은 미확인 — 임베딩을 본격적으로 돌리기 전에 1.22 계열로 핀 고정을 검토할 것.
- **자격증명 노출 주의**: `raw/.sessions/`(불변 원본 아카이브, iCloud 동기화 대상)에는 과거 세션에서 `.env`를 grep/cat한 내용이 그대로 보존된다. 평문 크리덴셜 9종이 담긴 세션 13개를 2026-07-08에 볼트+DB+graph에서 삭제, 원본 JSONL은 `~/.claude/secrets-quarantine/`(로컬 전용)로 격리함. 앞으로도 세션에서 시크릿을 열면 아카이브에 평문으로 남으므로, 노출된 키는 로테이션하고 raw 파일을 외부 공유·별도 백업할 때는 점검 필요. 재점검 스캔은 값 출력 없이 변수명·개수만 보는 방식으로 (자세한 내용: `.superpowers/sdd/task-8-report.md`)
- **검색 인덱스 드리프트**: iCloud 볼트에 대한 `secall sync`는 fileprovider 쓰기 충돌("Resource deadlock avoided")로 매 실행마다 검색 인덱스에서 세션을 몇 개씩 누락시킬 수 있었다. **볼트를 로컬로 옮긴 뒤 이 원인은 사라졌고, 그래서 주간 자동 복구 잡(`com.max.secall-reindex`)도 2026-07-30에 껐다** — 그 잡이 임베딩을 매주 지우고 있었기 때문(위 「적용 중인 launchd 잡」 참고). 필요하면 수동 복구: `secall reindex --from-vault` **+ 직후 `secall embed`**. 인덱스가 틀어졌는지 확인: `secall lint`(세션 수·FTS row 불일치 보고)
- **DB에만 있고 볼트엔 없는 것**: 임베딩(`turn_vectors`)과 지식그래프는 볼트 md에서 복원되지 않는 파생물이다. "DB는 파생 캐시라 재구축이 안전하다"는 명제는 여기까지 오면 깨진다 — 재구축 명령을 자동화에 걸기 전에 **원본에 없는 게 뭔지** 먼저 확인할 것.
- **wiki update도 같은 iCloud 쓰기 충돌에 노출**: `secall wiki update --backend claude`가 짧은 시간에 sync/reindex 등 다른 iCloud 쓰기 작업과 겹치면 내부 Sonnet 서브프로세스가 `EDEADLK` 류 에러를 만날 수 있다. 이 에이전트는 Bash/ps 툴이 없어서 원인을 진단할 방법이 없는데도, 로그에 "다른 프로세스(PID·시각까지)가 동시에 쓰고 있다"처럼 구체적이지만 근거 없는 이야기를 남기고 넘어갈 수 있음(2026-07-09 실측, 확인 결과 그런 경쟁 프로세스는 실제로 없었음 — 환각). 파일 손상 없이 그냥 아무 것도 안 쓰고 종료되는 형태였음. 평상시 금요일 단독 실행(다른 iCloud 작업과 안 겹침)에서는 재현 가능성 낮음 — 로그에 이런 텍스트가 보이면 `secall lint` + 위키 파일 최신순으로 실제 변경 여부만 확인하면 됨, 재실행하면 보통 해결
- **reindex는 내용 변경을 못 본다**: `secall reindex --from-vault`의 skip은 세션 존재 기준이라, 이미 인덱스된 세션의 볼트 md를 고쳐도(스크럽 등) 인덱스는 옛 내용을 유지한다. 갱신하려면 해당 세션 row를 DB(`~/Library/Caches/secall/index.sqlite`)의 turns_fts/turns/sessions에서 지우고 `secall reindex --from-vault` — 단, 이 재인덱스는 세션을 **turns 0개로** 만들므로 반드시 `secall reindex --from-vault --repair-missing-turns`까지 실행해야 완복구된다 (2026-07-15 vault 백필 때 실측). favorite/notes 있는 세션은 지우면 유실되니 삭제 전 확인. FTS 검증은 LIKE 말고 `MATCH`로 (FTS5 가상 테이블에서 LIKE가 오답 냄).
- **스크럽의 알려진 천장**: ① 08:45 시점에 30분 내 수정된(진행 중) 세션은 그날 sync에 평문으로 들어갈 수 있음 — 로컬은 다음 날 마스킹되지만 vault 사본은 남으므로, 의심되면 `scrub_secrets.py --report --paths <vault>`로 확인 후 수동 처리. ② 이미 iCloud에 올라간 평문은 Apple 서버에 버전이 남았을 수 있음 — 노출 키는 마스킹과 무관하게 로테이션.
- **daily sync의 wiki 백엔드 자동호출 함정 (2026-08-03 해결)**: 매일 09:00 `secall sync`는 `wiki.default_backend`가 유효한 백엔드면 **새 세션마다** LLM을 호출한다. 이 위험을 오랫동안 "config에 `disabled`를 박아서" 막고 있다고 믿었으나, 실제로는 그 값이 허용값이 아니라 파싱이 실패해 우연히 안 돌던 것이었다(`/tmp/secall-sync.err`에 `Unknown backend 'disabled'` 33건). 지금은 plist에 `--no-wiki`를 명시해 정식으로 끄고 config는 `claude`로 되돌렸다 — kickstart 실측으로 12세션 ingest / 경고 0건 / exit 0 확인.
  - **교훈: "설정으로 껐다"와 "설정이 깨져서 안 돈다"는 겉보기 증상이 같다.** 이 레포에서만 세 번째 사례다(`wiki.default_backend = codex` 모델 에러, `log.backend = ollama_cloud` API 키 부재, 그리고 이번 `disabled`). 로그인을 고치거나 키를 넣는 순간 매일 토큰이 나가기 시작한다. **끄는 의도는 config 값이 아니라 커맨드 플래그로 표현할 것** — 플래그는 허용값 검증을 받고 `--help`에 남는다.
