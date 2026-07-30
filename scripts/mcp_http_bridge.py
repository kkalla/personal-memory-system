#!/usr/bin/env python3
"""stdio → streamable HTTP MCP 브릿지 (의존성 0).

stdio만 받는 MCP 클라이언트를 공유 HTTP 서버에 붙인다. 필요한 이유:
`claude_desktop_config.json`은 `command`(stdio) 형태만 유효한 MCP 서버로 인정하고
`{"type":"http","url":...}`은 "not valid MCP server configurations"로 건너뛴다
(2026-07-30 실측 — 앱 번들에 StreamableHTTPClientTransport가 있는 건 커넥터 UI 쪽이다).
그런데 stdio로 `secall mcp`를 직접 띄우면 그 프로세스가 bge-m3 2.1GB를 또 로드한다.
이 브릿지는 모델을 로드하지 않는 파이썬 한 프로세스로, 실제 추론은 공유 서버가 한다.

    Desktop ──stdio──> mcp_http_bridge.py ──HTTP──> com.max.secall-mcp (모델 1개)

사용:
    mcp_http_bridge.py <URL>
    mcp_http_bridge.py --selftest <URL>    # 왕복 검증

ponytail: 요청/응답만 중계한다. 서버가 먼저 보내는 알림(tools/list_changed 등)은
전달하지 않는다 — secall은 그런 걸 보내지 않으므로 GET SSE 스트림을 열지 않는다.
"""

import json
import sys
import urllib.error
import urllib.request

HEADERS = {
    "Content-Type": "application/json",
    # streamable HTTP는 둘 다 요구한다 — 하나만 보내면 406
    "Accept": "application/json, text/event-stream",
}


def parse_body(raw: bytes):
    """SSE 프레임(`data: {...}`) 또는 순수 JSON에서 JSON-RPC 메시지들을 뽑는다."""
    text = raw.decode("utf-8", "replace")
    out = []
    for line in text.splitlines():
        payload = line[5:].strip() if line.startswith("data:") else line.strip()
        if not payload or payload in ("[DONE]",):
            continue
        try:
            out.append(json.loads(payload))
        except ValueError:
            continue
    return out


class Bridge:
    def __init__(self, url: str):
        self.url = url
        self.session = None

    def post(self, msg: dict):
        headers = dict(HEADERS)
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(
            self.url,
            data=json.dumps(msg).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session = sid
                return parse_body(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace").strip()
            if msg.get("id") is None:
                return []  # 알림 실패는 조용히 버린다 (응답할 id가 없다)
            # HTTP 오류를 JSON-RPC 오류로 번역 — 클라이언트가 연결을 잃지 않게
            return [
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {
                        "code": -32603,
                        "message": "HTTP %d: %s" % (exc.code, body[:200]),
                    },
                }
            ]
        except Exception as exc:
            if msg.get("id") is None:
                return []
            return [
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32603, "message": "bridge: %s" % exc},
                }
            ]


def serve(url: str) -> int:
    bridge = Bridge(url)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        for out in bridge.post(msg):
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def selftest(url: str) -> int:
    b = Bridge(url)
    init = b.post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bridge-selftest", "version": "0"},
            },
        }
    )
    assert init and init[0]["result"]["serverInfo"]["name"], init
    assert b.session, "Mcp-Session-Id를 못 받았다"
    b.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = b.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in tools[0]["result"]["tools"]]
    assert names, tools
    call = b.post(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "status", "arguments": {}},
        }
    )
    assert call[0]["result"]["content"][0]["text"], call
    bad = b.post({"jsonrpc": "2.0", "id": 4, "method": "nope/nope"})
    assert bad and ("error" in bad[0] or bad[0].get("result")), bad  # 죽지 않고 응답
    print("selftest OK — tools:", names)
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        sys.exit(selftest(args[1]))
    if not args:
        sys.exit("사용법: mcp_http_bridge.py <URL>")
    sys.exit(serve(args[0]))
