#!/usr/bin/env python3
"""메모리 볼트 읽기/쓰기 MCP 서버 (stdio, 의존성 없음).

훅이 없는 CLI(agy·codex·hermes)에 개인 메모리를 붙이는 레이어. 읽기는 secall MCP로
안 되는데, secall이 인덱싱하는 건 `raw/.sessions/`뿐이고 `memory/*.md`는 대상이 아니다
(2026-07-30 실측). 쓰기는 memory-tick 포맷(frontmatter 5필드 + 인덱스 줄)을 매번 손으로
맞추면 조용히 깨진 노트가 남으므로 툴로 고정한다.

- 프로토콜: JSON-RPC 2.0 / 줄단위 JSON. stdout은 프로토콜 전용, 로그는 stderr.
- 시크릿: scrub/scrub_secrets.py의 패턴을 그대로 재사용해 쓰기 직전에 마스킹한다.
  (import 실패 시 서버가 아예 안 뜬다 — 평문으로 쓰는 것보다 시끄럽게 죽는 게 낫다)
- 파이썬: /usr/bin/python3(3.9) 호환. 3.10+ 문법 금지.

사용:
    memory_mcp.py              # MCP 서버 (stdio)
    memory_mcp.py --selftest   # 임시 볼트로 왕복 검증
"""

import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrub"))
from scrub_secrets import scrub_text  # noqa: E402

PROTOCOL = "2025-06-18"
VAULT = Path(os.environ.get("MEMORY_VAULT", str(Path.home() / "99_memory" / "memory")))
INDEX = "MEMORY.md"
TYPES = ("user", "feedback", "project", "reference")
SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class MethodNotFound(Exception):
    pass


def write_atomic(path: Path, text: str) -> None:
    """항상 전체 쓰기 + 원자적 교체. append 금지 규칙 준수."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".mcp-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def yaml_line(key: str, value: str) -> str:
    """콜론+공백이 든 값은 plain scalar로 못 쓴다 — 그때만 인용."""
    if ": " in value or value[:1] in "\"'[{&*!|>%@`#-?":
        return '%s: "%s"' % (key, value.replace("\\", "\\\\").replace('"', '\\"'))
    return "%s: %s" % (key, value)


def existing_created(path: Path) -> str:
    """갱신 시 created 날짜 보존 — 기존 노트를 고쳤다고 생성일이 오늘이 되면 안 된다."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines()[:10]:
            if line.startswith("created:"):
                return line.split(":", 1)[1].strip()
    return date.today().isoformat()


def ensure_index_line(slug: str, filename: str, description: str) -> str:
    """인덱스에 없으면 한 줄 추가. 있으면 손대지 않는다(사람이 다듬은 훅 보존)."""
    path = VAULT / INDEX
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Memory Index", ""]
    if any(("](%s)" % filename) in ln for ln in lines):
        return "index kept"
    lines.append("- [%s](%s) — %s" % (slug, filename, description))
    write_atomic(path, "\n".join(lines) + "\n")
    return "index added"


def memory_save(kind: str, slug: str, description: str, body: str, tags=None) -> str:
    if kind not in TYPES:
        raise ValueError(
            "type은 %s 중 하나여야 함 (받음: %r)" % ("|".join(TYPES), kind)
        )
    if not SLUG_RX.match(slug or ""):
        raise ValueError(
            "slug은 kebab-case(소문자·숫자·하이픈)여야 함 (받음: %r)" % slug
        )
    if not (description or "").strip() or not (body or "").strip():
        raise ValueError("description과 body는 비울 수 없음")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = list(tags or [])

    counts = Counter()
    description = scrub_text(" ".join(description.split()), counts)
    body = scrub_text(body, counts)
    tags = [scrub_text(t, counts) for t in tags]

    path = VAULT / ("%s_%s.md" % (kind, slug))
    action = "updated" if path.exists() else "created"
    front = [
        "---",
        yaml_line("name", slug),
        yaml_line("description", description),
        "type: %s" % kind,
        "tags: [%s]" % ", ".join(tags),
        "created: %s" % existing_created(path),
        "---",
        "",
        "",  # frontmatter와 본문 사이 빈 줄 — 기존 노트 포맷과 동일하게
    ]
    write_atomic(path, "\n".join(front) + body.rstrip() + "\n")

    result = "%s %s (%s)" % (
        action,
        path.name,
        ensure_index_line(slug, path.name, description),
    )
    if counts:
        result += " / 마스킹: " + ", ".join(
            "%s x%d" % kv for kv in sorted(counts.items())
        )
    return result


