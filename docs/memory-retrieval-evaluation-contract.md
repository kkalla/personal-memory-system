# 개인 메모리 회귀 평가 계약 v1 — T1

이 계약은 [확정 설계](superpowers/specs/2026-09-10-memory-retrieval-design.md)의 T1 산출물이다. [공통 JSON](../tests/fixtures/memory_retrieval/cases.json)을 Claude Code와 Codex에 동일하게 사용한다. 로컬 검증기는 **구조만** 판정한다. 구조 통과는 기억 제공 후 행동 성공도, 실제 회상 연결 성공도 아니다.

## 데이터와 작업 경계

2026-09-10 실제 볼트의 아래 노트를 읽고 필요한 행동 규칙만 축약했다. 출처는 추적용 basename이며 검증기가 실제 볼트를 열지 않는다.

- `feedback_archive-over-delete-personal-config.md`: 미추적 개인 설정은 삭제 대신 보관하고 복원 방법 제공.
- `feedback_gitlab-review-tone-customization.md`: 리뷰 봇의 공식 존댓말과 진행·메타 서술 제외, 프로젝트 전용 변경을 전역화하지 않음.
- `project_agentic-ocr-workflow-name-uniqueness.md`: 프로젝트 단위 이름 고유성과 전역 고유 기각.
- `user_tech-stack-python-typescript.md`: Python 위주라는 관찰. 이를 “항상 Python만 원함”으로 과장한 **평가용 추론 후보**를 합성했다.

원문 전체, 인증 정보, 내부 링크, 고객 식별자와 실제 환경 경로는 fixture에 복사하지 않았다. 사용자 요청·방해 기억·예외는 `source_notes.adaptation`에 밝힌 평가용 재구성이다. 원문에 없는 scope/status를 실제 저장 속성이라고 주장하지 않는다.

아래 `scope`, `status`, `project_id`, `scope_inferred`는 평가에 필요한 논리 속성이다. `fixture-ocr`, `fixture-review-bot` 등은 불투명한 **테스트 전용 ID**다. T2의 실제 ID 규칙·메타데이터 직렬화·레거시 마이그레이션·핵심 후보·토큰 예산을 확정하지 않는다. 특히 어떤 fixture 기억도 항상 제공할 핵심 기억으로 선정한 것이 아니다. 제품 저장은 기존 frontmatter와 `scrub_secrets`를 보존하는 T3 범위이며 T1은 이를 변경하거나 대체하지 않는다.

## JSON 구조

UTF-8 JSON 문서 하나를 입력한다. 아래 필드는 모두 필수이며 미지정 필드와 중복 JSON 키를 거부한다. 문자열은 공백만으로 구성될 수 없다. null 허용은 명시한 필드에 한한다. NaN/Infinity는 허용하지 않는다.

| 위치 | 필드와 조건 |
| --- | --- |
| 최상위 | `schema_version`: 정수 1. `environments`: `claude-code`, `codex` 각각 한 번(순서 무관). `cases`: 비어 있지 않은 배열. |
| case | `id`: `MR-NNN` 형식, 문서 내 고유. `coverage`: 아래 표의 태그 배열, 1개 이상. `source_notes`: 출처 배열, 1개 이상. `situation`: 상황 객체. `prior_memories`: 기억 배열, 빈 배열 허용. `steps`: 순서가 있는 단계 배열, 1개 이상. |
| source_notes 항목 | `filename`: `(user\|feedback\|project\|reference)_슬러그.md` basename, 슬러그는 영문 소문자·숫자·하이픈. `adaptation`: 원문에서 축약·합성한 내용. |
| situation | `project_id`: 문자열 또는 null. `context`: 준비할 sandbox 파일·상황. `task_rules`: 해당 작업의 명시 규칙 문자열 배열, 빈 배열 허용. |
| prior_memories 항목 | `id`: 케이스 내 고유 문자열. `kind`: `user/feedback/project/reference`. `scope`: `global/project`. `status`: `confirmed/candidate`. `project_id`: 프로젝트 범위면 문자열 필수, 전역이면 null. `scope_inferred`: boolean, true이면 프로젝트 범위여야 함. `body`: 기억 본문. |
| steps 항목 | `user_request`: 그대로 제공할 사용자 요청. `project_id`: 이 단계의 작업 프로젝트 또는 null. `topic_changed`: boolean. `expected_behaviors`, `forbidden_behaviors`: 각각 비어 있지 않은 문자열 배열. |

