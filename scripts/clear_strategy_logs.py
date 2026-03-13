#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATE_DIR = PROJECT_ROOT / "strategies" / "simulate"
SKIP_DIR_NAMES = {"__pycache__"}


@dataclass
class ClearResult:
    strategy_dir: Path
    logs_dir: Path
    removed_count: int
    skipped: bool = False
    reason: str = ""


def is_strategy_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name.startswith((".", "_")) or path.name in SKIP_DIR_NAMES:
        return False
    return True


def iter_default_targets() -> list[Path]:
    if not SIMULATE_DIR.is_dir():
        raise SystemExit(f"simulate 目录不存在: {SIMULATE_DIR}")
    return sorted(path for path in SIMULATE_DIR.iterdir() if is_strategy_dir(path))


def resolve_target(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.exists():
        resolved = candidate.resolve()
    else:
        resolved = (SIMULATE_DIR / raw).resolve()

    if resolved.name == "logs":
        resolved = resolved.parent

    if not resolved.exists():
        raise FileNotFoundError(f"目录不存在: {raw}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"不是目录: {raw}")
    return resolved


def clear_logs(strategy_dir: Path) -> ClearResult:
    logs_dir = strategy_dir / "logs"
    if not logs_dir.exists():
        return ClearResult(strategy_dir=strategy_dir, logs_dir=logs_dir, removed_count=0, skipped=True, reason="logs 不存在")
    if not logs_dir.is_dir():
        return ClearResult(strategy_dir=strategy_dir, logs_dir=logs_dir, removed_count=0, skipped=True, reason="logs 不是目录")

    removed_count = 0
    for child in logs_dir.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed_count += 1

    return ClearResult(strategy_dir=strategy_dir, logs_dir=logs_dir, removed_count=removed_count)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="清空 strategies/simulate 下策略 logs 目录中的内容；默认处理全部策略，也可指定一个或多个目录。"
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="策略目录名、策略目录路径，或 logs 目录路径；不传则清空全部 simulate 策略日志",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.targets:
        targets = []
        errors = []
        for raw in args.targets:
            try:
                targets.append(resolve_target(raw))
            except Exception as exc:
                errors.append(f"{raw}: {exc}")
        if errors:
            for error in errors:
                print(f"[error] {error}", file=sys.stderr)
            return 1
    else:
        targets = iter_default_targets()

    seen = set()
    unique_targets = []
    for target in targets:
        key = str(target.resolve())
        if key not in seen:
            seen.add(key)
            unique_targets.append(target)

    print(f"目标目录: {SIMULATE_DIR}")
    print(f"处理数量: {len(unique_targets)}")

    results = [clear_logs(target) for target in unique_targets]

    for result in results:
        name = result.strategy_dir.name
        if result.skipped:
            print(f"[skip] {name}: {result.reason}")
        else:
            print(f"[ok] {name}: 已删除 {result.removed_count} 个条目")

    cleared = sum(1 for item in results if not item.skipped)
    skipped = sum(1 for item in results if item.skipped)
    removed = sum(item.removed_count for item in results)
    print("-" * 60)
    print(f"完成: cleared={cleared}, skipped={skipped}, removed={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
