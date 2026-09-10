# T2 저장 계약 v1 — 확정

상태: **2026-09-11 사용자 승인으로 S1–S6 확정**. K1–K4 본문과 S1–S6을 그대로 확정할지 묻는 요청에 사용자가 `go`로 답했다. [확정 설계](superpowers/specs/2026-09-10-memory-retrieval-design.md)의 결정을 변경하지 않는다. [핵심 선정 기록](memory-retrieval-core-review.md)의 「확인 기록」에 승인 근거와 범위를 남겼다. 구현은 T3이며 실제 볼트·제품 코드는 아직 변경하지 않았다.

## S1 — 직렬화와 독립된 의미

기존 Markdown 파일명 `{kind}_{slug}.md`, frontmatter의 `name/description/type/tags/created`, 본문을 유지하고 아래 필드를 추가한다. `type`은 노트 유형이며 적용 범위를 결정하지 않는다. 한 노트의 적용 범위·확정 상태는 하나다. 서로 다른 상태의 주장을 한 본문에 섞으면 분리하고 원본 참조를 남긴다.

| 필드 | 계약 |
| --- | --- |
| `memory_schema` | 정수 `1`. 새 메타데이터 집합이 완전함을 표시. |
| `scope` | `global`, `project`, 또는 YAML `null`. null은 범위 미정 후보의 표현이며 제3의 적용 범위가 아니다. |
| `status` | `confirmed` 또는 `candidate`. 명시적 선호·정정·결정에 근거하면 confirmed 가능. 추론은 candidate. |
| `project_id` | project면 아래 정규 ID 필수. global/null이면 YAML `null`. |
| `scope_inferred` | YAML boolean. true는 현재 프로젝트로 범위를 좁혀 추정한 경우에만 허용. 내용 확정 여부와 독립이다. |
| `scope_reason` | 비어 있지 않은 한 줄 문자열. 범위의 근거 또는 범위를 정하지 못한 이유. |
| `status_reason` | 비어 있지 않은 한 줄 문자열. 명시 지시·확인 또는 추론의 근거. 비밀값·대화 전문을 넣지 않는다. |

허용 조합:

| scope | status | project_id | scope_inferred | 의미 |
| --- | --- | --- | --- | --- |
| global | confirmed/candidate | null | false | 범위는 전역. 내용 추론이면 여전히 candidate. |
| project | confirmed/candidate | 정규 ID | false/true | 프로젝트 한정. 명시 정정을 좁게 추정하면 confirmed + true도 가능. |
| null | candidate | null | false | 범위를 특정 못 했고 프로젝트 문맥도 없음. 자동 적용 불가. |

null + confirmed, global + project_id, project + ID 없음, global/null + scope_inferred=true, 문자열 `"true"` 등 타입 오류, 중복 키, 부분 메타데이터는 거부한다. 이유 문자열만으로 사용자 확인을 새로 만들어내지 않는다. 서버는 구조를 검사하고, 저장 호출자는 내용의 근거를 책임진다.

## S2 — 범위가 불명확한 후보와 상태 전이

명시적으로 전역이라고 한 내용은 프로젝트 문맥 없이도 global이 가능하다. 범위가 애매하면 신뢰 가능한 현재 프로젝트 ID로 좁히고 `scope_inferred: true`로 쓴다. 내용 자체가 명시 정정이면 confirmed, 내용 추론이면 candidate다. 현재 프로젝트도 식별 못 하면 `scope: null`, `status: candidate`로 보관하고 `scope_reason`에 문맥 부재를 적는다. 명시 정정이더라도 적용 범위를 못 정한 이유로 격리됐다는 사실은 `status_reason`에 남긴다.

후보는 자동 행동 규칙에서 항상 제외한다. 검토용 조회에는 상태와 이유를 표시하며, 사용자가 범위를 확정하거나 내용 추론을 확인할 때에만 해당 상태를 변경한다. project → global 확대는 사용자 명시 또는 확인 필요. 확인이 내용만 대상으로 했다면 프로젝트 범위는 유지한다. 현재 지시와 충돌하면 이번 작업에서 적용을 중단하고, 영구 변경 여부가 불분명하면 기존 노트를 덮어쓰지 않는다.

