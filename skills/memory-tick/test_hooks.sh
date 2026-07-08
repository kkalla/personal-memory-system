#!/bin/bash
# memory-tick hook 스크립트 셀프 체크. bats 없이 bash만 사용.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $1"; exit 1; }

# --- stop-hook-throttle.sh ---
tmpdir=$(mktemp -d)
export MEMORY_TICK_MARKER="$tmpdir/marker"

# 1) 마커 없으면(=첫 실행) block JSON 출력
out=$(echo '{}' | "$DIR/stop-hook-throttle.sh")
echo "$out" | grep -q '"decision":"block"' || fail "첫 실행은 block을 출력해야 함"

# 2) 직후 재실행은 스로틀에 걸려 무출력
out=$(echo '{}' | "$DIR/stop-hook-throttle.sh")
[ -z "$out" ] || fail "스로틀 구간 재실행은 무출력이어야 함"

# 3) stop_hook_active=true면 마커 없어도 무출력 (무한루프 방지)
rm -f "$MEMORY_TICK_MARKER"
out=$(echo '{"stop_hook_active": true}' | "$DIR/stop-hook-throttle.sh")
[ -z "$out" ] || fail "stop_hook_active면 무출력이어야 함"

# 4) 어떤 경우에도 exit 0 (fail-open)
echo 'not-json' | "$DIR/stop-hook-throttle.sh" >/dev/null
[ $? -eq 0 ] || fail "비정상 입력에도 exit 0이어야 함"

rm -rf "$tmpdir"
echo "PASS: stop-hook-throttle"
