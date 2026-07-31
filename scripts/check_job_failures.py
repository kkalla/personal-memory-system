#!/usr/bin/env python3
"""launchd 잡 실패 감시 — 마지막 종료 코드를 읽어 macOS 알림으로 띄운다.

만든 이유: `/tmp/*.err`는 아무도 안 읽는다. 위키 잡이 등록(2026-07-15) 이후 한 번도
성공하지 못했는데 3일간 아무도 몰랐고, 일일 sync가 SIGTERM(-15)으로 죽은 것도
수동으로 `launchctl list`를 쳐볼 때까지 몰랐다.

각 plist를 셸 래퍼(`sh -c 'cmd || osascript ...'`)로 감싸는 방식을 쓰지 않은 이유:
잘 돌고 있는 잡 4개를 전부 고쳐야 하고, launchd 잡의 TCC 권한은 실행 바이너리에
귀속되므로 래퍼를 끼우면 권한 주체가 `~/.local/bin/secall`에서 `/bin/sh`로 바뀐다.
바깥에서 종료 코드만 읽으면 기존 잡을 건드리지 않고 앞으로 추가되는 잡도 자동으로
커버된다. 대가는 즉시성 — 최대 다음 점검 시각까지 지연된다(하루 두 번이면 충분).

판정 규칙:
- 마지막 종료 코드가 0이 아니면 실패 (음수는 시그널: -15=SIGTERM, -9=SIGKILL)
- RESIDENT에 적힌 상주 잡이 실행 중이 아니면 실패 (KeepAlive인데 죽어 있는 상태)
- 같은 상태를 반복 알림하지 않는다 (상태 파일로 dedupe) — 매일 같은 배너가 뜨면
  결국 무시하게 되고, 그게 원래 문제였던 "아무도 안 읽는 로그"의 재발이다

사용:
    check_job_failures.py              # 점검 + 실패 시 알림 (launchd가 이걸 실행)
    check_job_failures.py --report     # 알림 없이 현황만 출력
    check_job_failures.py --selftest   # 고정 입력으로 판정 로직 검증
"""

import json
import subprocess
import sys
import time
from pathlib import Path

PREFIX = "com.max."
RESIDENT = {"com.max.secall-mcp"}  # 항상 떠 있어야 하는 잡
STATE_FILE = Path.home() / ".claude" / "job_monitor_state.json"
LOG_FILE = Path("/tmp/job-monitor.log")
ERR_TAIL_CHARS = 300

# 위키 잡은 종료 코드로 감시가 안 된다 — 2026-07-31에 두 가지 실패를 실측했는데
# 둘 다 exit 0이었다: ① `claude -p`에 프롬프트가 안 넘어가 잡담만 하고 끝남
# ② 서브에이전트를 600초 상한에 잘리고도 `✓ Wiki update complete.` 출력.
# 그래서 이 잡만은 산출물의 신선도로 판정한다.
WIKI_LABEL = "com.max.secall-wiki"
WIKI_DIR = Path.home() / "99_memory" / "wiki"  # 볼트는 2026-07-30 로컬로 이전됨
WIKI_STALE_DAYS = 8  # 주간(화) 잡이므로 8일이면 한 주를 통째로 건너뛴 것


def launchctl_list() -> str:
    # 절대경로 — launchd가 주는 PATH에 의존하지 않는다
    return subprocess.run(
        ["/bin/launchctl", "list"], capture_output=True, text=True
    ).stdout


def parse(text: str):
    """`launchctl list` 출력 → {label: (pid, status)}. pid/status는 None일 수 있다('-')."""
    jobs = {}
    for line in text.splitlines()[1:]:  # 첫 줄은 헤더
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pid, status, label = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not label.startswith(PREFIX):
            continue
        jobs[label] = (
            int(pid) if pid.lstrip("-").isdigit() else None,
            int(status) if status.lstrip("-").isdigit() else None,
        )
    return jobs


