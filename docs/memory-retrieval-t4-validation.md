# T4 환경 연결·모델 회귀 중간 기록 — 2026-09-14

상태: **부분 실행, T4 미완료**. 현재 브랜치 `docs/memory-retrieval-handoff`에 T3 `64764d1`을 fast-forward하고, Orca 워크트리의 미커밋 T4 파일 6개를 원본 보존 상태로 가져왔다. 실제 볼트·전역 CLI 설정·launchd에는 설치하지 않았다.

## 실행 승인과 범위

축약 T1 fixture와 승인 K1–K4를 OpenAI·Anthropic에 전송하여 최대 44세션·52사용자 턴을 실행할지 물었고, 사용자는 2026-09-14 `진행`으로 승인했다. 이후 `continue`로 계속 진행을 지시했다. 이전 워커에서 받은 데이터 전송 승인 거부를 우회한 것이 아니라, 전송 대상과 내용을 제시한 뒤 받은 승인으로 실행했다.

계획은 11케이스 × 2환경 × 2모드 = 44세션, 다단계 사례 포함 52사용자 턴이다. 모델의 내부 도구 왕복 횟수와 사용자 턴 수는 다르다. Codex CLI 0.154.0의 `gpt-6-astra`, low와 Claude Code 2.1.267의 `sonnet`, low를 선택했다. Claude 초기화 로그는 `claude-sonnet-5`를 표시했지만 인증 실패로 모델 응답을 받지 못했다. 고정된 내부 모델 버전은 확인할 수 없어 Codex `model_version`은 unknown이다.

실제 볼트 원문·인증 정보·기대/금지 행동은 모델 평가 입력에 넣지 않았다. 케이스별 새 임시 workspace/vault와 CLI 설정 홈을 만들고, 기존 인증 파일만 mode 0600으로 별도 mode 0700 임시 홈에 복사해 CLI가 사용하게 했다. 해당 홈은 각 실행의 finally 경로에서 정리한다. 세션 안의 단계들은 같은 CLI 세션 ID를 재개하고 같은 임시 파일·볼트를 사용한다. 전체 실행은 같은 [프로젝트 ID 매핑](evaluations/memory-retrieval-t4-2026-09-14/mapping.json)을 사용했다.

## 산출물

- [memory_session.py](../scripts/memory_session.py): T3의 검증된 핵심과 공통 지침을 SessionStart JSON으로 반환. 핵심 실패 시 전체 인덱스로 대체하지 않는다.
- [공통 회상 지침](../scripts/memory-retrieval-instructions.md): 작업 시작·대상/주제 전환 검색, 적용 범위·후보 격리·저장·충돌 규칙.
- [memory_eval_server.py](../scripts/memory_eval_server.py): 실제 T3 MCP 핸들러에 평가용 도구 제한과 조회/저장 추적을 추가. provided-memory는 조회로 정답을 얻지 않도록 검색/원문 조회를 노출하지 않는다.
- [evaluate_memory_retrieval.py](../scripts/evaluate_memory_retrieval.py): 동일 fixture의 격리 준비, 두 CLI 실행·재개, 이벤트·스냅샷·결과 보존, 중단 사유 구분. 자연어 자동 채점기는 아니다.
- [원시 근거와 판정 레코드](evaluations/memory-retrieval-t4-2026-09-14/records.json), [집계](evaluations/memory-retrieval-t4-2026-09-14/summary.json), [전체 계획](evaluations/memory-retrieval-t4-2026-09-14/plan.json).

