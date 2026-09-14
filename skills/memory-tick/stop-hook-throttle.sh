#!/bin/bash
# memory-tick Stop hook: 세션별 60분에 한 번 저장 가치 평가를 요청한다.
# fail-open: 입력/상태/실행 오류에는 무출력으로 종료한다.
DIR="$(cd "$(dirname "$0")" && pwd)" || exit 0
/usr/bin/python3 "$DIR/stop_hook.py" 2>/dev/null || :
exit 0
