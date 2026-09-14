"""Claude hook protocol: reject broad AND queries without rewriting scope."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/memory_retrieval_hook.py'


class QueryHook(unittest.TestCase):
    def invoke(self, event):
        result = subprocess.run([sys.executable, str(SCRIPT)],
                                input=json.dumps(event), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_multiword_search_denied_single_word_and_other_tools_unmodified(self):
        event = {'hook_event_name': 'PreToolUse', 'tool_name': 'mcp__memory__memory_search',
                 'tool_input': {'query': 'alpha beta', 'current_project_id': 'prj-example'}}
        value = self.invoke(event)['hookSpecificOutput']
        self.assertEqual(value['permissionDecision'], 'deny')
        self.assertTrue(value['permissionDecisionReason'])
        self.assertNotIn('updatedInput', value)
        event['tool_input']['query'] = 'alpha'
        self.assertEqual(self.invoke(event), {})
        event['tool_name'] = 'Bash'
        event['tool_input'] = {'command': 'echo alpha beta'}
        self.assertEqual(self.invoke(event), {})



if __name__ == '__main__':
    unittest.main()
