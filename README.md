# personal-memory

개인 AI 메모리 시스템. 스펙: `docs/superpowers/specs/`, 계획: `docs/superpowers/plans/`, 검증 기록: `.superpowers/sdd/task-8-report.md`

## 구성

- **seCall** (v0.7.0) — Claude Code 세션 아카이브·검색·위키. 볼트: iCloud Obsidian vault `96_memory/` (경로에 공백 있음 — 항상 인용)
- **memory-tick** (`skills/memory-tick/`) — Stop hook 30분 스로틀로 인사이트 자동 저장, SessionStart hook으로 인덱스 주입. `~/.claude/skills/memory-tick`은 여기로 symlink
- **launchd** — 매일 09:00 `secall sync` (`launchd/com.max.secall-sync.plist`) + 매주 일요일 09:30 `secall reindex --from-vault` (`launchd/com.max.secall-reindex.plist`)

## 자주 쓰는 명령

- 검색: `secall recall "키워드"` (토크나이저 kiwi, 임베딩 없음 — BM25만)
- 벡터 검색 켜기: config에서 `embedding.backend`를 `ort`로 바꾸고 `secall reindex`
- 위키 갱신: `secall wiki update --backend claude --session <id>` — **`--backend` 필수 명시**. config 기본값(`wiki.default_backend`)은 최종 리뷰 반영으로 `disabled`(이전엔 `codex`, 모델 에러로 우연히 깨져 있었음 — Task 8 실측). 세션 전체 일괄 갱신(`secall wiki update`, backend 없이)은 토큰을 많이 쓰므로 품질 확인 후 수동 판단
- 정합성: `secall lint` (memory/ 서브폴더와 공존 확인됨, 0 errors)
- DB 복구: `secall reindex --from-vault` (볼트=원본, DB=로컬 파생 캐시)
- hook 셀프테스트: `skills/memory-tick/test_hooks.sh`
- kiwi 토크나이저 env: `~/.zshenv`에 `KIWI_LIBRARY_PATH`/`KIWI_MODEL_PATH` 영속화됨 (config.toml엔 해당 키 없음). MCP 서버는 `claude mcp add`가 zshenv를 거치지 않으므로 등록 시 `--env`로 동일하게 전달했음 — 이미 완료, 재등록 시에만 신경 쓰면 됨
- MCP 상태 확인: `claude mcp list` → `secall: /Users/max/.local/bin/secall mcp - ✔ Connected` (최종 리뷰 반영으로 bare `secall` 대신 절대경로로 재등록 — GUI 등 PATH에 `~/.local/bin`이 없는 컨텍스트에서도 안전)

## 주의

- seCall git sync 사용 금지 — 동기화는 iCloud가 담당 (둘 다 켜면 충돌)
- memory 파일은 항상 전체 쓰기, append 금지 (iCloud 충돌 방지)
- **launchd FDA 필요**: `~/.local/bin/secall`에 macOS 전체 디스크 접근 권한(시스템 설정 > 개인정보 보호 및 보안)을 등록하기 전까지, launchd가 새벽 09:00에 띄우는 `secall sync`는 iCloud(TCC) 접근에서 행(hang)한다. 증상: `/tmp/secall-sync.err`가 "Reindexing vault..." 이후 조용함. 복구: `pkill -f "secall sync"` 한 번. FDA 등록 후에는 재발하지 않음 (자세한 내용: `.superpowers/sdd/task-7-report.md`)
- 위키(`wiki update`)는 `--backend claude`로 명시 실행 — config 기본값(`wiki.default_backend`)은 최종 리뷰 반영으로 `disabled` (이전엔 `codex` 기본값이 모델 에러로 우연히 깨져 있었을 뿐)
- graph(지식 그래프)·log(작업일기 폴더) 백엔드는 비활성/미사용 상태 — config.toml `[graph] semantic_backend = "disabled"`, `[log] backend = "disabled"`(최종 리뷰 반영, 이전엔 `ollama_cloud` 기본값이 API 키 없어 우연히 깨져 있었을 뿐). 실제 작업 기록은 볼트 최상위 `log.md` 플랫 파일로 seCall이 자동 생성함 (스펙 초안의 `log/` 폴더 구조와 다름, 문제 없음)
- 토크나이저는 kiwi로 설정되어 있으나 기존 216세션 인덱스는 upstream 버그로 인한 재구축 리스크(git_branch 유실) 때문에 lindera 톤화 상태로 남아있음 — 신규 질의는 kiwi, 기존 인덱스는 lindera 혼용. 기능엔 지장 없음 (자세한 내용: `.superpowers/sdd/task-2-report.md`)
- **자격증명 노출 주의**: `raw/.sessions/`(불변 원본 아카이브, iCloud 동기화 대상)에는 과거 세션에서 `.env`를 grep/cat한 내용이 그대로 보존된다. 평문 크리덴셜 9종이 담긴 세션 13개를 2026-07-08에 볼트+DB+graph에서 삭제, 원본 JSONL은 `~/.claude/secrets-quarantine/`(로컬 전용)로 격리함. 앞으로도 세션에서 시크릿을 열면 아카이브에 평문으로 남으므로, 노출된 키는 로테이션하고 raw 파일을 외부 공유·별도 백업할 때는 점검 필요. 재점검 스캔은 값 출력 없이 변수명·개수만 보는 방식으로 (자세한 내용: `.superpowers/sdd/task-8-report.md`)
- **검색 인덱스 드리프트 + 주간 자동 복구**: iCloud 볼트에 대한 `secall sync`는 fileprovider 쓰기 충돌("Resource deadlock avoided")로 매 실행마다 검색 인덱스에서 세션을 몇 개씩 누락시킬 수 있다. 볼트 md 원본은 안전(불변)하고 DB는 파생 캐시라 손실은 아니며, 매주 일요일 09:30 `secall reindex --from-vault`(launchd)가 볼트에서 인덱스를 통째로 재구축해 자동 복구한다. 수동 복구: `secall reindex --from-vault`. 인덱스가 틀어졌는지 확인: `secall lint`(세션 수·FTS row 불일치 보고)
- **daily sync의 wiki/log 백엔드 자동호출 함정**: 매일 09:00 launchd가 돌리는 `secall sync`는 `wiki.default_backend`/`log.backend`가 활성 백엔드로 설정돼 있으면 자동으로 LLM을 호출한다. 지금은 두 값을 `disabled`로 명시 설정해 안전하지만(최종 리뷰 반영, config.toml), 이전엔 `wiki.default_backend = codex`(모델 에러로 우연히 실패)·`log.backend = ollama_cloud`(API 키 없어 우연히 실패)였다 — codex 로그인을 고치거나 `OLLAMA_CLOUD_API_KEY`를 설정하는 순간 매일 토큰이 나가기 시작했을 것. 위키 갱신은 항상 수동으로 `secall wiki update --backend claude`를 명시 실행하는 것이 공식 경로.
