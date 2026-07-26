from fastapi import APIRouter

from app.api.akshare.executions import router as executions_router
from app.api.akshare.interfaces import router as interfaces_router
from app.api.akshare.scripts import router as scripts_router
from app.api.akshare.tables import router as tables_router
from app.api.akshare.tasks import router as tasks_router

router = APIRouter()
router.include_router(scripts_router, tags=["Data Scripts"])
router.include_router(tasks_router, tags=["Data Tasks"])
router.include_router(executions_router, tags=["Data Executions"])
router.include_router(tables_router, tags=["Data Tables"])
router.include_router(interfaces_router, tags=["Data Interfaces"])

__all__ = ["router"]
