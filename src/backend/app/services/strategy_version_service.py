"""
Strategy version control service.

Supports versioning, branch management, rollback, and comparisons.
"""

import difflib
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from app.db import database as db
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestResultModel, BacktestTask
from app.models.strategy import Strategy
from app.models.strategy_version import (
    StrategyVersion,
    VersionBranch,
    VersionComparison,
    VersionRollback,
    VersionStatus,
)
from app.schemas.strategy_version import (
    VersionUpdate,
)
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class VersionControlService:
    """Service for managing strategy version control.

    Features:
    1. Creating strategy versions
    2. Managing strategy branches
    3. Version comparison (code, parameters, performance)
    4. Version rollback
    5. Tagging versions
    6. Setting default/active versions

    Attributes:
        version_repo: Repository for StrategyVersion entities.
        branch_repo: Repository for VersionBranch entities.
        comparison_repo: Repository for VersionComparison entities.
        rollback_repo: Repository for VersionRollback entities.
        strategy_repo: Repository for Strategy entities.
    """

    def __init__(self):
        """Initialize the VersionControlService with required repositories."""
        self.version_repo = SQLRepository(StrategyVersion)
        self.branch_repo = SQLRepository(VersionBranch)
        self.comparison_repo = SQLRepository(VersionComparison)
        self.rollback_repo = SQLRepository(VersionRollback)
        self.strategy_repo = SQLRepository(Strategy)

    async def _require_strategy_owner(self, strategy_id: str, user_id: str) -> Strategy:
        """Load a strategy and enforce ownership.

        Args:
            strategy_id: The strategy identifier.
            user_id: The user identifier to verify ownership.

        Returns:
            The Strategy entity if found and owned by the user.

        Raises:
            ValueError: If the strategy does not exist.
            PermissionError: If the user does not own the strategy.
        """
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy not found: {strategy_id}")
        if getattr(strategy, "user_id", None) != user_id:
            raise PermissionError("forbidden")
        return strategy

    async def create_version(
        self,
        user_id: str,
        strategy_id: str,
        version_name: str,
        code: str,
        params: dict[str, Any] | None = None,
        branch: str = "main",
        tags: list[str] | None = None,
        changelog: str | None = None,
        is_default: bool = False,
    ) -> StrategyVersion:
        """Create a new strategy version.

        Args:
            user_id: The user identifier creating the version.
            strategy_id: The strategy identifier to version.
            version_name: Version name (e.g., v1.0.0).
            code: Strategy code content.
            params: Default parameters for this version.
            branch: Branch name for this version.
            tags: Version tags for categorization.
            changelog: Update log describing changes.
            is_default: Whether to set as the default version.

        Returns:
            The created StrategyVersion entity.

        Raises:
            ValueError: If strategy does not exist or user lacks permission.
            PermissionError: If user does not own the strategy.
        """
        # Enforce strategy ownership.
        await self._require_strategy_owner(strategy_id=strategy_id, user_id=user_id)

        # Get or create branch
        version_branch = await self._get_or_create_branch(strategy_id, user_id, branch)

        # Calculate version number
        version_number = await self._get_next_version_number(strategy_id, branch)

        # If default version, unset other default versions
        if is_default:
            await self._unset_default_versions(strategy_id, branch)

        # Create version
        version = StrategyVersion(
            strategy_id=strategy_id,
            version_number=version_number,
            version_name=version_name,
            branch=branch,
            status=VersionStatus.DRAFT,
            tags=tags or [],
            code=code,
            params=params or {},
            description=changelog,
            is_active=True,
            is_default=is_default,
            is_current=True,  # New version is always current
            created_by=user_id,
        )

        # Set parent version (latest version in branch)
        last_version = await self._get_latest_version(strategy_id, branch)
        if last_version:
            version.parent_version_id = last_version.id

        version = await self.version_repo.create(version)

        # Update branch
        await self._update_branch(version_branch, version)

        logger.info(f"Created version {version.id} for strategy {strategy_id}")

        return version

    async def get_version(self, version_id: str) -> StrategyVersion | None:
        """Get a strategy version by ID.

        Args:
            version_id: The version identifier.

        Returns:
            The StrategyVersion entity if found, None otherwise.
        """
        return await self.version_repo.get_by_id(version_id)

    async def list_versions(
        self,
        user_id: str,
        strategy_id: str,
        branch: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List versions for a strategy.

        Args:
            user_id: The user identifier requesting the list.
            strategy_id: The strategy identifier.
            branch: Optional branch name filter.
            status: Optional status filter.
            limit: Maximum number of items to return.
            offset: Number of items to skip.

        Returns:
            A tuple of (items, total) where items are API-shaped dictionaries
            and total is the count of all matching versions.

        Raises:
            PermissionError: If user does not own the strategy.
        """
        await self._require_strategy_owner(strategy_id=strategy_id, user_id=user_id)

        filters: dict[str, Any] = {"strategy_id": strategy_id}
        if branch:
            filters["branch"] = branch
        if status:
            filters["status"] = status

        versions = await self.version_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        total = await self.version_repo.count(filters=filters)
        return [self._to_response(v) for v in versions], total

    async def update_version(
        self,
        version_id: str,
        user_id: str,
        update_data: VersionUpdate,
    ) -> StrategyVersion | None:
        """Update a strategy version.

        Args:
            version_id: The version identifier.
            user_id: The user identifier making the update.
            update_data: Dictionary containing fields to update.

        Returns:
            The updated StrategyVersion entity if successful, None otherwise.

        Raises:
            ValueError: If version is not in DRAFT status.
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return None
        if getattr(version, "created_by", None) != user_id:
            return None

        # Can only update DRAFT status versions
        if version.status != VersionStatus.DRAFT:
            raise ValueError(
                f"Can only update DRAFT status versions, current status: {version.status}"
            )

        # Update fields
        update_dict = {
            "updated_at": datetime.now(timezone.utc),
            "updated_by": user_id,
        }

        if update_data.code is not None:
            update_dict["code"] = update_data.code

        if update_data.params is not None:
            update_dict["params"] = update_data.params

        if update_data.description is not None:
            update_dict["description"] = update_data.description

        if update_data.tags is not None:
            update_dict["tags"] = update_data.tags

        if update_data.status is not None:
            update_dict["status"] = update_data.status

        # If updated to STABLE, optionally record changelog.
        status_val = (
            update_data.status.value
            if isinstance(update_data.status, VersionStatus)
            else update_data.status
        )
        if status_val == VersionStatus.STABLE.value and getattr(update_data, "changelog", None):
            if not version.changelog:
                update_dict["changelog"] = update_data.changelog

        version = await self.version_repo.update(version_id, update_dict)

        # Push version update notification
        await ws_manager.send_to_task(
            f"strategy_version:{version.strategy_id}",
            {
                "type": "version_updated",
                "version_id": version.id,
                "data": {
                    "status": version.status,
                    "is_active": version.is_active,
                    "is_default": version.is_default,
                },
            },
        )

        return version

    async def set_version_default(
        self,
        version_id: str,
        user_id: str,
    ) -> bool:
        """Set a version as the default version.

        Args:
            version_id: The version identifier.
            user_id: The user identifier making the change.

        Returns:
            True if successful, False otherwise.
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return False
        if getattr(version, "created_by", None) != user_id:
            return False

        # Unset other default versions on branch
        await self._unset_default_versions(version.strategy_id, version.branch)

        # Set as default version
        await self.version_repo.update(
            version_id,
            {
                "is_default": True,
                "updated_at": datetime.now(timezone.utc),
            },
        )

        return True

    async def activate_version(
        self,
        version_id: str,
        user_id: str,
    ) -> bool:
        """Activate a version.

        Args:
            version_id: The version identifier.
            user_id: The user identifier making the change.

        Returns:
            True if successful, False otherwise.
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return False
        if getattr(version, "created_by", None) != user_id:
            return False

        # Unset other active versions on branch
        await self._unset_active_versions(version.strategy_id, version.branch)

        # Set as active version
        await self.version_repo.update(
            version_id,
            {
                "is_active": True,
                "updated_at": datetime.now(timezone.utc),
            },
        )

        return True

    async def compare_versions(
        self,
        user_id: str,
        strategy_id: str,
        from_version_id: str,
        to_version_id: str,
    ) -> VersionComparison:
        """Compare two strategy versions.

        Args:
            user_id: The user identifier requesting the comparison.
            strategy_id: The strategy identifier.
            from_version_id: The source version identifier.
            to_version_id: The target version identifier.

        Returns:
            The VersionComparison entity containing code, parameters,
            and performance differences.

        Raises:
            ValueError: If versions do not exist.
            PermissionError: If user does not have access to both versions.
        """
        # Get both versions
        from_version = await self.version_repo.get_by_id(from_version_id)
        to_version = await self.version_repo.get_by_id(to_version_id)

        if not from_version or not to_version:
            raise ValueError("Version not found")
        if (
            getattr(from_version, "created_by", None) != user_id
            or getattr(to_version, "created_by", None) != user_id
        ):
            raise PermissionError("forbidden")

        # Calculate code diff
        code_diff = self._generate_code_diff(
            from_version.code,
            to_version.code,
            from_version.version_name,
            to_version.version_name,
        )

        # Calculate parameters diff
        params_diff = self._generate_params_diff(
            from_version.params,
            to_version.params,
        )

        # Calculate performance diff
        performance_diff = await self._generate_performance_diff(
            from_version_id,
            to_version_id,
        )

        # Create comparison record
        comparison = VersionComparison(
            strategy_id=strategy_id,
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            code_diff=code_diff,
            params_diff=params_diff,
            performance_diff=performance_diff,
        )

        comparison = await self.comparison_repo.create(comparison)

        logger.info(f"Created comparison between {from_version_id} and {to_version_id}")

        return comparison

    async def rollback_version(
        self,
        user_id: str,
        strategy_id: str,
        target_version_id: str,
        reason: str,
    ) -> StrategyVersion:
        """Rollback to a specific version.

        Args:
            user_id: The user identifier initiating the rollback.
            strategy_id: The strategy identifier.
            target_version_id: The target version to rollback to.
            reason: The reason for the rollback.

        Returns:
            The newly created rollback version.

        Raises:
            ValueError: If target version does not exist or current version not found.
            PermissionError: If user lacks necessary permissions.
        """
        # Get target version
        target_version = await self.version_repo.get_by_id(target_version_id)
        if not target_version:
            raise ValueError(f"Target version not found: {target_version_id}")
        if getattr(target_version, "created_by", None) != user_id:
            raise PermissionError("forbidden")

        await self._require_strategy_owner(strategy_id=strategy_id, user_id=user_id)

        # Get current active version
        current_version = await self._get_current_version(strategy_id)
        if not current_version:
            raise ValueError(f"Current version not found: {strategy_id}")
        if getattr(current_version, "created_by", None) != user_id:
            raise PermissionError("forbidden")

        # Save current version snapshot (for undo)
        snapshot_data = {
            "version_id": current_version.id,
            "code": current_version.code,
            "params": current_version.params,
            "description": current_version.description,
        }

        # Create rollback record
        rollback = VersionRollback(
            strategy_id=strategy_id,
            from_version_id=current_version.id,
            to_version_id=target_version_id,
            reason=reason,
            snapshot_data=snapshot_data,
            created_by=user_id,
        )

        await self.rollback_repo.create(rollback)

        # Create new version (based on target version code and params)
        new_version = StrategyVersion(
            strategy_id=strategy_id,
            version_number=await self._get_next_version_number(strategy_id, "main"),
            version_name=f"rollback-{target_version.version_name}",
            branch="main",
            status=VersionStatus.STABLE,
            tags=["rollback"],
            code=target_version.code,
            params=target_version.params,
            description=f"Rolled back to {target_version.version_name}, reason: {reason}",
            parent_version_id=target_version.id,
            is_active=True,
            is_default=False,  # Rollback version not set as default
            is_current=True,
            created_by=user_id,
        )

        # Unset active status for other versions
        await self._unset_active_versions(strategy_id, "main")

        new_version = await self.version_repo.create(new_version)

        logger.info(f"Rolled back strategy {strategy_id} to {target_version.version_name}")

        return new_version

    def _generate_code_diff(
        self,
        code1: str,
        code2: str,
        name1: str,
        name2: str,
    ) -> str:
        """Generate a code difference in unified diff format.

        Args:
            code1: Source code content.
            code2: Target code content.
            name1: Source name for diff header.
            name2: Target name for diff header.

        Returns:
            String containing the unified diff.
        """
        lines1 = code1.splitlines(keepends=True)
        lines2 = code2.splitlines(keepends=True)

        diff = difflib.unified_diff(lines1, lines2, fromfile=name1, tofile=name2, lineterm="")
        return "".join(diff)

    def _generate_params_diff(
        self,
        params1: dict[str, Any],
        params2: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Generate a parameter difference between two parameter sets.

        Args:
            params1: Source parameters dictionary.
            params2: Target parameters dictionary.

        Returns:
            Dictionary with keys 'added', 'removed', 'modified', and 'unchanged'
            containing the respective parameter differences.
        """
        all_keys = set(params1.keys()) | set(params2.keys())

        diff = {
            "added": {},
            "removed": {},
            "modified": {},
            "unchanged": {},
        }

        for key in all_keys:
            if key not in params1:
                diff["added"][key] = params2[key]
            elif key not in params2:
                diff["removed"][key] = params1[key]
            elif params1[key] != params2[key]:
                diff["modified"][key] = {
                    "from": params1[key],
                    "to": params2[key],
                }
            else:
                diff["unchanged"][key] = params1[key]

        return diff

    async def _generate_performance_diff(
        self,
        from_version_id: str,
        to_version_id: str,
    ) -> dict[str, Any]:
        """Generate a performance difference between two versions.

        Compares backtest results from both versions.

        Args:
            from_version_id: Source version identifier.
            to_version_id: Target version identifier.

        Returns:
            Dictionary containing performance metrics differences with keys:
            - available: Whether performance data exists for both versions
            - from: Source version metrics
            - to: Target version metrics
            - diff: Metric differences (to - from)
        """

        async def _latest(version_id: str) -> dict[str, Any] | None:
            async with db.async_session_maker() as session:
                stmt = (
                    select(BacktestTask, BacktestResultModel)
                    .join(BacktestResultModel, BacktestResultModel.task_id == BacktestTask.id)
                    .where(BacktestTask.strategy_version_id == version_id)
                    .where(BacktestTask.status == "completed")
                    .order_by(desc(BacktestTask.created_at))
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.first()
                if not row:
                    return None
                task, res = row
                return {
                    "task_id": task.id,
                    "created_at": task.created_at.isoformat()
                    if getattr(task, "created_at", None)
                    else None,
                    "metrics": {
                        "total_return": float(getattr(res, "total_return", 0.0)),
                        "annual_return": float(getattr(res, "annual_return", 0.0)),
                        "sharpe_ratio": float(getattr(res, "sharpe_ratio", 0.0)),
                        "max_drawdown": float(getattr(res, "max_drawdown", 0.0)),
                        "win_rate": float(getattr(res, "win_rate", 0.0)),
                        "total_trades": int(getattr(res, "total_trades", 0)),
                        "profitable_trades": int(getattr(res, "profitable_trades", 0)),
                        "losing_trades": int(getattr(res, "losing_trades", 0)),
                    },
                }

        from_res = await _latest(from_version_id)
        to_res = await _latest(to_version_id)
        if not from_res or not to_res:
            return {"available": False, "from": from_res, "to": to_res}

        diff: dict[str, Any] = {}
        for k, v in to_res["metrics"].items():
            if (
                k in from_res["metrics"]
                and isinstance(v, (int, float))
                and isinstance(from_res["metrics"][k], (int, float))
            ):
                diff[k] = v - from_res["metrics"][k]

        return {"available": True, "from": from_res, "to": to_res, "diff": diff}

    def _to_response(self, version: StrategyVersion) -> dict[str, Any]:
        """Convert a StrategyVersion entity to an API response dictionary.

        Args:
            version: The StrategyVersion entity.

        Returns:
            Dictionary containing version data for API responses.
        """
        return {
            "id": version.id,
            "strategy_id": version.strategy_id,
            "version_number": version.version_number,
            "version_name": version.version_name,
            "branch": version.branch,
            "status": version.status,
            "tags": version.tags,
            "description": version.description,
            "params": version.params,
            "is_active": version.is_active,
            "is_default": version.is_default,
            "is_current": version.is_current,
            "parent_version_id": version.parent_version_id,
            "created_at": version.created_at.isoformat(),
            "updated_at": version.updated_at.isoformat(),
        }

    async def _get_or_create_branch(
        self,
        strategy_id: str,
        user_id: str,
        branch_name: str,
    ) -> VersionBranch:
        """Get an existing branch or create a new one.

        Args:
            strategy_id: The strategy identifier.
            user_id: The user identifier.
            branch_name: The branch name.

        Returns:
            The VersionBranch entity.
        """
        branches = await self.branch_repo.list(
            filters={"strategy_id": strategy_id, "branch_name": branch_name}, limit=1
        )

        if branches:
            return branches[0]

        # Create new branch
        branch = VersionBranch(
            strategy_id=strategy_id,
            branch_name=branch_name,
            version_count=0,
            is_default=(branch_name == "main"),
            created_by=user_id,
        )

        branch = await self.branch_repo.create(branch)

        return branch

    async def _update_branch(
        self,
        branch: VersionBranch,
        version: StrategyVersion,
    ):
        """Update branch information after a version is created.

        Args:
            branch: The VersionBranch entity to update.
            version: The StrategyVersion entity to incorporate.
        """
        await self.branch_repo.update(
            branch.id,
            {
                "version_count": branch.version_count + 1,
                "last_version_id": version.id,
            },
        )

    async def create_branch(
        self,
        user_id: str,
        strategy_id: str,
        branch_name: str,
        parent_branch: str | None = None,
    ) -> VersionBranch:
        """Create a strategy branch (idempotent if it already exists).

        Args:
            user_id: The user identifier creating the branch.
            strategy_id: The strategy identifier.
            branch_name: The name for the new branch.
            parent_branch: Optional parent branch name.

        Returns:
            The created or existing VersionBranch entity.

        Raises:
            PermissionError: If user does not own the strategy.
        """
        await self._require_strategy_owner(strategy_id=strategy_id, user_id=user_id)

        existing = await self.branch_repo.list(
            filters={"strategy_id": strategy_id, "branch_name": branch_name},
            limit=1,
        )
        if existing:
            return existing[0]

        if parent_branch:
            await self._get_or_create_branch(
                strategy_id=strategy_id, user_id=user_id, branch_name=parent_branch
            )

        branch = VersionBranch(
            strategy_id=strategy_id,
            branch_name=branch_name,
            parent_branch=parent_branch,
            version_count=0,
            is_default=(branch_name == "main"),
            created_by=user_id,
        )
        return await self.branch_repo.create(branch)

    async def list_branches(
        self,
        user_id: str,
        strategy_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[VersionBranch], int]:
        """List strategy branches with pagination.

        Args:
            user_id: The user identifier requesting the list.
            strategy_id: The strategy identifier.
            limit: Maximum number of items to return.
            offset: Number of items to skip.

        Returns:
            A tuple of (branches, total) where branches is a list of
            VersionBranch entities and total is the count.

        Raises:
            PermissionError: If user does not own the strategy.
        """
        await self._require_strategy_owner(strategy_id=strategy_id, user_id=user_id)
        branches = await self.branch_repo.list(
            filters={"strategy_id": strategy_id},
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        total = await self.branch_repo.count(filters={"strategy_id": strategy_id})
        return branches, total

    @staticmethod
    def branch_to_response(branch: VersionBranch) -> dict[str, Any]:
        """Convert a branch ORM object to the API response dict.

        Args:
            branch: The VersionBranch entity.

        Returns:
            Dictionary containing branch data for API responses.
        """
        return {
            "branch_id": branch.id,
            "strategy_id": branch.strategy_id,
            "branch_name": branch.branch_name,
            "parent_branch": getattr(branch, "parent_branch", None),
            "version_count": int(getattr(branch, "version_count", 0) or 0),
            "last_version_id": getattr(branch, "last_version_id", None),
            "is_default": bool(getattr(branch, "is_default", False)),
            "created_at": branch.created_at,
        }

    async def _get_latest_version(
        self,
        strategy_id: str,
        branch: str,
    ) -> StrategyVersion | None:
        """Get the latest version for a branch.

        Args:
            strategy_id: The strategy identifier.
            branch: The branch name.

        Returns:
            The latest StrategyVersion entity or None if not found.
        """
        versions = await self.version_repo.list(
            filters={
                "strategy_id": strategy_id,
                "branch": branch,
                "is_active": True,
            },
            limit=1,
            sort_by="created_at",
            sort_order="desc",
        )

        return versions[0] if versions else None

    async def _get_current_version(
        self,
        strategy_id: str,
    ) -> StrategyVersion | None:
        """Get the current version of a strategy (is_current=True).

        Args:
            strategy_id: The strategy identifier.

        Returns:
            The current StrategyVersion entity or None if not found.
        """
        versions = await self.version_repo.list(
            filters={
                "strategy_id": strategy_id,
                "is_current": True,
            },
            limit=1,
        )

        return versions[0] if versions else None

    async def _get_next_version_number(
        self,
        strategy_id: str,
        branch: str,
    ) -> int:
        """Get the next version number for a branch.

        Args:
            strategy_id: The strategy identifier.
            branch: The branch name.

        Returns:
            The next available version number (integer).
        """
        # Get current maximum version number
        versions = await self.version_repo.list(
            filters={
                "strategy_id": strategy_id,
                "branch": branch,
            },
            limit=1,
            sort_by="version_number",
            sort_order="desc",
        )

        if versions:
            return versions[0].version_number + 1
        else:
            return 1

    async def _unset_default_versions(
        self,
        strategy_id: str,
        branch: str,
    ):
        """Unset default flag for all versions on a branch.

        Args:
            strategy_id: The strategy identifier.
            branch: The branch name.
        """
        versions = await self.version_repo.list(
            filters={
                "strategy_id": strategy_id,
                "branch": branch,
                "is_default": True,
            },
        )

        for version in versions:
            await self.version_repo.update(version.id, {"is_default": False})

    async def _unset_active_versions(
        self,
        strategy_id: str,
        branch: str,
    ):
        """Unset active flag for all versions on a branch.

        Args:
            strategy_id: The strategy identifier.
            branch: The branch name.
        """
        versions = await self.version_repo.list(
            filters={
                "strategy_id": strategy_id,
                "branch": branch,
                "is_active": True,
            },
        )

        for version in versions:
            await self.version_repo.update(version.id, {"is_active": False})
