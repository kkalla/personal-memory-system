"""Stop hook subprocess contract; all state stays in a temporary directory."""
import json
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'skills/memory-tick/stop-hook-throttle.sh'


class StopHook(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state'
        self.env = dict(os.environ, MEMORY_TICK_STATE_DIR=str(self.state),
                        MEMORY_TICK_MARKER=str(Path(self.temp.name) / 'old-marker'))

    def run_hook(self, event):
        payload = event if isinstance(event, str) else json.dumps(event)
        result = subprocess.run(['/bin/bash', str(HOOK)], input=payload,
                                text=True, capture_output=True, env=self.env, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout) if result.stdout else None

    def test_malformed_input_does_not_request_evaluation(self):
        self.assertIsNone(self.run_hook('not-json'))
        self.assertFalse(self.state.exists())

    def test_sessions_have_independent_sixty_minute_intervals(self):
        self.assertEqual(self.run_hook({'session_id': 'claude-a'})['decision'], 'block')
        self.assertIsNone(self.run_hook({'session_id': 'claude-a'}))
        self.assertEqual(self.run_hook({'session_id': 'codex-b'})['decision'], 'block')
        # State timestamps are the public persisted throttle clock. No wall-clock sleep.
        for p in self.state.glob('*.stamp'):
            os.utime(p, (1, 1))
        self.assertEqual(self.run_hook({'session_id': 'claude-a'})['decision'], 'block')

    def test_busy_session_skips_without_waiting_or_consuming_interval(self):
        self.run_hook({'session_id': 'busy'})
        stamp, = self.state.glob('*.stamp')
        os.utime(stamp, (1, 1))
        with stamp.open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertIsNone(self.run_hook({'session_id': 'busy'}))
        self.assertEqual(self.run_hook({'session_id': 'busy'})['decision'], 'block')

    def test_prompt_points_to_existing_shared_skill(self):
        output = self.run_hook({'session_id': 'path'})
        self.assertIn(str(HOOK.parent / 'SKILL.md'), output['reason'])
        self.assertNotIn('~/.claude/', output['reason'])

    def test_missing_session_and_recursive_events_leave_no_state(self):
        for event in [{}, [], {'session_id': ''}, {'session_id': 1},
                      {'session_id': 's', 'stop_hook_active': True},
                      {'session_id': 's', 'stop_hook_active': 'false'}]:
            with self.subTest(event=event):
                self.assertIsNone(self.run_hook(event))
                self.assertFalse(self.state.exists())

    def test_state_write_failure_is_silent_and_does_not_consume_interval(self):
        self.state.write_text('not a directory')
        self.assertIsNone(self.run_hook({'session_id': 'write-failure'}))
        self.state.unlink()
        self.assertEqual(self.run_hook({'session_id': 'write-failure'})['decision'], 'block')

    def test_sixty_minutes_is_preserved(self):
        self.run_hook({'session_id': 'clock'})
        stamp, = self.state.glob('*.stamp')
        recent = time.time() - 59 * 60
        os.utime(stamp, (recent, recent))
        self.assertIsNone(self.run_hook({'session_id': 'clock'}))
        expired = time.time() - 61 * 60
        os.utime(stamp, (expired, expired))
        self.assertEqual(self.run_hook({'session_id': 'clock'})['decision'], 'block')

    def test_concurrent_same_session_requests_evaluation_once(self):
        processes = [subprocess.Popen(['/bin/bash', str(HOOK)], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                     env=self.env) for _ in range(8)]
        for process in processes:
            process.stdin.write(json.dumps({'session_id': 'concurrent'}))
            process.stdin.close()
            process.stdin = None
        outputs = []
        for process in processes:
            out, err = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(err, '')
            if out:
                outputs.append(json.loads(out))
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]['decision'], 'block')


if __name__ == '__main__':
    unittest.main()
