#!/usr/bin/env python3
"""Shared Claude Code / Codex SessionStart JSON, Python 3.9 compatible."""
import json
import sys

import memory_mcp as memory


def session_output():
    result = {}
    try:
        core = memory.memory_core_get()
    except ValueError as exc:
        core = ''
        result['systemMessage'] = str(exc)
        core = '핵심 제공 실패: 이 세션의 핵심 회상 연결은 미성공이다.'
    result['hookSpecificOutput'] = dict(hookEventName='SessionStart', additionalContext=core)
    return result


if __name__ == '__main__':
    sys.stdout.write(json.dumps(session_output(), ensure_ascii=False) + '\n')
