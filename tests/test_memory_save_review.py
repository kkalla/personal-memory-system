"""Saving review is separate from retrieval; fixtures never touch the live vault."""

import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import memory_mcp as m
import memory_retrieval_hook as hook


class SaveReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = m.VAULT
        m.VAULT = Path(self.tmp.name)

    def tearDown(self):
        m.VAULT = self.old
        self.tmp.cleanup()

    def test_review_lane_does_not_bypass_or_reset_retrieval(self):
        state = {}

        def call(kind, ident="s", **inputs):
            return hook.request_output(
                dict(
                    prompt_id="request",
                    hook_event_name=kind,
                    tool_name="mcp__memory__memory_search",
                    tool_use_id=ident,
                    tool_input=inputs,
                    tool_response=[dict(type="text", text="[]")],
                ),
                state,
            )

        call("UserPromptSubmit")
        denied = call("PreToolUse", query="topic", review=True, purpose="save_review")
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        for i in range(3):
            self.assertEqual(call("PreToolUse", str(i), query="topic"), {})
            call("PostToolUse", str(i))
        self.assertEqual(call("PreToolUse", "review", query="topic", review=True, purpose="save_review"), {})
        call("PostToolUse", "review")
        self.assertEqual(state["attempts"], 3)
        self.assertTrue(state["searched"])
        denied = call("PreToolUse", "escape", query="topic", review=True)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        for i in range(2):
            ident = "review-" + str(i)
            self.assertEqual(call("PreToolUse", ident, query="topic", review=True, purpose="save_review"), {})
            call("PostToolUse", ident)
        denied = call("PreToolUse", "exhausted", query="topic", review=True, purpose="save_review")
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(state["attempts"], 3)
        self.assertEqual(state["review_attempts"], 3)

    def test_explicit_review_finds_legacy_without_promoting_it(self):
        path = m.VAULT / "project_original.md"
        path.write_text("---\nname: original\ntype: project\n---\nplanning repository path\n")
        before = path.read_bytes()
        self.assertEqual(m.memory_search("planning"), [])
        rows = m.memory_search("planning", review=True, purpose="save_review")
        self.assertEqual([r["filename"] for r in rows], [path.name])
        self.assertFalse(rows[0]["automatically_applicable"])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            m.memory_search("planning", purpose="save_review")
        with self.assertRaises(ValueError):
            m.memory_search("planning", purpose="unknown")

    def call(self, tool_name, **arguments):
        return m.handle(dict(method="tools/call", params=dict(name=tool_name, arguments=arguments)))

    def test_review_returns_foreign_and_unscoped_notes_without_applying_them(self):
        current = m.memory_project_register("A", ["/fixture-a"], confirmed=True)["id"]
        foreign = m.memory_project_register("B", ["/fixture-b"], confirmed=True)["id"]
        meta = dict(
            memory_schema=1,
            scope="project",
            status="confirmed",
            project_id=foreign,
            scope_inferred=False,
            scope_reason="Project B only",
            status_reason="User decision",
        )
        m.memory_save("project", "foreign", "planning", "Project B path", metadata=meta)
        legacy = m.VAULT / "reference_legacy.md"
        legacy.write_text("planning path; project unknown")
        before = {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()}
        result = self.call(
            "memory_search", query="planning", current_project_id=current, review=True, purpose="save_review"
        )
        rows = json.loads(result["content"][0]["text"])
        self.assertEqual({r["filename"] for r in rows}, {"project_foreign.md", legacy.name})
        self.assertTrue(all(not r["automatically_applicable"] for r in rows))
        self.assertEqual(m.memory_search("planning", current_project_id=current), [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()})

    def test_reviewed_legacy_classification_merge_readback_and_archive(self):
        original = m.VAULT / "project_location.md"
        original.write_text(
            "---\nname: location\ntype: project\ncreated: 2000-01-01\ncustom: keep\n---\nplanning path /repo\n"
        )
        duplicate = m.VAULT / "reference_different-slug.md"
        duplicate.write_text("planning path /repo\ndecision log /repo/.decision-log.md\n")
        duplicate_bytes = duplicate.read_bytes()
        rows = json.loads(
            self.call("memory_search", query="planning", review=True, purpose="save_review")["content"][0]["text"]
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertFalse(self.call("memory_get", name=row["filename"]).get("isError"))
        # Fixture review: both notes explicitly describe /repo; only the decision-log line is new.
        # No registered project or confirmed content: explicitly classify the whole fixture as unscoped candidate.
        meta = dict(
            memory_schema=1,
            scope=None,
            status="candidate",
            project_id=None,
            scope_inferred=False,
            scope_reason="Fixture has no registered project or verified scope",
            status_reason="Legacy content remains unconfirmed after explicit classification",
        )
        merged = "planning path /repo\ndecision log /repo/.decision-log.md"
        saved = self.call(
            "memory_save", kind="project", slug="location", description="planning path", body=merged, metadata=meta
        )
        self.assertFalse(saved.get("isError"))
        readback = self.call("memory_get", name=original.name)["content"][0]["text"]
        self.assertIn(merged, readback)
        self.assertIn("created: 2000-01-01\ncustom: keep", readback)
        self.assertIn('status: "candidate"', readback)
        self.assertIn("scope: null", readback)
        archived = self.call(
            "memory_archive", filename=duplicate.name, reason="Verified fixture merge", replaced_by=original.name
        )
        result = json.loads(archived["content"][0]["text"])
        self.assertEqual(result["status"], "archived")
        self.assertEqual(Path(result["archive_path"]).read_bytes(), duplicate_bytes)
        self.assertEqual(m.memory_search("planning"), [])
        self.assertEqual([r["filename"] for r in m.memory_search("planning", review=True)], [original.name])

    def test_failed_merge_and_partial_archive_have_distinct_outcomes(self):
        m.memory_save("project", "target", "planning", "Original")
        m.memory_save("reference", "duplicate", "planning", "Additional line")
        original = m.memory_get("project_target.md")
        # Caller stops on this error; a failed save does not authorize archive.
        failed = self.call("memory_save", kind="project", slug="target", description="planning", body="Merged")
        self.assertTrue(failed["isError"])
        self.assertEqual(m.memory_get("project_target.md"), original)
        self.assertTrue((m.VAULT / "reference_duplicate.md").exists())
        self.assertFalse((m.VAULT / "archive").exists())
        meta = dict(
            memory_schema=1,
            scope=None,
            status="candidate",
            project_id=None,
            scope_inferred=False,
            scope_reason="No project context in legacy API",
            status_reason="Unreviewed legacy API input; isolated candidate",
        )
        saved = self.call(
            "memory_save",
            kind="project",
            slug="target",
            description="planning",
            body="Original\nAdditional line",
            metadata=meta,
        )
        self.assertFalse(saved.get("isError"))
        self.assertIn("Original\nAdditional line", m.memory_get("project_target.md"))
        self.assertEqual(m.memory_search("planning"), [])
        real_replace = os.replace

        def fail_index(src, dest):
            if Path(dest).name == m.INDEX:
                raise OSError("injected index failure")
            return real_replace(src, dest)

        with patch.object(m.os, "replace", side_effect=fail_index):
            response = self.call(
                "memory_archive",
                filename="reference_duplicate.md",
                reason="Verified merge",
                replaced_by="project_target.md",
            )
        partial = json.loads(response["content"][0]["text"])
        self.assertEqual(partial["status"], "partial_failure")
        self.assertIn("Original\nAdditional line", m.memory_get("project_target.md"))
        self.assertEqual(m.memory_archive(**partial["retry"])["status"], "archived")

    def test_stdio_exposes_and_accepts_save_review_purpose(self):
        request = dict(
            id=1,
            method="tools/call",
            params=dict(name="memory_search", arguments=dict(query="planning", review=True, purpose="save_review")),
        )
        process = subprocess.run(
            [sys.executable, m.__file__],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            check=True,
            env=dict(os.environ, MEMORY_VAULT=str(m.VAULT)),
        )
        result = json.loads(process.stdout)["result"]
        self.assertFalse(result.get("isError"))
        self.assertEqual(json.loads(result["content"][0]["text"]), [])
        schema = next(t for t in m.TOOLS if t["name"] == "memory_search")["inputSchema"]
        self.assertIn("save_review", schema["properties"]["purpose"]["enum"])

    def test_no_new_information_review_leaves_all_files_unchanged(self):
        m.memory_save("reference", "existing", "planning", "planning path /repo")
        before = {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()}
        rows = m.memory_search("planning", review=True, purpose="save_review")
        self.assertEqual(len(rows), 1)
        self.assertIn("planning path /repo", m.memory_get(rows[0]["filename"]))
        # The fixture's proposed information is already present: the documented action is to stop here.
        self.assertEqual(before, {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()})
        self.assertFalse((m.VAULT / "archive").exists())
