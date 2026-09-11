#!/usr/bin/env python3
"""메모리 볼트 읽기/쓰기 MCP 서버 (stdio, 의존성 없음).

훅이 없는 CLI(agy·codex·hermes)에 개인 메모리를 붙이는 레이어. 읽기는 secall MCP로
안 되는데, secall이 인덱싱하는 건 `raw/.sessions/`뿐이고 `memory/*.md`는 대상이 아니다
(2026-07-30 실측). 쓰기는 memory-tick 포맷(frontmatter 5필드 + 인덱스 줄)을 매번 손으로
맞추면 조용히 깨진 노트가 남으므로 툴로 고정한다.

- 프로토콜: JSON-RPC 2.0 / 줄단위 JSON. stdout은 프로토콜 전용, 로그는 stderr.
- 시크릿: scrub/scrub_secrets.py의 패턴을 그대로 재사용해 쓰기 직전에 마스킹한다.
  (import 실패 시 서버가 아예 안 뜬다 — 평문으로 쓰는 것보다 시끄럽게 죽는 게 낫다)
- 파이썬: /usr/bin/python3(3.9) 호환. 3.10+ 문법 금지.

사용:
    memory_mcp.py              # MCP 서버 (stdio)
    memory_mcp.py --selftest   # 임시 볼트로 왕복 검증
"""

import json
import os
import re
import sys
import tempfile
import uuid
from collections import Counter
from memory_contract import (FIELDS, validate_metadata, parse_note, note_state,
                             strict_json, project_id, root_path, one_line, validate_registry)
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrub"))
from scrub_secrets import scrub_text  # noqa: E402

PROTOCOL = "2025-06-18"
VAULT = Path(os.environ.get("MEMORY_VAULT", str(Path.home() / "99_memory" / "memory")))
INDEX = "MEMORY.md"
TYPES = ("user", "feedback", "project", "reference")
SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class MethodNotFound(Exception):
    pass


def write_atomic(path: Path, text: str) -> None:
    """항상 전체 쓰기 + 원자적 교체. append 금지 규칙 준수."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".mcp-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def yaml_line(key: str, value: str) -> str:
    """JSON string syntax is also safe YAML, including reserved scalar words."""
    return key + ': ' + json.dumps(value, ensure_ascii=False)


def existing_created(path: Path) -> str:
    """갱신 시 created 날짜 보존 — 기존 노트를 고쳤다고 생성일이 오늘이 되면 안 된다."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines()[:10]:
            if line.startswith("created:"):
                return line.split(":", 1)[1].strip()
    return date.today().isoformat()


def ensure_index_line(slug: str, filename: str, description: str) -> str:
    """인덱스에 없으면 한 줄 추가. 있으면 손대지 않는다(사람이 다듬은 훅 보존)."""
    path = VAULT / INDEX
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Memory Index", ""]
    if any(("](%s)" % filename) in ln for ln in lines):
        return "index kept"
    lines.append("- [%s](%s) — %s" % (slug, filename, description))
    write_atomic(path, "\n".join(lines) + "\n")
    return "index added"


def load_registry():
    path = VAULT / 'projects.json'
    if not path.exists():
        return dict(schema_version=1, projects=[])
    return validate_registry(strict_json(path.read_text(encoding='utf-8')))


def registered_ids():
    return {entry['id'] for entry in load_registry()['projects']}


def registered_id(value):
    identity = project_id(value)
    if identity not in registered_ids():
        raise ValueError('unregistered project_id')
    if scrub_text(identity, Counter()) != identity:
        raise ValueError('scrub changed project_id')
    return identity


def memory_project_register(label, roots, confirmed=False, existing_id=None):
    """Explicit registration only; existing_id adds aliases to the same project."""
    if confirmed is not True:
        raise ValueError('registration/alias requires explicit user confirmation')
    label = scrub_text(one_line(label, 'label'), Counter())
    if not isinstance(roots, list) or not roots:
        raise ValueError('roots must be a nonempty array')
    roots = [root_path(root) for root in roots]
    if any(scrub_text(root, Counter()) != root for root in roots):
        raise ValueError('scrub would change root identity')
    registry = load_registry()
    if existing_id is None:
        identity = 'prj-' + str(uuid.uuid4())
        registry['projects'].append(dict(id=identity, label=label, roots=roots))
    else:
        identity = registered_id(existing_id)
        entry = next(e for e in registry['projects'] if e['id'] == identity)
        entry['label'] = label
        entry['roots'].extend(root for root in roots if root not in entry['roots'])
    if scrub_text(identity, Counter()) != identity:
        raise ValueError('scrub changed project_id')
    registry = validate_registry(registry)
    write_atomic(VAULT / 'projects.json', json.dumps(registry, ensure_ascii=False, indent=2) + '\n')
    return dict(id=identity)