Codex는 여러 설정 출처의 훅을 합치므로 기존 홈의 훅을 덮어쓴다고 가정하지 않고 별도 홈에 평가 훅만 두었다. 훅 신뢰 생략 옵션은 검토한 평가 훅에만 호출 단위로 사용했다. [공식 훅 문서](https://learn.chatgpt.com/docs/hooks).

평가용 Codex MCP에는 `default_tools_approval_mode="approve"`를 호출 단위로 지정했다. 서버는 임시 볼트의 제한된 도구만 제공한다. 모델 실행 샌드박스는 workspace-write로 유지했다. 전역 MCP 승인 설정은 바꾸지 않았다. [공식 MCP 설정 문서](https://learn.chatgpt.com/docs/extend/mcp).

## 실제 결과

| 환경·모드 | 계획 | 완료 | 중단 | 미착수 | 행동 pass | 회상 연결 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Codex / provided-memory | 11 | 3 | 8 | 0 | 3 | not_applicable 11 |
| Codex / recall-integration | 11 | 2 | 9 | 0 | 2 | pass 1, fail 1, not_run 9 |
| Claude Code / provided-memory | 11 | 0 | 0 | 11 | 0 | not_applicable 11 |
| Claude Code / recall-integration | 11 | 0 | 1 | 10 | 0 | not_run 11 |
| 합계 | 44 | 5 | 18 | 21 | 5 | 모드별로 구분 |

23세션을 시작 시도했고 **5/44세션, 6/52사용자 턴**이 완료됐다. 중단 18개는 Codex 사용량 한도 17개와 Claude 인증 실패 1개다. Claude의 나머지 21개는 인증 실패를 확인한 뒤 실행하지 않았다. 완료된 5개 행동은 실제 응답·파일 스냅샷으로 수동 검토했으며 각 기대/금지 항목 번호에 근거를 연결했다. 나머지 39개 행동은 not_run이다. 5/5를 전체 성공률로 보고하지 않는다.

- **MR-001 Codex provided-memory:** archive 이동, keep-me 보존, 복원 문서, active.rules 보존을 확인했다.
- **MR-001 Codex recall-integration:** 핵심 본문을 받아 동일 파일 행동은 성공했다. 그러나 resolve/search가 `MCP tool call requires approval, but approval policy is never`로 거부돼 **회상 연결은 fail**이다. 추적에는 초기화와 핵심 주입만 있으며 검색은 서버에 도달하지 않았다. 이후 평가용 MCP 승인 설정을 수정했지만 이 결과를 덮어쓰거나 재실행하지 않았다.
- **MR-002 Codex 두 모드:** project-B invoice 허용, project-A INVOICE 거부를 정확히 설명했다. recall 모드의 trace 4–5행에는 현재 프로젝트 식별과 실제 OCR 기억 반환이 있다. 행동과 연결이 모두 pass다.
- **MR-007 Codex provided-memory:** 두 단계가 같은 세션 ID다. 첫 단계는 disposable.rules만 삭제하고 old.rules를 유지했다. 다음 단계는 old.rules를 archive로 이동하고 preserve를 보존했다. 기억은 두 단계 모두 변경되지 않았다.
- **MR-003 Codex provided-memory:** project/confirmed/scope_inferred=true 및 분리된 이유로 임시 기억을 저장한 흔적은 있다. 이후 사용량 한도에 막혀 최종 응답이 없으므로 전체 행동 성공으로 세지 않았다.

MR-004/005/006/008/009/010/011과 Claude 행동은 판정 가능한 완료 근거가 없다. 특히 MR-010 두 환경 동등성, MR-008 주제 변경 후 실제 검색, MR-009 의역 검색 성능은 검증 완료라고 할 수 없다. 핵심 K1만으로 파일 정리를 수행한 사례를 키워드 검색 성능의 근거로 사용하지 않는다.

CLI가 반환한 usage 합계는 input_tokens 404,098, 그중 cached_input_tokens 302,592, output_tokens 2,322다. 도구 왕복을 포함한 CLI 보고치이며 실제 청구 금액 계산은 하지 않았다. 중단된 요청에 usage가 없으므로 전체 소비량의 완전한 집계도 아니다. Claude의 첫 실행은 duration_api_ms와 usage가 0이었다.

## 발견한 실행기 결함과 수정

1. **전역 설정 격리:** CLI 옵션만으로 기존 메모리/훅 격리를 가정하지 않고 독립 설정 홈을 추가했다. 인증 파일 외에 기존 지침·설정은 복사하지 않는다. 공개 준비 경계에서 홈 권한·허용 파일·훅 내용을 검증하는 RED → GREEN을 수행했다.
2. **exit 0 ≠ 완료:** Codex `turn.completed` 및 Claude `result`의 success와 `is_error=false`를 확인해야 실행 완료다. 시작 이벤트만 있는 출력·turn.failed·예산 오류를 거부하는 RED → GREEN을 수행했다.
3. **오류 이벤트 파싱:** Codex의 최상위 `message`는 오류 때 문자열이었다. 모델 버전을 추출하며 객체로 가정해 기록기가 예외를 냈다. 문자열/비객체 이벤트와 한도·인증 오류 분류 테스트를 RED → GREEN으로 수정했다.
4. **배치 중단:** 초기 임시 배치 러너는 오류 후 다음 케이스도 계속 시작해 17개 한도 실패를 남겼다. 이 반복 실패를 숨기지 않았다. 제품 실행기의 `--batch`는 첫 미완료 결과에서 멈추고 기존 중단 결과를 자동 재시도하지 않도록 추가했다. 한 번만 실행하고 남은 21개가 보존되는 경계를 RED → GREEN으로 검증했다. 이 수정 후 추가 모델 호출은 없다.

기록기 예외가 난 실행도 원시 events와 임시 파일은 남아 있었다. 이를 읽어 결과와 after 스냅샷을 복구했고 `recorder_recovery`, `snapshot_recovered`로 표시했다. 당시 exit code·duration·정확한 실행 시각을 복구할 수 없어 null/unknown으로 남겼다. 후속 로컬 스냅샷을 당시 즉시 찍은 것으로 주장하지 않는다. 전후 자료와 원시 이벤트는 작업 경로에 미추적 로컬 파일로 보존했으며 기존 scrub으로 검사한 탐지 건수는 0이다. 인증 홈·세션 전체 로그는 근거 디렉터리에 복사하지 않았다.

## 로컬 검증

| 명령 | 결과 |
| --- | --- |
| `/usr/bin/python3 -m unittest discover -s tests -p 'test_memory*.py' -v` | 26 tests OK (T1 8 + T3 12 + T4 6) |
| `/usr/bin/python3 scripts/validate_memory_retrieval_cases.py tests/fixtures/memory_retrieval/cases.json` | STRUCTURE PASS 11; 이 명령 자체는 행동·회상 연결 NOT RUN |
| `bash skills/memory-tick/test_hooks.sh` | 두 그룹 PASS |
| `/usr/bin/python3 scripts/memory_mcp.py --selftest` | 임시 볼트 selftest OK |
| `git diff --check` | 오류 없음 |

기존 사용자 훅 변경의 SHA-1은 계속 `405495a60da413ec38c0b6e91c02e663c0e95c40`이다. 훅을 수정·되돌리거나 커밋에 포함하지 않는다. 원 Orca 워크트리의 T4 파일도 보존했다.

## 재개 경계

현재 차단 조건은 기존 Claude 환경의 로그아웃과 Codex 사용량 한도다. Claude는 `claude auth status --json`에서도 loggedIn=false였고, 사용자에게 `claude auth login`을 요청했다. Codex 오류는 `try again at 12:43 PM`을 안내했다. 계정 업그레이드·사용량 리셋·자격 증명 갱신을 임의로 수행하지 않는다.

실행 전 계획 확인은 모델 호출이 없다:

```bash
/usr/bin/python3 scripts/evaluate_memory_retrieval.py
```

실행은 새 output 디렉터리를 명시한다. `--mapping`으로 기존 매핑을 재사용할 수 있다. `--execute --batch --environment codex --output <새 디렉터리>`는 환경별 순차 실행이고 첫 중단에서 멈춘다. 기존 output은 자동 덮어쓰지 않는다. 이번 승인 상한을 넘는 재실행은 새 실행량을 산정하고 사용자와 확인한 뒤 수행한다. 정상 완료된 결과를 다시 실행해 성공률을 높이지 않는다.

남은 작업은 계정 상태 회복 후 중단/미실행 사례 및 최초 검색 연결 실패의 재검증, 동일 기준의 Claude 결과 확보, 전체 판정과 필요시 검색 지침 보강이다. 실제 볼트 핵심·registry 설치와 전역 환경 연결은 아직 적용하지 않았고, 이 임시 환경의 부분 성공을 실제 설치 완료로 보고하지 않는다.

## 커밋 경계

자동 승인 검토가 원시 평가자료·모델 로그의 영구 커밋을 거부했다. 평가 실행/전송 승인이 민감할 수 있는 기억 기반 자료의 저장소 영구 기록 승인까지 포함하지 않는다는 사유다. 따라서 `docs/evaluations/memory-retrieval-t4-2026-09-14/`는 로컬 미추적 자료로 남기고, 실행기·테스트·이 요약만 커밋했다. 위 근거 링크는 현재 작업 경로에서는 열리지만 새 checkout에는 포함되지 않는다. 원시 자료의 버전 관리·공유는 별도 사용자 승인 전까지 하지 않는다.