`kind`는 노트 유형이고 `scope`는 적용 범위다. 둘을 동일시하지 않는다. `scope_inferred`는 적용 범위 추정이며, 내용 자체가 추론인 `status=candidate`와 별개다. 프로젝트 문맥이 없는 새 후보의 최종 저장 표현은 T2에서 정한다. MR-011은 저장 결과가 후보로 격리되는지를 행동으로 평가하며 미정 저장 형식을 강제하지 않는다.

ID는 케이스의 정체성으로 유지한다. 의미가 바뀌는 새 시나리오는 새 ID를 사용한다. 실행 결과는 단계와 기준의 1부터 시작하는 배열 위치를 기록하고 fixture SHA-256도 함께 남긴다. 따라서 기준 문구 수정 전후의 결과를 혼동하지 않는다.

## 회귀 케이스

| ID | coverage | 관찰할 결과 |
| --- | --- | --- |
| MR-001 | global-preference | 파일 보관 및 내용 보존·복원 안내 |
| MR-002 | project-constraint | 다른 프로젝트의 동명 허용, 같은 프로젝트의 대소문자 중복 거부 |
| MR-003 | scope-inference | 명시적 정정을 현재 프로젝트로 좁히고 범위 추정 표시 |
| MR-004 | unrelated-project | OCR 제약을 별도 제품에 전파하지 않음 |
| MR-005 | candidate-exclusion | Python 전용이라는 후보를 적용하지 않고 작업 규칙대로 TypeScript 계획 작성 |
| MR-006 | current-instruction-conflict | 현재 반말 요청이 작업 규칙·저장 선호보다 우선, 영구 기억 보존 |
| MR-007 | one-off-exception | 지정 파일만 예외 삭제, 다음 요청은 원래 보관 선호 적용 |
| MR-008 | topic-change | OCR에서 리뷰 봇으로 전환한 뒤 새 주제의 규칙을 실제 출력에 적용 |
| MR-009 | paraphrased-search | “치워줘/다시 쓸 수도” 표현에도 파일 보관 |
| MR-010 | cross-environment | 두 환경에서 동등한 완성 리뷰, 실제 게시 없음 |
| MR-011 | scope-inference, no-project-context | 프로젝트 문맥 없는 정정은 후보 보관, 전역 확정 승격 금지 |

이 태그들은 커버리지 표식이지 의미적 성공의 증명이 아니다. 일반 검증기는 위 시나리오의 부분집합도 허용한다. 저장소 테스트는 배포된 fixture의 11개 ID와 합의한 태그 집합이 유지되는지 추가 확인한다.

## 실행과 판정 계약 — T4에서 사용

케이스 × 환경 × 모드마다 새 세션과 새 임시 저장소를 만든다. `context`에 명시된 파일을 준비하고 파일 내용·메모리의 실행 전 스냅샷을 남긴다. 케이스 사이에는 상태를 공유하지 않는다. 한 케이스 안의 `steps`는 같은 세션에서 순서대로 실행하고 중간 파일·메모리 상태를 다음 단계에 유지한다. 실제 볼트와 CLI 설정을 평가 대상 저장소로 사용하지 않는다. 응답 초안 요청을 실제 외부 게시로 확대하지 않는다.

두 모드는 별도 실행한다.

1. **provided-memory / 기억 제공 후 행동**: 사전 기억과 논리 속성을 모두 입력으로 제공한다. candidate와 무관한 프로젝트 기억도 포함해 배제 행동을 평가한다. 실제 검색 연결의 성공을 주장하지 않는다.
2. **recall-integration / 실제 회상 연결**: 동일한 사전 기억을 격리된 저장소에 준비한다. T2에서 확정한 핵심 제공 정책 외에 테스트 실행자가 정답 기억을 임의 주입하지 않는다. 작업 시작과 주제 변경 시 실제 환경 연결을 통한 검색·조회 흔적과 최종 행동을 각각 수집한다. 검색을 호출했더라도 기억을 찾지 못했거나 행동에 반영하지 못하면 통과가 아니다. 표현이 다른 MR-009의 실패는 키워드 검색의 한계를 분석할 근거이며 의미 검색 성공을 미리 가정하지 않는다.