def memory_project_resolve(explicit_id=None, target_paths=None, cwd=None):
    registry = load_registry()
    identity = registered_id(explicit_id) if explicit_id is not None else None
    if target_paths is not None and (not isinstance(target_paths, list) or any(not isinstance(p, str) for p in target_paths)):
        raise ValueError('target_paths must be a string array')
    paths = target_paths if target_paths else ([cwd] if cwd is not None else [])
    targets = []
    for path in paths:
        path = root_path(path)
        matches = [(root, e['id']) for e in registry['projects'] for root in e['roots']
                   if os.path.commonpath([root, path]) == root]
        match = max(matches, key=lambda pair: len(pair[0]))[1] if matches else None
        conflict = identity is not None and match is not None and identity != match
        targets.append(dict(path=path, project_id=None if conflict else identity or match, conflict=conflict))
    resolved = {t['project_id'] for t in targets}
    ambiguous = any(t['conflict'] for t in targets) or len(resolved) > 1
    return dict(project_id=None if ambiguous else (next(iter(resolved)) if resolved else identity),
                targets=targets, ambiguous=ambiguous)


def memory_search(query='', current_project_id=None, project_filter=None, kind=None, review=False):
    """Case-insensitive AND keyword substring search; no semantic expansion."""
    if not isinstance(query, str) or type(review) is not bool:
        raise ValueError('query must be string; review must be boolean')
    if kind is not None and kind not in TYPES:
        raise ValueError('invalid kind filter')
    current = registered_id(current_project_id) if current_project_id is not None else None
    selected = registered_id(project_filter) if project_filter is not None else None
    ids = registered_ids()
    results = []
    for path in sorted(VAULT.glob('*.md')):
        if not re.fullmatch(r'(user|feedback|project|reference)_.+\.md', path.name):
            continue
        data = path.read_bytes()
        text = data.decode('utf-8', errors='replace')
        values, body, error = {}, text, None
        try:
            data.decode('utf-8')
            values, _, body = parse_note(text)
            state, meta = note_state(values, ids)
            if values.get('type') not in TYPES:
                raise ValueError('invalid note type')
        except ValueError as exc:
            state, meta, error = 'invalid', dict.fromkeys(FIELDS), str(exc)
        note_kind = values.get('type', path.name.split('_', 1)[0])
        applicable = (state == 'valid' and meta['status'] == 'confirmed' and
                      (meta['scope'] == 'global' or
                       (meta['scope'] == 'project' and meta['project_id'] == current)))
        if not review and not applicable:
            continue
        if kind is not None and note_kind != kind:
            continue
        if selected is not None and meta['project_id'] != selected:
            continue
        if not all(word in text.casefold() for word in query.casefold().split()):
            continue
        results.append(dict(filename=path.name, type=note_kind,
                            description=values.get('description'), body=body,
                            metadata_state=state, automatically_applicable=applicable,
                            metadata_error=error, raw_metadata={k: values[k] for k in FIELDS if k in values}, **meta))
    return results


