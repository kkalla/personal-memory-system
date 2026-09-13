#!/usr/bin/env python3
"""Evaluation transport with trace capture around the real T3 MCP handler."""
import json
import os
from pathlib import Path
import sys
import time

import memory_mcp as memory
from memory_session import session_output


def trace(value):
    path = Path(os.environ['MEMORY_EVAL_TRACE'])
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(dict(time=time.time(), **value), ensure_ascii=False) + '\n')


if '--session' in sys.argv:
    output = session_output()
    trace(dict(event='session_context', output=output))
    print(json.dumps(output, ensure_ascii=False))
else:
    allowed = {'memory_save', 'memory_project_resolve'}
    if os.environ['MEMORY_EVAL_MODE'] == 'recall-integration':
        allowed.update({'memory_search', 'memory_get', 'memory_core_get'})
    for line in sys.stdin:
        try:
            request = memory.strict_json(line)
            if 'id' not in request:
                continue
            if request.get('method') == 'tools/call' and request.get('params', {}).get('name') not in allowed:
                result = dict(isError=True, content=[dict(type='text', text='Tool excluded from evaluation')])
            else:
                result = memory.handle(request)
            if request.get('method') == 'tools/list':
                result = dict(tools=[tool for tool in result['tools'] if tool['name'] in allowed])
            response = dict(jsonrpc='2.0', id=request['id'], result=result)
            trace(dict(event='mcp', request=request, response=response))
        except Exception:
            response = dict(jsonrpc='2.0', id=None, error=dict(code=-32603, message='evaluation transport error'))
        print(json.dumps(response, ensure_ascii=False), flush=True)
