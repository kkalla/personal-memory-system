# T2 검증·완료 기록 — 2026-09-11

브랜치: `docs/memory-retrieval-handoff`. 기준: 설계 `ee8b367`, T1 `d079f04`.

산출물은 [핵심 선정 기록](memory-retrieval-core-review.md)과 [저장 계약](memory-retrieval-storage-contract.md)이다. **2026-09-11 사용자 `go` 응답으로 K1–K4와 S1–S6을 수정 없이 확정했고 T2를 완료했다.** 아래 기존 테스트 실행 결과는 2026-09-10 검토안 작성 당시의 결과다. 승인 반영은 문서 상태·확인 기록만 바꾸며 계약과 핵심 본문은 유지한다.

실제 볼트는 읽기만 했다. 102개 유형별 노트의 목록·description과 선정/주요 제외 항목의 본문을 읽었으며, 모든 노트 전문을 검증했다고 주장하지 않는다. 제품 코드·fixture·검증기 변경은 없어 새로운 TDD 사이클은 수행하지 않았다.

| 검증 | 결과 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_memory_retrieval_cases.py' -v` | 8 tests, OK |
| `python3 scripts/validate_memory_retrieval_cases.py tests/fixtures/memory_retrieval/cases.json` | STRUCTURE PASS: 11 cases; agent behavior NOT RUN; recall integration NOT RUN |
| `bash skills/memory-tick/test_hooks.sh` | stop-hook-throttle / session-start-memory PASS |
| `python3 scripts/memory_mcp.py --selftest` | selftest OK, 임시 볼트 사용 |
| `git diff --check` | exit 0 |
| 문서 상대 링크 존재 확인 | 통과 |
| 핵심 본문 UTF-8 계수 | 799바이트 / 확정 한도 2048. 실제 모델 토큰 수 아님 |

계수 재현: 후보 문서의 `core-body:start`와 `core-body:end` 사이 text 코드 블록 내용만 추출하고, 마지막 LF를 보존해 `len(body.encode("utf-8"))`를 계산한다. 코드 펜스와 HTML 마커는 제외한다.

기존 사용자 변경 `skills/memory-tick/stop-hook-throttle.sh`의 작업 전후 SHA-1은 `405495a60da413ec38c0b6e91c02e663c0e95c40`으로 동일하다. 수정·되돌리기·스테이징·커밋하지 않았다. CLI 설정·launchd·실제 볼트도 변경하지 않았다. 네트워크와 실제 모델 호출은 0회다. 구조 검증 결과로 행동 성공이나 회상 연결 성공을 보고하지 않는다.

2026-09-11 승인 반영 후 문서 상대 링크, 핵심 본문 799바이트, `git diff --check`, 기존 훅 SHA-1 보존을 재확인했다. 제품 변경이 없어 기존 테스트를 반복 실행하지 않았다. 다음은 T3 저장·검색 구현이다. T3는 확정 계약 S1–S6과 검증 경계를 사용하고, T1 fixture·검증기·기존 MCP 함수·scrub을 재사용한다. 환경 연결·모델 실행은 T4다. 실제 볼트의 낡은 “다음 T1” 진행 메모는 읽기 전용 경계 때문에 갱신하지 않았다.
