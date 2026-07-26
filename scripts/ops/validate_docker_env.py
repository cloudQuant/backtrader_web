from __future__ import annotations

import argparse
import pathlib
import socket
import sys
from typing import Iterable


REQUIRED_KEYS = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "ADMIN_PASSWORD",
)

DEFAULT_SECRET_VALUES = {
    "your-secret-key-change-in-production",
    "your-jwt-secret-change-in-production",
}

DEFAULT_ADMIN_PASSWORDS = {"admin123", "password", "12345678"}


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        raise FileNotFoundError(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def validate_required_keys(values: dict[str, str], required_keys: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for key in required_keys:
        if not values.get(key):
            errors.append(f"Missing required key: {key}")
    has_db_triplet = bool(values.get("DB_USER") and values.get("DB_PASSWORD") and values.get("DB_NAME"))
    has_mysql_root = bool(values.get("MYSQL_ROOT_PASSWORD") and values.get("MYSQL_DB_MAIN"))
    has_database_url = bool(values.get("DATABASE_URL"))
    if not (has_db_triplet or has_mysql_root or has_database_url):
        errors.append(
            "Missing Docker database configuration: provide DB_USER/DB_PASSWORD/DB_NAME, "
            "or MYSQL_ROOT_PASSWORD/MYSQL_DB_MAIN, or DATABASE_URL"
        )
    return errors


def validate_secret_values(values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    debug_enabled = values.get("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = values.get(key, "")
        if value in DEFAULT_SECRET_VALUES:
            message = f"{key} still uses default placeholder value"
            if debug_enabled:
                warnings.append(message)
            else:
                errors.append(message)
        if len(value) < 32:
            message = f"{key} should be at least 32 characters long"
            if debug_enabled:
                warnings.append(message)
            else:
                errors.append(message)
    admin_password = values.get("ADMIN_PASSWORD", "")
    if admin_password in DEFAULT_ADMIN_PASSWORDS:
        message = "ADMIN_PASSWORD still uses an insecure default value"
        if debug_enabled:
            warnings.append(message)
        else:
            errors.append(message)
    return errors, warnings


def validate_mysql_connectivity(host: str, port: int, timeout: float) -> list[str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return []
    except OSError as exc:
        return [f"Cannot connect to MySQL at {host}:{port}: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Docker env file and local MySQL reachability.")
    parser.add_argument("--env-file", default="src/backend/.env")
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=3306)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    env_path = pathlib.Path(args.env_file).expanduser().resolve()
    try:
        values = parse_env_file(env_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(validate_required_keys(values, REQUIRED_KEYS))
    secret_errors, secret_warnings = validate_secret_values(values)
    errors.extend(secret_errors)
    warnings.extend(secret_warnings)
    errors.extend(validate_mysql_connectivity(args.mysql_host, args.mysql_port, args.timeout))

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1

    print("Validation passed.")
    print(f"- env file: {env_path}")
    print(f"- mysql: {args.mysql_host}:{args.mysql_port}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
