import typing

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.services.options_chain import get_options_chain_service

router = APIRouter(prefix="/options-chain", tags=["Options Chain"])


@router.get("/{symbol}", response_model=None)
async def get_options_chain(
    symbol: str,
    expiry: str,
    provider: str = "data_governance",
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    return await get_options_chain_service().build_chain(symbol, expiry, provider)
