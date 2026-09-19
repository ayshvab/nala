"""Run the bundled CLI layout with the tool environment's Python and helpers."""
import os
from pathlib import Path
import runpy
import sys


def main():
    command = Path(sys.argv[0]).name
    # Editable development uses the original files; wheels carry the same layout.
    runtime = Path(__file__).resolve().parent / 'runtime'
    if not runtime.is_dir():
        runtime = Path(__file__).resolve().parents[2]
    script = runtime / 'bin' / command
    if not command.startswith('nala') or not script.is_file():
        raise SystemExit(f'Unknown nala command: {command}')
    # Internal scripts use /usr/bin/env python3 and invoke siblings by name.
    # Keep both tied to this installation even inside another project's venv.
    os.environ['PATH'] = os.pathsep.join((
        str(Path(sys.executable).parent), str(runtime / 'bin'), os.environ.get('PATH', '')
    ))
    runpy.run_path(str(script), run_name='__main__')
