import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/evaluate_case_knowledge.py'


class CaseEvaluation(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('cke', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_prepare_preserves_inputs_separates_case_and_rejects_duplicate(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            a = module.prepare(Path(temp)/'a', 'CKE-001', 'source-only')
            b = module.prepare(Path(temp)/'b', 'CKE-001', 'source-plus-case')
            self.assertEqual((a/'archive/options.txt').read_text(), 'archived\n')
            self.assertEqual((b/'config/options.txt').read_text(), 'current\n')
            self.assertFalse((a/'case.md').exists())
            self.assertTrue((b/'case.md').exists())
            self.assertEqual({p.name:p.read_bytes() for p in (a/'sources').iterdir()},
                             {p.name:p.read_bytes() for p in (b/'sources').iterdir()})
            self.assertFalse((a/'rubric.json').exists())
            with self.assertRaises(FileExistsError):
                module.prepare(Path(temp)/'a', 'CKE-001', 'source-only')

    def test_invalid_inputs_and_campaign_reservations_rejected_before_work(self):
        module = self.module()
        import copy
        original=list(module.load_tasks().values())
        missing=copy.deepcopy(original);missing[0].pop('prompt')
        traversal=copy.deepcopy(original);traversal[0]['files']={'../escape':'x'}
        duplicate=copy.deepcopy(original);duplicate[1]['id']=duplicate[0]['id']
        for tasks in (missing,traversal,duplicate):
            with self.assertRaises(ValueError):module.validate_tasks(tasks)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for i in range(24):
                module.reserve(root, str(i))
            with self.assertRaises(ValueError):module.reserve(root, '24')
            with self.assertRaises(ValueError):module.reserve(root, '0')
            self.assertEqual(len(list((root/'attempts').iterdir())),24)

    def test_process_timeout_preserves_partial_output_and_cannot_be_completed(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            result=module.capture([sys.executable,'-c',
                'import time; print("started",flush=True); time.sleep(20)'],
                '',out,dict(__import__('os').environ),out,0.1)
            self.assertEqual(result['execution'],'timeout')
            self.assertIn('started',(out/'events.jsonl').read_text())
            self.assertEqual(result['exit_code'],124)
            self.assertEqual(module.execution_status('codex',0,[]),'error')
            self.assertEqual(module.execution_status('codex',0,[{'type':'turn.failed'}]),'error')

    def test_runtime_environment_redirects_claude_native_temp_root(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as temp:
            runtime=Path(temp)
            env=module.runtime_environment(runtime,{'HOME':'/original','TMPDIR':'/shared',
                'CLAUDE_CODE_TMPDIR':'/old','ORCA_CALLBACK':'old','MEMORY_VAULT':'real'})
            self.assertEqual(env['CLAUDE_CODE_TMPDIR'],str(runtime/'tmp'))
            self.assertEqual(env['TMPDIR'],str(runtime/'tmp'))
            self.assertNotIn('ORCA_CALLBACK',env)
            self.assertNotIn('MEMORY_VAULT',env)


if __name__ == '__main__':
    unittest.main()
