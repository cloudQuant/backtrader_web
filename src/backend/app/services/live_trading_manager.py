"""
实盘交易管理服务

管理策略实例的增删、启停，使用 JSON 文件持久化配置，子进程运行策略。
"""
import json
import uuid
import sys
import signal
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id

logger = logging.getLogger(__name__)

# 持久化文件
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"


def _load_instances() -> Dict[str, dict]:
    if _INSTANCES_FILE.is_file():
        try:
            return json.loads(_INSTANCES_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _save_instances(data: Dict[str, dict]):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _INSTANCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _find_latest_log_dir(strategy_dir: Path) -> Optional[str]:
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None
    subdirs = sorted(logs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in subdirs:
        if d.is_dir():
            return str(d)
    return None


def _is_pid_alive(pid: int) -> bool:
    """检查进程是否存活"""
    try:
        import os
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class LiveTradingManager:
    """实盘交易管理器（单例模式使用）"""

    def __init__(self):
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        # 启动时同步进程状态
        self._sync_status_on_boot()

    def _sync_status_on_boot(self):
        """启动时检查之前 running 的实例是否还在运行"""
        instances = _load_instances()
        changed = False
        for iid, inst in instances.items():
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
                    changed = True
        if changed:
            _save_instances(instances)

    # ---- CRUD ----

    def list_instances(self) -> List[dict]:
        instances = _load_instances()
        result = []
        for iid, inst in instances.items():
            # 实时刷新 status
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
            inst["id"] = iid
            # 最新日志目录
            strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
            inst["log_dir"] = _find_latest_log_dir(strategy_dir)
            result.append(inst)
        # 保存刷新后的状态
        _save_instances({r["id"]: {k: v for k, v in r.items()} for r in result})
        return result

    def add_instance(self, strategy_id: str, params: Optional[Dict[str, Any]] = None) -> dict:
        strategy_dir = STRATEGIES_DIR / strategy_id
        if not (strategy_dir / "run.py").is_file():
            raise ValueError(f"策略 {strategy_id} 不存在或缺少 run.py")

        tpl = get_template_by_id(strategy_id)
        name = tpl.name if tpl else strategy_id

        iid = str(uuid.uuid4())[:8]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst = {
            "id": iid,
            "strategy_id": strategy_id,
            "strategy_name": name,
            "status": "stopped",
            "pid": None,
            "error": None,
            "params": params or {},
            "created_at": now,
            "started_at": None,
            "stopped_at": None,
            "log_dir": _find_latest_log_dir(strategy_dir),
        }

        instances = _load_instances()
        instances[iid] = inst
        _save_instances(instances)
        return inst

    def remove_instance(self, instance_id: str) -> bool:
        instances = _load_instances()
        if instance_id not in instances:
            return False
        inst = instances[instance_id]
        # 先停止
        if inst.get("status") == "running" and inst.get("pid"):
            self._kill_pid(inst["pid"])
        del instances[instance_id]
        _save_instances(instances)
        self._processes.pop(instance_id, None)
        return True

    def get_instance(self, instance_id: str) -> Optional[dict]:
        instances = _load_instances()
        inst = instances.get(instance_id)
        if inst:
            inst["id"] = instance_id
            strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
            inst["log_dir"] = _find_latest_log_dir(strategy_dir)
        return inst

    # ---- 启停 ----

    async def start_instance(self, instance_id: str) -> dict:
        instances = _load_instances()
        if instance_id not in instances:
            raise ValueError("实例不存在")
        inst = instances[instance_id]

        if inst["status"] == "running" and inst.get("pid") and _is_pid_alive(inst["pid"]):
            raise ValueError("策略已在运行中")

        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        run_py = strategy_dir / "run.py"
        if not run_py.is_file():
            raise ValueError(f"run.py 不存在: {run_py}")

        # 启动子进程
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(run_py),
            cwd=str(strategy_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[instance_id] = proc

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst["status"] = "running"
        inst["pid"] = proc.pid
        inst["error"] = None
        inst["started_at"] = now
        instances[instance_id] = inst
        _save_instances(instances)

        # 后台等待进程结束
        asyncio.create_task(self._wait_process(instance_id, proc))

        inst["id"] = instance_id
        return inst

    async def stop_instance(self, instance_id: str) -> dict:
        instances = _load_instances()
        if instance_id not in instances:
            raise ValueError("实例不存在")
        inst = instances[instance_id]

        pid = inst.get("pid")
        if pid and _is_pid_alive(pid):
            self._kill_pid(pid)

        # 清理 asyncio 进程引用
        proc = self._processes.pop(instance_id, None)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst["status"] = "stopped"
        inst["pid"] = None
        inst["stopped_at"] = now
        instances[instance_id] = inst
        _save_instances(instances)
        inst["id"] = instance_id
        return inst

    async def start_all(self) -> dict:
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if inst["status"] == "running" and inst.get("pid") and _is_pid_alive(inst["pid"]):
                continue
            try:
                await self.start_instance(iid)
                success += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": "started"})
            except Exception as e:
                failed += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": str(e)})
        return {"success": success, "failed": failed, "details": details}

    async def stop_all(self) -> dict:
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if inst["status"] != "running":
                continue
            try:
                await self.stop_instance(iid)
                success += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": "stopped"})
            except Exception as e:
                failed += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": str(e)})
        return {"success": success, "failed": failed, "details": details}

    # ---- 内部方法 ----

    async def _wait_process(self, instance_id: str, proc: asyncio.subprocess.Process):
        """后台等待进程结束，更新状态"""
        try:
            await proc.wait()
        except Exception:
            pass
        finally:
            instances = _load_instances()
            if instance_id in instances:
                inst = instances[instance_id]
                if proc.returncode != 0:
                    stderr = ""
                    if proc.stderr:
                        try:
                            stderr_bytes = await proc.stderr.read()
                            stderr = stderr_bytes.decode("utf-8", errors="replace")[-500:]
                        except Exception:
                            pass
                    inst["status"] = "error"
                    inst["error"] = stderr or f"进程退出码: {proc.returncode}"
                else:
                    inst["status"] = "stopped"
                inst["pid"] = None
                inst["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 刷新日志目录
                strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
                inst["log_dir"] = _find_latest_log_dir(strategy_dir)
                instances[instance_id] = inst
                _save_instances(instances)
            self._processes.pop(instance_id, None)

    @staticmethod
    def _kill_pid(pid: int):
        import os
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


# 全局单例
_manager: Optional[LiveTradingManager] = None


def get_live_trading_manager() -> LiveTradingManager:
    global _manager
    if _manager is None:
        _manager = LiveTradingManager()
    return _manager
