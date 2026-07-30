#!/usr/bin/env python3
"""MCP stdio 프록시 — agy의 비표준 `server/discover` 프로브만 가로채고 나머지는 그대로 통과.

agy(antigravity-cli)는 MCP 연결을 열면 `initialize` 전에 `server/discover`를 먼저 보낸다.
표준 MCP에 없는 메서드라 엄격한 서버 구현(secall이 쓰는 rmcp)은 그 자리에서
`expect initialized request, but received: ... "server/discover"`를 내고 연결을 끊는다.
관대한 서버(-32601 돌려주고 연결 유지)는 그냥 붙는다 — 이 프록시가 그 관대함만 얹어준다.

즉 이건 agy 쪽 프로토콜 방언을 흡수하는 어댑터고, 그 외 바이트는 손대지 않는다.

사용:
    mcp_shim.py <실제 서버 커맨드> [인자...]
    mcp_shim.py --selftest                 # memory_mcp.py를 감싸 왕복 검증
"""

import json
import subprocess
import sys
import threading
from pathlib import Path

# 가로챌 비표준 메서드. 여기 없는 건 전부 자식에게 그대로 넘긴다.
INTERCEPT = ("server/discover",)


def proxy(argv) -> int:
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert child.stdin is not None and child.stdout is not None  # PIPE로 열었으므로
    child_in, child_out = child.stdin, child.stdout
    out_lock = threading.Lock()

    def emit(data: bytes) -> None:
        with out_lock:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

    def pump_up() -> None:
        for line in child_out:
            emit(line)

    threading.Thread(target=pump_up, daemon=True).start()

    for line in sys.stdin.buffer:
        try:
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")
        except ValueError:
            method = req_id = None
        if method in INTERCEPT:
            if req_id is not None:  # 알림이면 응답 없이 그냥 버린다
                emit(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32601,
                                "message": "Method not found: %s" % method,
                            },
                        }
                    ).encode()
                    + b"\n"
                )
            continue
        child_in.write(line)
        child_in.flush()

    child_in.close()
    return child.wait()


def selftest() -> int:
    target = [sys.executable, str(Path(__file__).resolve().parent / "memory_mcp.py")]
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ]
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *target],
        input="".join(json.dumps(r) + "\n" for r in requests).encode(),
        stdout=subprocess.PIPE,
        timeout=30,
    )
    got = {
        r["id"]: r
        for r in (json.loads(l) for l in proc.stdout.splitlines() if l.strip())
    }
    assert got[1]["error"]["code"] == -32601, got[1]  # discover는 프록시가 답한다
    assert got[2]["result"]["serverInfo"]["name"] == "memory", got[
        2
    ]  # 그 뒤 initialize가 살아있어야 한다
    assert [t["name"] for t in got[3]["result"]["tools"]] == [
        "memory_get",
        "memory_save",
    ], got[3]
    print("selftest OK")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("사용법: mcp_shim.py <실제 서버 커맨드> [인자...]")
    sys.exit(selftest() if args[0] == "--selftest" else proxy(args))
