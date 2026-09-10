"""Local contract checks through the validator CLI; no model or live vault."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_memory_retrieval_cases.py"


def valid_suite():
    return {
        "schema_version": 1,
        "environments": ["claude-code", "codex"],
        "cases": [{
            "id": "MR-001",
            "coverage": ["global-preference"],
            "source_notes": [{"filename": "feedback_example.md", "adaptation": "Synthetic test."}],
            "situation": {"project_id": None, "context": "Isolated sandbox.", "task_rules": []},
            "prior_memories": [{
                "id": "archive", "kind": "feedback", "scope": "global",
                "status": "confirmed", "project_id": None, "scope_inferred": False,
                "body": "Archive unused untracked configuration files.",
            }],
            "steps": [{
                "user_request": "Clean unused settings.", "project_id": None,
                "topic_changed": False,
                "expected_behaviors": ["Move settings into archive/."],
                "forbidden_behaviors": ["Delete the settings permanently."],
            }],
        }],
    }


class ContractCLI(unittest.TestCase):
    def run_json(self, value):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                capture_output=True, text=True, check=False,
            )

    def assert_rejected(self, value, diagnostic):
        result = self.run_json(value)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn("STRUCTURE PASS", result.stdout)

    def test_valid_suite_reports_structure_only(self):
        result = self.run_json(valid_suite())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STRUCTURE PASS: 1 cases", result.stdout)
        self.assertIn("agent behavior NOT RUN; recall integration NOT RUN", result.stdout)

    def test_repository_fixture_is_valid_and_covers_agreed_scenarios(self):
        fixture = ROOT / "tests/fixtures/memory_retrieval/cases.json"
        suite = json.loads(fixture.read_text(encoding="utf-8"))
        result = self.run_json(suite)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({case["id"] for case in suite["cases"]},
                         {"MR-%03d" % number for number in range(1, 12)})
        self.assertEqual({tag for case in suite["cases"] for tag in case["coverage"]}, {
            "global-preference", "project-constraint", "scope-inference", "unrelated-project",
            "candidate-exclusion", "current-instruction-conflict", "one-off-exception",
            "topic-change", "paraphrased-search", "cross-environment", "no-project-context",
        })

    def test_project_candidate_and_empty_memory_inputs_are_valid(self):
        suite = valid_suite()
        suite["cases"][0]["prior_memories"][0].update(
            scope="project", project_id="fixture-project", status="candidate", scope_inferred=True)
        self.assertEqual(self.run_json(suite).returncode, 0)
        suite["cases"][0]["prior_memories"] = []
        self.assertEqual(self.run_json(suite).returncode, 0)

    def test_file_errors_and_ambiguous_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for payload in [None, b'{', b'\xff', b'{"cases": [], "cases": []}',
                            b'{"schema_version": NaN}']:
                with self.subTest(payload=payload):
                    if payload is not None:
                        path.write_bytes(payload)
                    result = subprocess.run([sys.executable, str(VALIDATOR), str(path)],
                                            capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("STRUCTURE FAIL:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    if payload and b'"cases": [], "cases"' in payload:
                        self.assertIn("duplicate JSON key", result.stderr)
                    if payload and b'NaN' in payload:
                        self.assertIn("non-finite JSON number", result.stderr)

    def test_missing_required_case_field_is_rejected(self):
        suite = valid_suite()
        del suite["cases"][0]["situation"]
        self.assert_rejected(suite, "cases[0].situation")

    def test_duplicate_case_id_is_rejected(self):
        suite = valid_suite()
        suite["cases"].append(copy.deepcopy(suite["cases"][0]))
        self.assert_rejected(suite, "cases[1].id: duplicate")

    def test_scope_consistency_and_memory_identity(self):
        for updates, diagnostic in [
            ({"scope": "project", "project_id": None}, ".project_id"),
            ({"scope": "global", "project_id": "fixture-project"}, ".project_id"),
            ({"scope_inferred": True}, ".scope_inferred"),
        ]:
            with self.subTest(updates=updates):
                suite = valid_suite()
                suite["cases"][0]["prior_memories"][0].update(updates)
                self.assert_rejected(suite, diagnostic)
        suite = valid_suite()
        memories = suite["cases"][0]["prior_memories"]
        memories.append(copy.deepcopy(memories[0]))
        self.assert_rejected(suite, "prior_memories[1].id: duplicate")

    def test_contract_shapes_and_required_nested_fields(self):
        # Each mutation represents a distinct malformed caller input.
        mutations = [
            ((), [], "suite"),
            (("schema_version",), True, "schema_version"),
            (("schema_version",), 2, "schema_version"),
            (("environments",), ["codex"], "environments"),
            (("environments",), ["codex", "codex"], "environments"),
            (("cases",), [], "cases"),
            (("cases",), {}, "cases"),
            (("cases", 0), None, "cases[0]"),
            (("cases", 0, "id"), "unstable name", ".id"),
            (("cases", 0, "coverage"), ["unknown"], ".coverage"),
            (("cases", 0, "source_notes"), [], ".source_notes"),
            (("cases", 0, "source_notes", 0, "filename"), "../private.md", ".filename"),
            (("cases", 0, "source_notes", 0, "adaptation"), " ", ".adaptation"),
            (("cases", 0, "situation", "context"), 42, ".context"),
            (("cases", 0, "situation", "task_rules"), "rule", ".task_rules"),
            (("cases", 0, "situation", "project_id"), " ", ".project_id"),
            (("cases", 0, "prior_memories"), {}, ".prior_memories"),
            (("cases", 0, "prior_memories", 0, "body"), "", ".body"),
            (("cases", 0, "prior_memories", 0, "kind"), "other", ".kind"),
            (("cases", 0, "prior_memories", 0, "scope"), "tenant", ".scope"),
            (("cases", 0, "prior_memories", 0, "status"), "inferred", ".status"),
            (("cases", 0, "prior_memories", 0, "scope_inferred"), "false", ".scope_inferred"),
            (("cases", 0, "steps"), [], ".steps"),
            (("cases", 0, "steps", 0, "user_request"), " ", ".user_request"),
            (("cases", 0, "steps", 0, "topic_changed"), 1, ".topic_changed"),
            (("cases", 0, "steps", 0, "expected_behaviors"), [], ".expected_behaviors"),
            (("cases", 0, "steps", 0, "forbidden_behaviors"), [""], ".forbidden_behaviors"),
        ]
        for path, value, diagnostic in mutations:
            with self.subTest(path=path, value=value):
                suite = valid_suite()
                if not path:
                    suite = value
                else:
                    parent = suite
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = value
                self.assert_rejected(suite, diagnostic)

        containers = [(), ("cases", 0), ("cases", 0, "source_notes", 0),
                      ("cases", 0, "situation"), ("cases", 0, "prior_memories", 0),
                      ("cases", 0, "steps", 0)]
        for path in containers:
            parent = valid_suite()
            for key in path:
                parent = parent[key]
            for field in parent:
                with self.subTest(container=path, missing=field):
                    suite = valid_suite()
                    target = suite
                    for key in path:
                        target = target[key]
                    del target[field]
                    self.assert_rejected(suite, field)
            with self.subTest(container=path, unknown="typo"):
                suite = valid_suite()
                target = suite
                for key in path:
                    target = target[key]
                target["typo"] = "unexpected"
                self.assert_rejected(suite, "typo")


if __name__ == "__main__":
    unittest.main()
