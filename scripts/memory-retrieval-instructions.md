# 개인 메모리 회상

작업을 파악한 뒤, 작업 대상 또는 주제가 바뀔 때 memory_project_resolve로 현재 프로젝트를 식별하고 memory_search로 관련 기억을 검색한다. 명시된 등록 ID와 작업 대상 경로를 우선하고 조회 결과의 project_id를 current_project_id로 사용한다. 문맥이 없거나 충돌하면 global만 적용한다. 검색어는 현재 작업의 핵심어로 구성하고 결과가 없으면 더 짧은 키워드로 다시 찾는다.

자동 적용은 valid confirmed 중 global 또는 현재 프로젝트 일치 항목으로 제한한다. review 조회와 memory_get 원문/전체 목록은 적용 승인이 아니다. 현재 사용자 명시 지시 → 해당 작업 명시 규칙 → 저장된 일반 선호 순서로 적용한다. 일회성 예외는 그 작업에만 적용하고 영구 변경이 불분명하면 기존 기억을 보존한다.

저장이 필요한 사용자 선호·정정·제약은 memory_save의 완전한 metadata로 저장한다. 내용 추론은 candidate다. 범위가 애매하면 식별된 현재 프로젝트로 좁혀 scope_inferred=true로 기록한다. 명시 정정 내용은 confirmed일 수 있다. 프로젝트 문맥도 없으면 scope=null, status=candidate, project_id=null, scope_inferred=false로 격리한다. 전역 확대와 후보 확정은 사용자 명시/확인 근거가 필요하다. scope_reason과 status_reason은 각각 범위와 내용의 근거를 짧게 설명한다.

세션에 제공된 핵심은 승인된 짧은 본문이다. 원본에서 정정이나 충돌이 드러나면 해당 항목 적용을 중단하고 재검토한다. 핵심 제공 실패를 검색 성공이나 전체 인덱스 주입으로 대체하지 않는다. 저장/검색 호출만으로 요청한 행동이 완료됐다고 보고하지 않는다.