def validate_core(manifest):
    fields = {'schema_version', 'budget_method', 'budget_limit', 'entries'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('invalid core manifest fields')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('invalid core schema_version')
    if manifest['budget_method'] != 'utf8-byte-v1' or type(manifest['budget_limit']) is not int or manifest['budget_limit'] != 2048:
        raise ValueError('core requires utf8-byte-v1 budget_limit 2048')
    if not isinstance(manifest['entries'], list):
        raise ValueError('core entries must be array')
    entries, ids = [], set()
    for original in manifest['entries']:
        if not isinstance(original, dict) or set(original) != {'id', 'source_notes', 'body', 'approved_on', 'approval_ref', 'scope', 'status', 'scope_inferred'}:
            raise ValueError('invalid core entry fields')
        entry = dict(original)
        if isinstance(entry['body'], str):
            entry['body'] = entry['body'].strip()
        for key in ('id', 'body', 'approved_on', 'approval_ref'):
            entry[key] = one_line(entry[key], key)
        if entry['id'] in ids:
            raise ValueError('duplicate core ID')
        ids.add(entry['id'])
        if entry['scope'] != 'global' or entry['status'] != 'confirmed' or entry['scope_inferred'] is not False:
            raise ValueError('core requires global confirmed and scope_inferred=false')
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', entry['approved_on']):
            raise ValueError('approved_on must be YYYY-MM-DD')
        date.fromisoformat(entry['approved_on'])
        names = entry['source_notes']
        if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ValueError('source_notes must be nonempty unique basenames')
        for name in names:
            if not isinstance(name, str) or not re.fullmatch(r'(user|feedback|project|reference)_[a-z0-9][a-z0-9-]*\.md', name):
                raise ValueError('source_notes must be note basenames')
            if not (VAULT / name).is_file():
                raise ValueError('missing core source note')
        # Never silently modify an approved body/reference when scrub detects secrets.
        if scrub_text(json.dumps(entry, ensure_ascii=False), Counter()) != json.dumps(entry, ensure_ascii=False):
            raise ValueError('core contains scrub-sensitive text; revise and reapprove')
        entries.append(entry)
    rendered = '# 핵심 기억\n' + ''.join('- ' + entry['body'] + '\n' for entry in entries)
    used = len(rendered.encode('utf-8'))
    if used > 2048:
        raise ValueError('core budget used %d exceeds 2048 by %d bytes; revise and reapprove' % (used, used - 2048))
    return dict(manifest, entries=entries), rendered, used


def memory_core_initial():
    """Return the frozen approved K1–K4 manifest; never install on read."""
    return strict_json(Path(__file__).with_name('memory-core-approved.json').read_text(encoding='utf-8'))


def memory_core_save(manifest, confirmed=False):
    if confirmed is not True:
        raise ValueError('core update requires explicit approval of exact bodies')
    manifest, _, used = validate_core(manifest)
    write_atomic(VAULT / 'core-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return dict(budget_used=used, budget_limit=2048, budget_method='utf8-byte-v1')


def memory_core_get():
    try:
        _, rendered, _ = validate_core(strict_json((VAULT / 'core-manifest.json').read_text(encoding='utf-8')))
        return rendered
    except (ValueError, OSError, TypeError) as exc:
        raise ValueError('core unavailable: ' + str(exc))


def memory_save(kind: str, slug: str, description: str, body: str, tags=None, metadata=None) -> str:
    if kind not in TYPES:
        raise ValueError(
            "type은 %s 중 하나여야 함 (받음: %r)" % ("|".join(TYPES), kind)
        )
    if not isinstance(slug, str) or not SLUG_RX.fullmatch(slug):
        raise ValueError(
            "slug은 kebab-case(소문자·숫자·하이픈)여야 함 (받음: %r)" % slug
        )
    if scrub_text(slug, Counter()) != slug:
        raise ValueError('scrub would change slug; choose a nonsecret identifier')
    if not isinstance(description, str) or not isinstance(body, str) or not description.strip() or not body.strip():
        raise ValueError("description과 body는 비울 수 없음")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(t, str) for t in tags)):
        raise ValueError("tags must be a string or string array")
    tags = list(tags or [])

    counts = Counter()
    description = scrub_text(" ".join(description.split()), counts)
    body = scrub_text(body, counts)
    tags = [scrub_text(t, counts) for t in tags]

    path = VAULT / ("%s_%s.md" % (kind, slug))
    action = "updated" if path.exists() else "created"
    old, raw = {}, []
    if path.exists():
        old, raw, _ = parse_note(path.read_bytes().decode('utf-8'))
        if metadata is None and any(key in old for key in FIELDS):
            raise ValueError("v1 update requires complete metadata; retry with metadata")
    if metadata is None and not path.exists():
        metadata = dict(memory_schema=1, scope=None, status='candidate', project_id=None,
                        scope_inferred=False, scope_reason='No project context in legacy API',
                        status_reason='Unreviewed legacy API input; isolated candidate')
    if metadata is not None:
        metadata = validate_metadata(metadata, registered_ids())
        for key in ('scope_reason', 'status_reason'):
            metadata[key] = scrub_text(metadata[key], counts)
        if metadata['project_id'] is not None and scrub_text(metadata['project_id'], counts) != metadata['project_id']:
            raise ValueError('scrub changed project_id')
        metadata = validate_metadata(metadata, registered_ids())
    replacement = {
        'name': yaml_line('name', slug),
        'description': yaml_line('description', description),
        'type': 'type: ' + kind,
        'tags': 'tags: [' + ', '.join(json.dumps(t, ensure_ascii=False) for t in tags) + ']',
    }
    if metadata is not None:
        replacement.update({k: k + ': ' + json.dumps(v, ensure_ascii=False) for k, v in metadata.items()})
    front = ['---\n']
    for key, line in raw:
        front.append(replacement.pop(key) + '\n' if key in replacement else line)
    if 'created' not in old:
        front.append('created: ' + existing_created(path) + '\n')
    front.extend(line + '\n' for line in replacement.values())
    front.append('---\n\n')
    # All validation precedes either write. Existing untargeted lines stay byte-identical.
    write_atomic(path, ''.join(front) + body.rstrip() + '\n')
    try:
        index_result = ensure_index_line(slug, path.name, description)
    except OSError:
        raise ValueError('partial failure: note saved; index failed; retry same save with complete metadata to repair index')
    result = '%s %s (%s)' % (action, path.name, index_result)
    if metadata is None:
        result += ' / legacy: unreviewed, not automatically applicable'
    elif metadata['status'] == 'candidate':
        result += ' / candidate: isolated, not automatically applicable'
    if counts:
        result += " / 마스킹: " + ", ".join(
            "%s x%d" % kv for kv in sorted(counts.items())
        )
    return result


