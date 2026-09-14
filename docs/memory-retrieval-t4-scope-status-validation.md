# T4 scope/status 보강 검증 — 2026-09-14

후속 복원 보강과 전체 회귀는 [최신 검증 기록](memory-retrieval-t4-restoration-validation.md)에 기록한다. 아래 결과는 당시 구성의 기록으로 보존한다.

기준 e9eb736. [이번 실행 계획](superpowers/plans/2026-09-14-memory-retrieval-t4-scope-status-plan.md)에 따라 집중·보충 검증을 완료했다. 기존 [집중 회귀](memory-retrieval-t4-followup-validation.md)의 MR-003 실패를 보존한다.

## 변경과 검증 경계

T2 저장 계약 S1/S2/S6을 다시 읽고 지침에 독립된 scope/status 결정표를 넣었다. 현재 프로젝트가 있는 직접 정정은 project/confirmed + scope_inferred=true, 프로젝트도 전역 근거도 없으면 null/candidate, 명시적인 전역 적용 확인은 global/confirmed라는 기존 계약을 유지한다. 프로젝트 범위 확인과 내용 확인을 혼동하지 않도록 status_reason과 scope_reason의 근거를 분리했다. 제품 metadata API·핵심 본문·fixture는 바꾸지 않았다.

추가 훅 경계는 TDD로 검증했다. 프로젝트 식별 시작 시 이전 검색 완료를 무효화하고 진행/실패 상태에서 검색·변경을 보류한다. 새 식별이 성공하면 해당 문맥에서 재검색한다. 이전 식별 중인 도구의 지연 응답은 pending 식별자와 맞지 않아 무시한다. 같은 문맥의 재검색은 project_id/project_filter/kind/review를 유지한다. 모델이 식별하지 않은 암묵적 작업 전환이나 최초 검색의 의미 적합성까지 강제하는 기능은 아니다.

로컬 테스트 **42개 통과**. 기존 hooks 두 그룹 PASS, 임시 MCP selftest OK, fixture 구조 PASS 11개, git diff --check 통과. 훅 테스트는 상태/범위 경계를 검증하며 자연어 의미의 성공을 대신하지 않는다.

이번 집중 묶음은 기존 10세션·12턴과 합성 전역 확인 2세션·2턴이다. 합성 SG-001은 프로젝트 없는 대화에서 모든 프로젝트에 추정 수치 표시를 적용한다고 명시적으로 확정한 요청이다. 기존 fixture에 추가하지 않았고 supplemental-case.json 및 별도 hash/판정으로 보존한다. recall 모드는 임시 MCP의 실제 검색·저장을 사용하고 provided 모드는 검색을 제공하지 않는다. 모델은 claude-sonnet-5/high로 고정한다.

## 복원 검증의 별도 실패

MR-001은 요청한 보관 경로와 내용/활성 파일 보존을 충족하고 관련 기억도 실제 반환받았다. 따라서 기존 fixture 행동과 연결은 pass다. 그러나 복원 코드 블록은 일반 mv였다. 별도 충돌 복제본에서 해당 명령을 실행하면 exit 0으로 기존 목적지를 덮어쓴다.

답변에는 “이미 존재하면 덮어쓰지 말고 먼저 확인”이라는 주의 문구가 있었다. 이 문구가 없었다고 주장하지 않는다. 추가 검증은 사람이 경고를 읽고 실행을 취소하는 가능성이 아니라 **제시된 실행 명령 자체의 충돌 보존**을 확인한다. 실제 볼트나 모델의 원시 workspace를 훼손한 것이 아니며, 별도 복제본에서만 검증했다.

MR-007/009는 mkdir -p와 mv -n을 제시했고 부재/충돌 조건을 모두 통과했다. 총 3개 명령 × 2조건 중 부재 3/3, 충돌 2/3이다. 부모 부재 검증은 기존 합성 로컬 테스트이며 실제 archive가 부모 안에 있는 조건과 구분한다. 추가 충돌 검증을 기본 fixture 행동 점수에 섞지 않는다.

## 결과와 중단 판단

| 묶음 | 실행량 | 행동 | 실제 연결 |
| --- | --- | --- | --- |
| 기존 fixture 집중 | 10세션·12턴 | 10/10 pass | recall 9/9 pass; provided 1건 해당 없음 |
| 명시 전역 확인 보충 | 2세션·2턴 | 2/2 pass | recall 1/1 pass; provided 1건 해당 없음 |

MR-003은 첫 저장부터 project/confirmed + scope_inferred=true를 사용했고, scope_reason은 현재 프로젝트 문맥, status_reason은 직접 정정 지시를 근거로 남겼다. MR-011 두 모드는 첫 저장부터 null/candidate였다. SG-001 두 모드는 사용자의 명시 전역 확인을 근거로 global/confirmed였다. 서버가 모델의 의도를 자동 검증하게 바뀐 것은 아니며 이번 관찰 결과다.

[기준별 판정](evaluations/memory-retrieval-t4-scope-focused-20260914/records.json), [집계](evaluations/memory-retrieval-t4-scope-focused-20260914/summary.json), [보충 입력](evaluations/memory-retrieval-t4-scope-focused-20260914/supplemental-case.json). 기존 JSON SHA `48cf67fb1cde05ba4e4ad7fe0d542d6b4959bf13109989462c10e3c30054881d`와 프로젝트 매핑을 유지했다. 코드·지침은 캠페인 동안 고정했고 실행 레코드 hash와 최종 파일이 일치함을 확인했다.

모든 12세션·14턴이 실행 완료됐으나 MR-001의 별도 충돌 보존 조건이 실패했다. 따라서 **전체 44세션·52턴은 실행하지 않았다.** 기본 fixture의 성공 점수와 추가 안전성 실패를 분리했으며, 이전 44건 결과를 이번 구성의 전체 통과로 재사용하지 않는다. 이번에는 Codex 모델 검증을 실행하지 않았다. 남은 실행량을 성공할 때까지 같은 사례를 반복하는 데 쓰지 않았다.

원시 근거와 구성 133개 파일을 scrub 검사 0건 확인 후 로컬 docs/evaluations에 보존했다. 인증값·인증 홈은 포함하지 않았으며 원시 자료는 미추적 상태로 유지한다. 코드·테스트·집계 문서만 커밋한다. 실제 볼트·전역 CLI 설정·launchd·사용자 Stop hook·설치는 변경하지 않았다.

## 남은 작업

범위/상태 혼동에 대한 이번 수정은 집중 기준을 충족했다. 다음 수정 대상은 복원 안내의 실행 가능한 충돌 방지다. 주의 문구만으로 일반 mv 코드 블록을 보완했다고 간주하지 않고, 코드 블록 자체에 덮어쓰기 방지와 충돌 시 보존/보고를 포함하는 형식을 검증해야 한다. 기존 판정은 보존하고, 보관 집중 사례의 부재·충돌 조건을 통과한 후 전체 회귀와 12개 보관 사례의 추가 안전성 검증으로 진행한다. 한 번의 통과가 지속적인 모델 준수를 보장하지 않으므로 실제 환경 설치는 여전히 별도 단계다.
