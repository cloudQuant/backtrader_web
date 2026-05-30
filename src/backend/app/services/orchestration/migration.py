"""
Migration tool: APScheduler tasks → Airflow DAGs.

Reads active ScheduledTasks from the database and generates
corresponding Airflow DAG files.
"""

from typing import Any

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.akshare_mgmt import DataScript, ScheduledTask
from app.services.orchestration.dag_generator import DAGGenerator
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MigrationTool:
    """Migrates APScheduler tasks to Airflow DAG files.

    Args:
        dag_output_dir: Directory to write generated DAG files.
    """

    def __init__(self, dag_output_dir: str) -> None:
        self._generator = DAGGenerator(dag_output_dir=dag_output_dir)

    async def migrate_all(self) -> dict[str, Any]:
        """Migrate all active scheduled tasks to Airflow DAGs.

        Returns:
            Migration report with success_count, failure_count, total_count,
            successes list, and failures list.
        """
        successes: list[dict[str, str]] = []
        failures: list[dict[str, str]] = []

        async with async_session_maker() as session:
            # Load all active tasks with their scripts
            result = await session.execute(
                select(ScheduledTask).where(ScheduledTask.is_active.is_(True))
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                try:
                    # Load the associated script
                    script_result = await session.execute(
                        select(DataScript).where(DataScript.script_id == task.script_id)
                    )
                    script = script_result.scalar_one_or_none()

                    if script is None:
                        failures.append(
                            {
                                "task_id": str(task.id),
                                "task_name": task.name,
                                "reason": f"Script '{task.script_id}' not found",
                            }
                        )
                        continue

                    # Generate DAG file
                    path = self._generator.generate_dag(script, task)
                    successes.append(
                        {
                            "task_id": str(task.id),
                            "task_name": task.name,
                            "dag_file": path,
                        }
                    )

                except Exception as exc:
                    failures.append(
                        {
                            "task_id": str(task.id),
                            "task_name": task.name,
                            "reason": str(exc),
                        }
                    )

        total = len(successes) + len(failures)
        logger.info(
            f"Migration completed: {len(successes)} success, {len(failures)} failed, {total} total"
        )

        return {
            "success_count": len(successes),
            "failure_count": len(failures),
            "total_count": total,
            "successes": successes,
            "failures": failures,
        }

    async def validate_generated_dags(self) -> list[str]:
        """Validate all generated DAG files are valid Python.

        Returns:
            List of error messages for invalid files. Empty if all valid.
        """
        from pathlib import Path

        errors: list[str] = []
        dag_dir = Path(self._generator._output_dir)

        if not dag_dir.exists():
            return [f"DAG directory does not exist: {dag_dir}"]

        for dag_file in dag_dir.glob("dag_*.py"):
            try:
                content = dag_file.read_text(encoding="utf-8")
                compile(content, str(dag_file), "exec")
            except SyntaxError as exc:
                errors.append(f"{dag_file.name}: {exc}")

        return errors