def memory_get(name=None) -> str:
    if not name:
        return (VAULT / INDEX).read_text(encoding="utf-8")
    if "/" in name or ".." in name:
        raise ValueError("경로가 아니라 노트 이름/슬러그를 줄 것 (받음: %r)" % name)
    for candidate in (name, name + ".md"):
        path = VAULT / candidate
        if path.is_file():
            return path.read_text(encoding="utf-8")
    hits = sorted(VAULT.glob("*_%s.md" % name))
    if len(hits) == 1:
        return hits[0].read_text(encoding="utf-8")
    if not hits:
        raise ValueError("그런 노트 없음: %r — memory_get()으로 인덱스부터 확인" % name)
    raise ValueError("여러 개 매칭: %s" % ", ".join(p.name for p in hits))


TOOLS = [
    {
        "name": "memory_get",
        "description": (
            "개인 메모리를 읽는다. 인자 없이 호출하면 전체 인덱스(한 줄 요약 목록), "
            "name을 주면 그 노트 전문. **세션 시작 시 인자 없이 한 번 호출해 인덱스를 먼저 보고**, "
            "지금 하는 일과 관련된 항목만 name으로 펼쳐 읽어라."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "노트 슬러그(예: cross-cli-config-sharing) 또는 파일명. 생략하면 인덱스",
                }
            },
        },
    },
    {
        "name": "memory_save",
        "description": (
            "개인 메모리에 노트를 저장한다(같은 type+slug이면 갱신). 저장 대상: 사용자 선호·정정 "
            "피드백, 반복되는 교훈, 코드로 알 수 없는 프로젝트 제약, 외부 참조(URL·티켓). "
            "저장하지 않을 것: 코드/git 히스토리가 이미 기록하는 것, 이 대화에서만 유효한 것. "
            "먼저 memory_get으로 기존 노트를 확인해 중복이면 새 슬러그 대신 그 노트를 갱신하라. "
            "관찰한 사실과 추측을 섞지 말고, 확인 못 한 건 '미확인:'으로 표시하라. "
            "시크릿 값은 넣지 마라(서버가 마스킹하지만 애초에 안 넣는 게 맞다)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(TYPES),
                    "description": "노트 종류",
                },
                "slug": {
                    "type": "string",
                    "description": "kebab-case 식별자. 파일명은 {kind}_{slug}.md",
                },
                "description": {
                    "type": "string",
                    "description": "한 줄 요약 — 회상 시 관련성 판단에 쓰임",
                },
                "body": {
                    "type": "string",
                    "description": (
                        "마크다운 본문. feedback/project는 '**Why:**'와 '**How to apply:**' 줄을 포함. "
                        "관련 노트는 [[슬러그]]로 링크"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "태그 목록",
                },
            },
            "required": ["kind", "slug", "description", "body"],
        },
    },
]

