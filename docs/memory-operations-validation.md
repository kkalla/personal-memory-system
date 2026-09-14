# 개인 메모리 운영 연결 — 2026-09-14

사용자 “연결작업 진행하자” 및 “continue” 승인으로 [운영 적용 계획](superpowers/plans/2026-09-14-memory-retrieval-operations-plan.md)을 실행했다. **Claude Code·Codex에 로컬 stdio memory MCP와 핵심 제공을 연결했고 실제 검색을 확인했다.** 설치 중 기존 Claude 세션의 검색 제어 장애가 발생해 부분 해제·수정 후 새 세션에만 제어를 활성화하도록 재연결했다. 모든 기억의 전환이나 전체 모델 회귀 완료를 뜻하지 않는다.

## 배포 형태와 변경 범위

- 두 환경의 `memory` 서버: `/usr/bin/python3 /Users/max/00_Projects/95_personal-memory/scripts/memory_mcp.py`, `MEMORY_VAULT=/Users/max/99_memory/memory`. CLI마다 별도 프로세스가 같은 볼트를 사용한다. 평가용 서버를 운영에 등록하지 않았다.
- `secall` MCP는 과거 대화 검색용 그대로 유지했다. 기존 MCP 목록 비교 및 Codex 기존 설정 접두사 byte 비교로 보존을 확인했다. 별도 포트·daemon·launchd·패키지 설치·새 인증은 없다.
- Claude: `~/.claude.json`에 memory 추가, `~/.claude/settings.json`에서 기존 전체 인덱스 SessionStart만 핵심 제공으로 교체하고 검색 제어 추가. 사용 기록이 계속 갱신돼 hash 가드가 두 번 쓰기 전에 중단했으며, 등록은 최신 기록을 보존하는 `claude mcp add memory --scope user`로 처리했다.
- Codex: `~/.codex/config.toml`에 memory 추가, `~/.codex/hooks.json`에 핵심 SessionStart 추가, `~/.codex/AGENTS.md`에 개인 메모리 지침 신규 작성. memory 서버에만 `default_tools_approval_mode="approve"`를 적용했고 기존 셸 정책·전역 모델/effort·다른 MCP는 바꾸지 않았다. CLI `hooks/list`가 제공한 신규 memory SessionStart의 hash 하나만 신뢰 등록했다. 전역 trust 우회는 사용하지 않는다.
- Claude가 참조하는 `/Users/max/dotfiles/shared/AGENTS.md`의 개인 메모리 절만 새 검색·적용·저장 계약으로 교체했다. 앞뒤 다른 절과 기존 심볼릭 링크를 유지했다. 두 환경은 실제 로드되는 지침에 본문을 제공하며 경로만 두고 자동 로드를 가정하지 않는다.
- 기존 memory-tick Stop, Orca·보안 훅은 보존했다. 검색 제어와 저장 평가 Stop은 역할이 다르다. Codex에는 Claude 전용 검색 제어를 등록하지 않았다.

## 실제 볼트

등록 프로젝트는 `personal-memory`, root `/Users/max/00_Projects/95_personal-memory`, ID `prj-f0682c0b-6d1c-4a1c-9378-b219e71eb2f7`다. 임시 준비 단계에서 기존 등록 API로 한 번 생성한 UUID를 검증된 registry와 함께 설치했다. fixture ID나 다른 프로젝트 alias를 사용하지 않았다.

승인된 K1–K4를 `core-manifest.json`에 설치했다. 최종 핵심은 861 UTF-8 바이트 / 2048 대리 예산이며 실제 모델 토큰 수는 아니다. 출처 원문을 읽어 승인 본문과의 충돌 여부를 검토했으며, 본문을 확대하지 않았다.

검색용으로 `feedback_approved-core-k1.md`부터 `feedback_approved-core-k4.md`까지 4개를 추가했다. 각각 승인된 짧은 본문, 승인 참조, 원본 basename 및 적용 조건을 담고 global/confirmed로 저장했다. 기존 API의 metadata 검증·scrub·원자 쓰기를 사용했다. 원본 104개는 byte 그대로 보존하고 메타데이터를 일괄 승격하지 않았다. 전체 인덱스는 보존하면서 새 항목을 추가했다.

따라서 현재 **핵심 4개 + 검색 가능한 승인 파생 노트 4개**가 연결된 상태다. 기존 104개는 legacy로 검토 조회에 남고 자동 검색 전환은 미완료다. 실제 모델 읽기 검증 전후 볼트 파일별 hash가 동일함을 확인했다.

## 실행 근거와 한계

CLI는 Claude 2.1.267, Codex 0.154.0이다. 검증 요청 모델은 claude-sonnet-5/high, gpt-6-astra/low이며 기존 사용자의 전역 모델 설정은 유지했다. 임시 2세션·8턴 + 실제 2세션·4턴, 합계 4세션·12턴을 실행했다. 동일 구성 재시도나 전체 44세션 회귀는 하지 않았다.

