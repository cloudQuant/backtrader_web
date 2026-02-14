"""
实盘交易管理服务测试

测试：
- 实例CRUD操作
- 实例启动/停止
- 子进程管理
- 进程状态同步
- 错误处理
- 日志目录查找
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path
import asyncio

from app.services.live_trading_manager import (
    LiveTradingManager,
    get_live_trading_manager,
    _load_instances,
    _save_instances,
    _find_latest_log_dir,
    _is_pid_alive,
    _manager,
)


class TestUtilityFunctions:
    """测试工具函数"""

    def test_load_instances_from_file(self):
        """测试从文件加载实例"""
        # Mock file exists with content
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = '{"test": {"status": "running"}}'

            result = _load_instances()

            assert result == {"test": {"status": "running"}}

    def test_load_instances_file_not_exists(self):
        """测试文件不存在时返回空字典"""
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = False

            result = _load_instances()

            assert result == {}

    def test_load_instances_invalid_json(self):
        """测试无效JSON返回空字典"""
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = 'invalid json'

            result = _load_instances()

            assert result == {}

    def test_save_instances(self):
        """测试保存实例到文件"""
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            test_data = {"test": {"status": "running"}}

            _save_instances(test_data)

            # Verify write was called
            mock_file.write_text.assert_called_once()

    def test_find_latest_log_dir(self):
        """测试查找最新日志目录"""
        with patch('app.services.live_trading_manager.Path') as mock_path:
            mock_strategy_dir = MagicMock()
            mock_logs_dir = MagicMock()
            mock_subdir1 = MagicMock()
            mock_subdir2 = MagicMock()

            # Setup mock hierarchy
            mock_subdir1.is_dir.return_value = True
            mock_subdir2.is_dir.return_value = True
            mock_subdir1.stat.return_value.st_mtime = 1000
            mock_subdir2.stat.return_value.st_mtime = 2000  # Latest

            mock_logs_dir.is_dir.return_value = True
            mock_logs_dir.iterdir.return_value = [mock_subdir1, mock_subdir2]
            mock_strategy_dir.__truediv__.return_value = mock_logs_dir

            result = _find_latest_log_dir(mock_strategy_dir)

            # Should return the latest directory
            assert result is not None

    def test_find_latest_log_dir_no_logs(self):
        """测试没有日志目录时返回None"""
        with patch('app.services.live_trading_manager.Path') as mock_path:
            mock_strategy_dir = MagicMock()
            mock_logs_dir = MagicMock()
            mock_logs_dir.is_dir.return_value = False
            mock_strategy_dir.__truediv__.return_value = mock_logs_dir

            result = _find_latest_log_dir(mock_strategy_dir)

            assert result is None

    def test_is_pid_alive(self):
        """测试检查进程存活"""
        # Test with a valid PID (current process)
        import os
        current_pid = os.getpid()
        assert _is_pid_alive(current_pid) is True

    def test_is_pid_not_alive(self):
        """测试检查不存在的进程"""
        # Use an invalid PID
        assert _is_pid_alive(999999) is False


class TestLiveTradingManagerInitialization:
    """测试管理器初始化"""

    def test_initialization(self):
        """测试初始化"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()
            assert manager._processes == {}

    def test_initialization_syncs_status(self):
        """测试初始化时同步状态"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"status": "running", "pid": 12345},  # Will be marked as stopped
                "inst2": {"status": "stopped", "pid": None},
            }

            with patch('app.services.live_trading_manager._is_pid_alive', return_value=False):
                with patch('app.services.live_trading_manager._save_instances') as mock_save:
                    manager = LiveTradingManager()
                    # Should have saved updated status
                    assert mock_save.called


class TestListInstances:
    """测试列出实例"""

    def test_list_all_instances(self):
        """测试列出所有实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "user_id": "user2", "status": "running"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager._is_pid_alive', return_value=True):
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value="/logs/test"):
                        with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                            manager = LiveTradingManager()
                            result = manager.list_instances()

                            assert len(result) == 2
                            assert all("id" in r for r in result)

    def test_list_instances_by_user(self):
        """测试按用户筛选实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "user_id": "user2", "status": "running"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager._is_pid_alive', return_value=True):
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value="/logs/test"):
                        with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                            manager = LiveTradingManager()
                            result = manager.list_instances(user_id="user1")

                            assert len(result) == 1
                            assert result[0]["id"] == "inst1"

    def test_list_instances_updates_dead_processes(self):
        """测试列出实例时更新已停止的进程"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._save_instances') as mock_save:
                with patch('app.services.live_trading_manager._is_pid_alive', return_value=False):
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                        with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                            manager = LiveTradingManager()
                            result = manager.list_instances()

                            # Status should be updated to stopped
                            assert result[0]["status"] == "stopped"
                            assert result[0]["pid"] is None


