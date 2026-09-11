# T3 저장·검색 구현 및 로컬 검증 — 2026-09-11

브랜치 `kkalla/memory-retrieval-t3`, 시작 HEAD `cd5f176`. `git merge-base --is-ancestor cd5f176 HEAD` exit 0으로 T2 승인 반영을 확인했다. 이 Orca 워크트리에서만 작업했다. 적용 경로의 AGENTS.md/CLAUDE.md/CONTEXT.md는 없었다. 확정 설계, S1–S6, K1–K4 승인 및 T1/T2 평가·검증 기록을 기준으로 구현했다.

## 산출물과 호출 계약

- [memory_mcp.py](../scripts/memory_mcp.py): 기존 저장/조회와 원자 쓰기·created·인덱스·scrub 재사용, 검색·registry·핵심 API 및 MCP stdio 연결.
- [memory_contract.py](../scripts/memory_contract.py): 중복 키를 거부하는 JSON 및 보수적인 flat YAML 파싱, 메타데이터·registry 검증.
- [memory-core-approved.json](../scripts/memory-core-approved.json): 승인 기록에서 옮긴 K1–K4의 정확한 manifest 템플릿. 실제 볼트 설치본이 아니다.
- [test_memory_storage.py](../tests/test_memory_storage.py): 임시 볼트 공개 API 및 실제 MCP subprocess 테스트 12개. subtest 변형 수를 독립 테스트 수로 세지 않았다.

`memory_save(kind, slug, description, body, tags=None, metadata=None)`의 `metadata`는 S1의 일곱 필드를 모두 담는 객체다. 신규 구형 호출은 null candidate, 기존 legacy 구형 갱신은 legacy 유지, 기존 v1/부분 메타데이터 노트의 metadata 생략 갱신은 거부한다. 완전한 새 metadata를 제공하면 안전하게 파싱 가능한 부분/잘못된 메타데이터를 명시적으로 복구할 수 있다. 중복 키·지원하지 않는 YAML·깨진 UTF-8은 쓰기 전에 거부한다. 기존 created와 비대상 frontmatter 줄·주석은 CRLF도 보존한다. 요청한 본문은 전체 교체하며 다른 노트를 고치지 않는다.

`memory_search(query='', current_project_id=None, project_filter=None, kind=None, review=False)`는 공백으로 나눈 키워드의 대소문자 무시 AND 부분 문자열 검색이다. 파일명 오름차순, 상한 없음. 검색 대상은 유형별 Markdown의 frontmatter와 본문이다. 기본 결과는 valid confirmed 중 global 또는 현재 등록 프로젝트뿐이다. 현재 프로젝트가 없으면 global만 반환한다. `project_filter`는 조회 필터이고 적용 문맥을 변경하지 않는다. 다른 프로젝트를 보려면 `review=true`를 명시해야 한다. 반환은 filename/type/description/body, S1 필드, `metadata_state`, `automatically_applicable`, `metadata_error`, `raw_metadata`를 포함한다. invalid의 정규 메타데이터는 null이며 파싱 가능한 원래 필드는 raw_metadata로 검토한다. 파싱 자체가 실패하면 body에 원문을 남긴다. 검토 결과에서도 candidate/legacy/invalid/다른 프로젝트는 자동 적용 불가다. `memory_get()`의 전체 인덱스 및 `memory_get(name)`의 원문 계약은 유지한다.

`memory_project_register(label, roots, confirmed=False, existing_id=None)`는 `confirmed=True`인 명시 등록만 허용하고 UUID v4를 생성한다. 기존 ID를 주면 alias를 추가하고 표시 이름을 갱신한다. ID/정규 root 중복 소유·비정규 저장 ID·손상 registry를 거부한다. `memory_project_resolve(explicit_id=None, target_paths=None, cwd=None)`는 명시 작업 경로가 있으면 cwd를 무시한다. 최장 등록 조상을 사용하고 충돌/여러 프로젝트에서는 공통 ID를 null로 반환하며 targets/ambiguous로 분리 결과를 알린다. 기억의 범위/확정 근거 판단은 호출자의 책임이다. resolve 결과가 없을 때 scope=null candidate로 저장하는 S2 흐름을 사용한다. 서버가 내용의 근거나 사용자 확인을 만들어내지 않는다.

