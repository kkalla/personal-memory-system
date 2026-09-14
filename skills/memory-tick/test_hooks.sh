#!/bin/bash
# memory-tick hook 스크립트 셀프 체크. bats 없이 bash만 사용.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAIL: $1"; exit 1; }

# Stop 훅의 JSON/세션/60분/재귀/동시 호출/오류 경계를 임시 상태에서 검증한다.
/usr/bin/python3 -m unittest discover -s "$DIR/../../tests" -p 'test_memory_tick_hook.py' -v || exit 1
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