class TestAddInstance:
    """测试添加实例"""

    def test_add_instance_success(self):
        """测试成功添加实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
                    with patch('app.services.live_trading_manager.get_template_by_id') as mock_tpl:
                        with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="测试策略")

                            manager = LiveTradingManager()
                            result = manager.add_instance("test_strategy", user_id="user1")

                            assert result["strategy_id"] == "test_strategy"
                            assert result["status"] == "stopped"
                            assert result["user_id"] == "user1"
                            assert "id" in result

    def test_add_instance_strategy_not_found(self):
        """测试策略不存在"""
        with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
            with patch('app.services.live_trading_manager._load_instances', return_value={}):
                with patch('app.services.live_trading_manager._save_instances'):
                    mock_strategy_dir = MagicMock()
                    mock_run_py = MagicMock()
                    mock_run_py.is_file.return_value = False
                    mock_strategy_dir.__truediv__.return_value = mock_run_py
                    mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                    manager = LiveTradingManager()

                    with pytest.raises(ValueError, match="不存在或缺少 run.py"):
                        manager.add_instance("test_strategy")

    def test_add_instance_with_params(self):
        """测试添加带参数的实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
                    with patch('app.services.live_trading_manager.get_template_by_id') as mock_tpl:
                        with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="测试策略")

                            manager = LiveTradingManager()
                            params = {"fast": 10, "slow": 20}
                            result = manager.add_instance("test_strategy", params=params, user_id="user1")

                            assert result["params"] == params


class TestRemoveInstance:
    """测试删除实例"""

    def test_remove_instance_success(self):
        """测试成功删除实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user1")

                assert result is True

    def test_remove_instance_not_found(self):
        """测试删除不存在的实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("nonexistent")

                assert result is False

    def test_remove_instance_wrong_user(self):
        """测试删除其他用户的实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user2")

                assert result is False

    def test_remove_instance_kills_process(self):
        """测试删除实例时终止进程"""
        import os
        import signal

        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                # Patch os.kill directly to verify the kill attempt
                with patch.object(os, 'kill') as mock_kill:
                    manager = LiveTradingManager()
                    manager.remove_instance("inst1")

                    # Should have called kill with SIGTERM (os.kill is also called by _is_pid_alive with signal 0)
                    mock_kill.assert_any_call(12345, signal.SIGTERM)


class TestGetInstance:
    """测试获取实例"""

    def test_get_instance_success(self):
        """测试成功获取实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                with patch('app.services.live_trading_manager._find_latest_log_dir', return_value="/logs/test"):
                    manager = LiveTradingManager()
                    result = manager.get_instance("inst1", user_id="user1")

                    assert result is not None
                    assert result["id"] == "inst1"

    def test_get_instance_not_found(self):
        """测试获取不存在的实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()
            result = manager.get_instance("nonexistent")

            assert result is None

    def test_get_instance_wrong_user(self):
        """测试获取其他用户的实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            manager = LiveTradingManager()
            result = manager.get_instance("inst1", user_id="user2")

            assert result is None


