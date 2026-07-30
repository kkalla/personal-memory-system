# personal-memory

개인 AI 메모리 시스템. 스펙: `docs/superpowers/specs/`, 계획: `docs/superpowers/plans/`, 검증 기록: `.superpowers/sdd/task-8-report.md`

## 구성

- **seCall** (v0.7.0) — Claude Code 세션 아카이브·검색·위키. 볼트: **`/Users/max/99_memory`(로컬)**. 2026-07-30에 iCloud Obsidian 볼트(`96_memory/`)에서 이전했다 — `/tmp/secall-sync.err`에 `Resource deadlock avoided (os error 11)`가 **479건** 쌓여 있었고, 하나하나가 인덱스에서 조용히 누락된 세션이다. 이전의 대가로 **다기기 동기화를 포기**했다(맥 전용). 이전 볼트는 삭제하지 않고 `96_memory.migrated-20260730`으로 남겨뒀다
- **업무용 세션 수집** (`~/.claude-work`, `CLAUDE_CONFIG_DIR` 분리) — seCall이 자동으로 보게 하려면 `~/.claude/projects/_work--<프로젝트디렉토리명>` 심링크가 필요하다. `scripts/link_work_projects.sh`(매일 08:40 launchd)가 갱신하고 끊어진 링크도 정리한다. 상세 제약은 아래 「주의」 참고. **⚠️ 한시적 — 2026-08-11에 설정을 `~/.claude`로 통일하면 스크립트·plist·`_work--*` 링크를 전부 제거할 것**(제거 절차는 스크립트 헤더 주석). 현재 링크 확인: `command ls -l ~/.claude/projects | grep _work--`
- **memory-tick** (`skills/memory-tick/`) — Stop hook 30분 스로틀로 인사이트 자동 저장, SessionStart hook으로 인덱스 주입. `~/.claude/skills/memory-tick`은 여기로 symlink
- **launchd** — 아래 「적용 중인 launchd 잡」 참고
- **시크릿 마스킹** (`scrub/`) — 3중 방어: ① PreToolUse 훅 `block_env_dump.py`가 `.env` 값 덤프를 세션에서 차단 (`~/.claude/settings.json` 등록) ② `scrub_secrets.py`가 매일 08:45(sync 15분 전) 로컬 세션 JSONL에서 시크릿 패턴·`<private>` 스팬을 마스킹 — 로컬 파일만 만지므로 FDA 불필요. 스캔 루트는 `DEFAULT_ROOTS` 2개(`~/.claude/projects` + `~/.claude-work/projects`)로, 업무용이 빠지면 `GITLAB_TOKEN` 류가 마스킹 없이 볼트로 올라간다(2026-07-30 실측: 업무용 34파일 중 4파일에 시크릿 14건). `_work--` 심링크 때문에 같은 inode를 두 번 스캔하지만 마스킹은 멱등이라 무해하며, 심링크가 사라져도 커버리지가 유지되도록 두 루트를 일부러 남겨둔다 ③ memory-tick 스킬에 시크릿 저장 금지 규칙. 수동 점검: `python3 scrub/scrub_secrets.py --report`, vault 백필: `--paths <vault>/raw <vault>` (값 미출력, 룰명×개수만 로그). 셀프테스트: `python3 scrub/test_scrub.py`

## 적용 중인 launchd 잡

레포 `launchd/*.plist`가 원본이고, `~/Library/LaunchAgents/`로 **복사**해서 쓴다(심링크 아님). 2026-07-30 기준 5개 전부 로드돼 있고 레포 원본과 내용이 일치한다.

| 시각 | Label | 실행 | 로그 |
|---|---|---|---|
| 매일 08:40 | `com.max.claude-work-links` | `/bin/sh scripts/link_work_projects.sh` | `/tmp/claude-work-links.{log,err}` |
| 매일 08:45 | `com.max.secall-scrub` | `/usr/bin/python3 scrub/scrub_secrets.py` | `/tmp/secall-scrub.{log,err}` |
| 매일 09:00 | `com.max.secall-sync` | `secall sync` | `/tmp/secall-sync.{log,err}` |
| 매주 월 09:10 | `com.max.secall-reindex` | `secall reindex --from-vault` | `/tmp/secall-reindex.{log,err}` |
| 매주 화 13:00 | `com.max.secall-wiki` | `secall wiki update --backend claude --no-pull` | `/tmp/secall-wiki.{log,err}` |