METADATA_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': list(FIELDS),
    'properties': {
        'memory_schema': {'type': 'integer', 'enum': [1]},
        'scope': {'enum': ['global', 'project', None]},
        'status': {'enum': ['confirmed', 'candidate']},
        'project_id': {'type': ['string', 'null']},
        'scope_inferred': {'type': 'boolean'},
        'scope_reason': {'type': 'string'}, 'status_reason': {'type': 'string'},
    },
}
TOOLS[0]['description'] = ('전체 인덱스 또는 이름별 원문 조회. 목록/원문에는 candidate·legacy·invalid도 포함되며 '
                           '자동 적용 승인이 아니다. 항상 제공할 핵심은 memory_core_get, 관련 검색은 memory_search.')
TOOLS[1]['inputSchema']['properties']['metadata'] = METADATA_SCHEMA
TOOLS[1]['description'] += (' metadata는 완전한 v1 집합. 생략한 신규 저장은 scope=null candidate, '
                            'legacy 갱신은 미검토 유지, v1 갱신은 metadata 생략 거부. '
                            '추론은 candidate, 범위 불명은 현재 등록 프로젝트로 좁혀 scope_inferred=true; '
                            '프로젝트 문맥도 없으면 null candidate. 전역 확대/후보 확정은 사용자 근거가 필요하다.')


def tool(name, description, properties=None, required=None):
    return dict(name=name, description=description, inputSchema=dict(
        type='object', properties=properties or {}, required=required or [], additionalProperties=False))


TOOLS.extend([
    tool('memory_search', '키워드 AND 검색. 기본은 현재 문맥의 valid confirmed만. review=true는 격리 항목도 반환. '
         'project_filter는 조회 필터일 뿐 적용 권한을 넓히지 않음. 작업 파악/대상·주제 변경 시 검색.', {
             'query': {'type': 'string'}, 'current_project_id': {'type': 'string'},
             'project_filter': {'type': 'string'}, 'kind': {'enum': list(TYPES)}, 'review': {'type': 'boolean'}}),
    tool('memory_project_resolve', '명시 등록 ID 또는 작업 대상의 최장 root로 식별. 대상 경로가 cwd보다 우선. '
         '충돌/다중 프로젝트는 targets별로 분리하며 공통 project_id는 null.', {
             'explicit_id': {'type': 'string'}, 'target_paths': {'type': 'array', 'items': {'type': 'string'}},
             'cwd': {'type': 'string'}}),
    tool('memory_project_register', '사용자가 동일 프로젝트라고 명시한 경우만 등록/alias 추가. 로컬 UUID v4 생성.', {
        'label': {'type': 'string'}, 'roots': {'type': 'array', 'items': {'type': 'string'}},
        'confirmed': {'type': 'boolean'}, 'existing_id': {'type': 'string'}}, ['label', 'roots', 'confirmed']),
    tool('memory_core_initial', '승인 K1–K4 초기 manifest 반환. 읽기 전용이며 볼트에 설치하지 않음.'),
    tool('memory_core_get', '검증된 승인 핵심 본문만 제공. 손상/2048 UTF-8 byte 초과 시 오류; 인덱스로 대체 안 함. '
         '현재 지시와 충돌한 핵심은 적용 중단하고 재검토; 자동 영구 수정 금지.'),
    tool('memory_core_save', '정확한 본문에 사용자 승인 후 manifest 전체 갱신. confirmed=true는 호출자의 승인 증언. '
         '원본 변경을 승인 본문에 자동 반영하지 않음. 예산 초과/시크릿은 수정·재승인 필요.', {
             'manifest': {'type': 'object'}, 'confirmed': {'type': 'boolean'}}, ['manifest', 'confirmed']),
])
DISPATCH = {fn.__name__: fn for fn in (memory_get, memory_save, memory_search, memory_project_resolve,
                                     memory_project_register, memory_core_initial, memory_core_get, memory_core_save)}


def handle(req):
    method = req.get("method")
    params = req.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "memory", "version": "0.2.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "ping":
        return {}
    if method == "tools/call":
        fn = DISPATCH.get(params.get("name") or "")
        if fn is None:
            return {
                "content": [
                    {"type": "text", "text": "그런 툴 없음: %s" % params.get("name")}
                ],
                "isError": True,
            }
        try:
            value = fn(**(params.get("arguments") or {}))
            return {"content": [{"type": "text", "text": value if isinstance(value, str)
                                 else json.dumps(value, ensure_ascii=False)}]}
        except Exception as exc:  # 툴 오류는 모델이 고칠 수 있게 결과로 돌려준다
            return {
                "content": [{"type": "text", "text": "오류: %s" % exc}],
                "isError": True,
            }
    raise MethodNotFound(method)


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = strict_json(line)
        except ValueError:
            sys.stdout.write(json.dumps(dict(jsonrpc='2.0', id=None,
                                            error=dict(code=-32700, message='Invalid JSON or duplicate key'))) + '\n')
            sys.stdout.flush()
            continue
        if not isinstance(req, dict) or "id" not in req:
            continue  # 알림(notifications/initialized 등)은 응답하지 않는다
        try:
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": handle(req)}
        except MethodNotFound as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": req["id"],
                "error": {"code": -32601, "message": "Method not found: %s" % exc},
            }
        except Exception as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": req["id"],
                "error": {"code": -32603, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def selftest() -> int:
    global VAULT
    tmpdir = tempfile.mkdtemp()
    VAULT = Path(tmpdir)
    (VAULT / INDEX).write_text("# Memory Index\n\n", encoding="utf-8")

    assert (
        handle({"method": "initialize", "params": {"protocolVersion": "2024-11-05"}})[
            "protocolVersion"
        ]
        == "2024-11-05"
    )
    assert [t["name"] for t in handle({"method": "tools/list"})["tools"]] == [
        "memory_get",
        "memory_save", "memory_search", "memory_project_resolve", "memory_project_register",
        "memory_core_initial", "memory_core_get", "memory_core_save",
    ]

    def call(name, args):
        return handle(
            {"method": "tools/call", "params": {"name": name, "arguments": args}}
        )

    # 가짜 토큰은 런타임에 조립한다 — 리터럴로 두면 scrub_secrets.py --report가
    # 이 파일을 영구히 시크릿 보유로 플래그해서 진짜 유출을 가린다
    fake_token = "GITLAB_TOKEN=glpat-" + "x" * 24
    out = call(
        "memory_save",
        {
            "kind": "feedback",
            "slug": "test-note",
            "tags": ["a", "b"],
            "description": "요약: 콜론 든 설명",
            "body": "본문\n%s\n" % fake_token,
        },
    )
    text = out["content"][0]["text"]
    assert "created feedback_test-note.md" in text and "index added" in text, text
    assert "gitlab-token x1" in text, text

    note = call("memory_get", {"name": "test-note"})["content"][0]["text"]
    assert (
        'description: "요약: 콜론 든 설명"' in note
    ), note  # 인용 없으면 YAML이 깨진다
    assert 'tags: ["a", "b"]' in note and "type: feedback" in note, note
    assert "glpat-" not in note and "[REDACTED:gitlab]" in note, note

    index = call("memory_get", {})["content"][0]["text"]
    assert "- [test-note](feedback_test-note.md) — 요약: 콜론 든 설명" in index, index

    created = [ln for ln in note.splitlines() if ln.startswith("created:")][0]
    (VAULT / "feedback_test-note.md").write_text(
        note.replace(created, "created: 2020-01-01"), encoding="utf-8"
    )
    again = call(
        "memory_save",
        {
            "kind": "feedback",
            "slug": "test-note",
            "description": "갱신",
            "body": "새 본문",
            "metadata": dict(memory_schema=1, scope=None, status='candidate', project_id=None,
                             scope_inferred=False, scope_reason='No project context', status_reason='Unreviewed'),
        },
    )
    assert (
        "updated" in again["content"][0]["text"]
        and "index kept" in again["content"][0]["text"]
    )
    assert (
        "created: 2020-01-01"
        in call("memory_get", {"name": "test-note"})["content"][0]["text"]
    )
    assert len(index.splitlines()) == len(
        call("memory_get", {})["content"][0]["text"].splitlines()
    )

    for bad in (
        {"kind": "nope", "slug": "x", "description": "d", "body": "b"},
        {"kind": "feedback", "slug": "Bad_Slug", "description": "d", "body": "b"},
        {"kind": "feedback", "slug": "x", "description": " ", "body": "b"},
    ):
        assert call("memory_save", bad).get("isError"), bad
    assert call("memory_get", {"name": "../../etc/passwd"}).get("isError")
    assert call("memory_get", {"name": "nope"}).get("isError")
    assert call("nope", {}).get("isError")

    print("selftest OK (%s)" % tmpdir)
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else serve())
