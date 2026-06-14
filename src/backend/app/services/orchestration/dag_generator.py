"""
DAG file generator from DataScript metadata.

Generates Airflow-compatible DAG Python files using Jinja2 templates.
"""

from collections import deque
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.services.orchestration.exceptions import DAGGenerationError
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class DAGGenerator:
    """Generates Airflow DAG files from DataScript metadata.

    Args:
        dag_output_dir: Directory to write generated DAG files.
        template_dir: Optional custom template directory.
    """

    def __init__(self, dag_output_dir: str, template_dir: str | None = None) -> None:
        self._output_dir = Path(dag_output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        tpl_dir = Path(template_dir) if template_dir else _TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            keep_trailing_newline=True,
        )

    def generate_dag(
        self,
        script: Any,
        task: Any | None = None,
    ) -> str:
        """Generate a single-task DAG file.

        Args:
            script: DataScript model instance or dict with script metadata.
            task: Optional ScheduledTask for schedule/retry info.

        Returns:
            Path to the generated DAG file.
        """
        script_id = getattr(script, "script_id", script.get("script_id", "unknown"))
        source = getattr(script, "source", script.get("source", "akshare"))
        timeout = getattr(script, "timeout", script.get("timeout", 300))
        description = getattr(script, "description", script.get("description", "")) or ""
        category = getattr(script, "category", script.get("category", "default"))
        parameters = getattr(script, "parameters", script.get("parameters", {})) or {}

        retries = 3
        schedule_interval = "@daily"
        if task:
            retries = getattr(task, "max_retries", task.get("max_retries", 3))
            expr = getattr(task, "schedule_expression", task.get("schedule_expression", ""))
            if expr:
                schedule_interval = self._convert_schedule(expr)

        try:
            template = self._env.get_template("dag_single.py.j2")
            content = template.render(
                script_id=script_id,
                source=source,
                timeout=timeout,
                description=description.replace('"', '\\"'),
                retries=retries,
                schedule_interval=schedule_interval,
                tags=repr([category, "auto-generated"]),
                parameters=repr(parameters),
            )
        except Exception as exc:
            raise DAGGenerationError(script_id, str(exc)) from exc

        output_path = self._output_dir / f"dag_{script_id}.py"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated DAG file: {output_path}")
        return str(output_path)

    def generate_grouped_dag(self, scripts: list[Any], category: str) -> str:
        """Generate a multi-task DAG from scripts in the same category.

        Args:
            scripts: List of DataScript instances sharing the same category.
            category: Category name for the DAG.

        Returns:
            Path to the generated DAG file.
        """
        # Build dependency edges
        script_ids = [getattr(s, "script_id", s.get("script_id", "")) for s in scripts]
        deps_map: dict[str, list[str]] = {}
        for s in scripts:
            sid = getattr(s, "script_id", s.get("script_id", ""))
            raw_deps = getattr(s, "dependencies", s.get("dependencies", None)) or []
            # Only include deps that are within this group
            deps_map[sid] = [d for d in raw_deps if d in script_ids]

        # Generate task definitions and dependency lines
        task_defs = []
        dep_lines = []
        for sid in script_ids:
            task_defs.append(
                f'task_{sid} = PythonOperator(task_id="{sid}", python_callable=_noop, dag=dag)'
            )
            for upstream in deps_map.get(sid, []):
                dep_lines.append(f"task_{upstream} >> task_{sid}")

        content = f'''"""Auto-generated grouped DAG for category: {category}."""
from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

default_args = {{"owner": "ai_for_trader", "retries": 3, "retry_delay": timedelta(minutes=5)}}

dag = DAG(
    dag_id="dag_group_{category}",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["{category}", "grouped", "auto-generated"],
)

def _noop(**ctx): pass

{chr(10).join(task_defs)}

{chr(10).join(dep_lines)}
'''
        output_path = self._output_dir / f"dag_group_{category}.py"
        output_path.write_text(content, encoding="utf-8")
        return str(output_path)

    def validate_dependencies(self, scripts: list[Any]) -> list[str]:
        """Validate dependency graph for cycles using topological sort.

        Args:
            scripts: List of DataScript instances.

        Returns:
            List of error messages. Empty if no cycles.
        """
        # Build adjacency list
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}

        for s in scripts:
            sid = getattr(s, "script_id", s.get("script_id", ""))
            graph.setdefault(sid, [])
            in_degree.setdefault(sid, 0)

        for s in scripts:
            sid = getattr(s, "script_id", s.get("script_id", ""))
            deps = getattr(s, "dependencies", s.get("dependencies", None)) or []
            for dep in deps:
                if dep in graph:
                    graph[dep].append(sid)
                    in_degree[sid] = in_degree.get(sid, 0) + 1

        # Kahn's algorithm for topological sort
        queue = deque([node for node, deg in in_degree.items() if deg == 0])
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(graph):
            # Find nodes in cycle
            cycle_nodes = [n for n, deg in in_degree.items() if deg > 0]
            return [f"Cyclic dependency detected among: {', '.join(cycle_nodes)}"]

        return []

    def remove_dag(self, script_id: str) -> bool:
        """Remove a generated DAG file.

        Args:
            script_id: Script identifier.

        Returns:
            True if file was removed, False if not found.
        """
        path = self._output_dir / f"dag_{script_id}.py"
        if path.exists():
            path.unlink()
            return True
        return False

    @staticmethod
    def _convert_schedule(expression: str) -> str:
        """Convert schedule expression to Airflow-compatible format.

        Supports:
        - Cron expressions (pass through): "0 8 * * *"
        - Time format: "18:00" → "0 18 * * *"
        - Interval: "30m" → "*/30 * * * *", "2h" → "0 */2 * * *"
        """
        expr = expression.strip()

        # Already a cron expression (has spaces and 5 parts)
        parts = expr.split()
        if len(parts) == 5:
            return expr

        # HH:MM format
        if ":" in expr and len(expr) <= 5:
            hour, minute = expr.split(":")
            return f"{minute} {hour} * * *"

        # Interval format
        lower = expr.lower()
        if lower.endswith("m"):
            minutes = int(lower[:-1])
            return f"*/{minutes} * * * *"
        if lower.endswith("h"):
            hours = int(lower[:-1])
            return f"0 */{hours} * * *"
        if lower.endswith("d"):
            return "@daily"

        # Fallback
        return expr