def verdicts(jobs):
    """실패한 잡만 (label, 사유) 리스트로."""
    out = []
    for label, (pid, status) in sorted(jobs.items()):
        if label in RESIDENT:
            # 상주 잡은 KeepAlive로 재시작되므로 "마지막 종료 코드"는 이미 죽은 이전
            # 인스턴스의 것이다 — `launchctl kickstart -k`로 정상 재시작만 해도 -15가
            # 남아 오탐이 난다(2026-07-31 실측). PID 유무가 유일한 신호.
            if pid is None:
                out.append((label, "상주 잡인데 실행 중이 아님"))
        elif status not in (0, None):
            sig = (
                " (SIGTERM)" if status == -15 else " (SIGKILL)" if status == -9 else ""
            )
            out.append((label, "종료 코드 %d%s" % (status, sig)))
    return out


def newest_wiki_mtime():
    """위키 페이지 중 가장 최근 mtime. 디렉토리가 없거나 페이지가 0개면 None."""
    try:
        return max(p.stat().st_mtime for p in WIKI_DIR.rglob("*.md"))
    except (OSError, ValueError):  # ValueError = 빈 시퀀스
        return None


def wiki_stale_reason(newest_mtime, now):
    """위키 산출물이 너무 오래됐으면 사유 문자열, 아니면 None.

    사유에 경과 일수를 넣지 않는다 — 매일 문자열이 달라지면 dedupe가 풀려서 같은
    실패를 매일 알리게 되고, 그게 이 스크립트가 막으려던 "결국 무시하는 알림"이다.
    """
    if newest_mtime is None:
        return "위키 디렉토리가 비었거나 없음 (%s)" % WIKI_DIR
    if now - newest_mtime > WIKI_STALE_DAYS * 86400:
        return "산출물이 %d일 넘게 안 바뀜 (잡이 exit 0이어도 실패)" % WIKI_STALE_DAYS
    return None


def wiki_failure(now):
    """위키 산출물 판정 → (label, 사유) 또는 None."""
    reason = wiki_stale_reason(newest_wiki_mtime(), now)
    return (WIKI_LABEL, reason) if reason else None


def err_tail(label: str) -> str:
    """해당 잡의 stderr 로그 끝부분 — 알림에 원인 힌트를 담기 위해."""
    path = Path("/tmp/%s.err" % label.replace(PREFIX, ""))
    try:
        text = path.read_text(errors="replace").strip()
    except OSError:
        return ""
    return text[-ERR_TAIL_CHARS:]


def notify(title: str, message: str) -> None:
    # osascript는 GUI 세션에 붙어야 배너가 뜬다 — plist를 gui/<uid>로 bootstrap할 것
    script = 'display notification %s with title %s sound name "Basso"' % (
        json.dumps(message),
        json.dumps(title),
    )
    subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def main() -> int:
    report_only = "--report" in sys.argv
    jobs = parse(launchctl_list())
    failures = verdicts(jobs)

    # 종료 코드가 0이어도 산출물이 안 나온 경우를 잡는다. 이미 종료 코드로 실패한
    # 잡이면 사유를 덮어쓰지 않는다 — 그쪽이 더 구체적이다.
    stale = wiki_failure(time.time())
    if stale and not any(label == WIKI_LABEL for label, _ in failures):
        failures.append(stale)

    if report_only:
        for label, (pid, status) in sorted(jobs.items()):
            mark = "✗" if any(label == f[0] for f in failures) else "✓"
            print("%s %-32s pid=%-8s status=%s" % (mark, label, pid, status))
        # 위키 신선도는 launchctl에 안 나오므로 따로 한 줄
        print(
            "%s %-32s %s"
            % (
                "✗" if stale else "✓",
                "(wiki 산출물 신선도)",
                stale[1] if stale else "최근 %d일 내 갱신됨" % WIKI_STALE_DAYS,
            )
        )
        return 1 if failures else 0

    # 상태가 바뀐 것만 알린다 (같은 실패를 매번 다시 알리면 무시하게 된다)
    state = load_state()
    new_state = {label: reason for label, reason in failures}
    fresh = [
        (label, reason) for label, reason in failures if state.get(label) != reason
    ]
    recovered = [label for label in state if label not in new_state]

    if fresh:
        detail = "; ".join(
            "%s %s" % (label.replace(PREFIX, ""), reason) for label, reason in fresh
        )
        notify("launchd 잡 실패", detail)
        with LOG_FILE.open("a") as f:
            for label, reason in fresh:
                f.write("[fail] %s — %s\n%s\n" % (label, reason, err_tail(label)))
    if recovered:
        notify("launchd 잡 복구", ", ".join(l.replace(PREFIX, "") for l in recovered))
        # 알림만 띄우고 로그에 안 남기면 복구 경로가 도는지 확인할 방법이 없다
        with LOG_FILE.open("a") as f:
            for label in recovered:
                f.write("[recovered] %s\n" % label)
        print("RECOVERED " + ", ".join(recovered))

    STATE_FILE.write_text(json.dumps(new_state, indent=0, ensure_ascii=False))
    for label, reason in failures:
        print("FAIL %s — %s" % (label, reason))
    print(
        "[monitor] %d jobs checked, %d failing, %d newly notified"
        % (len(jobs), len(failures), len(fresh))
    )
    return 0


