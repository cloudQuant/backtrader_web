from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.services.equity_research import get_equity_research_service

router = APIRouter(prefix="/equity-research", tags=["Equity Research"])


@router.get("/search")
async def search_equities(q: str = Query(...), current_user=Depends(get_current_user)):
    return get_equity_research_service().search(q)


@router.get("/quote/{symbol}")
async def get_quote(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().get_quote(symbol)


@router.get("/info/{symbol}")
async def get_info(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().info(symbol)


@router.get("/history/{symbol}")
async def get_history(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().history(symbol)


@router.get("/financials/{symbol}")
async def get_financials(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().financials(symbol)


@router.get("/technicals/{symbol}")
async def get_technicals(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().technicals(symbol)


@router.get("/peers/{symbol}")
async def get_peers(symbol: str, current_user=Depends(get_current_user)):
    return get_equity_research_service().peers(symbol)
