"""Verify a wheel as a uv tool in a clean home, away from the source checkout.

Usage: uv run python tests/verify_install.py dist/nala-0.2.0-py3-none-any.whl
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def main():
    wheel = Path(sys.argv[1]).resolve()
    uv = shutil.which('uv')
    assert uv, 'uv must be installed'
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any('__pycache__' in name or name.endswith('.pyc') for name in names)
        tools = sorted(Path(n).name for n in names if n.startswith('nala/runtime/bin/') and n.count('/') == 3)
        assert len(tools) == 10, tools
        for required in ('context.yaml', 'context/data-oriented-design.md', 'prompts/compact-conversation.md'):
            assert 'nala/runtime/' + required in names, required
    with tempfile.TemporaryDirectory(prefix='nala-install-check-') as tmp:
        root = Path(tmp)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('NALA_', 'UV_', 'PYTHON', 'OPENROUTER')) and k != 'VIRTUAL_ENV'}
        env.update(HOME=tmp, UV_TOOL_DIR=str(root/'tools'), UV_TOOL_BIN_DIR=str(root/'commands'), PATH='/usr/bin:/bin')

        def run(args, cwd=root, ok=True):
            result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True, capture_output=True, timeout=120)
            if ok:
                assert result.returncode == 0, f'{args}\n{result.stdout}\n{result.stderr}'
            return result

        run([uv, 'tool', 'install', '--python', sys.argv[2] if len(sys.argv) > 2 else sys.executable, wheel])
        hostile = root/'unrelated-venv/bin'
        hostile.mkdir(parents=True)
        (hostile/'python3').write_text('#!/bin/sh\nexit 89\n')
        (hostile/'python3').chmod(0o755)
        env['PATH'] = str(hostile) + ':/usr/bin:/bin'
        env['VIRTUAL_ENV'] = str(hostile.parent)
        for tool in tools:
            run([root/'commands'/tool, '--help'])
        print(f'PASS: clean uv tool installation; all {len(tools)} command entry points run')
        for project in ('project-a', 'project-b'):
            cwd = root/project
            cwd.mkdir()
            run(['git', 'init', '-q', cwd])
            result = run([root/'commands/nala', '--status', '--json'], cwd=cwd)
            assert str(cwd/'.nala') in result.stdout, result.stdout
            assert 'deepseek/deepseek-v4.1-flash' in result.stdout
        print('PASS: independent .nala roots in two unrelated Git projects')
        source = root/'project-a/example.py'
        source.write_text('def hello():\n    return "world"\n')
        run([root/'commands/nala-file-split', '--file', source, '--output', root/'split', '--json'])
        assert (root/'split/index.json').is_file()
        print('PASS: installed file-split launches its bundled Python helper')
        prompt = root/'prompt.txt'
        prompt.write_text('hello')
        result = run([root/'commands/nala-llm-text', '--file', prompt], ok=False)
        assert result.returncode != 0 and 'missing credentials' in result.stderr, result.stderr
        print('PASS: clean home reports missing credentials without using host configuration')
        python = root/'tools/nala/bin/python'
        check = '''
from pathlib import Path
import sys
import nala
runtime = Path(nala.__file__).parent / 'runtime'
sys.path.insert(0, str(runtime / 'bin/helpers'))
from nala_cli import resolve_prompt_path
assert resolve_prompt_path(Path.cwd(), 'compact-conversation.md').is_file()
assert (runtime / 'context.yaml').read_text().strip() == '- context/data-oriented-design.md'
'''
        run([python, '-c', check])
        print('PASS: installed prompt and context resources resolve outside checkout')


if __name__ == '__main__':
    main()
