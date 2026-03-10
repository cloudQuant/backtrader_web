"""
Live Trading Manager Service Tests.

Tests:
    - Instance CRUD operations
    - Instance start/stop
    - Subprocess management
    - Process status synchronization
    - Error handling
    - Log directory lookup
"""
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.live_trading_manager import (
    LiveTradingManager,
    _find_latest_log_dir,
    _is_pid_alive,
    _load_instances,
    _save_instances,
    get_live_trading_manager,
)


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_load_instances_from_file(self):
        """Test loading instances from file.

        Verifies that instances are correctly loaded from
        a JSON file.
        """
        # Mock file exists with content
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = '{"test": {"status": "running"}}'

            result = _load_instances()

            assert result == {"test": {"status": "running"}}

    def test_load_instances_file_not_exists(self):
        """Test loading when file doesn't exist.

        Verifies that an empty dictionary is returned when
        the instances file doesn't exist.
        """
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = False

            result = _load_instances()

            assert result == {}

    def test_load_instances_invalid_json(self):
        """Test loading with invalid JSON.

        Verifies that an empty dictionary is returned when
        the file contains invalid JSON.
        """
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = 'invalid json'

            result = _load_instances()

            assert result == {}

    def test_save_instances(self):
        """Test saving instances to file.

        Verifies that instances are correctly written to
        the JSON file.
        """
        with patch('app.services.live_trading_manager._INSTANCES_FILE') as mock_file:
            test_data = {"test": {"status": "running"}}

            _save_instances(test_data)

            # Verify write was called
            mock_file.write_text.assert_called_once()

    def test_find_latest_log_dir(self):
        """Test finding the latest log directory.

        Verifies that the most recently modified log directory
        is returned.
        """
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
        """Test finding log directory when none exists.

        Verifies that None is returned when no log directory
        exists for the strategy.
        """
        with patch('app.services.live_trading_manager.Path') as mock_path:
            mock_strategy_dir = MagicMock()
            mock_logs_dir = MagicMock()
            mock_logs_dir.is_dir.return_value = False
            mock_strategy_dir.__truediv__.return_value = mock_logs_dir

            result = _find_latest_log_dir(mock_strategy_dir)

            assert result is None

    def test_is_pid_alive(self):
        """Test checking if process is alive.

        Verifies that the function correctly identifies
        a running process.
        """
        # Test with a valid PID (current process)
        import os
        current_pid = os.getpid()
        assert _is_pid_alive(current_pid) is True

    def test_is_pid_not_alive(self):
        """Test checking if non-existent process is alive.

        Verifies that the function returns False for a
        non-existent PID.
        """
        # Use an invalid PID
        assert _is_pid_alive(999999) is False


class TestLiveTradingManagerInitialization:
    """Tests for manager initialization."""

    def test_initialization(self):
        """Test basic manager initialization.

        Verifies that a new LiveTradingManager initializes
        with an empty processes dictionary.
        """
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()
            assert manager._processes == {}

    def test_initialization_syncs_status(self):
        """Test status synchronization during initialization.

        Verifies that the manager synchronizes process status
        during initialization by checking if PIDs are alive.
        """
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
    """Tests for listing instances."""

    def test_list_all_instances(self):
        """Test listing all instances.

        Verifies that all instances are returned with
        proper formatting.
        """
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
        """Test listing instances filtered by user.

        Verifies that only instances belonging to the
        specified user are returned.
        """
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
        """Test updating dead processes when listing.

        Verifies that instances with dead PIDs are marked
        as stopped when listing.
        """
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
    """Tests for adding instances."""

    def test_add_instance_success(self):
        """Test successful instance addition.

        Verifies that a new instance can be added with
        proper configuration.
        """
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
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

                            manager = LiveTradingManager()
                            result = manager.add_instance("test_strategy", user_id="user1")

                            assert result["strategy_id"] == "test_strategy"
                            assert result["status"] == "stopped"
                            assert result["user_id"] == "user1"
                            assert "id" in result

    def test_add_instance_strategy_not_found(self):
        """Test adding non-existent strategy.

        Verifies that a ValueError is raised when trying
        to add an instance for a non-existent strategy.
        """
        with patch('app.services.live_trading_manager.STRATEGIES_DIR') as mock_dir:
            with patch('app.services.live_trading_manager._load_instances', return_value={}):
                with patch('app.services.live_trading_manager._save_instances'):
                    mock_strategy_dir = MagicMock()
                    mock_run_py = MagicMock()
                    mock_run_py.is_file.return_value = False
                    mock_strategy_dir.__truediv__.return_value = mock_run_py
                    mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                    manager = LiveTradingManager()

                    with pytest.raises(ValueError, match="does not exist or lacks run.py"):
                        manager.add_instance("test_strategy")

    def test_add_instance_with_params(self):
        """Test adding instance with parameters.

        Verifies that custom parameters are correctly
        stored when adding an instance.
        """
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
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

                            manager = LiveTradingManager()
                            params = {"fast": 10, "slow": 20}
                            result = manager.add_instance("test_strategy", params=params, user_id="user1")

                            assert result["params"] == params


