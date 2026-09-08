"""Resolve logical market datasets to explicitly registered storage bindings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget


class DatasetStorageNotFoundError(LookupError):
    """Raised when a dataset has no unambiguous active primary storage binding."""


@dataclass(frozen=True)
class DatasetStorageResolution:
    """A non-secret reference to one physical data materialization."""

    dataset_id: str
    dataset_code: str
    storage_id: str
    engine: str
    database_name: str
    physical_table: str
    write_mode: str


class DataCatalogResolver:
    """Read primary bindings without trusting legacy endpoint target columns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_primary(self, dataset_code: str) -> DatasetStorageResolution:
        """Resolve exactly one active primary binding for ``dataset_code``."""
        rows = (
            await self._session.execute(
                select(DgDatasetStorage, DgDataset, DgStorageTarget)
                .join(DgDataset, DgDatasetStorage.dataset_id == DgDataset.id)
                .join(DgStorageTarget, DgDatasetStorage.storage_target_id == DgStorageTarget.id)
                .where(
                    DgDataset.dataset_code == dataset_code,
                    DgDataset.is_active.is_(True),
                    DgStorageTarget.is_active.is_(True),
                    DgDatasetStorage.is_primary.is_(True),
                )
            )
        ).all()
        if len(rows) != 1:
            raise DatasetStorageNotFoundError(
                f"No unambiguous active primary storage binding for dataset {dataset_code!r}"
            )

        binding, dataset, storage = rows[0]
        return DatasetStorageResolution(
            dataset_id=dataset.id,
            dataset_code=dataset.dataset_code,
            storage_id=storage.storage_id,
            engine=storage.engine,
            database_name=storage.database_name,
            physical_table=binding.physical_table,
            write_mode=binding.write_mode,
        )