**아침 3연쇄의 순서에 의미가 있다** — 08:40 링크 갱신(새 업무 프로젝트를 그날 수집에 포함) → 08:45 스크럽(시크릿 마스킹) → 09:00 sync(볼트/iCloud에 반영). 앞의 둘이 sync보다 뒤로 가면 평문이 볼트로 새거나 새 업무 세션이 하루 늦게 들어온다.

**실행 방식이 두 부류로 갈린다:**
- **iCloud를 만지는 잡**(sync·reindex·wiki)은 `~/.local/bin/secall`을 **직접 exec**해야 한다. launchd 잡의 TCC 권한은 실행 바이너리에 귀속되므로 `/bin/zsh -c` 래퍼를 쓰면 zsh에 전체 디스크 접근(FDA)을 줘야 한다. `~/.local/bin/secall`에 FDA 1회 등록으로 해결돼 있다. `~/.zshenv`를 안 거치므로 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH`/`ORT_DYLIB_PATH`를 plist의 `EnvironmentVariables`에 직접 넣는다 — 특히 `ORT_DYLIB_PATH`가 없으면 `embedding.backend=ort` 상태에서 sync가 패닉으로 죽는다.
- **로컬 파일만 만지는 잡**(scrub·claude-work-links)은 FDA가 필요 없어 `/usr/bin/python3`·`/bin/sh` 래퍼를 써도 된다.

**상태 확인**: `launchctl list | grep com.max` — 두 번째 컬럼이 마지막 종료 코드다(`0`이 정상, `-9`는 SIGKILL). 1회 강제 실행은 `launchctl kickstart -k gui/$(id -u)/<Label>`. plist를 고친 뒤엔 `~/Library/LaunchAgents/`로 다시 복사하고 `launchctl bootout` → `bootstrap` 해야 반영된다.

**실패 알림은 아직 없다** — `/tmp/*.err`는 아무도 안 읽어서 위키 잡 실패를 3일간 못 알아챈 전례가 있다(README 「주의」 참고).

## 자주 쓰는 명령

- 검색: `secall recall "키워드"` (토크나이저 kiwi, 임베딩 없음 — BM25만)
- 벡터 검색 켜기: config에서 `embedding.backend`를 `ort`로 바꾸고 `secall reindex`
- 위키 갱신: `secall wiki update --backend claude --session <id>` — **`--backend` 필수 명시**. config 기본값(`wiki.default_backend`)은 최종 리뷰 반영으로 `disabled`(이전엔 `codex`, 모델 에러로 우연히 깨져 있었음 — Task 8 실측). 세션 전체 일괄 갱신(`secall wiki update`, backend 없이)은 토큰을 많이 쓰므로 품질 확인 후 수동 판단
- 정합성: `secall lint` (memory/ 서브폴더와 공존 확인됨, 0 errors)
- DB 복구: `secall reindex --from-vault` (볼트=원본, DB=로컬 파생 캐시)
- hook 셀프테스트: `skills/memory-tick/test_hooks.sh`
- kiwi 토크나이저 env: `~/.zshenv`에 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 영속화됨 (config.toml엔 해당 키 없음). MCP 서버는 `claude mcp add`가 zshenv를 거치지 않으므로 등록 시 `--env`로 동일하게 전달했음 — 이미 완료, 재등록 시에만 신경 쓰면 됨
- MCP 상태 확인: `claude mcp list` → `secall: /Users/max/.local/bin/secall mcp - ✔ Connected` (최종 리뷰 반영으로 bare `secall` 대신 절대경로로 재등록 — GUI 등 PATH에 `~/.local/bin`이 없는 컨텍스트에서도 안전)

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
- 위키(`wiki update`)는 `--backend claude`로 명시 실행 — config 기본값(`wiki.default_backend`)은 최종 리뷰 반영으로 `disabled` (이전엔 `codex` 기본값이 모델 에러로 우연히 깨져 있었을 뿐)
- graph(지식 그래프)·log(작업일기 폴더) 백엔드는 비활성/미사용 상태 — config.toml `[graph] semantic_backend = "disabled"`, `[log] backend = "disabled"`(최종 리뷰 반영, 이전엔 `ollama_cloud` 기본값이 API 키 없어 우연히 깨져 있었을 뿐). 실제 작업 기록은 볼트 최상위 `log.md` 플랫 파일로 seCall이 자동 생성함 (스펙 초안의 `log/` 폴더 구조와 다름, 문제 없음)
- 토크나이저는 kiwi로 설정되어 있으나 기존 216세션 인덱스는 upstream 버그로 인한 재구축 리스크(git_branch 유실) 때문에 lindera 톤화 상태로 남아있음 — 신규 질의는 kiwi, 기존 인덱스는 lindera 혼용. 기능엔 지장 없음 (자세한 내용: `.superpowers/sdd/task-2-report.md`)
- **업무용(`~/.claude-work`) 세션 수집 — 경로 제약 3종 (2026-07-30 실측)**: 업무용 config dir 세션은 그냥은 절대 수집되지 않는다. 원인이 셋이고 전부 seCall 바이너리에 하드코딩돼 있어 config.toml로는 못 바꾼다.
  1. **포맷 감지가 경로 문자열 기반이다.** 동일 파일을 `~/.claude-work/projects/…`에 두면 `unknown session format`으로 실패하고, `~/.claude/projects/…`로 복사하면 정상 ingest된다(내용은 무관). 감지 앵커는 `/.claude/projects/`, `/.codex/sessions/`, `/.gemini/`.
  2. **`--auto` 스캔 깊이는 `projects/<프로젝트디렉토리>/*.jsonl` 딱 한 단계다.** 그래서 `projects/_work/<프로젝트디렉토리>/x.jsonl`처럼 한 단계 깊으면 못 본다. 부수적으로 발견된 사실 — `projects/<projdir>/<uuid>/subagents/*.jsonl`(개인용 256개)도 같은 이유로 **한 번도 인덱스된 적 없다**. 서브에이전트 트랜스크립트는 사실상 수집 대상 밖(파생 노이즈라 의도적 방치로 두는 중).
  3. **심링크는 depth 1에서만 따라간다.** `projects/_work → ~/.claude-work/projects` 같은 상위 심링크는 `--auto`가 무시하지만, `projects/_work--<projdir> → ~/.claude-work/projects/<projdir>`처럼 **프로젝트 디렉토리 자체를 depth 1 형제로** 걸면 정상 수집된다. 디렉토리명은 겉치레일 뿐 — seCall은 프로젝트명을 jsonl 안의 `cwd`에서 뽑는다.

  채택한 형태: `~/.claude-work/projects`는 실체로 그대로 두고(`projects/`는 심링크 금지 대상), `~/.claude/projects/_work--<projdir>` 심링크만 건다. 링크 갱신은 `scripts/link_work_projects.sh`(매일 08:40, `com.max.claude-work-links`)가 맡는다 — 새 업무 프로젝트 디렉토리를 링크하고 사라진 것의 끊어진 링크를 지운다. **대안으로 검토했다 기각한 것 둘**: ① 별도 `secall ingest <dir>` launchd 잡 — `ingest`는 **새로 넣은 게 0이면 에러가 없어도 항상 exit 1**이라 조용한 날마다 실패로 보여 진짜 실패를 가린다 ② 레이아웃 스왑(`~/.claude-work/projects` 실체를 `~/.claude/projects/_work`로 옮기고 심링크 역방향) — 위 ②번 깊이 제약에 걸려 **작동하지 않는다**(실제로 해보고 되돌림).

  스크립트 자체의 함정 하나: `"$linked개"`처럼 변수 바로 뒤에 한글이 붙으면 bash가 멀티바이트를 변수명의 일부로 먹어 `unbound variable`이 난다 — `${linked}개`로 중괄호를 쓸 것. `set -u`가 없었으면 빈 문자열로 조용히 넘어갔다.
- **자격증명 노출 주의**: `raw/.sessions/`(불변 원본 아카이브, iCloud 동기화 대상)에는 과거 세션에서 `.env`를 grep/cat한 내용이 그대로 보존된다. 평문 크리덴셜 9종이 담긴 세션 13개를 2026-07-08에 볼트+DB+graph에서 삭제, 원본 JSONL은 `~/.claude/secrets-quarantine/`(로컬 전용)로 격리함. 앞으로도 세션에서 시크릿을 열면 아카이브에 평문으로 남으므로, 노출된 키는 로테이션하고 raw 파일을 외부 공유·별도 백업할 때는 점검 필요. 재점검 스캔은 값 출력 없이 변수명·개수만 보는 방식으로 (자세한 내용: `.superpowers/sdd/task-8-report.md`)
- **검색 인덱스 드리프트 + 주간 자동 복구**: iCloud 볼트에 대한 `secall sync`는 fileprovider 쓰기 충돌("Resource deadlock avoided")로 매 실행마다 검색 인덱스에서 세션을 몇 개씩 누락시킬 수 있다. 볼트 md 원본은 안전(불변)하고 DB는 파생 캐시라 손실은 아니며, 매주 일요일 09:30 `secall reindex --from-vault`(launchd)가 볼트에서 인덱스를 통째로 재구축해 자동 복구한다. 수동 복구: `secall reindex --from-vault`. 인덱스가 틀어졌는지 확인: `secall lint`(세션 수·FTS row 불일치 보고)
- **wiki update도 같은 iCloud 쓰기 충돌에 노출**: `secall wiki update --backend claude`가 짧은 시간에 sync/reindex 등 다른 iCloud 쓰기 작업과 겹치면 내부 Sonnet 서브프로세스가 `EDEADLK` 류 에러를 만날 수 있다. 이 에이전트는 Bash/ps 툴이 없어서 원인을 진단할 방법이 없는데도, 로그에 "다른 프로세스(PID·시각까지)가 동시에 쓰고 있다"처럼 구체적이지만 근거 없는 이야기를 남기고 넘어갈 수 있음(2026-07-09 실측, 확인 결과 그런 경쟁 프로세스는 실제로 없었음 — 환각). 파일 손상 없이 그냥 아무 것도 안 쓰고 종료되는 형태였음. 평상시 금요일 단독 실행(다른 iCloud 작업과 안 겹침)에서는 재현 가능성 낮음 — 로그에 이런 텍스트가 보이면 `secall lint` + 위키 파일 최신순으로 실제 변경 여부만 확인하면 됨, 재실행하면 보통 해결
- **reindex는 내용 변경을 못 본다**: `secall reindex --from-vault`의 skip은 세션 존재 기준이라, 이미 인덱스된 세션의 볼트 md를 고쳐도(스크럽 등) 인덱스는 옛 내용을 유지한다. 갱신하려면 해당 세션 row를 DB(`~/Library/Caches/secall/index.sqlite`)의 turns_fts/turns/sessions에서 지우고 `secall reindex --from-vault` — 단, 이 재인덱스는 세션을 **turns 0개로** 만들므로 반드시 `secall reindex --from-vault --repair-missing-turns`까지 실행해야 완복구된다 (2026-07-15 vault 백필 때 실측). favorite/notes 있는 세션은 지우면 유실되니 삭제 전 확인. FTS 검증은 LIKE 말고 `MATCH`로 (FTS5 가상 테이블에서 LIKE가 오답 냄).
- **스크럽의 알려진 천장**: ① 08:45 시점에 30분 내 수정된(진행 중) 세션은 그날 sync에 평문으로 들어갈 수 있음 — 로컬은 다음 날 마스킹되지만 vault 사본은 남으므로, 의심되면 `scrub_secrets.py --report --paths <vault>`로 확인 후 수동 처리. ② 이미 iCloud에 올라간 평문은 Apple 서버에 버전이 남았을 수 있음 — 노출 키는 마스킹과 무관하게 로테이션.
- **daily sync의 wiki/log 백엔드 자동호출 함정**: 매일 09:00 launchd가 돌리는 `secall sync`는 `wiki.default_backend`/`log.backend`가 활성 백엔드로 설정돼 있으면 자동으로 LLM을 호출한다. 지금은 두 값을 `disabled`로 명시 설정해 안전하지만(최종 리뷰 반영, config.toml), 이전엔 `wiki.default_backend = codex`(모델 에러로 우연히 실패)·`log.backend = ollama_cloud`(API 키 없어 우연히 실패)였다 — codex 로그인을 고치거나 `OLLAMA_CLOUD_API_KEY`를 설정하는 순간 매일 토큰이 나가기 시작했을 것. 위키 갱신은 항상 수동으로 `secall wiki update --backend claude`를 명시 실행하는 것이 공식 경로.
