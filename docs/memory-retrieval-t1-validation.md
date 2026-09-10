# T1 로컬 검증 기록 — 2026-09-10

브랜치: `docs/memory-retrieval-handoff`. 기준 설계 커밋: `ee8b367`.

산출물은 [평가 계약](memory-retrieval-evaluation-contract.md), [JSON 11개 케이스](../tests/fixtures/memory_retrieval/cases.json), [로컬 구조 검증기](../scripts/validate_memory_retrieval_cases.py), [CLI 회귀 테스트](../tests/test_memory_retrieval_cases.py)다.

## TDD 관찰

검증 경계는 사용자가 요청한 로컬 구조 검증 CLI다. 테스트가 매번 임시 JSON 파일을 만들고 exit code와 진단을 관찰한다. 모델이나 실제 볼트를 사용하지 않는다.

1. 필수 `situation` 누락 거부 테스트를 먼저 실행했다. 검증기가 없어 RED(exit 2)를 확인한 뒤 필드 검사 구현으로 GREEN(1 test)을 확인했다.
2. 중복 ID 거부 테스트를 추가했다. 기존 검증기가 exit 0을 반환해 RED(1 failure), 중복 검사 구현 후 GREEN(2 tests)을 확인했다.
3. 중첩 필수 필드, 타입·빈 값·알 수 없는 필드·버전·환경 계약의 입력 변형을 추가했다. RED(51 subtest failures) 후 구조 검사 구현으로 GREEN(3 test methods)을 확인했다.
4. 프로젝트 범위/ID 모순, 전역 범위 추정, 기억 ID 중복 거부를 추가했다. RED(4 failures) 후 GREEN(4 test methods)을 확인했다.
5. 정상 입력·구조 전용 출력과 파일/JSON 오류 테스트를 추가했다. 중복 JSON 키 및 NaN 진단이 없어 RED(2 failures), 엄격한 파싱 추가 후 GREEN(7 test methods)을 확인했다.
6. 완성된 공통 fixture의 구조·11개 ID·커버리지 보존 확인을 추가했다. 최종 8 test methods가 통과했다. unittest의 입력 변형 subtest 수를 독립 테스트 수로 부풀리지 않았다.

항상 exit 0을 반환하고 성공 문구만 출력하는 임시 가짜 검증기로 같은 8개 테스트를 실행하는 변이 점검도 했다. **70 failures, 0 errors**로 실패했다(입력 변형 subtest 포함). 따라서 항상 성공하는 검증기가 회귀 테스트를 통과하지 못한다. 제품 검증기 파일은 이 점검에서 변경하지 않았다.

## 실행 결과

| 명령 | 실제 결과 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_memory_retrieval_cases.py' -v` | 8 tests, OK |
| `python3 scripts/validate_memory_retrieval_cases.py tests/fixtures/memory_retrieval/cases.json` | STRUCTURE PASS: 11 cases; agent behavior NOT RUN; recall integration NOT RUN |
| `bash skills/memory-tick/test_hooks.sh` | stop-hook-throttle, session-start-memory 두 그룹 PASS |
| `python3 scripts/memory_mcp.py --selftest` | selftest OK, 임시 볼트 사용 |
| `git diff --check` | exit 0, 오류 없음 |

기존 `scrub_secrets.scrub_text`로 JSON fixture를 읽어 검사했으며 탐지 0건, 마스킹 전후 동일했다. 이것이 모든 종류의 민감 정보를 탐지한다는 뜻은 아니다. 원문에서는 행동 규칙만 수동 축약했다.

## 보존 및 다음 경계

기존 사용자 변경인 `skills/memory-tick/stop-hook-throttle.sh`의 작업 전후 SHA-1은 모두 `405495a60da413ec38c0b6e91c02e663c0e95c40`이었다. 이 파일을 수정하거나 되돌리지 않았다. T1 산출물에 포함하지 않는다.

확정 설계, MCP 제품 코드, CLI 설정, 실제 볼트, launchd는 변경하지 않았다. 실제 모델 실행 수는 **0**이며 행동 성공률과 회상 연결 성공률은 아직 산출할 수 없다. 11은 구조가 유효한 fixture 수다.

다음은 T2의 핵심 후보 검토와 저장 계약 구체화다. T3 저장·검색 구현 및 T4 환경 연결·모델 실행은 이 작업에 포함하지 않는다.
