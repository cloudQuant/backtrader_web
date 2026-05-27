from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akshare_mgmt import DataInterface
from app.models.data_governance import DgEndpoint, DgIngestJob, DgJobStatus, DgProvider
from app.services.data_connectors.executor import DataConnectorExecutor

_PROVIDER_SEEDS = [
    {"provider_id": "akshare", "name": "AkShare", "category": "china_market", "auth_type": "none", "rate_limit": 60},
    {"provider_id": "yahoo", "name": "Yahoo Finance", "category": "global_market", "auth_type": "none", "rate_limit": 120},
    {"provider_id": "fred", "name": "FRED", "category": "macro", "auth_type": "api_key", "api_key_env": "FRED_API_KEY", "rate_limit": 60},
    {"provider_id": "coingecko", "name": "CoinGecko", "category": "crypto", "auth_type": "none", "rate_limit": 30},
    {"provider_id": "cboe", "name": "CBOE", "category": "options", "auth_type": "none", "rate_limit": 30},
    {"provider_id": "cftc", "name": "CFTC", "category": "futures", "auth_type": "none", "rate_limit": 30},
    {"provider_id": "dbnomics", "name": "DBnomics", "category": "macro", "auth_type": "none", "rate_limit": 60},
    {"provider_id": "fmp", "name": "FMP", "category": "fundamental", "auth_type": "api_key", "api_key_env": "FMP_API_KEY", "rate_limit": 20},
]

_ENDPOINT_SEEDS = {
    "yahoo": ["quote", "history"],
    "fred": ["DGS10", "macro_series"],
    "coingecko": ["coin_price"],
    "cboe": ["option_chain"],
    "cftc": ["commitments_of_traders"],
    "dbnomics": ["dataset_series"],
    "fmp": ["company_profile"],
}


