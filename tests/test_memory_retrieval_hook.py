"""Claude hook protocol: reject broad AND queries without rewriting scope."""
import json
import os
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/memory_retrieval_hook.py'


class QueryHook(unittest.TestCase):
    def invoke(self, event, state=None):
        result = subprocess.run([sys.executable, str(SCRIPT)],
                                input=json.dumps(event), text=True, capture_output=True,
                                env=dict(os.environ, **({'MEMORY_RETRIEVAL_STATE': str(state)} if state else {})))
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


    def test_each_request_requires_search_before_write(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            def call(kind, **kw):
                return self.invoke(dict(session_id='session', prompt_id='request-1', hook_event_name=kind, **kw), state)
            call('UserPromptSubmit')
            blocked = call('PreToolUse', tool_name='Write', tool_input={}, tool_use_id='write-1')
            self.assertEqual(blocked['hookSpecificOutput']['permissionDecision'], 'deny')
            call('PreToolUse', tool_name='mcp__memory__memory_search', tool_input={'query': 'topic'}, tool_use_id='search-1')
            call('PostToolUse', tool_name='mcp__memory__memory_search', tool_input={'query': 'topic'}, tool_use_id='search-1', tool_response=[{'type': 'text', 'text': '[]'}])
            self.assertEqual(call('PreToolUse', tool_name='Write', tool_input={}, tool_use_id='write-2'), {})
            self.invoke(dict(session_id='session', prompt_id='request-2', hook_event_name='UserPromptSubmit'), state)
            blocked = self.invoke(dict(session_id='session', prompt_id='request-2', hook_event_name='PreToolUse', tool_name='Write', tool_input={}, tool_use_id='write-3'), state)
            self.assertEqual(blocked['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_only_matching_successful_search_unlocks_and_empty_feedback_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            def call(kind, tool=None, ident='s1', **kw):
                return self.invoke(dict(session_id='session', prompt_id='r1', hook_event_name=kind,
                                        tool_name=tool, tool_use_id=ident, tool_input={'query': ident}, **kw), temp)
            call('UserPromptSubmit')
            search = 'mcp__memory__memory_search'
            call('PostToolUse', search, tool_response=[{'type':'text','text':'[]'}])
            self.assertEqual(call('PreToolUse', 'Write')['hookSpecificOutput']['permissionDecision'], 'deny')
            call('PreToolUse', search)
            call('PostToolUseFailure', search, error='transport error')
            self.assertEqual(call('PreToolUse', 'Write')['hookSpecificOutput']['permissionDecision'], 'deny')
            call('PreToolUse', search, ident='s2')
            value=call('PostToolUse', search, ident='s2', tool_response=[{'type':'text','text':'[]'}])
            self.assertIn('0건', value['hookSpecificOutput']['additionalContext'])
            self.assertEqual(call('PreToolUse', 'Write'), {})
            call('PreToolUse', search, ident='s3')
            call('PostToolUse', search, ident='s3', tool_response=[{'type':'text','text':'[]'}])
            self.assertEqual(call('PreToolUse', search, ident='s4')['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_project_change_invalidates_search_and_stop_corrects_once(self):
        with tempfile.TemporaryDirectory() as temp:
            def call(kind, tool=None, ident='s1', inputs=None, **kw):
                return self.invoke(dict(session_id='session', prompt_id='r1', hook_event_name=kind,
                    tool_name=tool, tool_use_id=ident, tool_input=inputs or {}, **kw), temp)
            call('UserPromptSubmit')
            resolve='mcp__memory__memory_project_resolve'
            search='mcp__memory__memory_search'
            call('PreToolUse', resolve, ident='p1')
            call('PostToolUse', resolve, ident='p1', tool_response=[{'type':'text','text':'{"project_id":"A"}'}])
            call('PreToolUse', search, inputs={'query':'topic','current_project_id':'A'})
            call('PostToolUse', search, tool_response=[{'type':'text','text':'[]'}])
            self.assertEqual(call('PreToolUse','Write'), {})
            call('PreToolUse', resolve, ident='p2')
            call('PostToolUse', resolve, ident='p2', tool_response=[{'type':'text','text':'{"project_id":"B"}'}])
            self.assertEqual(call('PreToolUse','Write')['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertEqual(call('Stop',stop_hook_active=False)['decision'],'block')
            self.assertNotIn('decision',call('Stop',stop_hook_active=True))
            self.assertNotIn('decision',call('Stop',stop_hook_active=False))

    def test_stale_wrong_scope_and_corrupt_state_cannot_authorize_write(self):
        with tempfile.TemporaryDirectory() as temp:
            def call(kind, request='r1', tool=None, inputs=None, ident='t', **kw):
                return self.invoke(dict(session_id='session', prompt_id=request, hook_event_name=kind,
                    tool_name=tool, tool_use_id=ident, tool_input=inputs or {}, **kw), temp)
            call('UserPromptSubmit')
            search='mcp__memory__memory_search'
            call('PreToolUse',tool=search,inputs={'query':'topic'},ident='old')
            call('UserPromptSubmit',request='r2')
            call('PostToolUse',tool=search,ident='old',tool_response=[{'type':'text','text':'[]'}])
            self.assertEqual(call('PreToolUse',request='r2',tool='Write')['hookSpecificOutput']['permissionDecision'],'deny')
            call('PreToolUse',request='r2',tool='mcp__memory__memory_project_resolve',ident='resolve')
            call('PostToolUse',request='r2',tool='mcp__memory__memory_project_resolve',ident='resolve',tool_response=[{'type':'text','text':'{"project_id":"A","targets":[]}'}])
            self.assertEqual(call('PreToolUse',request='r2',tool=search,inputs={'query':'topic','current_project_id':'B'})['hookSpecificOutput']['permissionDecision'],'deny')
            path=next(Path(temp).glob('*.json'));path.write_text('{corrupted')
            self.assertFalse(call('PreToolUse',request='r2',tool='Write')['continue'])

    def test_state_files_private_and_sessions_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            for session in ['a','b']:
                self.invoke(dict(session_id=session,prompt_id='r',hook_event_name='UserPromptSubmit'),temp)
            self.assertEqual(len(list(Path(temp).glob('*.json'))),2)
            self.assertEqual(Path(temp).stat().st_mode & 0o777,0o700)
            for path in Path(temp).iterdir():self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_repeated_denial_stops_without_allowing_unsearched_write(self):
        with tempfile.TemporaryDirectory() as temp:
            self.invoke(dict(session_id='s',prompt_id='r',hook_event_name='UserPromptSubmit'),temp)
            for i in range(3):
                value=self.invoke(dict(session_id='s',prompt_id='r',hook_event_name='PreToolUse',tool_name='Write',tool_use_id=str(i),tool_input={}),temp)
            self.assertFalse(value['continue'])

    def test_concurrent_search_limit_is_atomic(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp:
            self.invoke(dict(session_id='s',prompt_id='r',hook_event_name='UserPromptSubmit'),temp)
            def search(i):
                return self.invoke(dict(session_id='s',prompt_id='r',hook_event_name='PreToolUse',tool_name='mcp__memory__memory_search',tool_use_id=str(i),tool_input={'query':'topic'}),temp)
            with ThreadPoolExecutor(max_workers=4) as pool:values=list(pool.map(search,range(4)))
            self.assertEqual(values.count({}),3)

    def test_same_project_new_target_requires_new_search(self):
        with tempfile.TemporaryDirectory() as temp:
            def call(kind,tool=None,ident='t',inputs=None,response=None):
                return self.invoke(dict(session_id='s',prompt_id='r',hook_event_name=kind,tool_name=tool,
                    tool_use_id=ident,tool_input=inputs or {},tool_response=response),temp)
            call('UserPromptSubmit')
            for i in range(2):
                call('PreToolUse','mcp__memory__memory_project_resolve',str(i))
                call('PostToolUse','mcp__memory__memory_project_resolve',str(i),response=[{'type':'text','text':json.dumps({'project_id':'A','targets':[{'path':str(i),'project_id':'A','conflict':False}]})}])
                if i==0:
                    call('PreToolUse','mcp__memory__memory_search','search',{'query':'topic','current_project_id':'A'})
                    call('PostToolUse','mcp__memory__memory_search','search',response=[{'type':'text','text':'[]'}])
                    self.assertEqual(call('PreToolUse','Write'),{})
            self.assertEqual(call('PreToolUse','Write')['hookSpecificOutput']['permissionDecision'],'deny')

    def test_invalid_state_shape_and_missing_request_stop_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            event=dict(session_id='s',prompt_id='r',hook_event_name='UserPromptSubmit')
            self.invoke(event,temp)
            next(Path(temp).glob('*.json')).write_text('{"request":"r"}')
            value=self.invoke(dict(event,hook_event_name='PreToolUse',tool_name='mcp__memory__memory_search',tool_input={'query':'topic'}),temp)
            self.assertFalse(value['continue'])
            event.pop('prompt_id')
            self.assertFalse(self.invoke(event,temp)['continue'])

    def test_resolve_pending_and_failure_invalidate_prior_search(self):
        with tempfile.TemporaryDirectory() as temp:
            def call(event, tool=None, ident='t', **kw):
                return self.invoke(dict(session_id='s',prompt_id='r',hook_event_name=event,
                    tool_name=tool,tool_use_id=ident,tool_input={'query':'topic'},**kw),temp)
            call('UserPromptSubmit')
            search='mcp__memory__memory_search';resolve='mcp__memory__memory_project_resolve'
            call('PreToolUse',search,'search')
            call('PostToolUse',search,'search',tool_response=[{'type':'text','text':'[]'}])
            call('PreToolUse',resolve,'resolve')
            self.assertEqual(call('PreToolUse','Write')['hookSpecificOutput']['permissionDecision'],'deny')
            call('PostToolUseFailure',resolve,'resolve',error='registry unavailable')
            self.assertEqual(call('PreToolUse',search)['hookSpecificOutput']['permissionDecision'],'deny')
            call('PreToolUse',resolve,'retry')
            call('PostToolUse',resolve,'retry',tool_response=[{'type':'text','text':'{"project_id":null,"targets":[]}'}])
            self.assertEqual(call('PreToolUse',search,'new'),{})
            call('PostToolUse',search,'new',tool_response=[{'type':'text','text':'[]'}])
            self.assertEqual(call('PreToolUse','Write'),{})

    def test_retry_scope_and_filters_cannot_change_without_new_context(self):
        for altered in [{'current_project_id':'B'}, {'kind':'feedback'}, {'project_filter':'B'}, {'review':True}]:
            with self.subTest(altered=altered), tempfile.TemporaryDirectory() as temp:
                def call(event,tool=None,ident='t',inputs=None,response=None):
                    return self.invoke(dict(session_id='s',prompt_id='r',hook_event_name=event,tool_name=tool,
                        tool_use_id=ident,tool_input=inputs or {},tool_response=response),temp)
                call('UserPromptSubmit')
                search='mcp__memory__memory_search';args={'query':'topic','current_project_id':'A'}
                call('PreToolUse',search,inputs=args)
                call('PostToolUse',search,response=[{'type':'text','text':'[]'}])
                value=call('PreToolUse',search,'retry',dict(args,**altered))
                self.assertEqual(value['hookSpecificOutput']['permissionDecision'],'deny')
                call('PreToolUse','mcp__memory__memory_project_resolve','resolve')
                call('PostToolUse','mcp__memory__memory_project_resolve','resolve',response=[{'type':'text','text':'{"project_id":"B","targets":[]}'}])
                self.assertEqual(call('PreToolUse',search,'new',{'query':'topic','current_project_id':'B'}),{})


if __name__ == '__main__':
    unittest.main()
