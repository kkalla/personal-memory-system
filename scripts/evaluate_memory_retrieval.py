#!/usr/bin/env python3
"""Local preparation and explicit CLI execution for T1's two-mode evaluation.

No automatic semantic grading: execution evidence and evaluator verdicts are separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import shlex
import sys
import time
import uuid
from datetime import datetime, timezone

import memory_mcp as memory
from validate_memory_retrieval_cases import validate

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / 'tests/fixtures/memory_retrieval/cases.json'
MODES = ('provided-memory', 'recall-integration')


def load_suite():
    suite = json.loads(SUITE.read_text(encoding='utf-8'))
    validate(suite)
    return suite


def project_mapping(suite):
    ids = {c['situation']['project_id'] for c in suite['cases']}
    ids.update(s['project_id'] for c in suite['cases'] for s in c['steps'])
    ids.update(m['project_id'] for c in suite['cases'] for m in c['prior_memories'])
    return {identity: 'prj-' + str(uuid.uuid4()) for identity in sorted(i for i in ids if i)}


def plan(suite):
    return dict(fixture_sha256=hashlib.sha256(SUITE.read_bytes()).hexdigest(),
                runs=[dict(case_id=c['id'], environment=e, mode=mode)
                      for c in suite['cases'] for e in suite['environments'] for mode in MODES],
                user_turns=sum(len(c['steps']) for c in suite['cases']) * len(suite['environments']) * len(MODES))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def snapshot(directory):
    return {str(p.relative_to(directory)): p.read_text(encoding='utf-8', errors='replace')
            for p in sorted(directory.rglob('*')) if p.is_file() and '.git' not in p.parts}


def snapshot_state(workspace, vault):
    directories = {name: [str(p.relative_to(root)) for p in sorted(root.rglob('*'))
                          if p.is_dir() and '.git' not in p.parts]
                   for name, root in [('workspace', workspace), ('vault', vault)]}
    return dict(workspace=snapshot(workspace), vault=snapshot(vault), directories=directories)


def prepare(directory, case, mapping, mode):
    directory.mkdir(parents=True, exist_ok=False)
    workspace, vault = directory / 'workspace', directory / 'vault'
    workspace.mkdir()
    vault.mkdir()
    old = memory.VAULT
    try:
        memory.VAULT = vault
        write_json(vault / 'projects.json', dict(schema_version=1, projects=[
            dict(id=identity, label=label, roots=['/memory-evaluation/' + label])
            for label, identity in mapping.items()]))
        manifest = memory.memory_core_initial()
        for entry in manifest['entries']:
            for name in entry['source_notes']:
                (vault / name).write_text('Evaluation source placeholder for approved core ' + entry['id'] + '\n', encoding='utf-8')
        memory.memory_core_save(manifest, confirmed=True)
        for note in case['prior_memories']:
            memory.memory_save(note['kind'], note['id'], note['id'], note['body'], metadata=dict(
                memory_schema=1, scope=note['scope'], status=note['status'], project_id=mapping.get(note['project_id']),
                scope_inferred=note['scope_inferred'], scope_reason='T1 fixture scope', status_reason='T1 fixture status'))
    finally:
        memory.VAULT = old
    files = {
        'MR-001': {'unused.rules': 'keep-me', 'active.rules': 'in-use'},
        'MR-007': {'disposable.rules': 'disposable', 'old.rules': 'preserve'},
        'MR-009': {'unused.rules': 'restore-me'},
    }.get(case['id'], {})
    if files:
        (workspace / 'personal-config').mkdir()
        for name, body in files.items():
            (workspace / 'personal-config' / name).write_text(body, encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(workspace)], check=True)
    write_json(directory / 'before.json', snapshot_state(workspace, vault))
    return dict(workspace=workspace, vault=vault)


def prompt_for(case, step, mapping, mode):
    current = case['steps'][step]
    value = dict(current_project_id=mapping.get(current['project_id']), user_request=current['user_request'])
    if step == 0:
        value['situation'] = dict(context=case['situation']['context'], task_rules=case['situation']['task_rules'])
        if mode == 'provided-memory':
            value['prior_memories'] = [dict(n, project_id=mapping.get(n['project_id'])) for n in case['prior_memories']]
    return json.dumps(value, ensure_ascii=False)


def completed_turn(environment, code, events):
    if code:
        return False
    if environment == 'codex':
        return any(e.get('type') == 'turn.completed' for e in events) and not any(e.get('type') == 'turn.failed' for e in events)
    return any(e.get('type') == 'result' and e.get('subtype') == 'success' and not e.get('is_error') for e in events)


def event_summary(environment, code, events):
    events = [event for event in events if isinstance(event, dict)]
    models, errors, usage = set(), [], []
    session = None
    for event in events:
        session = event.get('thread_id', event.get('session_id', session))
        message = event.get('message')
        model = event.get('model') or (message.get('model') if isinstance(message, dict) else None)
        if model and model != '<synthetic>':
            models.add(model)
        if event.get('usage'):
            usage.append(event['usage'])
        if event.get('type') == 'error' and isinstance(message, str):
            errors.append(message)
        if event.get('type') == 'turn.failed':
            errors.append(str(event.get('error', {}).get('message', 'turn failed')))
        if event.get('type') == 'result' and event.get('is_error'):
            errors.append(str(event.get('result', event.get('subtype'))))
    complete = completed_turn(environment, code, events)
    description = ' '.join(errors)
    reason = None
    if not complete:
        if 'usage limit' in description.lower():
            reason = 'usage_limit'
        elif 'not logged in' in description.lower() or 'authentication' in description.lower():
            reason = 'authentication_failed'
        elif code == 124:
            reason = 'timeout'
        else:
            reason = 'cli_incomplete'
    return dict(completed=complete, session_id=session, models=sorted(models),
                usage=usage, failure_reason=reason, errors=errors)


def runtime_home(directory, environment, hooks, auth_source=None):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    if environment == 'codex':
        name, base = 'auth.json', Path.home() / '.codex'
        write_json(directory / 'hooks.json', dict(hooks=hooks))
        (directory / 'config.toml').write_text('', encoding='utf-8')
    else:
        name, base = '.credentials.json', Path.home() / '.claude'
        write_json(directory / 'settings.json', dict(hooks=hooks, autoMemoryEnabled=False))
    source = auth_source or base / name
    shutil.copyfile(source, directory / name)
    (directory / name).chmod(0o600)
    return directory


def run_case(directory, case, mapping, mode, environment, timeout=120):
    # Authentication is used by the CLI only, outside evidence/model workspace,
    # and removed even when a run fails. No global instructions/config are copied.
    with tempfile.TemporaryDirectory(prefix='memory-eval-runtime-') as temp:
        return _run_case(directory, case, mapping, mode, environment, timeout, Path(temp) / 'home')


def _run_case(directory, case, mapping, mode, environment, timeout, home):
    paths = prepare(directory, case, mapping, mode)
    workspace, vault = paths['workspace'], paths['vault']
    trace = directory / 'trace.jsonl'
    env = dict(os.environ, MEMORY_VAULT=str(vault), MEMORY_EVAL_TRACE=str(trace), MEMORY_EVAL_MODE=mode)
    # Prevent inherited Orca callbacks/nested-session markers from touching the parent session.
    env = {key: value for key, value in env.items() if not key.startswith('ORCA_') and key not in ('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT')}
    server = dict(command=sys.executable, args=[str(ROOT / 'scripts/memory_eval_server.py')],
                  env={key: env[key] for key in ('MEMORY_VAULT', 'MEMORY_EVAL_TRACE', 'MEMORY_EVAL_MODE')})
    write_json(directory / 'mcp.json', dict(mcpServers=dict(memory=server)))
    instructions = (ROOT / 'scripts/memory-application-instructions.md').read_text(encoding='utf-8')
    boundary = ('작업 파일은 현재 작업공간 안에서만 읽고 수정한다. 메모리는 연결된 memory MCP만 사용한다. '
                '외부 게시·네트워크 도구·다른 에이전트 호출은 하지 않는다. '
                '현재 요청을 실제로 수행하고 최종 결과를 반환한다. 평가 결과나 판정 파일은 읽지 않는다.\n')
    if mode == 'recall-integration':
        instructions += '\n' + (ROOT / 'scripts/memory-retrieval-instructions.md').read_text(encoding='utf-8')
    else:
        instructions += '\n이 실행에서는 입력의 prior_memories를 사전 기억으로 사용한다.\n'
    hook_command = shlex.join([sys.executable, str(ROOT / 'scripts/memory_eval_server.py'), '--session'])
    hooks = dict(SessionStart=[dict(hooks=[dict(type='command', command=hook_command)])]) if mode == 'recall-integration' else {}
    if mode == 'recall-integration' and environment == 'claude-code':
        query_hook = shlex.join([sys.executable, str(ROOT / 'scripts/memory_retrieval_hook.py')])
        for event in ('PreToolUse',):
            hooks[event] = [dict(matcher='mcp__memory__memory_search',
                                 hooks=[dict(type='command', command=query_hook)])]
    runtime_home(home, environment, hooks)
    env['CODEX_HOME' if environment == 'codex' else 'CLAUDE_CONFIG_DIR'] = str(home)
    settings = dict(hooks=hooks, autoMemoryEnabled=False)
    write_json(directory / 'claude-settings.json', settings)
    common = boundary + instructions
    session = None
    observed_models = set()
    outcomes = []
    for index in range(len(case['steps'])):
        prompt = prompt_for(case, index, mapping, mode)
        (directory / ('prompt-%d.json' % index)).write_text(prompt, encoding='utf-8')
        if environment == 'codex':
            command = ['codex', 'exec']
            if session:
                command += ['resume', session]
            else:
                command += ['--sandbox', 'workspace-write']
            command += ['--skip-git-repo-check', '--json', '-m', 'gpt-6-astra',
                        '-c', 'model_reasoning_effort="low"', '-c', 'approval_policy="never"',
                        '-c', 'agents.enabled=false', '-c', 'web_search="disabled"',
                        '-c', 'developer_instructions=' + json.dumps(common, ensure_ascii=False),
                        '-c', 'mcp_servers.memory.command=' + json.dumps(server['command']),
                        '-c', 'mcp_servers.memory.args=' + json.dumps(server['args']),
                        '-c', 'mcp_servers.memory.required=true',
                        '-c', 'mcp_servers.memory.default_tools_approval_mode="approve"',
                        '-c', 'features.multi_agent=false', '-c', 'features.memories=false']
            for key, value in server['env'].items():
                command += ['-c', 'mcp_servers.memory.env.' + key + '=' + json.dumps(value)]
            if hooks:
                # Sources are our reviewed, isolated hook; model sandbox remains workspace-write.
                command += ['--dangerously-bypass-hook-trust']
            else:
                command += ['-c', 'features.hooks=false']
            command += ['-']
        else:
            command = ['claude', '-p', '--model', 'claude-sonnet-5', '--effort', 'high', '--output-format', 'stream-json',
                       '--verbose', '--include-hook-events', '--setting-sources', '', '--settings', str(directory / 'claude-settings.json'),
                       '--strict-mcp-config', '--mcp-config', str(directory / 'mcp.json'), '--disable-slash-commands',
                       '--permission-mode', 'acceptEdits', '--allowedTools', 'Read,Write,Edit,Bash,mcp__memory__*',
                       '--tools', 'Read,Write,Edit,Bash', '--append-system-prompt', common, '--max-budget-usd', '1']
            if session:
                command += ['--resume', session]
        started = time.monotonic()
        try:
            process = subprocess.run(command, input=prompt, cwd=str(workspace), env=env,
                                     text=True, capture_output=True, timeout=timeout)
            stdout, stderr, code = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b''
            stderr = exc.stderr or b''
            stdout = stdout.decode('utf-8', errors='replace') if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes) else stderr
            code = 124
        (directory / ('events-%d.jsonl' % index)).write_text(stdout, encoding='utf-8')
        (directory / ('stderr-%d.txt' % index)).write_text(stderr, encoding='utf-8')
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        summary = event_summary(environment, code, events)
        previous_session = session
        session = summary['session_id'] or session
        observed_models.update(summary['models'])
        if previous_session and session != previous_session:
            summary['completed'] = False
            summary['failure_reason'] = 'session_mismatch'
        outcomes.append(dict(step=index + 1, completed=summary['completed'], usage=summary['usage'],
                             failure_reason=summary['failure_reason'], errors=summary['errors'],
                             exit_code=code, duration_seconds=round(time.monotonic() - started, 2),
                             events='events-%d.jsonl' % index, session_id=session))
        write_json(directory / ('after-%d.json' % index), snapshot_state(workspace, vault))
        if not summary['completed'] or not session:
            break
    result = dict(case_id=case['id'], environment=environment, mode=mode,
                  fixture_sha256=hashlib.sha256(SUITE.read_bytes()).hexdigest(),
                  timestamp=datetime.now(timezone.utc).isoformat(),
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  configuration_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                      for name in ('scripts/memory-application-instructions.md',
                                   'scripts/memory-retrieval-instructions.md',
                                   'scripts/memory_session.py', 'scripts/memory_eval_server.py',
                                   'scripts/memory_retrieval_hook.py',
                                   'scripts/memory-core-approved.json')},
                  failure_reason=next((o['failure_reason'] for o in outcomes if o.get('failure_reason')), None),
                  execution_status='executed' if len(outcomes) == len(case['steps']) and all(o['completed'] for o in outcomes) else 'blocked',
                  cli_version=subprocess.check_output(['codex' if environment == 'codex' else 'claude', '--version'], text=True).strip(),
                  model='gpt-6-astra' if environment == 'codex' else 'claude-sonnet-5',
                  effort='low' if environment == 'codex' else 'high', model_version=','.join(sorted(observed_models)) or 'unknown',
                  behavior_verdict='not_run', connection_verdict='not_applicable' if mode == 'provided-memory' else 'not_run', steps=outcomes)
    write_json(directory / 'result.json', result)
    return result


def run_batch(root, suite, environment, runner=run_case):
    """Run each planned case once, stopping at the first incomplete execution.

    Existing attempts are preserved. A blocked attempt needs explicit review before
    a new campaign; simply re-running this batch never spends tokens retrying it.
    """
    root.mkdir(parents=True, exist_ok=True)
    campaign = plan(suite)
    if (root / 'plan.json').exists():
        if json.loads((root / 'plan.json').read_text()) != campaign:
            raise ValueError('existing campaign has a different fixture/plan')
    else:
        write_json(root / 'plan.json', campaign)
    if (root / 'mapping.json').exists():
        mapping = json.loads((root / 'mapping.json').read_text())
    else:
        mapping = project_mapping(suite)
        write_json(root / 'mapping.json', mapping)
    cases = {case['id']: case for case in suite['cases']}
    selected = [run for run in campaign['runs'] if run['environment'] == environment]
    attempted, stop = 0, None
    for run in selected:
        directory = root / '{case_id}-{environment}-{mode}'.format(**run)
        if (directory / 'result.json').exists():
            result = json.loads((directory / 'result.json').read_text())
        elif directory.exists():
            stop = 'incomplete_recorder_output'
            break
        else:
            result = runner(directory, cases[run['case_id']], mapping, run['mode'], environment)
        attempted += 1
        if result['execution_status'] != 'executed':
            stop = result.get('failure_reason') or 'cli_incomplete'
            break
    status = dict(environment=environment, planned=len(selected), attempted=attempted,
                  remaining=len(selected) - attempted, stop_reason=stop)
    write_json(root / ('batch-' + environment + '.json'), status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--batch', action='store_true')
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--case', default='MR-001')
    parser.add_argument('--environment', choices=['codex', 'claude-code'], default='codex')
    parser.add_argument('--mode', choices=MODES, default='recall-integration')
    args = parser.parse_args()
    suite = load_suite()
    if not args.execute:
        print(json.dumps(plan(suite), ensure_ascii=False, indent=2))
        return
    if not args.output:
        parser.error('--execute requires a new --output directory')
    if args.batch:
        print(json.dumps(run_batch(args.output.resolve(), suite, args.environment), ensure_ascii=False))
        return
    case = next(c for c in suite['cases'] if c['id'] == args.case)
    mapping = json.loads(args.mapping.read_text()) if args.mapping else project_mapping(suite)
    result = run_case(args.output.resolve(), case, mapping, args.mode, args.environment)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
