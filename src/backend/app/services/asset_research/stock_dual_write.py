"""Controlled dual-write coordinator for legacy stock signal compatibility."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

WriteResult = TypeVar("WriteResult")


class DualWriteMode(str, Enum):
    OFF = "OFF"
    SHADOW = "SHADOW"
    ENFORCE = "ENFORCE"


@dataclass(frozen=True, slots=True)
class DualWriteOutcome:
    """Audit outcome for one dual-write operation."""

    mode: DualWriteMode
    primary_succeeded: bool
    shadow_succeeded: bool
    shadow_error: str | None = None

    @property
    def operation_succeeded(self) -> bool:
        if self.mode == DualWriteMode.ENFORCE:
            return self.primary_succeeded and self.shadow_succeeded
        return self.primary_succeeded


class StockDualWriteCoordinator:
    """Apply OFF/SHADOW/ENFORCE semantics without coupling to one DB session."""

    def __init__(self, mode: DualWriteMode | str = DualWriteMode.OFF) -> None:
        if isinstance(mode, str):
            mode = DualWriteMode(mode.upper())
        self.mode = mode

    async def write(
        self,
        *,
        primary_write: Callable[[], Awaitable[WriteResult]],
        shadow_write: Callable[[], Awaitable[WriteResult]],
    ) -> DualWriteOutcome:
        """Execute the configured write policy with fail-closed ENFORCE semantics."""
        if self.mode == DualWriteMode.OFF:
            await primary_write()
            return DualWriteOutcome(
                mode=self.mode,
                primary_succeeded=True,
                shadow_succeeded=False,
            )

        primary_result = await primary_write()
        try:
            await shadow_write()
            shadow_result: str | None = None
            shadow_succeeded = True
        except Exception as exc:
            error_code = getattr(exc, "code", None)
            shadow_result = str(error_code) if error_code else str(exc)
            shadow_succeeded = False

        if self.mode == DualWriteMode.ENFORCE and not shadow_succeeded:
            raise RuntimeError(f"SHADOW_WRITE_FAILED:{shadow_result}")
        return DualWriteOutcome(
            mode=self.mode,
            primary_succeeded=primary_result is not None or primary_result is None,
            shadow_succeeded=shadow_succeeded,
            shadow_error=shadow_result,
        )