| 검증 | 관찰 |
| --- | --- |
| 임시 Claude 4턴 | 핵심 수신·두 주제 검색·project candidate 저장 및 기본 검색 제외 확인. 첫 답변은 검색 전에 나왔고 Stop 보정 후 검색했으므로 순서 준수까지 통과라고 하지 않는다. |
| 임시 Codex 4턴 | 핵심 응답은 나왔지만 최초 구성의 MCP 승인 설정 누락으로 호출이 차단됨. 후보 저장 실패를 그대로 기록했다. |
| 수정 승인 설정 | memory 서버만 approve로 지정하고 설치된 CLI의 config/read로 해석 결과 확인. 추가 모델 재시도 없이 실제 세션으로 읽기 연결 확인. |
| 임시 실제 MCP stdio 왕복 | candidate 저장, 기본 검색 제외, 검토 검색 반환 확인. 모델의 저장 판단을 검증한 것은 아니다. 최초 검토 결과 총수 1이라는 테스트 가정은 legacy 검색 결과도 포함하므로 잘못됐고, 대상 후보의 존재·상태 판정으로 바로잡았다. |
| 실제 Claude 2턴 | 현재 root 식별, K1 정리 기억 반환, 주제 변경 후 K4 토큰 기억 반환. 잘못된 scope·여러 단어 검색은 훅이 거부하고 보정된 호출이 성공했다. SessionStart hook_response에 실제 핵심 본문이 존재함을 확인. |
| 실제 Codex 2턴 | 등록 프로젝트 식별 및 두 주제 검색 모두 실제 MCP 응답 성공. 승인 차단 해소. 해당 세션 rollout의 response_item에 핵심 본문이 있는 것을 확인. |

실제 세션에는 기억·파일 쓰기를 요청하지 않았다. 수정된 Codex 승인 구성에서 **모델의 후보 저장을 다시 실행하지 않았으며**, 로컬 MCP 왕복을 그 성공으로 대신하지 않는다. 이전 행동 44/44·회상 21/22는 그 구성의 결과이며 이번 배포에 재사용하지 않는다. MR-002 키워드 누락은 사용자 지시에 따라 보류했다.

## 기존 Claude 세션 장애와 수정

배포 중 사용자가 다른 프로젝트의 진행 중 세션에서 `현재 요청의 검색 상태를 확인할 수 없습니다`와 `검색 상태 손상으로 작업을 중단했습니다`를 보고했다. 해당 세션의 상태 파일에는 실제로 `denials` 필드 하나만 있었다. 사용자 명령의 다운로드 URL이나 인증 파라미터는 원인 분석에 필요하지 않아 실행·복사·기록하지 않았다.

원인은 새 훅이 UserPromptSubmit을 보지 못한 채 기존 세션의 PreToolUse부터 받는 경우였다. 빈 상태에서 요청 불일치를 거부한 뒤 denials만 저장했고, 다음 이벤트는 이를 손상 상태로 판정했다. 새 세션만 검증한 운영 스모크가 이 배포 전환 경계를 놓쳤다.

1. 전역 설정에서 새 검색 제어 5개 항목만 즉시 해제했다. MCP·핵심 제공·기존 훅은 유지했다.
2. 이전 상태 경로 `~/.local/state/personal-memory/retrieval-claude`에 `DISABLED`를 두고 코드가 이를 확인하게 해 캐시된 옛 훅 호출도 무출력으로 만들었다. 기존 상태 파일은 삭제하거나 성공 상태로 조작하지 않았다.
3. 초기화되지 않은 도구 이벤트가 불완전한 상태를 저장하지 않도록 수정했다. 공개 CLI 테스트에서 보고된 두 오류가 같은 순서로 RED로 재현됐고 수정 후 GREEN이다.
4. 운영 제어에 `MEMORY_RETRIEVAL_REQUIRE_SESSION_START=1`을 추가하고 새 경로 `~/.local/state/personal-memory/retrieval-claude-v2`를 사용한다. SessionStart의 startup/resume/clear에서만 활성 표식을 만들고, compact만으로는 옛 세션을 활성화하지 않는다. 활성화되지 않은 기존 세션은 다음 사용자 요청에서도 제어 대상이 아니다.
5. SessionStart 초기화 항목을 포함한 새 설정으로 재연결했다. 기존 범위·검색 완료·변경 차단 로직은 새 세션에 유지한다. 모델의 자율적인 기억 적용 지침은 계속 제공되지만 진행 중 세션의 MCP 목록 갱신을 보장하지 않는다.

전체 로컬 테스트 **54개 PASS**(기존 51 + 배포 전환/운영 비활성/새 세션 활성화 3개). 실제 배포 command의 상태 경로만 임시 경로로 치환한 재생에서도 기존 세션 Pre/Post 및 다음 요청은 무차단, 새 세션은 검색 전 변경 차단을 확인했다. 수정 후 추가 모델 호출·전체 모델 회귀는 하지 않았으므로 이 결과를 모델 회귀 통과로 부르지 않는다.

## 보존·복구·남은 일

백업은 `~/.local/state/personal-memory/backups/operations-20260914/`에 비공개 파일로 보존한다. manifest에는 원래 경로·심볼릭 링크 대상·hash가 있으며, 장애 전·부분 해제 후 설정도 별도 보존했다. 실제 복구는 이번 memory 항목만 제거/복원하고 다른 사용자 변경은 유지한다. manifest의 초기 적용 hash와 현재 재연결 설정 hash는 다를 수 있으므로 최신 상태를 확인해야 한다. 기존 사용자 Stop 훅을 30분 버전으로 되돌리지 않는다.

운영 근거는 [집계](evaluations/memory-operations-20260914/summary.json)와 [수정 후 재생](evaluations/memory-operations-20260914/post-incident-replay.json)에 로컬 미추적으로 보존한다. 이벤트·집계 34개 파일에서 scrub의 private-tag 1곳을 마스킹했고 변경 hash는 scrub-report.json에 기록했다. 인증 홈·전체 설정·볼트 snapshot은 이 근거 묶음에 복사하지 않았다.

남은 범위는 104개 legacy 노트의 점진적 검토, 보류된 키워드 실패, 두 MCP 프로세스의 동시 writer 직렬화, 새 생명주기 조건의 전체 모델 회귀다. 사례 지식 추출은 [후속 문서](memory-case-knowledge-backlog.md)에 계속 보류한다. 새 memory 연결을 이용하려면 각 클라이언트에서 새 세션을 시작한다. 기존 세션은 이번 제어로 막지 않는다.
