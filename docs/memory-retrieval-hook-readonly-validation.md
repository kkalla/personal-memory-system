# 검색 훅의 조회 예외와 프로젝트 ID 안내 — 2026-09-15

사용자가 조회 명령 차단과 `96_ags-watchtower` 프로젝트 ID 오류를 보고하고 훅 수정을 요청했다. 기존 사례 지식 C4 모델 평가와 별개의 운영 버그 수정이다.

## 원인과 변경

정상 UserPromptSubmit 이후에도 검색 전에는 모든 Bash가 Write/Edit와 같은 분기로 거부됐다. `git log --oneline -8 && git show --stat 42db0e8 | head -30`도 차단됐다. 잘못된 프로젝트 이름은 훅을 통과해 검색 시도 횟수와 필터를 먼저 기록한 뒤 MCP의 UUID 검증에서 실패했다.

- Git 조회 중 작은 문법 집합만 검색 전 허용한다: `git log`와 숫자 개수/`--oneline`/`--stat`/`--max-count=N`, `git show --stat`, 선택적 hex commit 또는 HEAD/HEAD~N, 각 조회 뒤 숫자 head, 이 조회들 사이의 `&&`.
- 명령 치환·리다이렉션·줄바꿈·세미콜론·백그라운드·임의 파이프·Git config override·외부 diff/textconv 옵션은 예외로 인정하지 않는다. 임의 셸 명령을 완전히 분석하는 보안 경계가 아니라 검색 선행 조건의 제한적 예외다. 기존 CLI 실행 권한과 보안 정책은 별개다.
- 예외 조회는 searched를 true로 만들거나 차단 횟수를 증가시키지 않는다. 이후 변경·저장과 Stop의 검색 요구는 유지한다. 손상/다른 요청 상태를 조회 예외로 정상화하지 않는다.
- current_project_id/project_filter 형식은 기존 memory_contract.project_id 검증을 재사용한다. 잘못된 이름은 검색 시도·필터 기록 전에 거부하고 memory_project_resolve로 대상 경로를 식별하도록 안내한다. null이면 current_project_id 생략/null 및 프로젝트 필터 없이 검색한다. 임의 ID 생성·등록은 안내하지 않는다. 등록 여부의 실제 검증은 기존 MCP가 맡는다.
- Bash 거부 문구에 “조회 예외로 확인되지 않은 Bash”도 포함해 차단 범위를 설명한다.

조회와 프로젝트 식별은 검색을 준비하는 과정으로 허용한다. 기존의 관련 기억 검색 의무 자체를 제거한 것은 아니다. 모든 읽기 명령이 예외인 것은 아니며, 미지원 구문은 먼저 검색을 수행해야 한다.

## 검증

공개 hook CLI를 임시 상태 디렉터리로 실행한 회귀 테스트를 먼저 추가했다. 변경 전 18개 중 조회 재현은 실패, ID 사전 거부는 오류로 RED를 확인했다. 최소 수정 후 같은 18개 모두 GREEN이다.

최종 로컬 memory 테스트 57개 PASS, memory-tick/SessionStart 훅 테스트 PASS, 임시 볼트 memory_mcp selftest OK, git diff --check PASS다.

새 회귀 3개는 보고된 명령의 허용과 상태 보존, 변경/실행 가능한 명령 조합의 계속 차단, 프로젝트 이름 거부 후 resolve null→검색→Write 허용의 복구 경로를 확인한다. 기존 테스트의 A/B 프로젝트 자리표시자는 실제 계약에 맞는 합성 prj-UUID로 교체했다. 실프로젝트 등록값을 변경한 것이 아니다.

운영 Claude 설정을 읽어 검색 훅 6개 이벤트가 이 저장소의 scripts/memory_retrieval_hook.py를 직접 실행하는 것을 확인했다. 별도 배포 복사나 전역 설정 변경이 필요하지 않으며 다음 훅 프로세스 실행부터 수정 코드를 읽는다. 이미 쌓인 차단 횟수나 손상 상태를 초기화하지 않았다. 이번 수정 전 차단 한도에 도달한 요청은 새 사용자 요청에서 정상 초기화해야 한다.

실제 볼트·전역 설정·launchd·memory-tick Stop 훅은 수정하지 않았다. 모델 실행과 실제 CLI 세션의 의미 행동 검증은 수행하지 않았다. 로컬 테스트 통과를 모델 회귀 통과로 보고하지 않는다.
