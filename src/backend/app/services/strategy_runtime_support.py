from pathlib import Path
from typing import Any

import yaml

_BACKTRADER_WEB_DIR = Path(__file__).resolve().parents[4]

_FLAT_LOG_FILENAMES = frozenset(
    {
        "value.log",
        "data.log",
        "trade.log",
        "bar.log",
        "indicator.log",
        "position.log",
        "order.log",
        "system.log",
        "tick.log",
    }
)

_LOG_METADATA_FILENAMES = frozenset(
    {
        "current_position.yaml",
        "current_position.json",
        "run_info.json",
        "monitor.log",
        "error.log",
        "signal.log",
    }
)


def has_log_artifacts(log_dir: Path) -> bool:
    if not log_dir.is_dir():
        return False
    known_files = _FLAT_LOG_FILENAMES | _LOG_METADATA_FILENAMES
    return any((log_dir / file_name).is_file() for file_name in known_files)


def find_latest_log_dir(strategy_dir: Path) -> str | None:
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None
    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    meaningful_subdirs = [d for d in subdirs if has_log_artifacts(d)]
    if meaningful_subdirs:
        return str(meaningful_subdirs[0])
    if has_log_artifacts(logs_dir):
        return str(logs_dir)
    return None


def load_strategy_config(strategy_dir: Path) -> dict[str, Any]:
    config_path = strategy_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_strategy_env(
    strategy_dir: Path,
    backtrader_web_dir: Path | None = None,
) -> dict[str, str]:
    project_dir = backtrader_web_dir or _BACKTRADER_WEB_DIR
    result: dict[str, str] = {}
    for candidate in (strategy_dir / ".env", project_dir / ".env"):
        if not candidate.is_file():
            continue
        with candidate.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text or text.startswith("#") or "=" not in text:
                    continue
                key, _, value = text.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in result:
                    result[key] = value
    return result


def resolve_strategy_dir(strategy_id: str, strategies_dir: Path) -> Path:
    text = str(strategy_id or "")
    if ".." in text or text.startswith("/") or "\\" in text:
        raise ValueError(f"Invalid strategy_id: {strategy_id}")
    base_dir = strategies_dir.resolve() if isinstance(strategies_dir, Path) else strategies_dir
    path = (strategies_dir / text).resolve()
    try:
        path.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Strategy path escapes base directory: {strategy_id}") from None
    return path


def infer_gateway_params(strategy_dir: Path) -> dict[str, Any] | None:
    config_path = strategy_dir / "config.yaml"
    if not isinstance(config_path, Path):
        return None
    if not config_path.is_file():
        return None
    try:
        cfg = yaml.safe_load(config_path.read_text("utf-8")) or {}
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None

    gateway = cfg.get("gateway")
    if isinstance(gateway, dict) and gateway.get("enabled"):
        return {
            "enabled": True,
            "provider": str(gateway.get("provider", "ctp_gateway")),
            "exchange_type": str(gateway.get("exchange_type", "CTP")),
            "asset_type": str(gateway.get("asset_type", "FUTURE")),
        }

    if isinstance(cfg.get("ctp"), dict):
        return {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
        }

    return None