def memory_get(name=None) -> str:
    if not name:
        return (VAULT / INDEX).read_text(encoding="utf-8")
    if "/" in name or ".." in name:
        raise ValueError("경로가 아니라 노트 이름/슬러그를 줄 것 (받음: %r)" % name)
    for candidate in (name, name + ".md"):
        path = VAULT / candidate
        if path.is_file():
            return path.read_text(encoding="utf-8")
    hits = sorted(VAULT.glob("*_%s.md" % name))
    if len(hits) == 1:
        return hits[0].read_text(encoding="utf-8")
    if not hits:
        raise ValueError("그런 노트 없음: %r — memory_get()으로 인덱스부터 확인" % name)
    raise ValueError("여러 개 매칭: %s" % ", ".join(p.name for p in hits))


TOOLS = [
    {
        "name": "memory_get",
        "description": (
            "개인 메모리를 읽는다. 인자 없이 호출하면 전체 인덱스(한 줄 요약 목록), "
            "name을 주면 그 노트 전문. **세션 시작 시 인자 없이 한 번 호출해 인덱스를 먼저 보고**, "
            "지금 하는 일과 관련된 항목만 name으로 펼쳐 읽어라."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "노트 슬러그(예: cross-cli-config-sharing) 또는 파일명. 생략하면 인덱스",
                }
            },
        },
    },
    {
        "name": "memory_save",
        "description": (
            "개인 메모리에 노트를 저장한다(같은 type+slug이면 갱신). 저장 대상: 사용자 선호·정정 "
            "피드백, 반복되는 교훈, 코드로 알 수 없는 프로젝트 제약, 외부 참조(URL·티켓). "
            "저장하지 않을 것: 코드/git 히스토리가 이미 기록하는 것, 이 대화에서만 유효한 것. "
            "먼저 memory_get으로 기존 노트를 확인해 중복이면 새 슬러그 대신 그 노트를 갱신하라. "
            "관찰한 사실과 추측을 섞지 말고, 확인 못 한 건 '미확인:'으로 표시하라. "
            "시크릿 값은 넣지 마라(서버가 마스킹하지만 애초에 안 넣는 게 맞다)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": list(TYPES),
                    "description": "노트 종류",
                },
                "slug": {
                    "type": "string",
                    "description": "kebab-case 식별자. 파일명은 {kind}_{slug}.md",
                },
                "description": {
                    "type": "string",
                    "description": "한 줄 요약 — 회상 시 관련성 판단에 쓰임",
                },
                "body": {
                    "type": "string",
                    "description": (
                        "마크다운 본문. feedback/project는 '**Why:**'와 '**How to apply:**' 줄을 포함. "
                        "관련 노트는 [[슬러그]]로 링크"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "태그 목록",
                },
            },
            "required": ["kind", "slug", "description", "body"],
        },
    },
]

DISPATCH = {"memory_get": memory_get, "memory_save": memory_save}