`memory_core_initial()`은 승인 초기 manifest를 읽기 전용으로 반환한다. `memory_core_save(manifest, confirmed=False)`는 정확한 본문 승인 증언 `confirmed=True`, 출처 basename과 파일 존재, 승인 날짜/ref, 전역 확정·추정 없음, 중복 ID 및 예산을 검사한 후 원자 교체한다. 승인 본문에 scrub 탐지가 있으면 임의 마스킹된 문구를 승인 문구로 삼지 않고 수정·재승인을 요구한다. 출처가 legacy여도 별도로 승인된 짧은 manifest 본문은 제공 가능하며 출처 노트 자체는 승격하지 않는다. `memory_core_get()`은 manifest를 매번 검증하고 승인 본문만 반환한다. 없거나 손상·초과·출처 누락이면 core unavailable 오류이며 인덱스로 대체하지 않는다. 최초 핵심은 799 UTF-8 bytes이고 실제 모델 토큰 수가 아니다.

모든 위 함수는 MCP tools/list 및 tools/call에 연결된다. 구조화 반환값은 MCP text content 안의 JSON이다. stdio의 중복 JSON 키/잘못된 JSON은 -32700이며 쓰기를 실행하지 않는다. 기존 selftest는 v1 갱신에 전체 metadata를 제공하도록 갱신했다. memory_get의 도구 설명도 전체 인덱스를 항상 주입하라는 안내를 핵심/관련 검색 안내로 수정했다. 실제 환경 연결은 하지 않았다.

## RED → GREEN 관찰

1. 잘못된 metadata 입력과 구형 API 신규 격리 테스트: metadata 인자 미지원 5 errors와 후보 표시 부재 1 failure를 관찰했다. 저장 검증·격리 및 v1 갱신 제한 구현 후 통과. 테스트의 문자열 직렬화 기대도 실제 유효한 JSON 인용 YAML에 맞췄다.
2. registry 등록/식별 및 검색 범위 테스트: API 부재로 RED. 등록 ID, alias, 최장 root, 접두사 구분, 다중 대상/충돌, 다른 프로젝트 검토 조회 구현 후 GREEN.
3. legacy/invalid 읽기 보존·created/주석·scrub·실제 인덱스 파일시스템 실패/재시도 테스트는 이미 구현한 경로에서 통과. 쉼표 태그와 YAML 예약어 설명 왕복 테스트는 invalid 결과로 RED였고 안전한 문자열/배열 직렬화 후 GREEN. 120개 인덱스 항목도 보존됨을 확인했다. 기존 ensure_index_line에 상한이 없어 재구축하지 않았다.
4. 핵심 API 부재로 2 errors RED. 승인/출처/예산/읽기 구현 후 GREEN. 경계 테스트에서 제목 크기를 처음 18로 잘못 센 테스트 산식을 16바이트로 바로잡았다(한글 3 + ASCII 2026 + 제목 16 + 불릿/LF 3 = 2048). 2049 초과량 1, 기존 manifest 보존, 손상 읽기 실패, K1–K4 승인 문서와 정확히 같은 799바이트를 확인했다.
5. 실제 subprocess MCP 테스트: tools/list에 검색 도구가 없어 RED. 도구 schema/dispatch/JSON 반환/중복 키 거부 연결 후 입력→저장→검색 및 구형 덮어쓰기 거부가 GREEN.
6. 명시적 부분 metadata 복구 테스트: 기존 metadata 검증이 복구까지 차단해 RED. 안전하게 파싱한 노트의 전체 metadata 교체를 허용하고 비대상 CRLF 보존 및 깨진 UTF-8 격리 확인 후 GREEN. S1 모든 허용 조합, 다수 거부 조합, 손상 registry, symlink·alias·Unicode 구분 테스트도 통과.
7. 앞뒤 공백/개행을 제거한 뒤 핵심을 세는 S5 테스트가 RED. trim 순서를 수정해 GREEN. 미래 scrub 패턴이 등록 ID와 일치하는 경우 저장 전 거부, 원본 변경이 승인 문구를 자동 변경하지 않음, 저장된 초과 manifest 읽기 실패도 확인했다.
8. 잘못된 YAML 단일 인용 및 값 없는 주석 이유가 자동 검색에 나오는 RED를 관찰했다. 엄격한 단일 인용·주석·숫자 scalar 처리, 유니코드 줄 구분자 이유 거부, scrub 대상 slug 거부 후 12 tests GREEN.