검색 구현에 필요한 최소 반환 계약: filename, type, description, 본문 또는 발췌, 위 메타데이터, `metadata_state`를 반환한다. `metadata_state`는 저장 필드가 아니라 `valid/legacy/invalid` 읽기 결과다. 기본 행동용 검색은 valid confirmed 중 global 및 현재 project ID 일치 항목만 허용한다. 프로젝트를 모르면 global만 허용한다. 후보·레거시·invalid는 명시적 검토 조회로 찾을 수 있어야 하며 자동 적용 불가 표시를 붙인다. 다른 프로젝트 필터로 자료를 조회하더라도 현재 작업의 적용 권한은 바뀌지 않는다.

## S3 — 메타데이터 없는 기존 노트와 API 호환

레거시를 일괄 global/confirmed로 간주하거나 읽을 때 파일을 고치지 않는다. 새 필드가 전혀 없으면 `metadata_state=legacy`로 반환하고 새 필드는 미지정(null)으로 표시한다. 이것은 S1의 새 후보 레코드와 다르다. 메타데이터 일부만 있거나 파싱 오류면 invalid로 격리한다. 둘 다 목록·이름 조회·검토 검색에서 보존하지만 자동 적용·핵심 제공에서 제외한다. 기존 내용의 사실성을 부정한 것이 아니라 적용 분류가 미검토라는 뜻이다.

점진적 전환은 노트별 원문·범위·내용 근거 검토 후 명시적으로 저장한다. 읽기, 인덱스 재생성, 검색 자체는 마이그레이션이 아니다. 핵심 승인은 승인된 짧은 본문에만 효력이 있으므로 여러 주제가 섞인 원본 전체를 confirmed global로 바꾸지 않는다. T3에서 승인된 핵심 본문을 별도 노트로 만들 경우 원본은 유지하고 출처 basename을 본문에 기록한다. T2에서는 만들지 않는다.

기존 `memory_get()`은 전체 인덱스, `memory_get(name)`은 원문을 반환하는 계약을 유지한다. 전체 인덱스는 보존하되 항상 제공하는 핵심과 구분한다. 기존 `memory_save(kind, slug, description, body, tags=None)` 호출 형태도 유지하고 새 메타데이터 인자는 선택 확장한다.

- 구형 호출의 신규 노트: 문맥 인자가 없으므로 S2의 범위 미정 candidate로 저장하고 반환에 격리 사실을 알린다.
- 구형 호출의 레거시 노트 갱신: 기존 형식과 legacy 상태를 보존하고 미검토임을 알린다.
- 이미 v1인 노트를 구형 호출로 갱신: 확정 범위/상태를 무심코 상속하는 내용 변경을 막기 위해 오류로 거부한다. 메타데이터를 포함한 재호출을 안내한다. 이는 호출 형태는 유지하지만 이 갱신 상황에는 의도적인 호환 제한을 둔다.
- v1 갱신은 필드 전체 검증 후 수행한다. 알 수 없는 기존 frontmatter와 `created`, 비대상 원문을 조용히 버리지 않는다. 안전하게 보존하지 못하는 파싱이면 쓰기 전에 오류를 낸다.

기존 `scrub_secrets.scrub_text`, `existing_created`, `write_atomic`, `ensure_index_line`을 재사용한다. 새 자유 텍스트에도 scrub을 적용한다. 실제 정규 ID는 scrub으로 변형되면 저장을 거부한다. 입력·예산 검증 오류는 노트/인덱스 쓰기 전에 반환한다. 파일별 원자 쓰기가 노트와 인덱스의 다중 파일 트랜잭션을 보장한다고 주장하지 않는다. 노트 쓰기 후 인덱스 실패는 부분 실패로 명시하고 재시도로 복구 가능해야 한다.

## S4 — 프로젝트 ID 식별과 정규화