def handle(req):
    method = req.get("method")
    params = req.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "memory", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "ping":
        return {}
    if method == "tools/call":
        fn = DISPATCH.get(params.get("name") or "")
        if fn is None:
            return {
                "content": [
                    {"type": "text", "text": "그런 툴 없음: %s" % params.get("name")}
                ],
                "isError": True,
            }
        try:
            return {
                "content": [
                    {"type": "text", "text": fn(**(params.get("arguments") or {}))}
                ]
            }
        except Exception as exc:  # 툴 오류는 모델이 고칠 수 있게 결과로 돌려준다
            return {
                "content": [{"type": "text", "text": "오류: %s" % exc}],
                "isError": True,
            }
    raise MethodNotFound(method)


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if "id" not in req:
            continue  # 알림(notifications/initialized 등)은 응답하지 않는다
        try:
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": handle(req)}
        except MethodNotFound as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": req["id"],
                "error": {"code": -32601, "message": "Method not found: %s" % exc},
            }
        except Exception as exc:
            resp = {
                "jsonrpc": "2.0",
                "id": req["id"],
                "error": {"code": -32603, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def selftest() -> int:
    global VAULT
    tmpdir = tempfile.mkdtemp()
    VAULT = Path(tmpdir)
    (VAULT / INDEX).write_text("# Memory Index\n\n", encoding="utf-8")

    assert (
        handle({"method": "initialize", "params": {"protocolVersion": "2024-11-05"}})[
            "protocolVersion"
        ]
        == "2024-11-05"
    )
    assert [t["name"] for t in handle({"method": "tools/list"})["tools"]] == [
        "memory_get",
        "memory_save",
    ]

    def call(name, args):
        return handle(
            {"method": "tools/call", "params": {"name": name, "arguments": args}}
        )

    # 가짜 토큰은 런타임에 조립한다 — 리터럴로 두면 scrub_secrets.py --report가
    # 이 파일을 영구히 시크릿 보유로 플래그해서 진짜 유출을 가린다
    fake_token = "GITLAB_TOKEN=glpat-" + "x" * 24
    out = call(
        "memory_save",
        {
            "kind": "feedback",
            "slug": "test-note",
            "tags": ["a", "b"],
            "description": "요약: 콜론 든 설명",
            "body": "본문\n%s\n" % fake_token,
        },
    )
    text = out["content"][0]["text"]
    assert "created feedback_test-note.md" in text and "index added" in text, text
    assert "gitlab-token x1" in text, text

    note = call("memory_get", {"name": "test-note"})["content"][0]["text"]
    assert (
        'description: "요약: 콜론 든 설명"' in note
    ), note  # 인용 없으면 YAML이 깨진다
    assert "tags: [a, b]" in note and "type: feedback" in note, note
    assert "glpat-" not in note and "[REDACTED:gitlab]" in note, note

    index = call("memory_get", {})["content"][0]["text"]
    assert "- [test-note](feedback_test-note.md) — 요약: 콜론 든 설명" in index, index

    created = [ln for ln in note.splitlines() if ln.startswith("created:")][0]
    (VAULT / "feedback_test-note.md").write_text(
        note.replace(created, "created: 2020-01-01"), encoding="utf-8"
    )
    again = call(
        "memory_save",
        {
            "kind": "feedback",
            "slug": "test-note",
            "description": "갱신",
            "body": "새 본문",
        },
    )
    assert (
        "updated" in again["content"][0]["text"]
        and "index kept" in again["content"][0]["text"]
    )
    assert (
        "created: 2020-01-01"
        in call("memory_get", {"name": "test-note"})["content"][0]["text"]
    )
    assert len(index.splitlines()) == len(
        call("memory_get", {})["content"][0]["text"].splitlines()
    )

    for bad in (
        {"kind": "nope", "slug": "x", "description": "d", "body": "b"},
        {"kind": "feedback", "slug": "Bad_Slug", "description": "d", "body": "b"},
        {"kind": "feedback", "slug": "x", "description": " ", "body": "b"},
    ):
        assert call("memory_save", bad).get("isError"), bad
    assert call("memory_get", {"name": "../../etc/passwd"}).get("isError")
    assert call("memory_get", {"name": "nope"}).get("isError")
    assert call("nope", {}).get("isError")

    print("selftest OK (%s)" % tmpdir)
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else serve())
