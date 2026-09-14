"""S1–S6 public storage/MCP contracts, isolated local vaults only."""
import json
import os
import re
from unittest.mock import patch
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import memory_mcp as m
import scrub_secrets


def metadata(**updates):
    value = dict(memory_schema=1, scope='global', status='confirmed',
                 project_id=None, scope_inferred=False,
                 scope_reason='Explicit global instruction', status_reason='User correction')
    value.update(updates)
    return value


class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = m.VAULT
        m.VAULT = Path(self.tmp.name)

    def tearDown(self):
        m.VAULT = self.old
        self.tmp.cleanup()

    def save(self, **kwargs):
        return m.memory_save('feedback', 'example', 'Archive settings', 'Keep originals', **kwargs)

    def test_metadata_rejection_and_old_api_isolation(self):
        for bad in [metadata(scope=None), metadata(scope_inferred='false'),
                    metadata(memory_schema=True), {'scope': 'global'},
                    metadata(project_id='fixture-project')]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.save(metadata=bad)
                self.assertEqual(list(m.VAULT.iterdir()), [])
        self.assertIn('candidate', self.save())
        self.assertIn('scope: null', m.memory_get('example'))
        before = m.memory_get('example')
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(m.memory_get('example'), before)
        self.save(metadata=metadata())
        self.assertIn('status: "confirmed"', m.memory_get('example'))

    def test_registry_identity_and_search_scope(self):
        with self.assertRaises(ValueError):
            m.memory_project_register('A', ['/repo-a'], confirmed=False)
        a = m.memory_project_register('A', ['/repo-a', '/alias-a'], confirmed=True)['id']
        b = m.memory_project_register('B', ['/repo-ab'], confirmed=True)['id']
        child = m.memory_project_register('child', ['/repo-a/sub'], confirmed=True)['id']
        self.assertEqual(m.memory_project_resolve(target_paths=['/alias-a/file'])['project_id'], a)
        self.assertEqual(m.memory_project_resolve(target_paths=['/repo-a/sub/x'])['project_id'], child)
        self.assertEqual(m.memory_project_resolve(target_paths=['/repo-ab/x'])['project_id'], b)
        self.assertIsNone(m.memory_project_resolve(target_paths=['/repo-abc/x'])['project_id'])
        self.assertIsNone(m.memory_project_resolve(target_paths=['/repo-a/x', '/repo-ab/y'])['project_id'])
        self.assertIsNone(m.memory_project_resolve(explicit_id=a, target_paths=['/repo-ab/x'])['project_id'])
        self.assertEqual(m.memory_project_resolve(explicit_id='  ' + a.upper() + ' ')['project_id'], a)
        with self.assertRaises(ValueError):
            m.memory_project_register('duplicate', ['/repo-a'], confirmed=True)
        for slug, meta in [('global', metadata()), ('a', metadata(scope='project', project_id=a)),
                           ('b', metadata(scope='project', project_id=b)),
                           ('candidate', metadata(status='candidate'))]:
            m.memory_save('feedback', slug, 'Archive', 'Keep original', metadata=meta)
        self.assertEqual([r['filename'] for r in m.memory_search('archive')], ['feedback_global.md'])
        rows = m.memory_search('KEEP', current_project_id=a)
        self.assertEqual({r['filename'] for r in rows}, {'feedback_a.md', 'feedback_global.md'})
        self.assertEqual(m.memory_search('', current_project_id=a, project_filter=b), [])
        review = m.memory_search('', current_project_id=a, project_filter=b, review=True)
        self.assertEqual(len(review), 1)
        self.assertFalse(review[0]['automatically_applicable'])
        self.assertEqual(m.memory_search('', kind='user'), [])
        self.assertEqual(len(m.memory_search('', current_project_id=b)), 2)

    def test_legacy_invalid_preservation_scrub_and_partial_failure(self):
        legacy = '---\nname: example\ndescription: Archive\ntype: feedback\ncreated: 2001-02-03\ncustom: untouched\n# human comment\n---\n\nOld body\n'
        path = m.VAULT / 'feedback_example.md'
        path.write_text(legacy)
        invalid = m.VAULT / 'feedback_invalid.md'
        invalid.write_text(legacy.replace('name: example', 'name: invalid\nscope: global\nscope: project'))
        before = {p.name: p.read_bytes() for p in m.VAULT.iterdir()}
        self.assertEqual(m.memory_search('Archive'), [])
        rows = m.memory_search('Archive', review=True)
        self.assertEqual({r['metadata_state'] for r in rows}, {'legacy', 'invalid'})
        self.assertTrue(all(not r['automatically_applicable'] for r in rows))
        self.assertEqual(before, {p.name: p.read_bytes() for p in m.VAULT.iterdir()})
        self.assertIn('legacy', self.save())
        self.assertIn('custom: untouched\n# human comment\n', m.memory_get('example'))
        self.assertIn('created: 2001-02-03', m.memory_get('example'))
        with self.assertRaises(ValueError):
            m.memory_save('feedback', 'invalid', 'Archive', 'new', metadata=metadata())
        self.assertEqual(invalid.read_bytes(), before['feedback_invalid.md'])
        token = 'glpat-' + 'x' * 24
        m.memory_save('feedback', 'example', token, token, tags=[token],
                      metadata=metadata(scope_reason=token, status_reason=token))
        self.assertNotIn(token, m.memory_get('example'))
        self.assertIn('[REDACTED:gitlab]', m.memory_get('example'))
        # Real filesystem failure after note write (directory in place of index).
        (m.VAULT / m.INDEX).unlink()
        (m.VAULT / m.INDEX).mkdir()
        with self.assertRaisesRegex(ValueError, 'partial failure: note saved'):
            self.save(metadata=metadata())
        self.assertIn('Keep originals', m.memory_get('example'))
        (m.VAULT / m.INDEX).rmdir()
        self.save(metadata=metadata())
        self.assertIn('feedback_example.md', m.memory_get())

    def test_safe_yaml_roundtrip_and_large_index(self):
        for i in range(120):
            m.memory_save('reference', 'note-%d' % i, 'Useful', 'Body')
        self.assertEqual(m.memory_get().count('](reference_'), 120)
        for body in ['true', 'a # comment', 'null', 'x: y']:
            m.memory_save('feedback', 'example', body, 'Body', tags=['a,b', 'true'], metadata=metadata())
            row = m.memory_search('', review=True)
            row = next(r for r in row if r['filename'] == 'feedback_example.md')
            self.assertEqual(row['metadata_state'], 'valid')
            self.assertEqual(row['description'], body)

    def test_core_approval_budget_and_failed_read(self):
        source = m.VAULT / 'feedback_source.md'
        source.write_text('Legacy original remains legacy')
        entry = dict(id='K-test', source_notes=[source.name], body='가' + 'a' * 2026,
                     approved_on='2026-09-11', approval_ref='User approved exact body',
                     scope='global', status='confirmed', scope_inferred=False)
        manifest = dict(schema_version=1, budget_method='utf8-byte-v1', budget_limit=2048,
                        entries=[entry])
        with self.assertRaises(ValueError):
            m.memory_core_save(manifest, confirmed=False)
        # Header=16 bytes, bullet+LF=3; Korean=3, ASCII=2026 => 2048.
        self.assertEqual(m.memory_core_save(manifest, confirmed=True)['budget_used'], 2048)
        self.assertEqual(len(m.memory_core_get().encode('utf-8')), 2048)
        before = (m.VAULT / 'core-manifest.json').read_bytes()
        entry['body'] += 'a'
        with self.assertRaisesRegex(ValueError, '2049.*1'):
            m.memory_core_save(manifest, confirmed=True)
        self.assertEqual((m.VAULT / 'core-manifest.json').read_bytes(), before)
        entry['body'] = 'Short body'
        for changes in [dict(scope='project'), dict(status='candidate'), dict(scope_inferred=True),
                        dict(approval_ref=''), dict(source_notes=[]), dict(source_notes=['../outside.md']),
                        dict(approved_on='2026-02-30'), dict(body='a\nb')]:
            bad = json.loads(json.dumps(manifest))
            bad['entries'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.memory_core_save(bad, confirmed=True)
        manifest['entries'].append(dict(entry))
        with self.assertRaises(ValueError):
            m.memory_core_save(manifest, confirmed=True)
        (m.VAULT / 'core-manifest.json').write_text('{broken')
        (m.VAULT / m.INDEX).write_text('Entire index must not be injected')
        with self.assertRaisesRegex(ValueError, 'core unavailable'):
            m.memory_core_get()
        self.assertEqual(source.read_text(), 'Legacy original remains legacy')

    def test_approved_initial_core_exact_bytes_and_missing_source(self):
        manifest = m.memory_core_initial()
        with self.assertRaises(ValueError):
            m.memory_core_save(manifest, confirmed=True)
        for entry in manifest['entries']:
            for name in entry['source_notes']:
                (m.VAULT / name).write_text('untouched source')
        self.assertEqual(m.memory_core_save(manifest, confirmed=True)['budget_used'], 861)
        rendered = m.memory_core_get()
        doc = (Path(__file__).resolve().parents[1] / 'docs/memory-retrieval-core-review.md').read_text()
        approved = doc.split('```text\n', 1)[1].split('```', 1)[0]
        self.assertEqual(rendered, approved)
        self.assertEqual(m.memory_search(''), [])

    def test_stdio_mcp_storage_search_and_duplicate_input(self):
        requests = [
            dict(id=1, method='tools/list'),
            dict(id=2, method='tools/call', params=dict(name='memory_save', arguments=dict(
                kind='feedback', slug='rpc', description='Archive', body='Preserve settings', metadata=metadata()))),
            dict(id=3, method='tools/call', params=dict(name='memory_search', arguments=dict(query='settings'))),
            dict(id=4, method='tools/call', params=dict(name='memory_save', arguments=dict(
                kind='feedback', slug='rpc', description='Changed', body='Overwrite'))),
        ]
        lines = [json.dumps(r) for r in requests]
        lines.append('{"id":5,"method":"tools/call","params":{"name":"memory_save","arguments":'
                     '{"kind":"feedback","slug":"duplicate","description":"d","body":"b",'
                     '"metadata":{"scope":"global","scope":"project"}}}}')
        result = subprocess.run([sys.executable, str(Path(m.__file__))],
                                input='\n'.join(lines) + '\n', text=True, capture_output=True,
                                env=dict(os.environ, MEMORY_VAULT=str(m.VAULT)), check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        names = {t['name'] for t in replies[0]['result']['tools']}
        self.assertTrue({'memory_search', 'memory_core_get', 'memory_project_resolve'} <= names)
        self.assertFalse(replies[1]['result'].get('isError', False))
        rows = json.loads(replies[2]['result']['content'][0]['text'])
        self.assertEqual([r['filename'] for r in rows], ['feedback_rpc.md'])
        self.assertTrue(replies[3]['result']['isError'])
        self.assertEqual(len(replies), 5)
        self.assertEqual(replies[4]['error']['code'], -32700)
        self.assertFalse((m.VAULT / 'feedback_duplicate.md').exists())

    def test_explicit_repair_preserves_untargeted_crlf_and_invalid_utf8_isolated(self):
        path = m.VAULT / 'feedback_example.md'
        path.write_bytes(b'---\r\nname: example\r\ndescription: old\r\ntype: feedback\r\n'
                         b'created: 2000-01-01\r\ncustom: preserve\r\nscope: global\r\n---\r\nold')
        self.save(metadata=metadata())
        self.assertIn(b'custom: preserve\r\n', path.read_bytes())
        self.assertIn(b'created: 2000-01-01\r\n', path.read_bytes())
        # A decode replacement must never promote damaged bytes to valid confirmed.
        path.write_bytes(path.read_bytes() + b'\xff')
        self.assertEqual(m.memory_search(''), [])
        self.assertEqual(m.memory_search('', review=True)[0]['metadata_state'], 'invalid')

    def test_metadata_combinations_and_registry_rejection_boundaries(self):
        identity = m.memory_project_register('A', [str(m.VAULT / 'repo')], confirmed=True)['id']
        for scope, status, inferred in [('global', 'confirmed', False), ('global', 'candidate', False),
                                        ('project', 'confirmed', False), ('project', 'confirmed', True),
                                        ('project', 'candidate', False), ('project', 'candidate', True),
                                        (None, 'candidate', False)]:
            self.save(metadata=metadata(scope=scope, status=status, scope_inferred=inferred,
                                        project_id=identity if scope == 'project' else None))
        before = {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()}
        for bad in [metadata(scope='project'), metadata(scope='project', project_id='prj-123e4567-e89b-42d3-a456-426614174000'),
                    metadata(scope='project', project_id='fixture-ocr'), metadata(scope=None, scope_inferred=True, status='candidate'),
                    metadata(scope_inferred=1), metadata(scope_reason=''), metadata(status_reason='a\nb'),
                    metadata(status='inferred'), metadata(memory_schema='1'), metadata(extra='x')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.save(metadata=bad)
            self.assertEqual(before, {p.name: p.read_bytes() for p in m.VAULT.iterdir() if p.is_file()})
        registry = json.loads((m.VAULT / 'projects.json').read_text())
        for bad in [dict(registry, schema_version=True), dict(registry, projects=registry['projects'] * 2),
                    dict(registry, projects=[dict(registry['projects'][0], roots=['relative'])]),
                    dict(registry, projects=[dict(registry['projects'][0], id=identity.upper())])]:
            (m.VAULT / 'projects.json').write_text(json.dumps(bad))
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.memory_project_resolve()
        (m.VAULT / 'projects.json').write_text('{"schema_version":1,"schema_version":1,"projects":[]}')
        with self.assertRaises(ValueError):
            m.memory_project_resolve()

    def test_project_symlink_alias_target_precedence_and_unicode_identity(self):
        real = m.VAULT / 'Répo'
        real.mkdir()
        link = m.VAULT / 'alias'
        link.symlink_to(real, target_is_directory=True)
        identity = m.memory_project_register('same name', [str(link) + '/'], confirmed=True)['id']
        self.assertEqual(m.memory_project_resolve(target_paths=[str(real / 'file')], cwd='/elsewhere')['project_id'], identity)
        alias = str(m.VAULT / 'other-checkout')
        self.assertEqual(m.memory_project_register('renamed', [alias], existing_id=identity, confirmed=True)['id'], identity)
        self.assertEqual(m.memory_project_resolve(cwd=alias)['project_id'], identity)
        self.assertIsNone(m.memory_project_resolve(cwd=str(m.VAULT / 'Répo'))['project_id'])
        with self.assertRaises(ValueError):
            m.memory_project_register('different', [str(real)], confirmed=True)
        spaced = str(m.VAULT / 'space ')
        spaced_id = m.memory_project_register('spaces', [spaced], confirmed=True)['id']
        self.assertEqual(m.memory_project_resolve(cwd=spaced)['project_id'], spaced_id)
        self.assertIsNone(m.memory_project_resolve(cwd=spaced.rstrip())['project_id'])

    def test_scrub_identity_rejection_and_core_read_corruption(self):
        identity = m.memory_project_register('A', ['/repo'], confirmed=True)['id']
        before = (m.VAULT / 'projects.json').read_bytes()
        # Simulate a future scrub rule matching the registered ID at the scrub boundary.
        with patch.object(scrub_secrets, 'PATTERNS', [('test-id', re.compile(re.escape(identity)), '[REDACTED]')]):
            with self.assertRaisesRegex(ValueError, 'scrub changed project_id'):
                self.save(metadata=metadata(scope='project', project_id=identity))
        self.assertEqual((m.VAULT / 'projects.json').read_bytes(), before)
        self.assertFalse((m.VAULT / 'feedback_example.md').exists())
        manifest = m.memory_core_initial()
        for entry in manifest['entries']:
            for name in entry['source_notes']:
                (m.VAULT / name).write_text('original')
        manifest['entries'][0]['body'] = '  \n' + manifest['entries'][0]['body'] + '\n '
        self.assertEqual(m.memory_core_save(manifest, confirmed=True)['budget_used'], 861)
        core = m.memory_core_get()
        (m.VAULT / manifest['entries'][0]['source_notes'][0]).write_text('changed source')
        self.assertEqual(m.memory_core_get(), core)
        manifest['entries'][0]['body'] = 'a' * 2049
        (m.VAULT / 'core-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'core unavailable.*exceeds'):
            m.memory_core_get()
        manifest['entries'][0]['body'] = 'glpat-' + 'x' * 24
        with self.assertRaisesRegex(ValueError, 'scrub-sensitive'):
            m.memory_core_save(manifest, confirmed=True)

    def test_ambiguous_yaml_reason_and_scrubbed_slug_rejected(self):
        self.save(metadata=metadata())
        path = m.VAULT / 'feedback_example.md'
        original = path.read_text()
        for reason in ["'bad' 'quote'", '1.5', '# comment without value']:
            path.write_text(original.replace('status_reason: "User correction"', 'status_reason: ' + reason))
            self.assertEqual(m.memory_search(''), [])
            self.assertEqual(m.memory_search('', review=True)[0]['metadata_state'], 'invalid')
        with self.assertRaises(ValueError):
            self.save(metadata=metadata(status_reason='one\u2028two'))
        token = 'sk-' + 'x' * 24
        with self.assertRaises(ValueError):
            m.memory_save('feedback', token, 'safe', 'safe')
        self.assertFalse((m.VAULT / ('feedback_' + token + '.md')).exists())


if __name__ == '__main__':
    unittest.main()
