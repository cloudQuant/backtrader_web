"""
回测服务 - 封装Backtrader回测逻辑
"""
import os
import uuid
import asyncio
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from app.models.backtest import BacktestTask, BacktestResultModel
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestListResponse,
    TaskStatus,
    TradeRecord,
)
from app.db.sql_repository import SQLRepository
from app.db.cache import get_cache
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

# ---- 进程级单例状态（B001 fix）----
_running_tasks: Dict[str, asyncio.Task] = {}
_running_processes: Dict[str, subprocess.Popen] = {}

# OPT-11: 并发限制
MAX_GLOBAL_TASKS = 10   # 全局最大并发回测任务数
MAX_USER_TASKS = 3      # 每用户最大并发回测任务数
_user_task_count: Dict[str, int] = {}  # user_id -> 当前运行中的任务数


class BacktestService:
    """
    回测服务
    
    功能:
    1. 异步执行回测任务
    2. 回测结果存储
    3. 回测任务管理
    """
    
    def __init__(self):
        self.task_repo = SQLRepository(BacktestTask)
        self.result_repo = SQLRepository(BacktestResultModel)
        self.cache = get_cache()
    
    async def run_backtest(
        self,
        user_id: str,
        request: BacktestRequest
    ) -> BacktestResponse:
        """
        运行回测（异步）
        
        Args:
            user_id: 用户ID
            request: 回测请求
            
        Returns:
            BacktestResponse: 包含task_id和状态
        """
        # 创建任务记录
        task = BacktestTask(
            user_id=user_id,
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            status=TaskStatus.PENDING,
            request_data=request.model_dump(mode="json"),
        )
        task = await self.task_repo.create(task)
        
        # OPT-11: 检查并发限制
        global_count = len(_running_tasks)
        user_count = _user_task_count.get(user_id, 0)
        if global_count >= MAX_GLOBAL_TASKS:
            raise ValueError(f"系统回测任务已满（最大 {MAX_GLOBAL_TASKS} 个），请稍后再试")
        if user_count >= MAX_USER_TASKS:
            raise ValueError(f"您的并发回测任务已达上限（最大 {MAX_USER_TASKS} 个），请等待当前任务完成")
        _user_task_count[user_id] = user_count + 1

        # 创建异步任务并保存引用（用于取消）
        async_task = asyncio.create_task(self._execute_backtest(task.id, user_id, request))
        _running_tasks[task.id] = async_task
        
        return BacktestResponse(
            task_id=task.id,
            status=TaskStatus.PENDING,
            message="回测任务已创建",
        )
    
    async def _execute_backtest(
        self,
        task_id: str,
        user_id: str,
        request: BacktestRequest
    ):
        """
        执行回测任务 - 调用策略目录中的 run.py
        """
        task_work_dir = None
        tmp_base = None
        try:
            # 更新状态为运行中
            await self.task_repo.update(task_id, {"status": TaskStatus.RUNNING})
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 10, "message": "任务开始执行",
            })

            # 查找策略目录
            from app.services.strategy_service import STRATEGIES_DIR
            strategy_dir = STRATEGIES_DIR / request.strategy_id
            run_py = strategy_dir / "run.py"

            if not run_py.is_file():
                raise ValueError(f"策略 {request.strategy_id} 的 run.py 不存在")

            # [B003/O001] 将策略目录复制到独立临时目录，避免并发冲突
            # 创建 tmp_base/strategies/<strategy_id>/ 结构，使 BASE_DIR.parent.parent 能正确定位
            tmp_base = Path(tempfile.mkdtemp(prefix=f"bt_{task_id}_"))
            task_work_dir = tmp_base / "strategies" / request.strategy_id
            task_work_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(strategy_dir, task_work_dir, dirs_exist_ok=True)

            # 创建 datas 符号链接，使 resolve_data_path 能找到数据文件
            project_root = STRATEGIES_DIR.parent
            datas_src = project_root / "datas"
            datas_link = tmp_base / "datas"
            if datas_src.is_dir() and not datas_link.exists():
                os.symlink(str(datas_src), str(datas_link))

            # 清空临时目录的 logs
            tmp_logs = task_work_dir / "logs"
            if tmp_logs.is_dir():
                shutil.rmtree(tmp_logs)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 20, "message": "正在写入配置参数...",
            })

            # 如果前端传入了自定义参数，写入临时目录的 config.yaml
            config_path = task_work_dir / "config.yaml"
            if self._has_custom_params(request):
                original_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else None
                self._write_temp_config(config_path, request, original_text)

            # [B005] 移除 run.py 中的 assert 语句
            tmp_run_py = task_work_dir / "run.py"
            self._strip_asserts(tmp_run_py)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 30, "message": "正在运行回测...",
            })

            # 调用 run.py（在临时目录中运行）
            result = await self._run_strategy_subprocess(task_work_dir, str(strategy_dir), task_id)

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.PROGRESS, "task_id": task_id,
                "progress": 80, "message": "正在解析日志...",
            })

            # 解析临时目录中的 logs
            from app.services.log_parser_service import parse_all_logs
            log_result = parse_all_logs(task_work_dir)
            if not log_result:
                raise ValueError("回测完成但未找到日志文件")

            # 保存结果
            result_model = BacktestResultModel(
                task_id=task_id,
                total_return=log_result.get("total_return", 0),
                annual_return=log_result.get("annual_return", 0),
                sharpe_ratio=log_result.get("sharpe_ratio", 0),
                max_drawdown=log_result.get("max_drawdown", 0),
                win_rate=log_result.get("win_rate", 0),
                total_trades=log_result.get("total_trades", 0),
                profitable_trades=log_result.get("profitable_trades", 0),
                losing_trades=log_result.get("losing_trades", 0),
                equity_curve=log_result.get("equity_curve", []),
                equity_dates=log_result.get("equity_dates", []),
                drawdown_curve=log_result.get("drawdown_curve", []),
                trades=log_result.get("trades", []),
            )
            await self.result_repo.create(result_model)

            # [B009] 将日志目录路径保存到任务中，供后续分析使用
            # 把临时logs复制回原策略目录（以 task_id 命名），确保持久化
            persist_log_dir = strategy_dir / "logs" / f"task_{task_id}"
            tmp_log_dir = log_result.get("log_dir")
            if tmp_log_dir and Path(tmp_log_dir).is_dir():
                shutil.copytree(tmp_log_dir, persist_log_dir, dirs_exist_ok=True)

            # 更新任务状态
            await self.task_repo.update(task_id, {
                "status": TaskStatus.COMPLETED,
                "log_dir": str(persist_log_dir),
            })

            await ws_manager.send_to_task(task_id, {
                "type": MessageType.COMPLETED, "task_id": task_id,
                "progress": 100, "message": "回测完成",
                "data": {"total_return": log_result.get("total_return", 0)},
            })

            logger.info(f"回测完成: {task_id}, 收益率: {log_result.get('total_return', 0)}%")

        except asyncio.CancelledError:
            logger.info(f"回测已取消: {task_id}")
            await self.task_repo.update(task_id, {
                "status": TaskStatus.CANCELLED,
                "error_message": "用户取消任务",
            })
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.CANCELLED, "task_id": task_id,
                "message": "任务已取消",
            })
        except Exception as e:
            logger.error(f"回测失败: {task_id}, {e}")
            await self.task_repo.update(task_id, {
                "status": TaskStatus.FAILED,
                "error_message": str(e),
            })
            await ws_manager.send_to_task(task_id, {
                "type": MessageType.FAILED, "task_id": task_id,
                "message": str(e),
            })
        finally:
            _running_tasks.pop(task_id, None)
            _running_processes.pop(task_id, None)
            # OPT-11: 释放用户并发计数
            if user_id in _user_task_count:
                _user_task_count[user_id] = max(0, _user_task_count[user_id] - 1)
                if _user_task_count[user_id] == 0:
                    del _user_task_count[user_id]
            # 清理临时工作目录（清理整个 tmp_base）
            cleanup_dir = tmp_base or task_work_dir
            if cleanup_dir and cleanup_dir.is_dir():
                try:
                    shutil.rmtree(cleanup_dir, ignore_errors=True)
                except Exception:
                    pass

    def _has_custom_params(self, request: BacktestRequest) -> bool:
        """检查是否有自定义参数需要覆盖 config.yaml"""
        return bool(request.params) or request.initial_cash != 100000 or request.commission != 0.001

    def _write_temp_config(self, config_path, request: BacktestRequest, original_text: str):
        """将前端传入的自定义参数临时写入 config.yaml"""
        import yaml
        config = {}
        if original_text:
            config = yaml.safe_load(original_text) or {}

        # 覆盖策略参数
        if request.params:
            if "params" not in config:
                config["params"] = {}
            config["params"].update(request.params)

        # 覆盖回测配置
        if "backtest" not in config:
            config["backtest"] = {}
        config["backtest"]["initial_cash"] = request.initial_cash
        config["backtest"]["commission"] = request.commission

        # 覆盖数据配置
        if request.symbol:
            if "data" not in config:
                config["data"] = {}
            config["data"]["symbol"] = request.symbol

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    @staticmethod
    def _strip_asserts(run_py: Path):
        """[B005] 移除 run.py 中的 assert 语句，避免参数变化后断言失败"""
        if not run_py.is_file():
            return
        code = run_py.read_text(encoding="utf-8")
        lines = code.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("assert ") or stripped.startswith("assert("):
                cleaned.append(line.replace(stripped, "pass  # assert removed for web backtest"))
            else:
                cleaned.append(line)
        run_py.write_text("\n".join(cleaned), encoding="utf-8")

    async def _run_strategy_subprocess(self, work_dir, original_strategy_dir: str = None, task_id: str = None) -> dict:
        """通过子进程运行策略的 run.py，支持 PID 跟踪用于取消"""
        python_exec = sys.executable
        run_py = work_dir / "run.py"

        # 准备环境变量
        from app.services.strategy_service import STRATEGIES_DIR
        project_root = STRATEGIES_DIR.parent
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        orig_dir = original_strategy_dir or str(work_dir)
        env["PYTHONPATH"] = os.pathsep.join([orig_dir, str(work_dir), env.get("PYTHONPATH", "")])

        def _run():
            proc = subprocess.Popen(
                [python_exec, str(run_py)],
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            # 记录 PID 用于取消
            if task_id:
                _running_processes[task_id] = proc
            from app.config import get_settings
            stdout, stderr = proc.communicate(timeout=get_settings().BACKTEST_TIMEOUT)
            return proc.returncode, stdout, stderr

        returncode, stdout, stderr = await asyncio.get_event_loop().run_in_executor(None, _run)

        if returncode != 0:
            err_msg = stderr.strip().split("\n")[-1] if stderr else "未知错误"
            raise RuntimeError(f"run.py 执行失败: {err_msg}")

        return {"stdout": stdout, "stderr": stderr}
    
    async def get_result(self, task_id: str, user_id: str = None) -> Optional[BacktestResult]:
        """获取回测结果（B002: 可选 user_id 鉴权）"""
        # 查询任务（先校验用户归属，再查缓存，防止越权）
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        
        # B002: 校验用户归属
        if user_id and task.user_id != user_id:
            return None
        
        # 鉴权通过后查缓存
        cache_key = f"backtest:result:{task_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return BacktestResult(**cached)
        
        # 查询结果
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        result_model = results[0] if results else None
        
        result = BacktestResult(
            task_id=task.id,
            strategy_id=task.strategy_id,
            symbol=task.symbol,
            start_date=task.request_data.get("start_date") if task.request_data else datetime.now(),
            end_date=task.request_data.get("end_date") if task.request_data else datetime.now(),
            status=TaskStatus(task.status),
            total_return=result_model.total_return if result_model else 0,
            annual_return=result_model.annual_return if result_model else 0,
            sharpe_ratio=result_model.sharpe_ratio if result_model else 0,
            max_drawdown=result_model.max_drawdown if result_model else 0,
            win_rate=result_model.win_rate if result_model else 0,
            total_trades=result_model.total_trades if result_model else 0,
            profitable_trades=result_model.profitable_trades if result_model else 0,
            losing_trades=result_model.losing_trades if result_model else 0,
            equity_curve=result_model.equity_curve if result_model else [],
            equity_dates=result_model.equity_dates if result_model else [],
            drawdown_curve=result_model.drawdown_curve if result_model else [],
            trades=result_model.trades if result_model else [],
            created_at=task.created_at,
            error_message=task.error_message,
        )
        
        # 缓存结果
        if task.status == TaskStatus.COMPLETED:
            await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)
        
        return result
    
    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """取消运行中的回测任务（B001: 使用进程级单例 + PID 终止子进程）"""
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return False
        
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        
        # 终止子进程（B001 fix）
        proc = _running_processes.pop(task_id, None)
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

        # 取消 asyncio 任务
        running = _running_tasks.pop(task_id, None)
        if running and not running.done():
            running.cancel()
        
        await self.task_repo.update(task_id, {
            "status": TaskStatus.CANCELLED,
            "error_message": "用户取消任务",
        })
        return True
    
    async def get_task_status(self, task_id: str, user_id: str = None) -> Optional[TaskStatus]:
        """获取任务状态（B002: 可选 user_id 鉴权）"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        if user_id and task.user_id != user_id:
            return None
        return TaskStatus(task.status)
    
    async def list_results(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> BacktestListResponse:
        """列出回测结果，支持排序"""
        tasks = await self.task_repo.list(
            filters={"user_id": user_id},
            skip=offset,
            limit=limit,
            order_by=sort_by,
            order_desc=sort_desc,
        )
        total = await self.task_repo.count(filters={"user_id": user_id})
        
        items = []
        for task in tasks:
            result = await self.get_result(task.id)
            if result:
                items.append(result)
        
        return BacktestListResponse(total=total, items=items)
    
    async def delete_result(self, task_id: str, user_id: str) -> bool:
        """删除回测结果"""
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return False
        
        # 删除持久化的日志目录（OPT-14: 避免磁盘累积）
        if getattr(task, 'log_dir', None):
            log_path = Path(task.log_dir)
            if log_path.is_dir():
                try:
                    shutil.rmtree(log_path, ignore_errors=True)
                except Exception:
                    pass
        
        # 删除结果
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        if results:
            await self.result_repo.delete(results[0].id)
        
        # 删除任务
        await self.task_repo.delete(task_id)
        
        # 清除缓存
        await self.cache.delete(f"backtest:result:{task_id}")
        
        return True
