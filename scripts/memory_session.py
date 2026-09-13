#!/usr/bin/env python3
"""Shared Claude Code / Codex SessionStart JSON, Python 3.9 compatible."""
import json
from pathlib import Path
import sys

import memory_mcp as memory


def session_output():
    instructions = Path(__file__).with_name('memory-retrieval-instructions.md').read_text(encoding='utf-8')
    result = {}
    try:
        core = memory.memory_core_get()
    except ValueError as exc:
        core = ''
        result['systemMessage'] = str(exc)
        instructions += '\n핵심 제공 실패: 이 세션의 핵심 회상 연결은 미성공이다.\n'
    result['hookSpecificOutput'] = dict(hookEventName='SessionStart', additionalContext=core + '\n' + instructions)
    return result


if __name__ == '__main__':
    sys.stdout.write(json.dumps(session_output(), ensure_ascii=False) + '\n')
