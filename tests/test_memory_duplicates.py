"""Cross-kind creation conflicts through the save API and real MCP processes."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import memory_mcp as m


class Duplicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = m.VAULT
        m.VAULT = Path(self.tmp.name)

    def tearDown(self):
        m.VAULT = self.old
        self.tmp.cleanup()

    def snapshot(self):
        return {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()}

    def test_new_kind_rejected_for_all_active_states_without_writes(self):
        path = m.VAULT / "project_example.md"
        m.memory_save("project", "example", "Candidate", "Original")
        candidate = path.read_bytes()
        for content in (candidate, b"Legacy body", b"---\nscope: global\nscope: null\n---\n\xff"):
            with self.subTest(content=content):
                path.write_bytes(content)
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "project_example.md"):
                    m.memory_save("reference", "example", "New", "Do not write")
                self.assertEqual(self.snapshot(), before)

    def test_existing_duplicates_can_be_updated_and_other_slugs_created(self):
        for kind in ("project", "reference"):
            (m.VAULT / (kind + "_example.md")).write_text(
                "---\nname: example\ntype: " + kind + "\ncreated: 2000-01-01\n---\nOriginal\n"
            )
        other = (m.VAULT / "project_example.md").read_bytes()
        self.assertIn("updated", m.memory_save("reference", "example", "Merged", "Additional information"))
        self.assertEqual((m.VAULT / "project_example.md").read_bytes(), other)
        self.assertIn("created: 2000-01-01", m.memory_get("reference_example.md"))
        self.assertIn("created", m.memory_save("reference", "another", "Different", "Body"))

    def test_archived_note_does_not_block_creation(self):
        m.memory_save("project", "example", "Original", "Body")
        archived = m.memory_archive("project_example.md", "Retired")
        original = Path(archived["archive_path"]).read_bytes()
        self.assertIn("created", m.memory_save("reference", "example", "New", "Body"))
        self.assertEqual(Path(archived["archive_path"]).read_bytes(), original)

    def test_conflict_lists_every_kind_without_parsing_or_changing_notes(self):
        for kind in ("user", "feedback", "project"):
            (m.VAULT / (kind + "_example.md")).write_bytes(b"unclassified original\xff")
        before = self.snapshot()
        with self.assertRaises(ValueError) as caught:
            m.memory_save("reference", "example", "New", "Body")
        for kind in ("user", "feedback", "project"):
            self.assertIn(kind + "_example.md", str(caught.exception))
        self.assertEqual(self.snapshot(), before)

    def test_symlinks_cannot_bypass_duplicate_guard(self):
        link = m.VAULT / "project_example.md"
        link.symlink_to(m.VAULT / "missing")
        with self.assertRaisesRegex(ValueError, "project_example.md"):
            m.memory_save("reference", "example", "New", "Body")
        with self.assertRaisesRegex(ValueError, "symlink"):
            m.memory_save("project", "example", "New", "Body")
        self.assertTrue(link.is_symlink())
        self.assertFalse((m.VAULT / "missing").exists())
        self.assertFalse((m.VAULT / m.INDEX).exists())

    def test_concurrent_mcp_creations_have_one_winner_and_exact_conflict(self):
        processes = []
        fd = os.open(str(m.VAULT), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            for kind in ("project", "reference"):
                process = subprocess.Popen(
                    [sys.executable, m.__file__],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=dict(os.environ, MEMORY_VAULT=str(m.VAULT)),
                )
                processes.append(process)
                request = dict(
                    id=1,
                    method="tools/call",
                    params=dict(
                        name="memory_save",
                        arguments=dict(kind=kind, slug="racing", description="Race", body="Preserved"),
                    ),
                )
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
            for process in processes:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.wait(timeout=0.05)
        finally:
            os.close(fd)
        replies = []
        for process in processes:
            output, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            replies.append(json.loads(output)["result"])
        winners = list(m.VAULT.glob("*_racing.md"))
        self.assertEqual(len(winners), 1)
        self.assertEqual(sum(bool(r.get("isError")) for r in replies), 1)
        failure = next(r for r in replies if r.get("isError"))
        self.assertIn(winners[0].name, failure["content"][0]["text"])
        self.assertEqual(m.memory_get().count("_racing.md)"), 1)
