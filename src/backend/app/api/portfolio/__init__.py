from fastapi import APIRouter

from app.api.portfolio.api import router as api_router
from app.api.portfolio.ledger import router as ledger_router

router = APIRouter()
router.include_router(api_router, prefix="/portfolio", tags=["Portfolio"])
router.include_router(ledger_router)

__all__ = ["router"]