9. 경로 끝 공백을 제거하여 다른 root와 동일시하는 RED를 발견했다. ID의 공백 정리와 경로 정규화를 분리해 실제 경로 공백을 보존한 뒤 최종 12 tests GREEN.

## 실행 결과와 재현

이 환경의 `python3`와 `/usr/bin/python3`는 모두 Python 3.9.6이다. 네트워크·제품 모델 호출·실토큰 사용 없이 실행했다.

| 명령 | 실제 결과 |
| --- | --- |
| `/usr/bin/python3 -m unittest discover -s tests -p 'test_memory_storage.py' -v` | 12 tests, OK |
| `python3 -m unittest discover -s tests -p 'test_memory_retrieval_cases.py' -v` | 8 tests, OK |
| `python3 scripts/validate_memory_retrieval_cases.py tests/fixtures/memory_retrieval/cases.json` | STRUCTURE PASS: 11 cases; agent behavior NOT RUN; recall integration NOT RUN |
| `bash skills/memory-tick/test_hooks.sh` | stop-hook-throttle / session-start-memory PASS |
| `python3 scripts/memory_mcp.py --selftest` | selftest OK,임시 볼트 |
| `git diff --check` | exit 0 |

## 검토 결과와 남은 경계

S1–S6을 대조하여 저장 전 거부, 원본 보존, 읽기 격리, 조회 필터와 현재 적용 문맥의 분리, byte 예산·승인 문구 보존을 검토했다. 실제 볼트·원 checkout·CLI 설정·launchd·secall·기존 훅 파일은 수정하지 않았다. 훅 보존은 `git diff cd5f176 -- skills/memory-tick/stop-hook-throttle.sh`가 비어 있음으로 확인한다. T1 fixture/검증기도 그대로다.

- YAML 전체 언어 구현이 아니다. flat scalar/간단한 flow 배열 외의 복합 YAML은 invalid로 격리하고 쓰기를 거부한다. 손실을 감수하고 강제 재작성하지 않는다. 손상 registry는 프로젝트 판정/검색/메타데이터 저장에 오류를 내며 수동 복구가 필요하다.
- 사용자 승인·내용의 진실성·현재 지시 충돌은 서버가 자연어로 판정하지 않는다. confirmed 인자와 이유/ref는 호출자 증언이다. 원본에서 정정/충돌이 드러나면 호출자가 해당 핵심 적용을 중단하고 사용자와 재검토해야 한다. 내용만 바뀌었다는 이유로 승인 문구를 자동 교체하지 않는다.
- 파일별 원자 교체이며 다중 파일 트랜잭션/여러 서버 프로세스 간 잠금은 없다. 노트 저장 후 인덱스 실패는 partial failure로 알리고 같은 전체 metadata 저장을 재시도해 복구한다. 동시 writer 직렬화는 T3에서 보장하지 않는다.
- 키워드 검색은 의역/의미 검색을 보장하지 않는다. T1 11개 fixture의 구조 통과와 로컬 MCP 통합은 실제 Claude Code/Codex의 행동·회상 연결 성공이 아니다. 두 환경 모델 실행은 0회이며 T4에 남긴다.
- Orca 일반 sandbox 호출에서는 runtime_unavailable/open timeout이 발생했다. 승인된 로컬 IPC 접근으로 카드의 in-review 갱신에 성공했다. 완료 커밋 후 completed로 갱신한다.

push/merge/배포 및 실제 볼트에 승인 기억·projects.json·core-manifest.json 설치는 수행하지 않는다.
