import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OPS_DIR = PROJECT_ROOT / "scripts" / "ops"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_restart_fails_when_backend_exits_after_initial_pid_check(tmp_path: Path) -> None:
    """A delayed FastAPI startup failure must make the restart command fail."""
    ops_dir = tmp_path / "scripts" / "ops"
    ops_dir.mkdir(parents=True)
    for script_name in ("restart_app.sh", "start_app.sh"):
        shutil.copy2(OPS_DIR / script_name, ops_dir / script_name)

    _write_executable(ops_dir / "stop_app.sh", "#!/bin/bash\nexit 0\n")
    (tmp_path / "src" / "backend").mkdir(parents=True)
    (tmp_path / "src" / "frontend").mkdir(parents=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    _write_executable(
        fake_python,
        """#!/bin/bash
if [ "${1:-}" = "--version" ]; then
    echo "Python 3.11.0"
    exit 0
fi
if [ "${1:-}" = "-c" ]; then
    exit 0
fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "uvicorn" ]; then
    sleep 4
    echo "database connection refused" >&2
    exit 1
fi
exit 0
""",
    )
    _write_executable(
        fake_bin / "setsid",
        "#!/bin/bash\nexec \"$@\"\n",
    )
    _write_executable(
        fake_bin / "node",
        "#!/bin/bash\necho 'v20.0.0'\n",
    )
    _write_executable(fake_bin / "npm", "#!/bin/bash\nexit 0\n")

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "BACKEND_PORT": str(_available_local_port()),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
        }
    )
    result = subprocess.run(
        ["bash", str(ops_dir / "restart_app.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "后端服务" in result.stdout
