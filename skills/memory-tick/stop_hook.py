"""Session-scoped, fail-open Stop hook. No vault access or model calls."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

INTERVAL_SEC = 60 * 60


def main():
    event = json.load(sys.stdin)
    if not isinstance(event, dict) or event.get('stop_hook_active', False) is not False:
        return
    session = event.get('session_id')
    if not isinstance(session, str) or not session.strip():
        return
    skill = Path(__file__).resolve().with_name('SKILL.md')
    if not skill.is_file():
        return
    root = Path(os.environ.get('MEMORY_TICK_STATE_DIR',
                              str(Path.home() / '.local/state/personal-memory/memory-tick')))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(session.encode('utf-8')).hexdigest()
    stamp = root / (key + '.stamp')
    fd = os.open(str(stamp), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b') as state:
        # Keep one inode per session; replacing/deleting it would break locking.
        fcntl.flock(state, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = os.fstat(state.fileno())
        if previous.st_size and time.time() - previous.st_mtime < INTERVAL_SEC:
            return
        state.seek(0)
        state.write(b'1')
        state.truncate()
        state.flush()
        os.fsync(state.fileno())
        os.utime(state.fileno(), None)
    print(json.dumps({'decision': 'block', 'reason':
        '[memory-tick] 이번 대화 구간에 저장 가치가 있는 인사이트를 판단하라. '
        f'있으면 {skill} 규칙대로 저장하고 종료하라. '
        '없으면 아무 것도 하지 말고 종료하라.'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError):
        # A failed check must not block the user's turn or print input/secrets.
        pass
