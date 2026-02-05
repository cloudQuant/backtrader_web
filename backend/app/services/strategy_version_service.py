"""
策略版本管理服务

支持策略的版本控制、分支管理、回滚、对比
"""
import uuid
import difflib
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import json

from app.models.strategy_version import (
    StrategyVersion,
    VersionStatus,
    VersionTag,
    VersionComparison,
    VersionRollback,
    VersionBranch,
)
from app.schemas.strategy_version import (
    VersionCreate,
    VersionResponse,
    VersionUpdate,
    VersionListResponse,
    VersionComparisonCreate,
    VersionRollbackCreate,
    BranchCreate,
    BranchResponse,
    BranchListResponse,
)
from app.models.strategy import Strategy
from app.db.sql_repository import SQLRepository
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class VersionControlService:
    """
    策略版本控制服务

    功能：
    1. 创建策略版本
    2. 管理策略分支
    3. 版本对比（代码、参数、性能）
    4. 版本回滚
    5. 标记版本
    6. 设置默认/活跃版本
    """

    def __init__(self):
        self.version_repo = SQLRepository(StrategyVersion)
        self.branch_repo = SQLRepository(VersionBranch)
        self.comparison_repo = SQLRepository(VersionComparison)
        self.rollback_repo = SQLRepository(VersionRollback)
        self.strategy_repo = SQLRepository(Strategy)

    async def create_version(
        self,
        user_id: str,
        strategy_id: str,
        version_name: str,
        code: str,
        params: Optional[Dict[str, Any]] = None,
        branch: str = "main",
        tags: Optional[List[str]] = None,
        changelog: Optional[str] = None,
        is_default: bool = False,
    ) -> StrategyVersion:
        """
        创建策略新版本

        Args:
            user_id: 用户 ID
            strategy_id: 策略 ID
            version_name: 版本名称（如 v1.0.0）
            code: 策略代码
            params: 默认参数
            branch: 分支名称
            tags: 版本标签
            changelog: 更新日志
            is_default: 是否设为默认版本

        Returns:
            StrategyVersion: 创建的版本
        """
        # 获取策略
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"策略不存在: {strategy_id}")

        # 获取或创建分支
        version_branch = await self._get_or_create_branch(
            strategy_id, user_id, branch
        )

        # 计算版本号
        version_number = await self._get_next_version_number(strategy_id, branch)

        # 如果是默认版本，先取消其他默认版本
        if is_default:
            await self._unset_default_versions(strategy_id, branch)

        # 创建版本
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
            is_current=True,  # 新版本总是当前版本
            created_by=user_id,
        )

        # 设置父版本（分支的最新版本）
        last_version = await self._get_latest_version(strategy_id, branch)
        if last_version:
            version.parent_version_id = last_version.id

        version = await self.version_repo.create(version)

        # 更新分支
        await self._update_branch(version_branch, version)

        logger.info(f"Created version {version.id} for strategy {strategy_id}")

        return version

    async def get_version(self, version_id: str) -> Optional[StrategyVersion]:
        """
        获取策略版本

        Args:
            version_id: 版本 ID

        Returns:
            StrategyVersion or None
        """
        return await self.version_repo.get_by_id(version_id)

    async def update_version(
        self,
        version_id: str,
        user_id: str,
        update_data: VersionUpdate,
    ) -> Optional[StrategyVersion]:
        """
        更新策略版本

        Args:
            version_id: 版本 ID
            user_id: 用户 ID
            update_data: 更新数据

        Returns:
            StrategyVersion or None
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return None

        # 只能更新 DRAFT 状态的版本
        if version.status != VersionStatus.DRAFT:
            raise ValueError(f"只能更新 DRAFT 状态的版本，当前状态：{version.status}")

        # 更新字段
        update_dict = {
            "updated_at": datetime.utcnow(),
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

        # 如果更新为 STABLE，记录 changelog
        if update_data.status == VersionStatus.STABLE and update_data.changelog:
            if not version.changelog:
                update_dict["changelog"] = update_data.changelog

        version = await self.version_repo.update(version_id, update_dict)

        # 推送版本更新通知
        await ws_manager.send_to_task(f"strategy_version:{version.strategy_id}", {
            "type": "version_updated",
            "version_id": version.id,
            "data": {
                "status": version.status,
                "is_active": version.is_active,
                "is_default": version.is_default,
            },
        })

        return version

    async def set_version_default(
        self,
        version_id: str,
        user_id: str,
    ) -> bool:
        """
        设置默认版本

        Args:
            version_id: 版本 ID
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return False

        # 取消分支上的其他默认版本
        await self._unset_default_versions(version.strategy_id, version.branch)

        # 设置为默认版本
        await self.version_repo.update(version_id, {
            "is_default": True,
            "updated_at": datetime.utcnow(),
        })

        return True

    async def activate_version(
        self,
        version_id: str,
        user_id: str,
    ) -> bool:
        """
        激活版本

        Args:
            version_id: 版本 ID
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        version = await self.version_repo.get_by_id(version_id)
        if not version:
            return False

        # 取消分支上的其他活跃版本
        await self._unset_active_versions(version.strategy_id, version.branch)

        # 设置为活跃版本
        await self.version_repo.update(version_id, {
            "is_active": True,
            "updated_at": datetime.utcnow(),
        })

        return True

    async def compare_versions(
        self,
        user_id: str,
        strategy_id: str,
        from_version_id: str,
        to_version_id: str,
    ) -> VersionComparison:
        """
        对比两个版本

        Args:
            user_id: 用户 ID
            strategy_id: 策略 ID
            from_version_id: 源版本 ID
            to_version_id: 目标版本 ID

        Returns:
            VersionComparison: 对比结果
        """
        # 获取两个版本
        from_version = await self.version_repo.get_by_id(from_version_id)
        to_version = await self.version_repo.get_by_id(to_version_id)

        if not from_version or not to_version:
            raise ValueError("版本不存在")

        # 计算代码差异
        code_diff = self._generate_code_diff(
            from_version.code,
            to_version.code,
            from_version.version_name,
            to_version.version_name,
        )

        # 计算参数差异
        params_diff = self._generate_params_diff(
            from_version.params,
            to_version.params,
        )

        # 计算性能差异
        performance_diff = await self._generate_performance_diff(
            from_version_id,
            to_version_id,
        )

        # 创建对比记录
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
        """
        回滚到指定版本

        Args:
            user_id: 用户 ID
            strategy_id: 策略 ID
            target_version_id: 目标版本 ID
            reason: 回滚原因

        Returns:
            StrategyVersion: 新的回滚版本
        """
        # 获取目标版本
        target_version = await self.version_repo.get_by_id(target_version_id)
        if not target_version:
            raise ValueError(f"目标版本不存在: {target_version_id}")

        # 获取当前活跃版本
        current_version = await self._get_current_version(strategy_id)

        # 保存当前版本快照（用于回滚）
        snapshot_data = {
            "version_id": current_version.id,
            "code": current_version.code,
            "params": current_version.params,
            "description": current_version.description,
        }

        # 创建回滚记录
        rollback = VersionRollback(
            strategy_id=strategy_id,
            from_version_id=current_version.id,
            to_version_id=target_version_id,
            reason=reason,
            snapshot_data=snapshot_data,
            created_by=user_id,
        )

        await self.rollback_repo.create(rollback)

        # 创建新版本（基于目标版本的代码和参数）
        new_version = StrategyVersion(
            strategy_id=strategy_id,
            version_number=await self._get_next_version_number(strategy_id, "main"),
            version_name=f"rollback-{target_version.version_name}",
            branch="main",
            status=VersionStatus.STABLE,
            tags=["rollback"],
            code=target_version.code,
            params=target_version.params,
            description=f"回滚到 {target_version.version_name}，原因：{reason}",
            parent_version_id=target_version.id,
            is_active=True,
            is_default=False,  # 回滚版本不设为默认
            is_current=True,
            created_by=user_id,
        )

        # 取消其他版本的活跃状态
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
        """
        生成代码差异（Unified diff）

        Args:
            code1: 源代码
            code2: 目标代码
            name1: 源名称
            name2: 目标名称

        Returns:
            str: Unified diff 格式
        """
        lines1 = code1.splitlines(keepends=True)
        lines2 = code2.splitlines(keepends=True)

        diff = difflib.unified_diff(lines1, lines2, fromfile=name1, tofile=name2, lineterm="")
        return ''.join(diff)

    def _generate_params_diff(
        self,
        params1: Dict[str, Any],
        params2: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """
        生成参数差异

        Args:
            params1: 源参数
            params2: 目标参数

        Returns:
            Dict: 参数差异
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
    ) -> Dict[str, Any]:
        """
        生成性能差异

        对比两个版本的回测结果

        Args:
            from_version_id: 源版本 ID
            to_version_id: 目标版本 ID

        Returns:
            Dict: 性能差异
        """
        # 获取两个版本的最新回测结果
        # TODO: 从 BacktestTask 获取
        # 这里暂时返回空
        return {}

    def _to_response(self, version: StrategyVersion) -> Dict[str, Any]:
        """
        转换为响应字典

        Args:
            version: 版本模型

        Returns:
            Dict: 响应数据
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
        """
        获取或创建分支

        Args:
            strategy_id: 策略 ID
            user_id: 用户 ID
            branch_name: 分支名称

        Returns:
            VersionBranch: 分支对象
        """
        branches = await self.branch_repo.list(
            filters={"strategy_id": strategy_id, "branch_name": branch_name},
            limit=1
        )

        if branches:
            return branches[0]

        # 创建新分支
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
        """
        更新分支信息

        Args:
            branch: 分支对象
            version: 版本对象
        """
        await self.branch_repo.update(branch.id, {
            "version_count": branch.version_count + 1,
            "last_version_id": version.id,
            "updated_at": datetime.utcnow(),
        })

    async def _get_latest_version(
        self,
        strategy_id: str,
        branch: str,
    ) -> Optional[StrategyVersion]:
        """
        获取分支的最新版本

        Args:
            strategy_id: 策略 ID
            branch: 分支名称

        Returns:
            StrategyVersion or None
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
    ) -> Optional[StrategyVersion]:
        """
        获取策略的当前版本（is_current=True）

        Args:
            strategy_id: 策略 ID

        Returns:
            StrategyVersion or None
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
        """
        获取下一个版本号

        Args:
            strategy_id: 策略 ID
            branch: 分支名称

        Returns:
            int: 下一个版本号
        """
        # 获取当前最大版本号
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
        """
        取消分支上的其他默认版本

        Args:
            strategy_id: 策略 ID
            branch: 分支名称
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
        """
        取消分支上的其他活跃版本

        Args:
            strategy_id: 策略 ID
            branch: 分支名称
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
