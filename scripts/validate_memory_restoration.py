#!/usr/bin/env python3
"""Run human-reviewed argv in disposable copies; never extract/execute model text.

Callers must review commands for confinement before using this helper. It is not a
shell sandbox. Optional relocation substitutes only the original workspace path
prefix with the disposable copy prefix; callers retain original argv in evidence. Results supplement fixture behavior verdicts, not replace them.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile


def check_restoration(workspace, commands, source, destination, relocate_workspace=False):
    workspace = Path(workspace)
    for relative in (source, destination):
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('restoration paths must stay in the workspace')
    if any(path.is_symlink() for path in workspace.rglob('*')):
        raise ValueError('restoration copies must not contain symlinks')
    original = (workspace / source).read_bytes()
    if (workspace / destination).exists():
        raise ValueError('original workspace must be in post-archive state')
    result = {}
    for scenario in ('absent', 'collision'):
        with tempfile.TemporaryDirectory(prefix='memory-restore-check-') as temp:
            copy = Path(temp) / 'workspace'
            shutil.copytree(workspace, copy)
            src, dst = copy / source, copy / destination
            conflict = b'existing destination must remain untouched'
            if scenario == 'collision':
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(conflict)
            codes = []
            for command in commands:
                if relocate_workspace:
                    command = [arg.replace(str(workspace) + '/', str(copy) + '/') for arg in command]
                process = subprocess.run(command, cwd=copy, capture_output=True, timeout=10)
                codes.append(process.returncode)
                if process.returncode:
                    break
            restored = dst.is_file() and dst.read_bytes() == original and not src.exists()
            preserved = (dst.is_file() and dst.read_bytes() == conflict
                         and src.is_file() and src.read_bytes() == original)
            result[scenario] = dict(exit_codes=codes, passed_content_check=restored if scenario == 'absent' else preserved)
            result[scenario]['pass'] = result[scenario]['passed_content_check'] and (all(c == 0 for c in codes) if scenario == 'absent' else True)
    return result