에이전트에는 `situation`, 사전 기억(모드에 맞는 전달 방식), 단계별 `user_request`와 현재 프로젝트 문맥만 제공한다. `coverage`, 출처 설명, 기대·금지 행동은 평가자용이며 에이전트에게 정답으로 주입하지 않는다. `topic_changed`는 평가자에게 전환을 표시하는 속성이지 에이전트에게 검색하라고 지시하는 추가 프롬프트가 아니다. 각 모드에서 동일한 충돌 규칙(현재 사용자 지시 → 해당 작업 규칙 → 일반 선호, 추론 후보 자동 적용 금지)을 적용한다.

각 단계의 기대 행동 **전부 충족**, 금지 행동 **전부 미발생**이어야 행동 성공이다. 기대/금지 항목마다 실제 응답 인용, 파일 diff·내용, 메모리 전후 diff 등 관찰 근거를 연결한다. 메모리 보존·미게시처럼 부정 조건을 확인할 수 없으면 `inconclusive`이며 통과가 아니다. MR-003/011의 저장은 임시 기억의 실제 변경을, MR-007은 두 단계의 파일 및 기억 전후 상태를 확인한다. “기억을 확인했다”라는 문장이나 검색 호출만으로는 어느 행동 항목도 충족하지 않는다.

회상 연결은 `connection_verdict`로 따로 기록한다. 시작/주제 전환에 필요한 조회가 실제 연결에서 일어났고 관련 기억이 돌아온 근거가 필요하다. 최종 출력만으로 연결 성공을 추정하지 않는다. 연결 성공과 행동 실패도, 행동 성공과 연결 실패도 각각 보존한다. MR-010의 “두 환경 모두” 기준은 실행별로 해당 환경을 판정한 뒤 두 결과를 종합한다. 한 환경의 성공을 다른 환경으로 복사하지 않는다.

후속 결과 레코드는 다음 정보를 포함한다(T1 검증기는 이 결과 형식을 검사하지 않는다).

- `case_id`, `fixture_sha256`, `environment`, `cli_version`, `model`, `model_version`(확인 불가 시 `unknown`), 실행 시각, `mode`.
- `execution_status`: `executed/not_run/blocked`, `behavior_verdict`: `pass/fail/inconclusive/not_run`, `connection_verdict`: `pass/fail/inconclusive/not_run/not_applicable`.
- 단계 번호, 기대·금지 항목 번호별 판정과 근거 artifact 경로/구간, 검색·조회 추적, 임시 저장소 전후 diff.
- 실패 사유: 구조 오류, 연결 미실행, 조회 누락, 검색 불일치, 범위 누출, 후보 오적용, 우선순위 위반, 예외의 영구화, 행동 불이행, 근거 부족 등을 구분한 `failure_reason`과 설명.

`provided-memory`의 연결 판정은 `not_applicable`이다. 실행하지 않았거나 막힌 케이스의 행동은 `not_run`으로 남긴다. 실행률(실행/계획)과 모드·환경별 pass/fail/inconclusive/not_run 수를 함께 기록하며 미실행을 분모에서 숨기거나 성공으로 합산하지 않는다. recall-integration의 전체 성공은 행동과 연결이 모두 pass일 때뿐이다. 환경별 문구의 완전 일치나 단순 문자열 검색으로 행동을 자동 채점하지 않는다.

## 로컬 명령

저장소 루트에서 실행한다. Python 표준 라이브러리만 사용하며 네트워크·모델·토큰이 필요 없다.

```bash
python3 -m unittest discover -s tests -p 'test_memory_retrieval_cases.py' -v
python3 scripts/validate_memory_retrieval_cases.py tests/fixtures/memory_retrieval/cases.json
bash skills/memory-tick/test_hooks.sh
python3 scripts/memory_mcp.py --selftest
git diff --check
```

CLI는 읽기 전용이다. 구조가 유효하면 exit 0과 `STRUCTURE PASS: N cases; agent behavior NOT RUN; recall integration NOT RUN`을 출력한다. 잘못된 파일·JSON·계약은 exit 1과 stderr의 `STRUCTURE FAIL: 필드 경로: 이유`로 거부한다(파일·JSON 구문 오류는 해당 파서 진단). 인자 사용법 오류는 argparse의 exit 2다. 검증은 첫 오류에서 종료한다. 출처 파일 존재나 내용의 사실성, 자연어 기준의 충분성, 실제 에이전트 행동은 구조 검증의 대상이 아니다.
