# T4 환경 연결·모델 회귀 중간 기록 — 2026-09-14

후속 보강과 Sonnet 5 high 최종 회귀는 [2026-09-14 보강 검증 기록](memory-retrieval-t4-remediation-validation.md)을 참고한다. 아래 최초 실행 결과는 변경하지 않았다.

상태: **44세션 실행·판정 완료, 성공 기준 미충족으로 보강 필요**. 최신 결과는 아래 「Keychain 인증 확인 후 전체 평가 완료」를 기준으로 하며 앞선 실행 기록은 보존한다. 현재 브랜치 `docs/memory-retrieval-handoff`에 T3 `64764d1`을 fast-forward하고, Orca 워크트리의 미커밋 T4 파일 6개를 원본 보존 상태로 가져왔다. 실제 볼트·전역 CLI 설정·launchd에는 설치하지 않았다.

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


## 사용량 회복 후 재개 — 2026-09-14

사용자의 “사용량 회복 완료. 나머지 진행” 지시에 따라 중단·미실행 39개와 최초 연결 실패 1개, 총 40세션·47사용자 턴을 재개 대상으로 산정했다. 기존 성공을 반복하지 않고 동일 fixture SHA-256과 프로젝트 ID 매핑을 유지했다. 새 순차 실행은 첫 실행 중단에서 정지하며 기존 결과를 덮어쓰지 않는다.

이번에는 Codex 18세션·21사용자 턴을 추가 완료했다. 기존 유효 결과와 합친 최신 매트릭스는 **22/44세션·26/52사용자 턴 완료**다. 최초 실패 시도는 삭제하지 않았으며 아래 표는 케이스별 최신 실행 판정이다.

| 환경·모드 | 완료/계획 | 행동 pass | 행동 fail | 행동 not_run | 회상 연결 |
| --- | ---: | ---: | ---: | ---: | --- |
| Codex / provided-memory | 11/11 | 10 | 1 | 0 | not_applicable 11 |
| Codex / recall-integration | 11/11 | 9 | 2 | 0 | pass 11 |
| Claude Code / provided-memory | 0/11 | 0 | 0 | 11 | not_applicable 11 |
| Claude Code / recall-integration | 0/11 | 0 | 0 | 11 | not_run 11 |

[재개 판정과 근거](evaluations/memory-retrieval-t4-resume-20260914/records.json), [이전 결과를 합친 최신 매트릭스](evaluations/memory-retrieval-t4-resume-20260914/latest-records.json), [집계](evaluations/memory-retrieval-t4-resume-20260914/summary.json)를 로컬 미추적 자료로 보존했다. 기대·금지 항목마다 단계·항목 번호, 판정과 수동 검토 근거를 연결했다. 추가 근거 123파일의 기존 scrub 탐지는 0건이며 인증 홈은 복사하지 않았다.

### 발견한 행동 실패

- **MR-009 provided-memory:** `restore-me`와 복원 명령을 보존했지만 실제 보관 경로는 작업공간 루트 `archive/unused.rules`다. 기대 항목 1의 `personal-config/archive/unused.rules`와 달라 fail이다.
- **MR-009 recall-integration:** 검색은 관련 확정 기억을 반환했지만 실제 보관 경로는 `archive/personal-config/unused.rules`다. 동일 기대 항목 1은 fail, 검색 연결은 pass다. 내용 보존·복원 안내·실제 작업 수행은 확인됐다.
- **MR-010 recall-integration:** 최종 코멘트의 합니다체·빈 배열 실패 조건·검증 요구는 맞지만, 앞선 사용자에게 보이는 진행 메시지에 “관련 리뷰 작성 선호를 확인한 뒤 코멘트 초안을 작성하겠습니다”가 포함됐다. 완성 코멘트만 작성하는 기대 항목 2와 진행 문구를 금지하는 항목 1이 fail이다. 최종 메시지만 잘라 판정하지 않았다. 실제 게시는 없었다.

MR-009는 검색 미적중이 아니다. 사전 기억의 `archive/`가 어느 디렉터리 기준인지는 명시되지 않았으나 평가 기대 경로는 구체적이다. 이는 기억 표현과 평가 경로 사이의 모호성을 드러낸다. 현재 계약대로 실패를 유지하며 fixture·승인된 핵심을 조용히 바꾸거나 평가 파일을 사후 수정하지 않았다. 경로 기준을 명시할지, 보존과 복원이 되는 다른 위치도 허용할지는 별도 설계 논의 대상이다. 이 결과만으로 의미 검색 도입 필요성을 주장하지 않는다.

