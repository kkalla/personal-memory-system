#!/usr/bin/env python3
"""Claude command hook; validate query shape without reading memory or changing scope."""
import json
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


if __name__ == '__main__':
    print(json.dumps(hook_output(json.load(sys.stdin)), ensure_ascii=False))