def selftest() -> int:
    sample = "\n".join(
        [
            "PID\tStatus\tLabel",
            "-\t0\tcom.max.secall-wiki",
            "-\t-15\tcom.max.secall-sync",
            "-\t1\tcom.max.secall-scrub",
            "13017\t0\tcom.max.secall-mcp",
            "-\t0\tcom.apple.something",  # 접두어 불일치 → 무시
            "garbage line",
        ]
    )
    jobs = parse(sample)
    assert set(jobs) == {
        "com.max.secall-wiki",
        "com.max.secall-sync",
        "com.max.secall-scrub",
        "com.max.secall-mcp",
    }, jobs
    got = dict(verdicts(jobs))
    assert "com.max.secall-sync" in got and "SIGTERM" in got["com.max.secall-sync"], got
    assert "com.max.secall-scrub" in got, got
    assert "com.max.secall-wiki" not in got, got  # exit 0은 실패 아님
    assert "com.max.secall-mcp" not in got, got  # 상주 + pid 있음 → 정상

    # 상주 잡이 죽은 경우
    dead = parse(
        sample.replace("13017\t0\tcom.max.secall-mcp", "-\t0\tcom.max.secall-mcp")
    )
    assert "상주" in dict(verdicts(dead))["com.max.secall-mcp"]

    # 상주 잡을 kickstart -k로 재시작하면 이전 인스턴스의 -15가 남는다 — 실행 중이면 정상
    restarted = parse(
        sample.replace("13017\t0\tcom.max.secall-mcp", "61236\t-15\tcom.max.secall-mcp")
    )
    assert "com.max.secall-mcp" not in dict(verdicts(restarted)), verdicts(restarted)

    # status가 '-'(한 번도 안 돌았거나 알 수 없음)면 실패로 보지 않는다
    unknown = parse("PID\tStatus\tLabel\n-\t-\tcom.max.never-ran")
    assert unknown["com.max.never-ran"] == (None, None), unknown
    assert verdicts(unknown) == [], verdicts(unknown)

    # 위키 산출물 신선도 — 잡이 exit 0이어도 실패로 잡아야 하는 케이스
    now = 100 * 86400
    assert wiki_stale_reason(now - 3 * 86400, now) is None  # 3일 전 갱신 → 정상
    assert wiki_stale_reason(now - 9 * 86400, now) is not None  # 9일 → 한 주 건너뜀
    assert wiki_stale_reason(None, now) is not None  # 위키가 통째로 없음
    # dedupe가 풀리지 않도록 사유 문자열이 경과 시간에 따라 변하면 안 된다
    assert wiki_stale_reason(now - 9 * 86400, now) == wiki_stale_reason(
        now - 30 * 86400, now
    )

    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
