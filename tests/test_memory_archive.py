"""Archive contracts exercised only against disposable vaults."""

import json
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import memory_mcp as m


class Archive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = m.VAULT
        m.VAULT = Path(self.tmp.name)
        self.name = "feedback_original.md"
        self.path = m.VAULT / self.name
        self.original = b"---\r\ncustom: untouched\r\n---\r\nlegacy original\xff\n"
        self.path.write_bytes(self.original)
        self.other = m.VAULT / "reference_keep.md"
        self.other.write_text("keep")
        self.kept_index = b"# Human index\r\n\r\n- [keep](reference_keep.md) custom\r\nHuman footer\n"
        (m.VAULT / m.INDEX).write_bytes(self.kept_index + b"- [original](feedback_original.md) old\r\n")

    def tearDown(self):
        m.VAULT = self.old
        self.tmp.cleanup()

    def test_archive_preserves_bytes_and_only_removes_target(self):
        result = m.memory_archive(self.name, "Merged", self.other.name)
        self.assertEqual(result["status"], "archived")
        self.assertFalse(self.path.exists())
        archived = Path(result["archive_path"])
        self.assertEqual(archived.read_bytes(), self.original)
        self.assertEqual((m.VAULT / m.INDEX).read_bytes(), self.kept_index)
        self.assertEqual(self.other.read_text(), "keep")
        for review in (False, True):
            self.assertNotIn(self.name, [r["filename"] for r in m.memory_search(review=review)])
        record = json.loads((archived.parent / "record.json").read_text())
        self.assertEqual(record["filename"], self.name)
        self.assertEqual(record["reason"], "Merged")
        self.assertEqual(record["replaced_by"], self.other.name)
        self.assertEqual(record["stage"], "complete")
        again = m.memory_archive(self.name, "Merged", self.other.name)
        self.assertEqual(again["status"], "already_archived")
        self.assertEqual(again["archive_id"], result["archive_id"])

    def test_rejects_unsafe_paths_and_core_sources_before_moving(self):
        for name in ("../feedback_original.md", "original", "MEMORY.md", "archive/x.md"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.memory_archive(name, "Merged")
        for replacement in (self.name, "reference_missing.md", "../reference_keep.md"):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                m.memory_archive(self.name, "Merged", replacement)
        link = m.VAULT / "feedback_link.md"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            m.memory_archive(link.name, "Merged")
        with self.assertRaises(ValueError):
            m.memory_archive(self.name, "Merged", link.name)
        core = dict(
            schema_version=1,
            budget_method="utf8-byte-v1",
            budget_limit=2048,
            entries=[
                dict(
                    id="K1",
                    source_notes=[self.name],
                    body="Keep source",
                    approved_on="2026-09-28",
                    approval_ref="explicit approval",
                    scope="global",
                    status="confirmed",
                    scope_inferred=False,
                )
            ],
        )
        m.memory_core_save(core, confirmed=True)
        before = (m.VAULT / "core-manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "core source"):
            m.memory_archive(self.name, "Merged")
        self.assertEqual((m.VAULT / "core-manifest.json").read_bytes(), before)
        (m.VAULT / "core-manifest.json").write_text("{broken")
        with self.assertRaises(ValueError):
            m.memory_archive(self.name, "Merged")
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse((m.VAULT / "archive").exists())

    def test_failures_at_journal_move_and_index_are_recoverable(self):
        real_replace = os.replace
        for failure in ("record.json", "move", m.INDEX):
            with self.subTest(failure=failure):
                self.path.write_bytes(self.original)
                (m.VAULT / m.INDEX).write_bytes(self.kept_index + b"- [original](feedback_original.md) old\r\n")

                def replace(src, dest):
                    if Path(dest).name == failure:
                        raise OSError("injected write failure")
                    return real_replace(src, dest)

                with patch.object(m.os, "replace", side_effect=replace):
                    if failure == "move":
                        with patch.object(m.os, "rename", side_effect=OSError("injected move failure")):
                            result = m.memory_archive(self.name, failure)
                    else:
                        result = m.memory_archive(self.name, failure)
                self.assertEqual(result["status"], "partial_failure")
                archived = Path(result["archive_path"])
                original = self.path if self.path.exists() else archived
                self.assertEqual(original.read_bytes(), self.original)
                recovered = m.memory_archive(self.name, failure)
                self.assertEqual(recovered["status"], "archived")
                self.assertEqual(recovered["archive_id"], result["archive_id"])
                self.assertEqual(archived.read_bytes(), self.original)
                self.assertEqual((m.VAULT / m.INDEX).read_bytes(), self.kept_index)

    def test_retry_preserves_new_same_name_note_and_index(self):
        real_replace = os.replace

        def fail_index(src, dest):
            if Path(dest).name == m.INDEX:
                raise OSError("injected index failure")
            return real_replace(src, dest)

        with patch.object(m.os, "replace", side_effect=fail_index):
            result = m.memory_archive(self.name, "Merged")
        self.assertEqual(result["status"], "partial_failure")
        m.memory_save("feedback", "original", "New generation", "New body")
        note, index = self.path.read_bytes(), (m.VAULT / m.INDEX).read_bytes()
        self.assertEqual(m.memory_archive(self.name, "Merged")["status"], "archived")
        self.assertEqual(m.memory_archive(self.name, "Merged")["status"], "already_archived")
        self.assertEqual(self.path.read_bytes(), note)
        self.assertEqual((m.VAULT / m.INDEX).read_bytes(), index)
        self.assertEqual(Path(result["archive_path"]).read_bytes(), self.original)

    def test_prepared_retry_refuses_replaced_source_even_with_same_bytes(self):
        with patch.object(m.os, "rename", side_effect=OSError("interrupted")):
            result = m.memory_archive(self.name, "Merged")
        fresh = m.VAULT / "new-file"
        fresh.write_bytes(self.original)
        os.replace(fresh, self.path)
        result = m.memory_archive(self.name, "Merged")
        self.assertEqual(result["status"], "partial_failure")
        self.assertIn("new generation", result["error"])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_restore_is_executable_and_never_overwrites(self):
        result = m.memory_archive(self.name, "Merged")
        self.assertIn("restore_command", result)
        restored = subprocess.run(result["restore_command"], shell=True, capture_output=True, text=True)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertIn(self.name, m.memory_get())
        self.assertEqual(Path(result["archive_path"]).read_bytes(), self.original)

        self.path.write_bytes(b"new content")
        conflict = subprocess.run(result["restore_command"], shell=True, capture_output=True, text=True)
        self.assertNotEqual(conflict.returncode, 0)
        self.assertEqual(self.path.read_bytes(), b"new content")
        self.assertEqual(Path(result["archive_path"]).read_bytes(), self.original)

    def test_restore_index_failure_resumes_without_changing_bytes(self):
        result = m.memory_archive(self.name, "Merged")
        real_replace = os.replace

        def fail_index(src, dest):
            if Path(dest).name == m.INDEX:
                raise OSError("index unavailable")
            return real_replace(src, dest)

        with patch.object(m.os, "replace", side_effect=fail_index), self.assertRaises(OSError):
            m.restore_archive(result["archive_id"])
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(m.restore_archive(result["archive_id"])["status"], "restored")
        self.assertIn(self.name, m.memory_get())

    def test_concurrent_writers_share_lock_and_preserve_all_index_entries(self):
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); import memory_mcp as m; "
            "print('ready', flush=True); "
            "result=eval(sys.argv[2]); print(result, flush=True)"
        )
        operations = ["m.memory_archive('feedback_original.md', 'Concurrent')"]
        operations += ["m.memory_save('reference', 'parallel-%d', 'Concurrent', 'Body')" % i for i in range(6)]
        operations += [
            "m.memory_core_save(dict(schema_version=1, budget_method='utf8-byte-v1', "
            "budget_limit=2048, entries=[]), confirmed=True)"
        ]
        processes = []
        fd = os.open(str(m.VAULT), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            for operation in operations:
                process = subprocess.Popen(
                    [sys.executable, "-c", script, str(Path(m.__file__).parent), operation],
                    env=dict(os.environ, MEMORY_VAULT=str(m.VAULT)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                processes.append(process)
                self.assertEqual(process.stdout.readline().strip(), "ready")
            for process in processes:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.wait(timeout=0.03)
            self.assertTrue(self.path.exists())
            self.assertFalse((m.VAULT / "core-manifest.json").exists())
            self.assertFalse(list(m.VAULT.glob("reference_parallel-*.md")))
        finally:
            os.close(fd)
            for process in processes:
                output, error = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, error + output)
        index = m.memory_get()
        for i in range(6):
            self.assertEqual(index.count("](" + "reference_parallel-%d.md" % i + ")"), 1)
        self.assertNotIn("](feedback_original.md)", index)
        self.assertIn("Human footer", index)
        self.assertFalse(self.path.exists())
        self.assertEqual(m.memory_core_get(), "# 핵심 기억\n")

    def test_stdio_registers_and_calls_archive_with_scrubbed_reason(self):
        secret = "glpat-" + "x" * 24
        requests = [
            dict(id=1, method="tools/list"),
            dict(
                id=2,
                method="tools/call",
                params=dict(name="memory_archive", arguments=dict(filename=self.name, reason="Merged " + secret)),
            ),
        ]
        process = subprocess.run(
            [sys.executable, m.__file__],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            env=dict(os.environ, MEMORY_VAULT=str(m.VAULT)),
            text=True,
            capture_output=True,
            check=True,
        )
        replies = [json.loads(line)["result"] for line in process.stdout.splitlines()]
        schema = next(t for t in replies[0]["tools"] if t["name"] == "memory_archive")["inputSchema"]
        self.assertEqual(schema["required"], ["filename", "reason"])
        self.assertFalse(replies[1].get("isError"))
        result = json.loads(replies[1]["content"][0]["text"])
        self.assertEqual(result["status"], "archived")
        record = Path(result["record_path"]).read_text()
        self.assertNotIn(secret, record)
        self.assertIn("[REDACTED:gitlab]", record)

    def test_restore_racing_destination_is_not_overwritten(self):
        result = m.memory_archive(self.name, "Merged")
        real_link = os.link

        def racing_link(src, dest):
            Path(dest).write_bytes(b"concurrent writer")
            return real_link(src, dest)

        with patch.object(m.os, "link", side_effect=racing_link), self.assertRaises(FileExistsError):
            m.restore_archive(result["archive_id"])
        self.assertEqual(self.path.read_bytes(), b"concurrent writer")
        self.assertEqual(Path(result["archive_path"]).read_bytes(), self.original)

    def test_post_move_and_final_journal_failures_resume(self):
        real_rename, real_replace = os.rename, os.replace
        for stage in ("after_move", "final_record"):
            self.path.write_bytes(self.original)

            def rename(src, dest):
                real_rename(src, dest)
                if stage == "after_move":
                    raise OSError("move succeeded but reply lost")

            def replace(src, dest):
                if (
                    stage == "final_record"
                    and Path(dest).name == "record.json"
                    and json.loads(Path(src).read_text())["stage"] == "complete"
                ):
                    raise OSError("final record unavailable")
                real_replace(src, dest)

            with patch.object(m.os, "rename", side_effect=rename), patch.object(m.os, "replace", side_effect=replace):
                result = m.memory_archive(self.name, stage)
            self.assertEqual(result["status"], "partial_failure")
            self.assertEqual(Path(result["archive_path"]).read_bytes(), self.original)
            self.assertEqual(m.memory_archive(self.name, stage)["status"], "archived")

    def test_confirmed_note_disappears_from_both_search_modes(self):
        self.path.unlink()
        m.memory_save(
            "feedback",
            "original",
            "Unique needle",
            "Unique needle",
            metadata=dict(
                memory_schema=1,
                scope="global",
                status="confirmed",
                project_id=None,
                scope_inferred=False,
                scope_reason="Explicit global",
                status_reason="User approved",
            ),
        )
        for review in (False, True):
            self.assertEqual(len(m.memory_search("needle", review=review)), 1)
        m.memory_archive(self.name, "Retired")
        for review in (False, True):
            self.assertEqual(m.memory_search("needle", review=review), [])

    def test_archive_and_index_symlinks_are_not_followed(self):
        outside = m.VAULT / "outside"
        outside.mkdir()
        root = m.VAULT / "archive"
        root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            m.memory_archive(self.name, "Retired")
        self.assertEqual(list(outside.iterdir()), [])
        root.unlink()
        index = m.VAULT / m.INDEX
        index.unlink()
        index.symlink_to(outside / "missing.md")
        result = m.memory_archive(self.name, "Retired")
        self.assertEqual(result["status"], "partial_failure")
        self.assertFalse((outside / "missing.md").exists())