MR-010은 검색된 리뷰 선호를 보기 전에 진행 메시지가 먼저 출력되는 순서 문제다. 리뷰 전용 어투를 전역 핵심으로 승격하지 않으면서 검색 전 출력도 작업 규칙에 맞추는 방안을 후속 검토해야 한다. 성공할 때까지 같은 실행을 반복하지 않았다.

### 확인된 경계와 한계

- MR-001 최초 MCP 승인 실패는 이번 별도 실행에서 해소됐고 검색·보관·복원이 모두 확인됐다.
- MR-003은 project/confirmed/scope_inferred=true와 별도 범위·확정 이유로 실제 저장됐다. MR-011은 scope/project_id=null, candidate, scope_inferred=false로 격리됐다. 없는 노트에 대한 추측성 get 실패 후 저장한 흔적도 보존했다.
- MR-004의 프로젝트 검색은 무관한 OCR 기억을, MR-005의 검색은 후보 기억을 제외했다. 현재 작업 규칙에 따른 결과와 기억 무변경을 확인했다.
- MR-006은 두 모드에서 현재 요청대로 반말 두 문장만 최종 샘플로 반환하고 기존 기억을 유지했다.
- MR-007은 같은 세션에서 지정 파일만 예외 삭제한 뒤 다음 파일은 보관했다. MR-008은 같은 세션에서 OCR ID에서 리뷰 봇 ID로 전환해 새 검색 결과와 최종 문구를 확인했다.
- MR-003/011의 저장 확인 응답은 리뷰 본문이 아니므로 그 앞의 저장 진행 안내를 별도 관찰로 기록했다. MR-008은 fixture가 최종 리뷰 결과의 진행 문구를 금지한다. 반면 MR-010은 완성 코멘트만 반환하라는 기준 때문에 앞선 진행 메시지도 위반으로 판정했다. 이 구분은 Claude에도 동일하게 적용한다.
- Claude 결과가 없어 MR-010의 두 환경 동등성 및 전체 회귀 성공은 미확정이다. 실제 볼트·전역 CLI 설정·launchd 설치도 진행하지 않았다.

### Claude 인증 대기

기본 `claude auth status`는 로그인 상태지만 격리된 평가 홈에서는 인증되지 않았다. 자동 승인 검토가 기존 macOS Keychain의 `Claude Code-credentials` 조회를 명시적 승인 부재로 거부해 해당 조회는 실행하지 않았다. 사용자에게 이유를 설명하고 승인을 요청했다.