class TestRemoveInstance:
    """Tests for removing instances."""

    def test_remove_instance_success(self):
        """Test successful instance removal.

        Verifies that an existing instance can be removed.
        """
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user1")

                assert result is True

    def test_remove_instance_not_found(self):
        """Test removing non-existent instance.

        Verifies that removing a non-existent instance
        returns False.
        """
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("nonexistent")

                assert result is False

    def test_remove_instance_wrong_user(self):
        """Test removing instance belonging to another user.

        Verifies that a user cannot remove instances
        belonging to other users.
        """
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch('app.services.live_trading_manager._save_instances'):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user2")

                assert result is False

    def test_remove_instance_kills_process(self):
        """Test that removing instance kills its process.

        Verifies that the associated process is terminated
        when removing a running instance.
        """
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
    """Tests for getting instances."""

    def test_get_instance_success(self):
        """Test successful instance retrieval.

        Verifies that an existing instance can be retrieved.
        """
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
        """Test getting non-existent instance.

        Verifies that None is returned for a non-existent
        instance.
        """
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()
            result = manager.get_instance("nonexistent")

            assert result is None

    def test_get_instance_wrong_user(self):
        """Test getting instance belonging to another user.

        Verifies that a user cannot retrieve instances
        belonging to other users.
        """
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            manager = LiveTradingManager()
            result = manager.get_instance("inst1", user_id="user2")

            assert result is None


class TestStartInstance:
    """Tests for starting instances."""

    @pytest.mark.asyncio
    async def test_start_instance_success(self):
        """Test successful instance start.

        Verifies that an instance can be started and
        its status is updated.
        """
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
                            # start_instance schedules _wait_process via asyncio.create_task; when patched,
                            # close the coroutine to avoid "coroutine was never awaited" warnings.
                            with patch('asyncio.create_task') as mock_create_task:
                                def _create_task(coro):
                                    try:
                                        coro.close()
                                    except Exception:
                                        pass
                                    return Mock()

                                mock_create_task.side_effect = _create_task
                                result = await manager.start_instance("inst1")

                                assert result["status"] == "running"
                                assert result["pid"] == 12345

    @pytest.mark.asyncio
    async def test_start_instance_already_running(self):
        """Test starting an already running instance.

        Verifies that a ValueError is raised when trying
        to start an instance that's already running.
        """
        with patch('app.services.live_trading_manager._load_instances') as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch('app.services.live_trading_manager._is_pid_alive', return_value=True):
                manager = LiveTradingManager()

                with pytest.raises(ValueError, match="already running"):
                    await manager.start_instance("inst1")

    @pytest.mark.asyncio
    async def test_start_instance_not_found(self):
        """Test starting non-existent instance.

        Verifies that a ValueError is raised when trying
        to start a non-existent instance.
        """
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="Instance does not exist"):
                await manager.start_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_start_instance_no_run_py(self):
        """Test starting instance when run.py doesn't exist.

        Verifies that a ValueError is raised when the
        strategy's run.py file is missing.
        """
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

                with pytest.raises(ValueError, match="run.py does not exist"):
                    await manager.start_instance("inst1")


class TestStopInstance:
    """Tests for stopping instances."""

    @pytest.mark.asyncio
    async def test_stop_instance_success(self):
        """Test successful instance stop.

        Verifies that a running instance can be stopped
        and its status is updated.
        """
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
        """Test stopping non-existent instance.

        Verifies that a ValueError is raised when trying
        to stop a non-existent instance.
        """
        with patch('app.services.live_trading_manager._load_instances', return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="Instance does not exist"):
                await manager.stop_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_instance_kills_process(self):
        """Test that stopping instance kills its process.

        Verifies that the associated process is terminated
        when stopping an instance.
        """
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
                        # proc.terminate()/kill() are sync; proc.wait() is async.
                        mock_proc = MagicMock()
                        mock_proc.returncode = None
                        mock_proc.wait = AsyncMock()
                        mock_proc.terminate = Mock()
                        mock_proc.kill = Mock()
                        manager._processes["inst1"] = mock_proc

                        result = await manager.stop_instance("inst1")

                        # Should have killed the process with SIGTERM
                        mock_kill.assert_any_call(12345, signal.SIGTERM)


class TestStartAllStopAll:
    """Tests for batch start/stop operations."""

    @pytest.mark.asyncio
    async def test_start_all(self):
        """Test starting all instances.

        Verifies that all stopped instances can be
        started in batch.
        """
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
        """Test batch start with partial failures.

        Verifies that the result correctly reports successes
        and failures when starting all instances.
        """
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
        """Test stopping all instances.

        Verifies that all running instances can be
        stopped in batch.
        """
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
    """Tests for process waiting."""

    @pytest.mark.asyncio
    async def test_wait_process_success(self):
        """Test process normal completion.

        Verifies that the status is updated to stopped
        when a process completes normally.
        """
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
        """Test process abnormal completion.

        Verifies that the status is updated to error
        when a process completes with an error.
        """
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
    """Tests for process termination."""

    def test_kill_pid_success(self):
        """Test successful process termination.

        Verifies that os.kill is called to terminate
        a process.
        """
        import os
        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, 'kill') as mock_kill:
            LiveTradingManager._kill_pid(12345)
            mock_kill.assert_called_once()

    def test_kill_pid_process_not_found(self):
        """Test terminating non-existent process.

        Verifies that no error is raised when trying
        to kill a non-existent process.
        """
        import os
        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, 'kill', side_effect=ProcessLookupError):
            # Should not raise an error
            LiveTradingManager._kill_pid(999999)


class TestGetLiveTradingManager:
    """Tests for getting the manager singleton."""

    def test_get_manager_singleton(self):
        """Test singleton pattern.

        Verifies that get_live_trading_manager returns
        the same instance on subsequent calls.
        """
        manager1 = get_live_trading_manager()
        manager2 = get_live_trading_manager()

        assert manager1 is manager2

    def test_manager_processes_dict(self):
        """Test manager's processes dictionary.

        Verifies that the manager has a _processes
        attribute that is a dictionary.
        """
        manager = get_live_trading_manager()
        assert hasattr(manager, '_processes')
        assert isinstance(manager._processes, dict)


class TestIntegration:
    """Integration tests."""

    def test_full_lifecycle(self):
        """Test complete instance lifecycle.

        Verifies the full lifecycle of an instance:
        add, get, list, and remove.
        """
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
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

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
