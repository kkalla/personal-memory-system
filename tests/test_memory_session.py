"""T4 session context boundary: validated core, never full index fallback."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import memory_mcp as m


class SessionContext(unittest.TestCase):
    def test_hook_validates_core_and_reports_failure_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            old = m.VAULT
            try:
                m.VAULT = vault
                manifest = m.memory_core_initial()
                for entry in manifest['entries']:
                    for name in entry['source_notes']:
                        (vault / name).write_text('source')
                m.memory_core_save(manifest, confirmed=True)
            finally:
                m.VAULT = old
            def run():
                return subprocess.run([sys.executable, str(ROOT / 'scripts/memory_session.py')],
                                      input='{}', text=True, capture_output=True,
                                      env=dict(os.environ, MEMORY_VAULT=tmp))
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            context = value['hookSpecificOutput']['additionalContext']
            self.assertIn('# 핵심 기억', context)
            self.assertIn('memory_search', context)
            self.assertIn('memory_project_resolve', context)
            (vault / 'core-manifest.json').write_text('{}')
            (vault / 'MEMORY.md').write_text('DO NOT INJECT FULL INDEX')
            value = json.loads(run().stdout)
            self.assertIn('core unavailable', value['systemMessage'])
            self.assertNotIn('DO NOT INJECT', json.dumps(value))
            self.assertNotIn('# 핵심 기억', value['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
