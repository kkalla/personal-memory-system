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

# --- session-start-memory.sh ---
tmpdir2=$(mktemp -d)

# 1) 인덱스 파일이 없으면 무출력, exit 0
export MEMORY_TICK_INDEX="$tmpdir2/none/MEMORY.md"
out=$("$DIR/session-start-memory.sh")
[ $? -eq 0 ] || fail "인덱스 없어도 exit 0이어야 함"
[ -z "$out" ] || fail "인덱스 없으면 무출력이어야 함"

# 2) 인덱스가 있으면 라벨 + 내용 출력
export MEMORY_TICK_INDEX="$tmpdir2/MEMORY.md"
echo "- [테스트 항목](feedback_test.md) — 후크" > "$MEMORY_TICK_INDEX"
out=$("$DIR/session-start-memory.sh")
echo "$out" | grep -q '\[personal-memory\]' || fail "라벨이 출력되어야 함"
echo "$out" | grep -q '테스트 항목' || fail "인덱스 내용이 출력되어야 함"

rm -rf "$tmpdir2"
echo "PASS: session-start-memory"
