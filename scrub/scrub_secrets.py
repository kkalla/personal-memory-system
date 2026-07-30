#!/usr/bin/env python3
"""세션 아카이브 시크릿 스크러버.

Claude Code 로컬 세션 JSONL(~/.claude/projects + ~/.claude-work/projects)에서
시크릿 패턴과 <private>...</private> 스팬을 마스킹한다. secall sync(09:00)가
읽기 전인 08:45에 launchd로 실행되므로 하류(vault/raw/FTS 인덱스)에 평문이 안 남는다.

원칙:
- 시크릿 값은 절대 로그에 출력하지 않는다 — 룰명 x 개수만
- 수정이 생긴 줄만 재직렬화하고, 나머지 줄은 바이트 그대로 보존
- 진행 중 세션 보호: 최근 30분 내 수정된 파일은 건너뜀 (다음 실행에서 처리)

사용:
    scrub_secrets.py                      # 기본: 개인용+업무용 세션 루트 스캔+마스킹
    scrub_secrets.py --report             # 마스킹 없이 개수만 보고
    scrub_secrets.py --paths DIR [DIR..]  # 지정 경로 스캔 (vault 백필용, 상태/나이 필터 없음)
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

# 개인용(~/.claude)과 업무용(CLAUDE_CONFIG_DIR=~/.claude-work) 세션 루트 둘 다.
# 업무용이 빠지면 GITLAB_TOKEN 류가 마스킹 없이 vault(iCloud)로 올라간다.
DEFAULT_ROOTS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".claude-work" / "projects",
]
# 상태는 절대경로 키라 두 루트를 한 파일에서 같이 추적해도 안전하다.
STATE_FILE = Path.home() / ".claude" / "scrub_state.json"
MIN_AGE_SECONDS = 30 * 60  # 진행 중 세션 append와의 경쟁 회피

# (룰명, 정규식, 치환) — 형식이 확실한 패턴만. 엔트로피 탐지는 JSONL의
# UUID/해시 바다에서 오탐 폭탄이라 쓰지 않는다.
PATTERNS = [
    ("private-tag", re.compile(r"<private>.*?</private>", re.S), "[PRIVATE]"),
    (
        "pem-block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED:pem]",
    ),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws]"),
    (
        "github-token",
        re.compile(
            r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"
        ),
        "[REDACTED:github]",
    ),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:gitlab]"),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED:slack]",
    ),
    ("sk-token", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:sk]"),
    ("notion-token", re.compile(r"\bntn_[A-Za-z0-9]{20,}\b"), "[REDACTED:notion]"),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"
        ),
        "[REDACTED:jwt]",
    ),
    (
        "bearer",
        re.compile(r"\bBearer\s+(?!\[REDACTED)[A-Za-z0-9_\-\.=]{20,}"),
        "Bearer [REDACTED:bearer]",
    ),
    # env 대입: 변수명은 보존 (검색·문맥 유지), 값만 마스킹
    (
        "env-assign",
        re.compile(
            r"\b([A-Z][A-Z0-9_]*(?:_KEY|_TOKEN|_SECRET|_PASSWORD|_PASSWD|_CREDENTIALS|APIKEY))"
            r"\s*=\s*(?!\[REDACTED)[\"']?[^\s\"']{8,}[\"']?"
        ),
        r"\1=[REDACTED]",
    ),
]


def scrub_text(text, counts):
    for name, rx, repl in PATTERNS:
        text, n = rx.subn(repl, text)
        if n:
            counts[name] += n
    return text


def scrub_value(value, counts):
    if isinstance(value, str):
        return scrub_text(value, counts)
    if isinstance(value, list):
        return [scrub_value(v, counts) for v in value]
    if isinstance(value, dict):
        return {k: scrub_value(v, counts) for k, v in value.items()}
    return value


def scrub_jsonl_line(line, counts):
    """한 줄 처리. 변경 없으면 원본 그대로 반환 (바이트 보존)."""
    stripped = line.rstrip("\n")
    if not stripped:
        return line
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        # JSON이 아닌 줄은 raw 텍스트로 처리
        new = scrub_text(stripped, counts)
        return line if new == stripped else new + "\n"
    line_counts = Counter()
    new_obj = scrub_value(obj, line_counts)
    if not line_counts:
        return line
    new_line = json.dumps(new_obj, ensure_ascii=False) + "\n"
    if new_line == line:
        return line
    counts.update(line_counts)
    return new_line


def scrub_file(path, report_only):
    """파일 하나 처리. 실제 마스킹된 패턴 Counter 반환."""
    counts = Counter()
    out_lines = []
    changed = False
    with open(path, encoding="utf-8") as f:
        if path.suffix == ".jsonl":
            for line in f:
                new_line = scrub_jsonl_line(line, counts)
                changed = changed or (new_line is not line)
                out_lines.append(new_line)
        else:
            text = f.read()
            new_text = scrub_text(text, counts)
            changed = new_text != text
            out_lines = [new_text]
    if changed and counts and not report_only:
        # 같은 디렉토리에 임시 파일 후 원자적 교체 (항상 전체 쓰기 — append 금지 규칙 준수)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".scrub-tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return counts


def collect_targets(paths):
    for p in paths:
        p = Path(p).expanduser()
        if p.is_file():
            yield p
        elif p.is_dir():
            for ext in ("*.jsonl", "*.md"):
                yield from sorted(p.rglob(ext))


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="마스킹 없이 개수만 보고")
    ap.add_argument(
        "--paths",
        nargs="+",
        help="기본 루트 대신 이 경로들을 스캔 (상태/나이 필터 없음)",
    )
    args = ap.parse_args()

    default_mode = not args.paths
    targets = list(collect_targets(args.paths or DEFAULT_ROOTS))
    state = load_state() if default_mode else {}
    now = time.time()

    scanned = modified = total_redactions = 0
    new_state = {}
    for path in targets:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        key = str(path)
        if default_mode:
            if now - mtime < MIN_AGE_SECONDS:
                continue  # 진행 중일 수 있는 세션 — 다음 실행에서 처리
            if state.get(key) == mtime:
                new_state[key] = mtime
                continue
        scanned += 1
        counts = scrub_file(path, args.report)
        if counts:
            modified += 1
            total_redactions += sum(counts.values())
            detail = ", ".join(f"{name} x{n}" for name, n in sorted(counts.items()))
            print(f"{path}: {detail}")
        if default_mode and not args.report:
            new_state[key] = path.stat().st_mtime

    if default_mode and not args.report:
        STATE_FILE.write_text(json.dumps(new_state, indent=0))

    mode = "report" if args.report else "scrub"
    print(
        f"[{mode}] scanned {scanned} files, "
        f"{'flagged' if args.report else 'modified'} {modified}, "
        f"redactions {total_redactions}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
