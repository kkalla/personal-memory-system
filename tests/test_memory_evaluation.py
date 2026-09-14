"""T4 preparation seams: isolated state and no answer leakage to model input."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class Preparation(unittest.TestCase):
    def test_preparation_isolated_and_prompt_does_not_disclose_answers(self):
        import evaluate_memory_retrieval as evaluation
        with tempfile.TemporaryDirectory() as tmp:
            suite = evaluation.load_suite()
            case = suite['cases'][7]
            mapping = evaluation.project_mapping(suite)
            first = evaluation.prepare(Path(tmp) / 'first', case, mapping, 'recall-integration')
            second = evaluation.prepare(Path(tmp) / 'second', case, mapping, 'provided-memory')
            prompt = evaluation.prompt_for(case, 0, mapping, 'recall-integration')
            for field in ['expected_behaviors', 'forbidden_behaviors', 'coverage', 'topic_changed']:
                self.assertNotIn(field, prompt)
            self.assertNotIn(case['prior_memories'][0]['body'], prompt)
            self.assertIn(case['prior_memories'][0]['body'], evaluation.prompt_for(case, 0, mapping, 'provided-memory'))
            self.assertEqual(evaluation.snapshot(first['vault']), evaluation.snapshot(second['vault']))
            self.assertNotEqual(first['vault'], second['vault'])
            self.assertEqual(len(evaluation.plan(suite)['runs']), 44)
            self.assertEqual(evaluation.plan(suite)['user_turns'], 52)

    def test_snapshot_preserves_directory_removal_evidence(self):
        import evaluate_memory_retrieval as evaluation
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace, vault = root / 'workspace', root / 'vault'
            workspace.mkdir()
            vault.mkdir()
            source = workspace / 'config'
            source.mkdir()
            (source / 'settings').write_text('restore-data')
            before = evaluation.snapshot_state(workspace, vault)
            archive = workspace / 'archive'
            archive.mkdir()
            (source / 'settings').rename(archive / 'settings')
            source.rmdir()
            after = evaluation.snapshot_state(workspace, vault)
            self.assertEqual(before['directories']['workspace'], ['config'])
            self.assertEqual(after['directories']['workspace'], ['archive'])
            self.assertEqual(after['workspace'], {'archive/settings': 'restore-data'})


class LaunchIsolation(unittest.TestCase):
    def test_runtime_home_contains_only_auth_and_reviewed_hooks(self):
        import evaluate_memory_retrieval as evaluation
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'auth-source'
            source.write_text('test authentication placeholder')
            hooks = {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'reviewed-hook'}]}]}
            for environment, auth_name in [('codex', 'auth.json'), ('claude-code', '.credentials.json')]:
                home = evaluation.runtime_home(root / environment, environment, hooks, source)
                self.assertEqual((home / auth_name).read_text(), source.read_text())
                self.assertEqual(home.stat().st_mode & 0o777, 0o700)
                self.assertFalse((home / 'CLAUDE.md').exists())
                self.assertFalse((home / 'AGENTS.md').exists())
                filename = 'hooks.json' if environment == 'codex' else 'settings.json'
                self.assertEqual(json.loads((home / filename).read_text())['hooks'], hooks)

    def test_recall_launch_delivers_procedure_in_system_instructions(self):
        import subprocess
        from unittest.mock import patch
        import evaluate_memory_retrieval as evaluation
        launches = []
        claude_settings = []
        original_run = subprocess.run

        def cli(command, **kwargs):
            if command[0] not in ('claude', 'codex'):
                return original_run(command, **kwargs)
            if '--version' in command:
                return subprocess.CompletedProcess(command, 0, stdout='test-cli', stderr='')
            launches.append(command)
            if command[0] == 'claude':
                claude_settings.append(json.loads(Path(command[command.index('--settings') + 1]).read_text()))
            events = ([{'type': 'system', 'session_id': 'test-session'},
                       {'type': 'result', 'subtype': 'success', 'is_error': False}]
                      if command[0] == 'claude' else
                      [{'type': 'thread.started', 'thread_id': 'test-session'},
                       {'type': 'turn.completed'}])
            return subprocess.CompletedProcess(command, 0,
                stdout='\n'.join(json.dumps(event) for event in events), stderr='')

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder, filename in [('.claude', '.credentials.json'), ('.codex', 'auth.json')]:
                (root / folder).mkdir()
                (root / folder / filename).write_text('test-only')
            suite = evaluation.load_suite()
            with patch.object(Path, 'home', return_value=root), patch.object(subprocess, 'run', side_effect=cli):
                for environment in ('claude-code', 'codex'):
                    evaluation.run_case(root / environment, suite['cases'][0],
                        evaluation.project_mapping(suite), 'recall-integration', environment)
        claude, codex = launches
        self.assertEqual(claude_settings[0]['hooks']['PreToolUse'][0]['matcher'],
                         'mcp__memory__memory_search')
        contexts = [claude[claude.index('--append-system-prompt') + 1],
                    json.loads(next(arg.split('=', 1)[1] for arg in codex
                                    if arg.startswith('developer_instructions=')))]
        for context in contexts:
            self.assertIn('memory_project_resolve', context)
            self.assertIn('memory_search', context)
            self.assertNotIn('git 미추적 개인 설정·파일을 정리할 때는', context)

class ExecutionEvidence(unittest.TestCase):
    def test_exit_zero_without_completed_turn_is_not_execution_success(self):
        import evaluate_memory_retrieval as evaluation
        self.assertFalse(evaluation.completed_turn('codex', 0, [{'type': 'thread.started', 'thread_id': 's'}]))
        self.assertFalse(evaluation.completed_turn('codex', 0, [{'type': 'turn.failed'}]))
        self.assertFalse(evaluation.completed_turn('claude-code', 0, [{'type': 'result', 'subtype': 'error_max_budget_usd', 'is_error': True}]))
        self.assertTrue(evaluation.completed_turn('codex', 0, [{'type': 'turn.completed'}]))
        self.assertTrue(evaluation.completed_turn('claude-code', 0, [{'type': 'result', 'subtype': 'success', 'is_error': False}]))

class FailureRecording(unittest.TestCase):
    def test_string_error_and_non_object_event_preserve_limit_failure(self):
        import evaluate_memory_retrieval as evaluation
        events = [{'type': 'thread.started', 'thread_id': 'session'},
                  {'type': 'error', 'message': "You've hit your usage limit."},
                  {'type': 'turn.failed', 'error': {'message': "You've hit your usage limit."}},
                  {'type': 'assistant', 'message': {'model': 'test-model'}}, None, 'non-object']
        summary = evaluation.event_summary('codex', 1, events)
        self.assertFalse(summary['completed'])
        self.assertEqual(summary['failure_reason'], 'usage_limit')
        self.assertEqual(summary['session_id'], 'session')
        self.assertEqual(summary['models'], ['test-model'])
        auth = evaluation.event_summary('claude-code', 1, [{'type': 'result', 'is_error': True, 'result': 'Not logged in'}])
        self.assertEqual(auth['failure_reason'], 'authentication_failed')

class BatchBoundary(unittest.TestCase):
    def test_batch_stops_at_limit_and_preserves_unattempted_runs(self):
        import evaluate_memory_retrieval as evaluation
        calls = []
        def blocked_runner(directory, case, mapping, mode, environment):
            calls.append(case['id'])
            directory.mkdir()
            result = dict(case_id=case['id'], environment=environment, mode=mode,
                          execution_status='blocked', failure_reason='usage_limit', steps=[])
            evaluation.write_json(directory / 'result.json', result)
            return result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'batch'
            result = evaluation.run_batch(root, evaluation.load_suite(), 'codex', blocked_runner)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['stop_reason'], 'usage_limit')
            self.assertEqual(result['remaining'], 21)
            # Re-entry must not launch already attempted cases or run past an unresolved limit.
            evaluation.run_batch(root, evaluation.load_suite(), 'codex', blocked_runner)
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
