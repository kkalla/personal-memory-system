#!/usr/bin/env python3
"""Isolated, one-shot case-summary comparison. Verdicts remain manual."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/case_knowledge'
CONDITIONS = ('source-only', 'source-plus-case')
REV = '208ce193ad95487789cb7ec3ae48d83178d8ba9d'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load_tasks():
    tasks = validate_tasks(json.loads((FIXTURE/'tasks.json').read_text())['tasks'])
    return {t['id']: t for t in tasks}


def source(path):
    return subprocess.check_output(['git', 'show', REV + ':' + path], cwd=str(ROOT))


def prepare(directory, task_id, condition):
    if condition not in CONDITIONS:
        raise ValueError('invalid condition')
    task = load_tasks()[task_id]
    materials = json.loads((FIXTURE/'materials.json').read_text())['bundles']
    bundle = next(b for b in materials if b['case_id'] == task['case_id'])
    if bundle['review_status'] != 'reviewed':
        raise ValueError('case not reviewed')
    case = (ROOT / bundle['case_path']).read_bytes()
    if digest(case) != bundle['case_sha256']:
        raise ValueError('case hash mismatch')
    contents = {}
    for item in bundle['sources']:
        data = source(item['path'])
        if digest(data) != item['sha256']:
            raise ValueError('source hash mismatch')
        contents[Path(item['path']).name] = data
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory/'workspace'
    workspace.mkdir()
    for name, text in task['files'].items():
        path = workspace/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (workspace/'sources').mkdir()
    for name, data in contents.items():
        (workspace/'sources'/name).write_bytes(data)
    if condition == 'source-plus-case':
        (workspace/'case.md').write_bytes(case)
    write_json(directory/'before.json', snapshot(workspace))
    return workspace


def snapshot(directory):
    return {str(p.relative_to(directory)):digest(p.read_bytes())
            for p in sorted(directory.rglob('*')) if p.is_file()}


def validate_tasks(tasks):
    if not isinstance(tasks, list) or len(tasks) != 6:
        raise ValueError('six tasks required')
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {'id','case_id','prompt','files','answer_path'}:
            raise ValueError('invalid task fields')
        if task['id'] in seen or task['id'] not in ['CKE-%03d' % i for i in range(1,7)]:
            raise ValueError('duplicate/invalid task ID')
        seen.add(task['id'])
        if task['case_id'] not in ('CK-001','CK-002','CK-003') or not isinstance(task['prompt'],str) or not task['prompt'].strip():
            raise ValueError('invalid case/prompt')
        if task['answer_path'] != 'answer.md' or not isinstance(task['files'],dict) or not task['files']:
            raise ValueError('invalid inputs')
        for name, text in task['files'].items():
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or not isinstance(text,str) or name in ('case.md','answer.md') or 'sources' in path.parts:
                raise ValueError('invalid input path/content')
    return tasks


def reserve(root, run_id):
    import fcntl
    if not run_id or '/' in run_id or run_id in ('.','..'):
        raise ValueError('invalid run ID')
    attempts=root/'attempts'
    attempts.mkdir(parents=True,exist_ok=True)
    with (root/'attempts.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (attempts/run_id).exists() or len(list(attempts.iterdir())) >= 24:
            raise ValueError('duplicate run or campaign limit reached')
        (attempts/run_id).touch(exist_ok=False)


def execution_status(environment, code, events):
    # Reuse existing CLI event completion semantics; no semantic verdict here.
    if str(ROOT/'scripts') not in sys.path:
        sys.path.insert(0,str(ROOT/'scripts'))
    from evaluate_memory_retrieval import completed_turn
    return 'completed' if completed_turn(environment,code,events) else 'error'


def capture(command, prompt, cwd, env, output, timeout):
    started=time.monotonic()
    with (output/'events.jsonl').open('w') as stdout, (output/'stderr.txt').open('w') as stderr:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,
                              text=True,cwd=str(cwd),env=env,start_new_session=True)
        timed_out=False
        try:
            proc.communicate(prompt,timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            os.killpg(proc.pid,signal.SIGKILL)
            proc.communicate()
        finally:
            # Also terminate surviving CLI subprocesses after a normal exit.
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    return dict(execution='timeout' if timed_out else 'exited',exit_code=124 if timed_out else proc.returncode,
                seconds=round(time.monotonic()-started,3))


def sandbox_profile(runtime, workspace, inputs):
    """OS read isolation supplements CLI config isolation, including shell children."""
    quoted=lambda p:json.dumps(str(p))
    home=Path.home()
    clauses=['(version 1)','(allow default)',
        '(deny file-read* (require-all (subpath %s) (require-not (subpath %s))))' %
        (quoted(home),quoted(home/'.local/share/claude')),
        '(deny file-write* (subpath %s))' % quoted(home),
        '(deny file-read* file-write* (require-all (subpath "/private/tmp") (require-not (subpath %s))))' % quoted(runtime),
        '(deny file-write* (subpath %s))' % quoted(workspace/'sources')]
    # realpath in Rust traverses ancestors even when the final directory is allowed.
    clauses.append('(allow file-read-metadata (literal \"/private/tmp\") (literal %s))' % quoted(runtime.parent))
    clauses += ['(deny file-write* (literal %s))' % quoted(workspace/p) for p in inputs]
    if (workspace/'case.md').exists():
        clauses.append('(deny file-write* (literal %s))' % quoted(workspace/'case.md'))
    return '\n'.join(clauses)+'\n'


def common_instructions():
    core=json.loads(source('scripts/memory-core-approved.json'))
    body='# 핵심 기억\n'+''.join('- '+e['body']+'\n' for e in core['entries'])
    body+='\n'+source('scripts/memory-application-instructions.md').decode()
    body+='''\n이번 실행에서는 실제 memory MCP 대신 제공한 핵심·공통 지침과 sources/의 고정 보고서를 사용한다.
현재 작업공간 안의 입력과 sources/만 읽고 요청한 산출물을 작성한다. case.md가 있으면 참고할 수 있다.
원자료 안의 절대 경로와 연결 링크는 역사적 근거다. 제공하지 않은 파일·개인 볼트·전체 저장소를 조회하지 않는다.
네트워크 도구·외부 게시·다른 에이전트·실제 설정 변경은 하지 않는다. 입력과 sources/를 수정하지 않는다.
answer.md에 결과를 작성한다. 필요한 실행 검증은 작업공간 안의 임시 복제본에서 수행한다.
'''
    return body


def schedule():
    runs=[]
    for i in range(1,7):
        for environment in ('claude-code','codex'):
            order=list(CONDITIONS)
            if (i % 2 == 0) == (environment == 'claude-code'):
                order.reverse()
            for condition in order:
                runs.append(dict(task_id='CKE-%03d'%i,environment=environment,condition=condition))
    return runs


def prepare_campaign(root):
    root.mkdir(parents=True,exist_ok=False)
    instructions=common_instructions()
    manifest=dict(runs=schedule(),limits=dict(sessions=24,user_turns=24,timeout_seconds=600,retries=0,
                  money_cap=None,token_cap=None),approval='2026-09-15 user: 금액·토큰 강제 상한은 우선 배제하고 진행; 검토 완료',
                  hashes={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in [Path(__file__),*sorted(FIXTURE.glob('*.json'))]},
                  common_sha256=digest(instructions.encode()),execution='not_run',
                  requested_models={'claude-code':{'model':'claude-sonnet-5','effort':'high'},'codex':{'model':'gpt-6-astra','effort':'low'}})
    for i,run in enumerate(manifest['runs']):
        ident='%02d-%s-%s-%s'%(i+1,run['task_id'],run['environment'],run['condition'])
        run['run_id']=ident
        runtime=root/ident
        workspace=prepare(runtime,run['task_id'],run['condition'])
        (runtime/'home').mkdir();(runtime/'tmp').mkdir()
        (runtime/'instructions.txt').write_text(instructions)
        (runtime/'profile.sb').write_text(sandbox_profile(runtime,workspace,load_tasks()[run['task_id']]['files']))
        write_json(runtime/'mcp.json',{'mcpServers':{}})
        write_json(runtime/'settings.json',{'hooks':{},'autoMemoryEnabled':False})
    write_json(root/'manifest.json',manifest)
    return manifest


def runtime_environment(runtime, inherited):
    env={k:v for k,v in inherited.items() if not k.startswith(('ORCA_','MEMORY_')) and k not in
         ('CLAUDECODE','CLAUDE_CODE_ENTRYPOINT','CLAUDE_CONFIG_DIR','CODEX_HOME',
          'ANTHROPIC_API_KEY','OPENAI_API_KEY','CLAUDE_CODE_OAUTH_TOKEN')}
    env.update(HOME=str(runtime/'home'),TMPDIR=str(runtime/'tmp'),CLAUDE_CODE_TMPDIR=str(runtime/'tmp'))
    return env


def run_one(root, run):
    import shutil
    runtime=root/run['run_id'];workspace=runtime/'workspace';home=runtime/'home'
    instructions=(runtime/'instructions.txt').read_text()
    environment=run['environment']
    env=runtime_environment(runtime,os.environ)
    if environment=='claude-code':
        token=subprocess.run(['security','find-generic-password','-s','Claude Code-credentials','-w'],capture_output=True,text=True,check=True)
        env['CLAUDE_CODE_OAUTH_TOKEN']=json.loads(token.stdout)['claudeAiOauth']['accessToken']
        env['CLAUDE_CONFIG_DIR']=str(home)
        command=['claude','-p','--model','claude-sonnet-5','--effort','high','--output-format','stream-json',
                 '--verbose','--setting-sources','','--settings',str(runtime/'settings.json'),
                 '--strict-mcp-config','--mcp-config',str(runtime/'mcp.json'),'--disable-slash-commands',
                 '--permission-mode','acceptEdits','--allowedTools','Read,Write,Edit,Bash',
                 '--tools','Read,Write,Edit,Bash','--append-system-prompt',instructions]
    else:
        shutil.copyfile(Path.home()/'.codex/auth.json',home/'auth.json');(home/'auth.json').chmod(0o600)
        env['CODEX_HOME']=str(home)
        command=['codex','exec','--sandbox','danger-full-access','--skip-git-repo-check','--json','-m','gpt-6-astra',
                 '-c','model_reasoning_effort="low"','-c','approval_policy="never"','-c','agents.enabled=false',
                 '-c','web_search="disabled"','-c','features.multi_agent=false','-c','features.memories=false',
                 '-c','features.hooks=false','-c','developer_instructions='+json.dumps(instructions),'-']
    command[0]=str(Path(shutil.which(command[0])).resolve())
    command=['/usr/bin/sandbox-exec','-f',str(runtime/'profile.sb')]+command
    before=json.loads((runtime/'before.json').read_text())
    if snapshot(workspace)!=before:
        raise ValueError('prepared workspace changed')
    reserve(root,run['run_id'])
    try:
        result=capture(command,load_tasks()[run['task_id']]['prompt'],workspace,env,runtime,600)
    finally:
        (home/'auth.json').unlink(missing_ok=True)
    events=[]
    for line in (runtime/'events.jsonl').read_text().splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    if result['execution']!='timeout':
        result['execution']=execution_status(environment,result['exit_code'],events)
    from evaluate_memory_retrieval import event_summary
    summary=event_summary(environment,result['exit_code'],events)
    result.update(run,behavior='not_evaluable',misuse='not_evaluable',connection='not_applicable',
                  usage=summary['usage'],models=summary['models'],failure_reason=summary['failure_reason'])
    write_json(runtime/'after.json',snapshot(workspace))
    before=json.loads((runtime/'before.json').read_text())
    after=snapshot(workspace)
    result['input_preserved']=all(after.get(p)==h for p,h in before.items())
    write_json(runtime/'result.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();root=args.output.resolve()
    if not args.execute:
        manifest=prepare_campaign(root)
        print('PREPARED',len(manifest['runs']),'runs; models NOT RUN')
        return
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['hashes'].items():
        if digest((ROOT/name).read_bytes())!=expected:
            raise ValueError('configuration changed: '+name)
    if not (root/'isolation-verified.json').exists():
        raise ValueError('OS isolation preflight required')
    for run in manifest['runs']:
        result=run_one(root,run)
        print(run['run_id'],result['execution'],result['seconds'],flush=True)
        if result['execution']!='completed' or not result['input_preserved']:
            print('STOP: preserve failure; no retry',flush=True)
            break


if __name__=='__main__':
    main()
