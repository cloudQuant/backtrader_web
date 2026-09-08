"""Bridge the sandbox execution receipt into server-owned workflow completion."""

from app.services.research.discovery_sandbox import DiscoverySandboxService
from app.services.research.workflow_worker import StageExecutionContext, StageExecutionOutcome


class DiscoveryStageExecutor:
    """Execute once; the stage service publishes its evidence in one transaction."""

    def __init__(self, *, sandbox_service: DiscoverySandboxService) -> None:
        self._sandbox = sandbox_service

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        """Return only the journal identity and its validated terminal disposition."""
        dispatch = await self._sandbox.execute(context)
        evidence = dispatch.result.snapshot
        return StageExecutionOutcome.discovered(
            execution_id=dispatch.journal_id,
            status=evidence["status"],
            error_code=evidence["error_code"],
        )
