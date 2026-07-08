#!/bin/bash
# memory-tick Stop hook: 30분에 한 번, 턴 종료 직전에 메모리 저장 가치 평가를 지시한다.
# fail-open: 어떤 오류도 세션을 막지 않는다 (항상 exit 0).
MARKER="${MEMORY_TICK_MARKER:-$HOME/.claude/memory-tick-last-check}"
INTERVAL_SEC=$((30 * 60))  # ponytail: 고정 30분, 조정은 이 상수만

input=$(cat)

# stop hook 지시로 이미 한 번 이어진 턴이면 재차 지시하지 않는다 (무한루프 방지)
if printf '%s' "$input" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

now=$(date +%s)
if [ -f "$MARKER" ]; then
  last=$(stat -f %m "$MARKER" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$INTERVAL_SEC" ]; then
    exit 0
  fi
fi

touch "$MARKER" 2>/dev/null

cat <<'EOF'
{"decision":"block","reason":"[memory-tick] 이번 대화 구간에 저장 가치가 있는 인사이트(사용자 선호, 반복되는 교훈, 프로젝트 제약, 외부 참조)가 있는지 판단하라. 있으면 ~/.claude/skills/memory-tick/SKILL.md 규칙대로 저장하고 종료하라. 없으면 아무 것도 하지 말고 그대로 종료하라."}
EOF
exit 0