사용자는 Claude auth token 사용 방식을 제안했다. 공식 `CLAUDE_CODE_OAUTH_TOKEN`은 임시 홈에서도 사용할 수 있는 OAuth 인증 경로다. 현재 실행 환경에는 이 변수가 없음을 값 없이 확인했고, 토큰 값 대신 로컬 설정 위치나 전달 방법을 요청했다. 토큰 생성은 `claude setup-token`으로 가능하다. 인증 값은 대화·로그·저장소에 남기지 않는다. [공식 환경 변수 문서](https://code.claude.com/docs/en/env-vars).

이번 재개에서 실행기·제품 코드는 바꾸지 않았다. 로컬 26개 테스트를 다시 실행해 통과했다. 남은 작업은 Claude 22세션·26사용자 턴 실행 및 동일 기준 판정, 위 행동 실패의 설계 논의와 후속 조치다. 원시 근거는 기존 커밋 경계에 따라 미추적으로 유지한다.


## Keychain 인증 확인 후 전체 평가 완료 — 2026-09-14

사용자가 “key chain 먼저 확인좀”으로 기존 Claude Keychain 조회를 명시적으로 승인했다. 정확한 `Claude Code-credentials` 항목에서 OAuth 접근 토큰 존재를 확인하고, 메모리에서 읽은 토큰을 평가 자식 프로세스의 `CLAUDE_CODE_OAUTH_TOKEN`으로 전달했다. 임시 홈의 로그인 상태와 이후 실제 모델 응답으로 인증을 검증했다. 토큰 값은 출력·인자·문서·저장소에 기록하지 않았다. MCP에는 `CLAUDE_CODE_MCP_ALLOWLIST_ENV=1`을 적용해 인증 환경 상속을 제한했다. 기존 전역 인증·CLI 설정은 바꾸지 않았다. 이전 자동 승인 거부는 이후 사용자 승인으로 해소됐으며 인증은 더 이상 차단 사유가 아니다.

Claude 22세션·26사용자 턴을 모두 완료했다. Claude Code 2.1.267, `sonnet`, low로 실행했으며 초기화가 보고한 모델은 `claude-sonnet-5`다. Codex 재개분과 합쳐 이번 재개는 40세션·47사용자 턴이고, 기존 유효 결과를 합친 최신 전체 매트릭스는 **44/44세션·52/52사용자 턴 완료**다. 실행 완료와 성공은 구분한다.

| 환경·모드 | 행동 pass | fail | inconclusive | 연결 pass | 연결 fail |
| --- | ---: | ---: | ---: | ---: | ---: |
| Codex / provided-memory | 10 | 1 | 0 | 해당 없음 | 해당 없음 |
| Codex / recall-integration | 9 | 2 | 0 | 11 | 0 |
| Claude Code / provided-memory | 8 | 3 | 0 | 해당 없음 | 해당 없음 |
| Claude Code / recall-integration | 7 | 3 | 1 | 2 | 9 |
| 합계 | 34 | 9 | 1 | 13 | 9 |

미실행/인증 중단은 최신 매트릭스에서 0개다. 기억 제공 후 행동은 18/22 pass, 실제 회상 모드는 행동과 연결이 **모두** pass인 결과가 11/22다(Codex 9, Claude 2). 연결만 성공하거나 기억 없이 우연히 맞힌 행동을 전체 성공으로 합산하지 않았다. 최초 중단·실패 기록은 별도 디렉터리에 그대로 남아 있다.

### Claude 항목별 결과

| 케이스 | 제공 기억 행동 | 실제 회상 행동 | 실제 회상 연결 | 근거 요약 |
| --- | --- | --- | --- | --- |
| MR-001 | pass | pass | fail | 올바른 경로·내용·복원·사용 파일 보존, 검색 생략 |
| MR-002 | pass | inconclusive | fail | 긴 AND 검색 0건 후 재검색 없음. 예상 결과를 미확인 가정으로만 제시하고 사용자에게 규칙 재확인 요청 |
| MR-003 | pass | pass | fail | 프로젝트 확정·범위 추정 표시를 실제 저장. resolve는 수행했으나 검색 생략 |
| MR-004 | pass | pass | pass | 현재 ID로 검색, 무관한 기억 미반환, 동명 허용·ID 구분 문서 작성 |
| MR-005 | pass | pass | pass | 현재 ID로 검색, 후보 미반환·미승격, TypeScript/Node.js 계획 |
| MR-006 | fail | pass | fail | 제공 모드에 두 문장 외 완료 설명 추가. 회상 모드는 두 문장 준수했으나 검색 생략 |
| MR-007 | pass | pass | fail | 같은 세션에서 예외 삭제 후 기본 보관 복귀, 기억 유지. 두 단계 모두 검색 생략 |
| MR-008 | fail | fail | fail | 두 모드 최종 리뷰에 에이전트 메타 설명. 회상은 OCR 기억을 찾았으나 주제 전환 후 리뷰 기억 미적중 |
| MR-009 | pass | fail | fail | 회상은 잘못된 보관 경로와 실행 불가능한 복원 명령, 검색 생략 |
| MR-010 | fail | fail | fail | 완성 코멘트만 반환하지 않고 초안 소개/에이전트 설명 추가, 회상 검색 생략 |
| MR-011 | pass | pass | fail | 문맥 없는 정정을 null/candidate로 실제 격리, 회상 검색 생략 |

MR-009 회상은 `archive/personal-config/unused.rules`에 `restore-me`를 보존한 뒤 `rmdir personal-config`를 실행했다. 최종 복원 안내는 `mv archive/personal-config/unused.rules personal-config/`뿐이므로 없는 디렉터리를 복구할 수 없다. 기대 항목 1과 2가 모두 fail이다. 파일을 영구 삭제한 것은 아니므로 두 금지 항목은 pass다.

MR-002 회상은 project-B 허용/project-A 거부를 조건부로 설명했지만, 실제 규칙인지 다시 확인해 달라고 요청했다. 실제 설계에 대한 확정 결과를 관찰하지 못했으므로 기대 두 항목을 inconclusive로 남겼다. MR-004/005는 적용 가능한 확정 사전 기억이 없는 배제 사례다. 올바른 명시 ID의 실제 검색과 무관한/후보 기억의 미반환을 확인했으나, 긴 검색어 자체도 미반환 원인이 될 수 있어 필터만의 인과적 효과를 입증했다고 주장하지 않는다.

### 설계 절에 따른 후속 판단

[확정 설계](superpowers/specs/2026-09-10-memory-retrieval-design.md)의 **확정 결정 5**는 “공통 에이전트 지침으로 시작하고 검색 누락이 검증되면 환경별 훅 보강을 검토”하도록 한다. Claude 회상 11개 중 7개에서 필수 시작 검색이 생략됐고, 2개는 필요한 기억에 미적중했다. MCP 연결 및 핵심 훅 전달은 존재했으므로 인증이나 서버 미연결과 구분된다. 공통 지침만으로 안정적인 시작·주제 전환 검색이 보장되지 않는다는 근거가 확보됐다.

다음 보강 검토안은 **미확정 제안**이다:

1. Claude 환경에서 작업 시작/대상 변경에 검색이 수행됐는지 확인하고, 누락 시 실제 검색을 유도하는 훅 보강을 설계한다. 기존 범위·후보 제한을 유지하며 전체 인덱스 강제 주입으로 대체하지 않는다.
2. AND 검색 결과가 없으면 한 개의 핵심 단어까지 줄이는 재검색 절차를 구체화한다. MR-008의 `workflow name`은 반환됐으나 `MR 리뷰 문구 코드 리뷰`는 반환되지 않았다. 이는 **확정 결정 6**의 키워드 검색을 보강할 근거이며, 현재 결과만으로 의미 검색이 필요하다고 확정하지 않는다.
3. 리뷰 코멘트만 요구하는 작업에서는 검색 안내·완료 설명을 사용자 출력에 섞지 않도록 작업 출력 규칙을 보강한다. 프로젝트 전용 리뷰 선호를 전역 확정 핵심으로 바꾸지 않는다.
4. 앞서 발견한 `archive/` 기준 위치의 모호성은 기억 본문과 평가 계약을 함께 검토한다. 사용자 확인 없이 승인 핵심/fixture의 의미를 바꾸지 않는다. 복원 경로 존재 여부는 후속 회귀에서 실제 검증할 대상으로 남긴다.

**Success Criteria**의 “기억을 요청하지 않은 작업에서 관련 선호·제약 반영”, “작업 주제 변경 후 필요한 기억을 다시 찾음”이 전체적으로 충족되지 않았다. MR-010의 두 환경 동등한 완성 코멘트도 미달이다. 따라서 T4의 계획된 실행·판정은 끝났지만 자동 회상의 안정성이나 제품 적용 완료를 선언하지 않는다. 이번 턴은 결과에 맞춘 조용한 설계 변경·제품 구현·추가 성공 목적 재실행을 하지 않았다.

### 근거·검증·보존

기존 [재개 판정](evaluations/memory-retrieval-t4-resume-20260914/records.json)에 Claude 판정을 추가하고 [최신 44개 매트릭스](evaluations/memory-retrieval-t4-resume-20260914/latest-records.json)와 [집계](evaluations/memory-retrieval-t4-resume-20260914/summary.json)를 갱신했다. 각 기대/금지 항목에 실제 응답·전후 스냅샷·trace 근거를 연결했다. Claude MR-007/008의 두 단계가 같은 세션 ID임을 확인했다. 원시 모델 result는 수정하지 않고 수동 판정 레코드를 별도로 유지했다.

재개 근거 268파일의 기존 scrub 탐지 건수는 0이다. 이전 사용자 승인 경계대로 근거는 로컬 미추적 상태로 두고 요약 문서만 커밋한다. 실행기·제품 코드 변경이 없어 앞선 26개 로컬 테스트 통과 기록을 유지하며 문서 diff 검사를 수행했다. 실제 볼트·전역 CLI 설정·launchd와 기존 사용자 Stop hook 변경은 보존했다.