class TestStartInstance:
    """测试启动实例"""

    @pytest.mark.asyncio
    async def test_start_instance_success(self):
        """测试成功启动实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                        mock_strategy_dir = MagicMock()
                        mock_run_py = MagicMock()
                        mock_run_py.is_file.return_value = True
                        mock_strategy_dir.__truediv__.return_value = mock_run_py
                        mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                        manager = LiveTradingManager()

                        # Mock create_subprocess_exec
                        mock_proc = AsyncMock()
                        mock_proc.pid = 12345
                        mock_proc.returncode = None

                        with patch('asyncio.create_subprocess_exec', return_value=mock_proc):
                            with patch('asyncio.create_task'):
                                result = await manager.start_instance("inst1")

                                assert result["status"] == "running"
                                assert result["pid"] == 12345

    @pytest.mark.asyncio
    async def test_start_instance_already_running(self):
        """测试启动已在运行的实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._is_pid_alive', return_value=True):
                manager = LiveTradingManager()

                with pytest.raises(ValueError, match="已在运行中"):
                    await manager.start_instance("inst1")

    @pytest.mark.asyncio
    async def test_start_instance_not_found(self):
        """测试启动不存在的实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="实例不存在"):
                await manager.start_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_start_instance_no_run_py(self):
        """测试run.py不存在"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
                mock_strategy_dir = MagicMock()
                mock_run_py = MagicMock()
                mock_run_py.is_file.return_value = False
                mock_strategy_dir.__truediv__.return_value = mock_run_py
                mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                manager = LiveTradingManager()

                with pytest.raises(ValueError, match="run.py 不存在"):
                    await manager.start_instance("inst1")


class TestStopInstance:
    """测试停止实例"""

    @pytest.mark.asyncio
    async def test_stop_instance_success(self):
        """测试成功停止实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()

                with patch('app.services.live_trading_manager._is_pid_alive', return_value=False):
                    result = await manager.stop_instance("inst1")

                    assert result["status"] == "stopped"
                    assert result["pid"] is None

    @pytest.mark.asyncio
    async def test_stop_instance_not_found(self):
        """测试停止不存在的实例"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="实例不存在"):
                await manager.stop_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_instance_kills_process(self):
        """测试停止实例时终止进程"""
        import os
        import signal

        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch.object(os, 'kill') as mock_kill:
                    manager = LiveTradingManager()

                    with patch('app.services.live_trading_manager._is_pid_alive', return_value=True):
                        # Add a mock process to the manager's process dict
                        mock_proc = AsyncMock()
                        mock_proc.returncode = None
                        manager._processes["inst1"] = mock_proc

                        result = await manager.stop_instance("inst1")

                        # Should have killed the process with SIGTERM
                        mock_kill.assert_any_call(12345, signal.SIGTERM)


