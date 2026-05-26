from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.api.deps import get_current_user, get_websocket_current_user
from app.schemas.overfitting import (
    OverfittingAnalysisRequest,
    OverfittingTaskResult,
    OverfittingTaskSubmission,
)
from app.services.overfitting.service import OverfittingService, get_overfitting_service
from app.websocket_manager import MessageType
from app.websocket_manager import manager as ws_manager

router = APIRouter()


def _overfitting_ws_channel(task_id: str) -> str:
    return f"overfitting:{task_id}"


def _is_terminal_overfitting_status(task_status: str | None) -> bool:
    return str(task_status or "") in {"completed", "failed", "cancelled"}


def _build_overfitting_runtime_snapshot(
    task_id: str,
    task_status: str,
    result: OverfittingTaskResult | None,
) -> dict:
    if task_status == "pending":
        return {
            "type": "task_created",
            "task_id": task_id,
            "status": "pending",
            "message": result.summary if result else "Overfitting task submitted",
        }
    if task_status == "running":
        return {
            "type": MessageType.PROGRESS,
            "task_id": task_id,
            "progress": 0,
            "message": result.summary if result else "Overfitting analysis is running",
            "data": {"status": task_status},
        }
    if task_status == "completed":
        return {
            "type": MessageType.COMPLETED,
            "task_id": task_id,
            "progress": 100,
            "message": result.summary if result else "Overfitting analysis completed",
            "result": result.model_dump(mode="python") if result else None,
        }
    if task_status == "failed":
        error_message = result.error_message if result and result.error_message else "Unknown error"
        return {
            "type": MessageType.FAILED,
            "task_id": task_id,
            "message": result.summary if result and result.summary else error_message,
            "error": error_message,
        }
    return {
        "type": MessageType.CANCELLED,
        "task_id": task_id,
        "message": result.summary if result else "Overfitting analysis cancelled",
    }


@router.post(
    "/overfitting/{backtest_id}",
    response_model=OverfittingTaskSubmission,
    summary="Create overfitting analysis task",
)
async def create_overfitting_task(
    backtest_id: str,
    data: OverfittingAnalysisRequest,
    current_user=Depends(get_current_user),
    service: OverfittingService = Depends(get_overfitting_service),
):
    try:
        submission = await service.schedule_analysis(
            backtest_id=backtest_id,
            user_id=current_user.sub,
            request=data,
        )
        submission_task_id = submission["task_id"] if isinstance(submission, dict) else submission.task_id
        submission_status = submission["status"] if isinstance(submission, dict) else submission.status
        await ws_manager.send_to_task(
            _overfitting_ws_channel(submission_task_id),
            {
                "type": "task_created",
                "task_id": submission_task_id,
                "status": submission_status,
                "message": "Overfitting task submitted",
            },
        )
        return submission
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/overfitting/task/{task_id}",
    response_model=OverfittingTaskResult,
    summary="Get overfitting analysis task",
)
async def get_overfitting_task(
    task_id: str,
    current_user=Depends(get_current_user),
    service: OverfittingService = Depends(get_overfitting_service),
):
    result = await service.get_task_result(task_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(status_code=404, detail="Overfitting analysis task not found")
    return result


async def websocket_endpoint(websocket: WebSocket, task_id: str):
    current_user, accepted_subprotocol = get_websocket_current_user(websocket)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    service = get_overfitting_service()
    task_result = await service.get_task_result(task_id, user_id=current_user.sub)
    if task_result is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    channel = _overfitting_ws_channel(task_id)
    client_id = f"client_{id(websocket)}"
    await ws_manager.connect(websocket, channel, client_id, accepted_subprotocol)

    try:
        initial_snapshot = _build_overfitting_runtime_snapshot(task_id, task_result.status, task_result)
        await ws_manager.send_to_task(channel, initial_snapshot)

        if _is_terminal_overfitting_status(task_result.status):
            return

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                data = None

            if data == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            latest_result = await service.get_task_result(task_id, user_id=current_user.sub)
            if latest_result is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                break
            if not _is_terminal_overfitting_status(latest_result.status):
                continue
            terminal_snapshot = _build_overfitting_runtime_snapshot(
                task_id,
                latest_result.status,
                latest_result,
            )
            await ws_manager.send_to_task(channel, terminal_snapshot)
            break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, channel, client_id)
