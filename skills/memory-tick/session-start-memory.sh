#!/bin/bash
# memory-tick SessionStart hook: 개인 메모리 인덱스를 새 세션 컨텍스트에 주입한다.
# fail-open: 항상 exit 0.
MEMORY_MD="${MEMORY_TICK_INDEX:-$HOME/99_memory/memory/MEMORY.md}"

if [ -f "$MEMORY_MD" ]; then
  echo "[personal-memory] 저장된 개인 메모리 인덱스. 관련 항목은 같은 폴더의 해당 파일을 Read해서 참고하라:"
  cat "$MEMORY_MD" 2>/dev/null
fi
exit 0