class TestStartAllStopAll:
    """测试批量启停"""

    @pytest.mark.asyncio
    async def test_start_all(self):
        """测试启动所有实例"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                        with patch('app.services.live_trading_manager._is_pid_alive', return_value=False):
                            manager = LiveTradingManager()

                            # Use AsyncMock for the async start_instance method
                            mock_start = AsyncMock(return_value={"status": "running", "id": "test"})
                            with patch.object(manager, 'start_instance', mock_start):
                                result = await manager.start_all()

                                assert result["success"] == 2
                                assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_start_all_partial_failure(self):
        """测试批量启动部分失败"""
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                    with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                        manager = LiveTradingManager()

                        # Mock start_instance - one succeeds, one fails
                        async def mock_start(iid):
                            if iid == "inst1":
                                return {"status": "running"}
                            else:
                                raise ValueError("Failed")

                        # Use side_effect with AsyncMock wrapper
                        mock_start_async = AsyncMock(side_effect=mock_start)
                        with patch.object(manager, 'start_instance', mock_start_async):
                            result = await manager.start_all()

                            assert result["success"] == 1
                            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_stop_all(self):
        """测试停止所有实例"""
        # Import the module to use patch.object
        from app.services import live_trading_manager

        # Create the data that will be returned consistently
        running_data = {
            "inst1": {"strategy_id": "s1", "status": "running", "pid": 12345},
            "inst2": {"strategy_id": "s2", "status": "running", "pid": 12346},
        }

        with patch.object(live_trading_manager, '_load_instances', return_value=running_data):
            with patch.object(live_trading_manager, '_save_instances'):
                with patch.object(live_trading_manager, '_is_pid_alive', return_value=True):
                    manager = live_trading_manager.LiveTradingManager()

                    # Use AsyncMock for the async stop_instance method
                    mock_stop = AsyncMock(return_value={"status": "stopped", "id": "test"})
                    with patch.object(manager, 'stop_instance', mock_stop):
                        result = await manager.stop_all()

                        assert result["success"] == 2
                        assert result["failed"] == 0


class TestWaitProcess:
    """测试进程等待"""

    @pytest.mark.asyncio
    async def test_wait_process_success(self):
        """测试进程正常结束"""
        manager = LiveTradingManager()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stderr = None

        # Track what was saved
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {"inst1": {"strategy_id": "s1", "status": "running"}}
            with patch('app.services.live_trading_manager._save_instances', side_effect=mock_save):
                with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                    with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                        await manager._wait_process("inst1", mock_proc)

                        # Check that status was updated to stopped
                        assert "inst1" in saved_data
                        assert saved_data["inst1"]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_wait_process_error(self):
        """测试进程异常结束"""
        manager = LiveTradingManager()

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"error message")

        # Track what was saved
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {"inst1": {"strategy_id": "s1", "status": "running"}}
            with patch('app.services.live_trading_manager._save_instances', side_effect=mock_save):
                with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                    with patch('app.services.live_trading_manager.STRATEGIES_DIR'):
                        await manager._wait_process("inst1", mock_proc)

                        # Check that status was updated to error
                        assert "inst1" in saved_data
                        assert saved_data["inst1"]["status"] == "error"


class TestKillPid:
    """测试终止进程"""

    def test_kill_pid_success(self):
        """测试成功终止进程"""
        import os
        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, 'kill') as mock_kill:
            LiveTradingManager._kill_pid(12345)
            mock_kill.assert_called_once()

    def test_kill_pid_process_not_found(self):
        """测试进程不存在时不抛错"""
        import os
        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, 'kill', side_effect=ProcessLookupError):
            # Should not raise an error
            LiveTradingManager._kill_pid(999999)


class TestGetLiveTradingManager:
    """测试获取管理器单例"""

    def test_get_manager_singleton(self):
        """测试单例模式"""
        manager1 = get_live_trading_manager()
        manager2 = get_live_trading_manager()

        assert manager1 is manager2

    def test_manager_processes_dict(self):
        """测试管理器的进程字典"""
        manager = get_live_trading_manager()
        assert hasattr(manager, '_processes')
        assert isinstance(manager._processes, dict)


class TestIntegration:
    """集成测试"""

    def test_full_lifecycle(self):
        """测试完整的实例生命周期"""
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            with patch('app.services.live_trading_manager._save_instances'):
                with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
                    with patch('app.services.live_trading_manager.get_template_by_id') as mock_tpl:
                        with patch('app.services.live_trading_manager._find_latest_log_dir', return_value=None):
                            # Setup strategy directory
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="测试策略")

                            manager = LiveTradingManager()

                            # Add instance
                            inst = manager.add_instance("test_strategy", {"param": 10}, user_id="user1")
                            inst_id = inst["id"]

                            # Get instance
                            retrieved = manager.get_instance(inst_id, user_id="user1")
                            assert retrieved is not None

                            # List instances
                            instances = manager.list_instances("user1")
                            assert len(instances) == 1

                            # Remove instance
                            result = manager.remove_instance(inst_id, user_id="user1")
                            assert result is True
