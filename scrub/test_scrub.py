#!/usr/bin/env python3
"""scrub_secrets.py 셀프 체크 — python3 test_scrub.py 로 실행. 프레임워크 없음."""

import json
import tempfile
from collections import Counter
from pathlib import Path

from scrub_secrets import scrub_file, scrub_jsonl_line, scrub_text

FAKE_GITLAB = "glpat-" + "a1B2c3D4e5F6g7H8i9J0"
FAKE_SK = "sk-" + "abcdefghij0123456789ABCD"
FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N"
)


def test_vendor_tokens():
    counts = Counter()
    out = scrub_text(f"token={FAKE_GITLAB} and {FAKE_SK}", counts)
    assert FAKE_GITLAB not in out and FAKE_SK not in out, out
    assert "[REDACTED:gitlab]" in out and "[REDACTED:sk]" in out, out
    assert counts["gitlab-token"] == 1 and counts["sk-token"] == 1, counts


def test_env_assign_keeps_var_name():
    counts = Counter()
    out = scrub_text("MY_API_TOKEN=hunter2hunter2 OTHER=short", counts)
    assert out.startswith("MY_API_TOKEN=[REDACTED]"), out
    assert "OTHER=short" in out, out  # 짧은 값·비시크릿 접미사는 안 건드림


def test_env_assign_idempotent():
    counts = Counter()
    once = scrub_text("DB_PASSWORD=supersecretvalue", counts)
    counts2 = Counter()
    twice = scrub_text(once, counts2)
    assert once == twice and not counts2, (once, twice, counts2)


def test_private_tag_span():
    counts = Counter()
    out = scrub_text("before <private>주민번호 123456</private> after", counts)
    assert out == "before [PRIVATE] after", out


def test_jsonl_line_nested_and_valid_json():
    counts = Counter()
    line = json.dumps({"msg": {"content": [f"Bearer {FAKE_JWT}"]}}) + "\n"
    out = scrub_jsonl_line(line, counts)
    parsed = json.loads(out)  # 재직렬화 후에도 유효한 JSON
    assert FAKE_JWT not in out, out
    assert "[REDACTED" in parsed["msg"]["content"][0], parsed


def test_clean_line_preserved_byte_for_byte():
    counts = Counter()
    line = '{"a":  "no secrets here",   "b": 1}\n'  # 일부러 이상한 공백
    out = scrub_jsonl_line(line, counts)
    assert out is line, "변경 없는 줄은 원본 객체 그대로여야 함"


def test_non_json_line_fallback():
    counts = Counter()
    out = scrub_jsonl_line(f"not json {FAKE_SK}\n", counts)
    assert FAKE_SK not in out and out.endswith("\n"), out


def test_file_roundtrip_and_report_mode():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.jsonl"
        dirty = json.dumps({"t": f"MY_SECRET_KEY={FAKE_GITLAB}"}) + "\n"
        clean = '{"t": "clean"}\n'
        p.write_text(dirty + clean, encoding="utf-8")

        counts = scrub_file(p, report_only=True)  # report: 파일 불변
        assert counts and p.read_text() == dirty + clean

        counts = scrub_file(p, report_only=False)  # scrub: 더러운 줄만 교체
        text = p.read_text()
        assert FAKE_GITLAB not in text, text
        assert text.endswith(clean), "깨끗한 줄은 그대로 보존"
        assert not scrub_file(p, report_only=False), "재실행은 no-op"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok {t.__name__}")
    print(f"{len(tests)} checks passed")
