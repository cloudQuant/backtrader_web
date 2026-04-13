from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import shlex
import subprocess
import sys


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_dump_command(args: argparse.Namespace, output_path: pathlib.Path) -> list[str]:
    command = [
        "mysqldump",
        f"--host={args.host}",
        f"--port={args.port}",
        f"--user={args.user}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--databases",
        args.database,
    ]
    if args.extra_database:
        command.append(args.extra_database)
    command.extend(["--result-file", str(output_path)])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup MySQL databases to a SQL file.")
    parser.add_argument("--env-file", default="src/backend/.env")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="")
    parser.add_argument("--extra-database", default="", help="Optional second database to dump")
    parser.add_argument("--output-dir", default="./runtime/backups")
    args = parser.parse_args()

    env_values = parse_env_file(pathlib.Path(args.env_file).expanduser())
    args.host = args.host or os.environ.get("DB_HOST") or env_values.get("DB_HOST") or "127.0.0.1"
    args.port = args.port or int(os.environ.get("DB_PORT") or env_values.get("DB_PORT") or "3306")
    args.user = args.user or os.environ.get("DB_USER") or env_values.get("DB_USER") or "root"
    args.password = (
        args.password
        or os.environ.get("DB_PASSWORD")
        or env_values.get("DB_PASSWORD")
        or os.environ.get("MYSQL_ROOT_PASSWORD")
        or env_values.get("MYSQL_ROOT_PASSWORD", "")
    )
    args.database = args.database or os.environ.get("DB_NAME") or env_values.get("DB_NAME") or "backtrader_web"

    if not args.password:
        print("Missing MySQL password. Pass --password or set DB_PASSWORD/MYSQL_ROOT_PASSWORD.", file=sys.stderr)
        return 1

    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"mysql-backup-{timestamp}.sql"

    command = build_dump_command(args, output_path)
    env = dict(os.environ)
    env["MYSQL_PWD"] = args.password

    print("Running:", " ".join(shlex.quote(part) for part in command))
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        if output_path.exists():
            output_path.unlink()
        print(result.stderr.strip() or "mysqldump failed", file=sys.stderr)
        return result.returncode

    print(f"Backup created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