class DataGovernanceService:
    def __init__(self, db: AsyncSession, executor: DataConnectorExecutor | None = None) -> None:
        self.db = db
        self.executor = executor or DataConnectorExecutor()

    async def bootstrap(self) -> dict[str, int]:
        providers = await self._ensure_seed_providers()
        seed_count = await self._ensure_seed_endpoints(providers)
        akshare_count = await self._migrate_akshare_interfaces(providers["akshare"])
        await self._ensure_compat_view()
        await self.db.commit()
        return {
            "providers": len(providers),
            "seed_endpoints": seed_count,
            "akshare_migrated_endpoints": akshare_count,
        }

    async def list_providers(self) -> dict[str, Any]:
        await self.bootstrap()
        result = await self.db.execute(select(DgProvider).order_by(DgProvider.provider_id))
        items = [self._provider_to_dict(provider) for provider in result.scalars().all()]
        return {"items": items, "total": len(items)}

    async def list_endpoints(self, provider_id: str | None = None) -> dict[str, Any]:
        await self.bootstrap()
        stmt = select(DgEndpoint, DgProvider).join(DgProvider)
        if provider_id:
            stmt = stmt.where(DgProvider.provider_id == provider_id)
        rows = (await self.db.execute(stmt.order_by(DgProvider.provider_id, DgEndpoint.endpoint_name))).all()
        items = [self._endpoint_to_dict(endpoint, provider) for endpoint, provider in rows]
        return {"items": items, "total": len(items)}

    async def get_endpoint(self, endpoint_id: str) -> tuple[DgEndpoint, DgProvider] | None:
        result = await self.db.execute(
            select(DgEndpoint, DgProvider).join(DgProvider).where(DgEndpoint.id == endpoint_id)
        )
        row = result.one_or_none()
        return row

    async def get_endpoint_by_name(self, endpoint_name: str) -> tuple[DgEndpoint, DgProvider] | None:
        result = await self.db.execute(
            select(DgEndpoint, DgProvider)
            .join(DgProvider)
            .where((DgEndpoint.endpoint_name == endpoint_name) | (DgEndpoint.function_path == endpoint_name))
            .order_by(DgProvider.provider_id, DgEndpoint.endpoint_name)
        )
        return result.first()

    async def preview_endpoint(self, endpoint_id: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        row = await self.get_endpoint(endpoint_id)
        if row is None:
            return None
        endpoint, provider = row
        result = await self.executor.preview(endpoint.function_path, params)
        payload = asdict(result)
        payload["status"] = str((payload.get("metadata") or {}).get("status") or "ok")
        payload["provider_id"] = provider.provider_id
        payload["endpoint_name"] = endpoint.endpoint_name
        payload["params"] = params or {}
        return payload

    async def create_job(self, endpoint_id: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        row = await self.get_endpoint(endpoint_id)
        if row is None:
            return None
        endpoint, _provider = row
        job = DgIngestJob(
            endpoint_id=endpoint_id,
            status=DgJobStatus.QUEUED,
            params=params or {},
            row_count=0,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        job.status = DgJobStatus.RUNNING
        await self.db.commit()
        try:
            preview = await self.executor.preview(endpoint.function_path, params)
            preview_payload = asdict(preview)
            job.row_count = len(preview_payload["rows"])
            if str((preview_payload.get("metadata") or {}).get("status") or "ok") == "failed":
                job.status = DgJobStatus.FAILED
                job.error_message = str((preview_payload.get("metadata") or {}).get("error") or "connector_preview_failed")
            else:
                job.status = DgJobStatus.COMPLETED
                job.error_message = None
        except Exception as exc:
            job.status = DgJobStatus.FAILED
            job.error_message = str(exc)
        await self.db.commit()
        await self.db.refresh(job)
        return self._job_to_dict(job)

    async def list_jobs(self, endpoint_id: str | None = None) -> dict[str, Any]:
        stmt = select(DgIngestJob).order_by(DgIngestJob.created_at.desc())
        if endpoint_id:
            stmt = stmt.where(DgIngestJob.endpoint_id == endpoint_id)
        items = (await self.db.execute(stmt)).scalars().all()
        return {"items": [self._job_to_dict(job) for job in items], "total": len(items)}

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = await self.db.get(DgIngestJob, job_id)
        if job is None:
            return None
        return self._job_to_dict(job)

    async def _ensure_seed_providers(self) -> dict[str, DgProvider]:
        existing = (await self.db.execute(select(DgProvider))).scalars().all()
        providers = {provider.provider_id: provider for provider in existing}
        for seed in _PROVIDER_SEEDS:
            if seed["provider_id"] not in providers:
                provider = DgProvider(**seed)
                self.db.add(provider)
                providers[seed["provider_id"]] = provider
        await self.db.flush()
        return providers

    async def _ensure_seed_endpoints(self, providers: dict[str, DgProvider]) -> int:
        existing = {
            (endpoint.provider_id, endpoint.endpoint_name)
            for endpoint in (await self.db.execute(select(DgEndpoint))).scalars().all()
        }
        created = 0
        for provider_key, names in _ENDPOINT_SEEDS.items():
            provider = providers[provider_key]
            for name in names:
                if (provider.id, name) in existing:
                    continue
                self.db.add(
                    DgEndpoint(
                        provider_id=provider.id,
                        endpoint_name=name,
                        display_name=name.replace("_", " ").title(),
                        function_path=f"{provider_key}.{name}",
                        category=provider.category,
                        params_schema={"symbol": {"type": "string", "required": False}},
                        auth_type=provider.auth_type,
                        api_key_env=provider.api_key_env,
                        rate_limit=provider.rate_limit,
                        target_table=f"{provider_key}_{name}",
                        incremental_sync_key="date",
                    )
                )
                created += 1
        await self.db.flush()
        return created

    async def _migrate_akshare_interfaces(self, provider: DgProvider) -> int:
        interfaces = (await self.db.execute(select(DataInterface))).scalars().all()
        existing = {
            endpoint.legacy_interface_name
            for endpoint in (await self.db.execute(select(DgEndpoint).where(DgEndpoint.provider_id == provider.id))).scalars().all()
            if endpoint.legacy_interface_name
        }
        created = 0
        for interface in interfaces:
            if interface.name in existing:
                continue
            self.db.add(
                DgEndpoint(
                    provider_id=provider.id,
                    endpoint_name=interface.name,
                    display_name=interface.display_name,
                    function_path=".".join(part for part in [interface.module_path, interface.function_name] if part),
                    category="akshare",
                    params_schema=interface.parameters or {},
                    target_table=interface.name,
                    incremental_sync_key=str((interface.extra_config or {}).get("incremental_sync_key") or "date"),
                    legacy_interface_name=interface.name,
                )
            )
            created += 1
        await self.db.flush()
        return created

    async def _ensure_compat_view(self) -> None:
        bind = await self.db.connection()
        dialect = bind.dialect.name
        if dialect != "sqlite":
            return
        await self.db.execute(
            text(
                "CREATE VIEW IF NOT EXISTS ak_data_interfaces_compat AS "
                "SELECT e.id AS id, e.endpoint_name AS name, e.display_name AS display_name, "
                "e.function_path AS module_path, e.params_schema AS parameters, e.is_active AS is_active "
                "FROM dg_endpoints e JOIN dg_providers p ON p.id = e.provider_id "
                "WHERE p.provider_id = 'akshare'"
            )
        )

    @staticmethod
    def _provider_to_dict(provider: DgProvider) -> dict[str, Any]:
        return {
            "id": provider.id,
            "provider_id": provider.provider_id,
            "name": provider.name,
            "category": provider.category,
            "auth_type": provider.auth_type,
            "api_key_env": provider.api_key_env,
            "rate_limit": provider.rate_limit,
            "is_active": provider.is_active,
        }

    @staticmethod
    def _endpoint_to_dict(endpoint: DgEndpoint, provider: DgProvider) -> dict[str, Any]:
        return {
            "id": endpoint.id,
            "provider_id": provider.provider_id,
            "endpoint_name": endpoint.endpoint_name,
            "display_name": endpoint.display_name,
            "category": endpoint.category,
            "function_path": endpoint.function_path,
            "params_schema": endpoint.params_schema,
            "auth_type": endpoint.auth_type,
            "api_key_env": endpoint.api_key_env,
            "rate_limit": endpoint.rate_limit,
            "cache_ttl_sec": endpoint.cache_ttl_sec,
            "target_database": endpoint.target_database,
            "target_table": endpoint.target_table,
            "normalization_profile": endpoint.normalization_profile,
            "quality_profile": endpoint.quality_profile,
            "incremental_sync_key": endpoint.incremental_sync_key,
            "is_active": endpoint.is_active,
        }

    @staticmethod
    def _job_to_dict(job: DgIngestJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "endpoint_id": job.endpoint_id,
            "status": job.status.value,
            "params": job.params or {},
            "row_count": job.row_count,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }
