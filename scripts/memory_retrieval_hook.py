#!/usr/bin/env python3
"""Claude command hook; validate query shape without reading memory or changing scope."""
import json
import fcntl
import hashlib
import os
from pathlib import Path
import tempfile
import sys


def hook_output(event):
    if event.get('tool_name') != 'mcp__memory__memory_search':
        return {}
    if event.get('hook_event_name') != 'PreToolUse':
        return {}
    query = event.get('tool_input', {}).get('query', '')
    if not isinstance(query, str) or len(query.split()) != 1:
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': '검색어는 주제나 대상 종류를 나타내는 핵심 명사 하나만 사용하세요. '
                'AND 조건의 여러 단어 또는 빈 검색어는 허용하지 않습니다. '
                '현재 프로젝트와 필터는 유지하세요. 검색 과정을 사용자에게 설명하지 마세요.'}}
    return {}



def deny(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny', 'permissionDecisionReason': reason}}


def request_output(event, state):
    kind, tool = event.get('hook_event_name'), event.get('tool_name')
    request = event.get('prompt_id')
    if kind == 'UserPromptSubmit':
        state.clear()
        state.update(request=request, searched=False, attempts=0, pending={}, outcome='not_searched', project=None, target_key=None, resolved=False, corrected=False, denials=0)
        return {'hookSpecificOutput': {'hookEventName': kind,
                'additionalContext': '새 요청입니다. 답변·변경·저장 전에 현재 프로젝트의 관련 기억을 검색하세요.'}}
    if state.get('request') != request:
        return deny('현재 요청의 검색 상태를 확인할 수 없습니다.') if kind == 'PreToolUse' else {}
    if kind == 'Stop' and not state.get('searched'):
        if not state['corrected'] and not event.get('stop_hook_active'):
            state['corrected'] = True
            return {'decision': 'block', 'reason': '현재 요청의 검색 완료가 확인되지 않았습니다. 현재 프로젝트의 관련 기억을 먼저 검색하세요. 오류/한도 때문에 불가능하면 미완료로 보고하고 끝내세요.'}
        return {'systemMessage': '현재 요청의 검색 미완료: 연결 검증 실패.'}
    ident = event.get('tool_use_id')
    if kind == 'PreToolUse' and tool == 'mcp__memory__memory_project_resolve':
        state['pending'][ident] = 'resolve'
    if kind == 'PostToolUse' and tool == 'mcp__memory__memory_project_resolve':
        if state['pending'].pop(ident, None) != 'resolve':
            return {}
        response = event.get('tool_response')
        if isinstance(response, dict) and not response.get('isError'):
            response = response.get('content')
        try:
            value = json.loads(response[0]['text'])
            project = value['project_id']
        except (ValueError, KeyError, TypeError, IndexError):
            state['searched'] = False
            state['outcome'] = 'error'
            return {}
        state['resolved'] = True
        target_key = hashlib.sha256(json.dumps(value.get('targets', []), sort_keys=True).encode()).hexdigest()
        if project != state['project'] or target_key != state['target_key']:
            state['target_key'] = target_key
            state.update(project=project, searched=False, outcome='not_searched', attempts=0, pending={})
    if kind == 'PreToolUse' and tool == 'mcp__memory__memory_search':
        inputs = event.get('tool_input', {})
        if state['resolved'] and inputs.get('current_project_id') != state['project']:
            return deny('식별된 현재 프로젝트와 검색 범위가 다릅니다. 현재 프로젝트를 유지하세요.')
        rejected = hook_output(event)
        if rejected:
            return rejected
        if state['attempts'] >= 3:
            return deny('이 문맥의 검색 3회 한도에 도달했습니다. 확인된 결과만 사용하고 미확인은 그대로 보고하세요.')
        state['attempts'] += 1
        state['pending'][ident] = 'search'
    if kind in ('PostToolUse', 'PostToolUseFailure') and tool == 'mcp__memory__memory_search':
        if state['pending'].pop(ident, None) != 'search':
            return {}
        outcome = 'error'
        response = event.get('tool_response')
        if kind == 'PostToolUse':
            if isinstance(response, dict) and not response.get('isError'):
                response = response.get('content')
            if isinstance(response, list):
                try:
                    values = [json.loads(x['text']) for x in response if x.get('type') == 'text']
                    if len(values) == 1 and isinstance(values[0], list):
                        outcome = 'returned' if values[0] else 'empty'
                except (ValueError, KeyError, TypeError):
                    pass
        state['outcome'] = outcome
        state['searched'] = outcome in ('returned', 'empty')
        if outcome == 'empty' and state['attempts'] < 3:
            return {'hookSpecificOutput': {'hookEventName': kind,
                'additionalContext': '현재 검색은 정상 0건입니다. 예시값·파일명 대신 작업 대상 종류를 나타내는 다른 핵심 명사 하나로 다시 검색하세요. 현재 프로젝트·필터를 유지하고 최대 3회를 넘기지 마세요.'}}
    if kind == 'PreToolUse' and tool in ('Write', 'Edit', 'Bash', 'mcp__memory__memory_save') and not state.get('searched'):
        return deny('현재 요청에서 memory_search를 먼저 수행하세요. 검색을 완료하기 전 변경·저장을 진행할 수 없습니다.')
    return hook_output(event)


def process_event(event, directory):
    if not all(isinstance(event.get(k), str) and event[k] for k in ('session_id', 'prompt_id')):
        return {'continue': False, 'stopReason': '요청 식별자가 없어 검색 상태를 확인할 수 없습니다.'}
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    key = hashlib.sha256(str(event.get('session_id')).encode()).hexdigest()
    path = root / (key + '.json')
    lock = os.open(str(root / (key + '.lock')), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock, 'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            if not isinstance(state, dict):
                raise ValueError('invalid state')
            if path.exists():
                expected = {'request': str, 'searched': bool, 'attempts': int, 'pending': dict,
                            'outcome': str, 'resolved': bool, 'corrected': bool, 'denials': int}
                if any(type(state.get(k)) is not t for k, t in expected.items()) or not {'project','target_key'} <= state.keys():
                    raise ValueError('invalid state fields')
        except (ValueError, OSError):
            return {'continue': False, 'stopReason': '검색 상태 손상으로 작업을 중단했습니다. 회상 연결 미완료.'}
        output = request_output(event, state)
        if output.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny':
            state['denials'] = state.get('denials', 0) + 1
            if state['denials'] >= 3:
                output['continue'] = False
                output['stopReason'] = '검색 보정 차단 3회 한도에 도달했습니다. 작업 미완료.'
        fd, tmp = tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return output


if __name__ == '__main__':
    event = json.load(sys.stdin)
    directory = os.environ.get('MEMORY_RETRIEVAL_STATE')
    output = process_event(event, directory) if directory else hook_output(event)
    if os.environ.get('MEMORY_EVAL_TRACE'):
        with open(os.environ['MEMORY_EVAL_TRACE'], 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(event='retrieval_hook', hook_event=event.get('hook_event_name'),
                prompt_id=event.get('prompt_id'), tool_name=event.get('tool_name'),
                tool_use_id=event.get('tool_use_id'), output=output), ensure_ascii=False) + '\n')
    print(json.dumps(output, ensure_ascii=False))
