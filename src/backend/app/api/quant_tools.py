import typing

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.services.quant_tools import get_quant_tools_service

router = APIRouter(prefix="/quant-tools", tags=["Quant Tools"])


@router.get("", response_model=None)
async def list_tools(current_user: typing.Any = Depends(get_current_user)) -> typing.Any:
    return get_quant_tools_service().list_tools()


@router.post("/call", response_model=None)
async def call_tool(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    status_code, body = await get_quant_tools_service().call_tool(
        db,
        user_id=current_user.sub,
        username=current_user.username,
        tool_name=str(payload.get("tool_name") or ""),
        payload=dict(payload.get("input") or {}),
    )

    return JSONResponse(status_code=status_code, content=body)


@router.post("/chat-simulate", response_model=None)
async def chat_simulate(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    status_code, body = await get_quant_tools_service().simulate_chat(
        db,
        user_id=current_user.sub,
        username=current_user.username,
        tool_calls=list(payload.get("tool_calls") or []),
    )

    return JSONResponse(status_code=status_code, content=body)
