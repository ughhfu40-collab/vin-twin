"""Installer regression: reject the logged Python 3.14 failure before pip."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/usr/bin/env bash\nset -eu\n' + body)
    path.chmod(0o755)


def project(tmp_path):
    shutil.copytree(ROOT / 'scripts', tmp_path / 'scripts')
    (tmp_path / 'frontend/node_modules').mkdir(parents=True)
    return tmp_path


def test_installer_rejects_python314_before_install(tmp_path):
    root = project(tmp_path)
    py = root / 'fake-python'
    executable(py, 'echo 3.14\n')
    result = subprocess.run(['bash', 'scripts/install.sh'], cwd=root,
                            env={**os.environ, 'VIN_PYTHON': str(py)}, capture_output=True, text=True)
    assert result.returncode == 1 and 'Python 3.12 is required' in result.stderr
    assert not (root / '.venv').exists()


def test_installer_preserves_incompatible_environment(tmp_path):
    root = project(tmp_path)
    executable(root / '.venv/bin/python', 'echo 3.14\n')
    (root / '.venv/old-marker').write_text('keep')
    py = root / 'fake-python'
    executable(py, '''if [ "$1" = "-c" ]; then echo 3.12; exit; fi
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
 mkdir -p .venv/bin
 printf '#!/usr/bin/env bash\necho pip-installed > pip-marker\n' > .venv/bin/python
 chmod +x .venv/bin/python
fi
''')
    executable(root / 'fake-bin/npm', 'echo npm-installed > npm-marker\n')
    result = subprocess.run(['bash', 'scripts/install.sh'], cwd=root,
                            env={**os.environ, 'VIN_PYTHON': str(py), 'PATH': str(root / 'fake-bin') + os.pathsep + os.environ['PATH']},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(list(root.glob('.venv-backup.*/environment/old-marker'))) == 1
    assert (root / 'pip-marker').exists() and (root / 'npm-marker').exists()


@pytest.mark.parametrize("command", [["bash", "scripts/dev.sh"], ["node", "scripts/dev.mjs"]])
def test_dev_stops_before_frontend_for_incomplete_backend(tmp_path, command):
    root = project(tmp_path)
    executable(root / '.venv/bin/python', 'exit 1\n')
    executable(root / 'fake-bin/npm', 'echo started > frontend-marker\n')
    result = subprocess.run(command, cwd=root,
                            env={**os.environ, 'PATH': str(root / 'fake-bin') + os.pathsep + os.environ['PATH']},
                            capture_output=True, text=True)
    assert result.returncode == 1 and 'incomplete' in result.stderr
    assert not (root / 'frontend-marker').exists()