ID는 `prj-` + 소문자 UUID v4(예: `prj-123e4567-e89b-42d3-a456-426614174000`)다. 이 예시는 실프로젝트 등록값이 아니다. 경로명·레포 basename·fixture ID를 프로젝트 ID로 재사용하지 않는다. ID는 처음 등록할 때 로컬에서 생성하고, 이름·경로가 바뀌어도 유지한다.

T3는 볼트의 `projects.json`에 `schema_version: 1`, `projects` 배열을 둔다. 항목은 `id`, `label`, `roots`(절대 경로 배열). ID는 고유, 동일 정규 root의 중복 소유는 거부한다. 이름은 표시용이고 일치 판정에 쓰지 않는다. 원격 URL 자동 추론·네트워크 호출은 하지 않는다. 등록·alias 추가는 사용자가 같은 프로젝트라고 명시한 문맥에서만 한다.

식별 순서: 명시된 등록 ID → 작업 대상 경로의 등록 root 중 가장 긴 조상 경로 → 식별 불가. cwd보다 명시 작업 대상이 우선한다. 명시 ID와 경로가 충돌하거나 여러 작업 대상이 서로 다른 프로젝트면 임의로 하나를 고르지 않고 대상별 분리한다. 분리할 수 없는 기억은 S2의 문맥 없는 후보로 보관한다.

입력 ID는 앞뒤 공백 제거와 ASCII 소문자 변환 후 UUID v4 형식을 검증하고 등록 여부를 확인한다. roots는 `expanduser` → 절대경로 → `realpath` → 끝 구분자 제거(루트 `/` 예외) 순서로 정규화하며 대소문자·Unicode를 임의 변환하지 않는다. 경로 구성요소로 조상 여부를 판정하므로 `/repo-a`가 `/repo-ab`를 포함하지 않는다. 워크트리·다른 checkout은 명시 root alias로 같은 ID에 연결한다. 공통 remote·부모 폴더만 같다는 이유로 자동 통합하지 않는다. monorepo의 하위 프로젝트는 각각 root를 등록할 수 있고 가장 긴 root가 우선한다.

S4 선택의 비용: 새 checkout을 처음 사용할 때 등록이 필요하다. 대신 경로 이동·동명 프로젝트·서로 다른 레포를 하나의 제품으로 묶는 경우를 암묵적으로 잘못 판단하지 않는다. 프로젝트 등록 전에는 후보 저장만 가능하며 이름 유사도로 ID를 생성·선택하지 않는다.

## S5 — 핵심 선정과 예산

핵심은 global + confirmed + scope_inferred=false 중 사용자 승인된 짧은 본문만이다. `status=confirmed`가 핵심 선정을 뜻하지 않는다. T3의 `core-manifest.json` 계약: `schema_version: 1`, `budget_method: "utf8-byte-v1"`, `budget_limit: 2048`, `entries` 배열. 항목은 `id`(K1 등), `source_notes`(basename 배열), `body`(승인된 한 줄 본문), `approved_on`(YYYY-MM-DD), `approval_ref`(확인 기록), `scope: "global"`, `status: "confirmed"`, `scope_inferred: false`. entries 순서가 제공 순서이며 중복 ID·누락 출처·승인 없는 항목은 거부한다. 원본 변경으로 승인 문구가 자동 변경되지 않는다. 원본의 정정/충돌이 드러나면 해당 핵심은 적용을 중단하고 재검토한다.

**2048 예산 단위, 계산은 최종 제공 문자열의 UTF-8 byte 수**로 확정했다. 언어별 문자÷4 추정을 사용하지 않고, 모델 tokenizer 설치·네트워크 없이 두 환경에서 같은 결과를 얻기 위한 보수적인 대리 계산이다. 이것은 실제 Claude/Codex 모델 토큰 수가 아니며 모든 tokenizer의 상한이라는 보장도 하지 않는다. 사용자는 이 대리 계산을 채택했다. 향후 실제 토큰을 정확히 제한하려면 tokenizer와 예산을 별도 변경 합의해야 한다.

