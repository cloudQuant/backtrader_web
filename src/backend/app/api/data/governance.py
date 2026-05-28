from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import get_current_db_user
from app.db.database import get_db
from app.services.data_connectors import DataGovernanceService

router = APIRouter(prefix="/data-governance", tags=["Data Governance"])


def get_data_governance_service(db: AsyncSession = Depends(get_db)) -> DataGovernanceService:
    return DataGovernanceService(db)


@router.post("/bootstrap")
async def bootstrap_data_governance(
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    return await service.bootstrap()


@router.get("/providers")
async def list_providers(
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    return await service.list_providers()


@router.get("/endpoints")
async def list_endpoints(
    provider_id: str | None = None,
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    return await service.list_endpoints(provider_id=provider_id)


@router.post("/endpoints/{endpoint_id}/preview")
async def preview_endpoint(
    endpoint_id: str,
    payload: dict | None = None,
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    result = await service.preview_endpoint(endpoint_id, dict((payload or {}).get("params") or {}))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="endpoint_not_found")
    return result


@router.get("/jobs")
async def list_jobs(
    endpoint_id: str | None = None,
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    return await service.list_jobs(endpoint_id=endpoint_id)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    result = await service.get_job(job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return result


@router.post("/endpoints/{endpoint_id}/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(
    endpoint_id: str,
    payload: dict | None = None,
    current_user=Depends(get_current_db_user),
    service: DataGovernanceService = Depends(get_data_governance_service),
):
    result = await service.create_job(endpoint_id, dict((payload or {}).get("params") or {}))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="endpoint_not_found")
    return result
