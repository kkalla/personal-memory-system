# 사례 지식 비교 평가 입력

[C3 계약](../../../docs/memory-case-knowledge-evaluation-contract.md)의 CKE-001~006을 고정한 별도 fixture다. 기존 memory_retrieval fixture와 검증기를 대체하지 않는다.

- tasks.json: 모델 요청과 합성 입력 파일. 모든 파일 본문은 UTF-8이며 JSON 문자열의 `\n`은 실제 LF로 작성한다.
- rubric.json: 평가자 전용 기대·금지 행동과 재조사 기준. 모델 작업공간에 제공하지 않는다.
- materials.json: 사례 본문과 고정 커밋의 보고서 위치/hash, 사람 검토 기록. 실행 manifest가 아니라 준비 자료 목록이다.

`python3 scripts/evaluate_case_knowledge.py --output NEW_DIRECTORY`는 원자료가 동일한 24개 독립 작업공간을 준비한다. 모델 호출은 하지 않는다. 각 source-plus-case에만 case.md가 추가된다. 원자료는 Git 고정 버전에서 추출하며 보고서가 연결한 미제공 자료를 자동으로 수집하지 않는다.

실행에는 별도의 OS 격리 사전 검증 기록과 `--execute`가 필요하다. 결과의 execution은 CLI 종료 판정이고 behavior/misuse는 별도 수동 판정이다. 자동 검색 연결은 이번 평가 대상이 아니다.