계산 규칙: 각 승인 본문의 앞뒤 공백 제거 → 내부 개행 금지 → `# 핵심 기억\n` 다음 각 항목을 `- {body}\n`으로 연결 → `len(rendered.encode("utf-8"))`. NFC 변환은 하지 않는다. 제목·공백·불릿·마지막 LF 포함. 출처·이유·frontmatter·인덱스·환경 연결 지침은 주입 본문 밖이며 예산에서 제외한다. T4는 이 기억 예산과 별도로 전체 프롬프트 비용을 기록한다. 원본·인덱스·검색 결과에 2048 제한을 전파하지 않는다.

2048을 초과하면 핵심 갱신을 쓰기 전에 거부하고 실제 계수와 초과량을 반환한다. 자동 잘라내기·요약·중요도 순 삭제·예산 자동 증가는 금지한다. 사용자에게 수정 본문 또는 검색 전환할 항목을 제시하고 재확인한다. 기존 유효 핵심은 유지한다. 읽을 때 이미 초과·손상된 manifest가 발견되면 핵심 제공 실패를 명시하고 전체 인덱스를 대신 주입하지 않는다. 이 경우 T4 회상 연결 성공으로 기록할 수 없다.

## S6 — 구체 예시와 T3 검증 경계

아래는 기존 5필드에 덧붙일 메타데이터 예시다. 실제 프로젝트 ID 등록이나 볼트 변경이 아니다.

```yaml
# 명시 정정은 확정, 애매한 범위는 현재 프로젝트로 좁힘
memory_schema: 1
scope: project
status: confirmed
project_id: prj-123e4567-e89b-42d3-a456-426614174000
scope_inferred: true
scope_reason: 현재 작업 프로젝트로 범위를 좁힘
status_reason: 사용자가 이 작업의 리뷰 출력에서 진행 서술을 빼라고 명시함
```

```yaml
# 같은 정정이라도 적용할 프로젝트 문맥이 없음
memory_schema: 1
scope: null
status: candidate
project_id: null
scope_inferred: false
scope_reason: 프로젝트 문맥이 없어 적용 범위 미정
status_reason: 명시 정정이지만 범위를 확인할 때까지 후보 격리
```

```yaml
# 관찰을 전역 선호로 추론한 경우: 범위와 확정 여부는 독립
memory_schema: 1
scope: global
status: candidate
project_id: null
scope_inferred: false
scope_reason: 프로젝트 전반에 관한 가설
status_reason: Python 사용 관찰에서 언어 선호를 추론했으며 사용자 확인 없음
```

T3에서 임시 볼트로 잘못된 입력을 거부하는 RED부터 검증할 경계:

1. S1 허용 조합과 거부 조합, metadata 부분 누락·타입·중복 키, 등록 안 된 ID.
2. legacy/invalid가 자동 적용·핵심에서 제외되지만 전체 목록·검토 조회에서 사라지지 않음. 읽기 전후 원본 byte 동일.
3. 구형 저장 호출의 신규/legacy/v1 갱신 정책, created·기존 필드 보존, scrub, 오류 시 파일 미변경, 인덱스 부분 실패 보고.
4. 다른 프로젝트·후보 제외, 같은 ID의 root alias, root 접두사 오인·ID 충돌·대상 전환.
5. 예산 2048은 허용, 2049는 거부. 한글·ASCII·마지막 LF·제목도 계산. 초과 갱신은 기존 핵심/전체 목록 보존.
6. 핵심 승인 없는 confirmed, project confirmed, global candidate는 핵심으로 제공 불가. 승인 원문을 임의 확대·자동 요약하지 않음.

T1 fixture는 평가용 논리 속성 계약 그대로 유지한다. S1 null 후보는 MR-011의 실제 저장 결과에 대응하며 T1 사전 기억 schema를 수정할 이유가 아니다. fixture-*는 T4 임시 registry의 유효 ID로 일관되게 매핑하되 두 환경에 같은 매핑과 행동 기준을 쓴다. K1 선정으로 MR-009가 핵심에서 충족될 경우 키워드 검색 성능을 검증했다고 주장하지 않는다. 모델 행동과 실제 회상 연결 검증은 T4에서 각각 실행한다.
