"""
Generate Airflow DAG files for all data fetch scripts.

Scans the data_fetch/scripts directory and generates one DAG per category+frequency
combination. Each DAG contains parallel tasks for all scripts in that group.

Usage:
    cd src/backend
    python scripts/generate_all_dags.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collections import defaultdict

BACKEND_DIR = Path(__file__).parent.parent / "src" / "backend"

# Schedule mapping: frequency → Airflow cron expression
SCHEDULE_MAP = {
    "daily": "0 18 * * 1-5",      # Workdays at 18:00 (after market close)
    "hourly": "0 * * * 1-5",      # Every hour on workdays
    "weekly": "0 8 * * 6",        # Saturday at 08:00
    "monthly": "0 8 1 * *",       # 1st of month at 08:00
}

DAG_OUTPUT_DIR = BACKEND_DIR / "dags"
SCRIPTS_DIR = BACKEND_DIR / "app" / "data_fetch" / "scripts"


def scan_scripts() -> dict[str, list[dict]]:
    """Scan scripts directory and group by category/frequency."""
    groups: dict[str, list[dict]] = defaultdict(list)

    for script_file in sorted(SCRIPTS_DIR.rglob("*.py")):
        if script_file.name.startswith("__"):
            continue

        # Parse path: scripts/{category}/{frequency}/{script_name}.py
        relative = script_file.relative_to(SCRIPTS_DIR)
        parts = relative.parts

        if len(parts) < 3:
            continue

        category = parts[0]      # stocks, bonds, futures, etc.
        frequency = parts[1]     # daily, hourly, weekly, monthly
        script_name = script_file.stem  # e.g. stock_zh_a_hist

        groups[f"{category}_{frequency}"].append({
            "script_id": script_name,
            "category": category,
            "frequency": frequency,
            "module_path": f"app.data_fetch.scripts.{'.'.join(parts[:-1])}.{script_name}",
            "file_path": str(script_file),
        })

    return groups


def generate_dag_file(group_name: str, scripts: list[dict]) -> str:
    """Generate a DAG file for a group of scripts."""
    if not scripts:
        return ""

    category = scripts[0]["category"]
    frequency = scripts[0]["frequency"]
    schedule = SCHEDULE_MAP.get(frequency, "@daily")

    # Category display names
    category_names = {
        "stocks": "A股",
        "bonds": "债券",
        "futures": "期货",
        "funds": "基金",
        "indexs": "指数",
        "common": "通用",
        "cryptos": "加密货币",
        "currencies": "外汇",
        "forexs": "外汇",
        "options": "期权",
    }
    freq_names = {
        "daily": "日频",
        "hourly": "时频",
        "weekly": "周频",
        "monthly": "月频",
    }

    cat_name = category_names.get(category, category)
    freq_name = freq_names.get(frequency, frequency)
    description = f"{cat_name}{freq_name}数据抓取 ({len(scripts)} 个任务)"

    # Generate task definitions
    task_lines = []
    for s in scripts:
        task_lines.append(f'''
task_{s["script_id"]} = PythonOperator(
    task_id="{s["script_id"]}",
    python_callable=run_script,
    op_kwargs={{"module_path": "{s["module_path"]}"}},
    dag=dag,
)''')

    dag_content = f'''"""
Auto-generated DAG: {group_name}
{description}
Scripts: {len(scripts)}
Schedule: {schedule}
"""
from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

default_args = {{
    "owner": "ai_for_investor",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=60),
}}

dag = DAG(
    dag_id="dag_{group_name}",
    default_args=default_args,
    description="{description}",
    schedule_interval="{schedule}",
    start_date=days_ago(1),
    catchup=False,
    max_active_tasks=5,
    tags=["{category}", "{frequency}", "akshare", "auto-generated"],
)


def run_script(module_path: str, **context):
    """Execute a data fetch script by module path."""
    import importlib
    module = importlib.import_module(module_path)
    # Try to find and call the main() function or the class
    if hasattr(module, "main"):
        module.main()
    else:
        # Find the first class that has a fetch_data or run method
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and hasattr(attr, "fetch_data"):
                instance = attr()
                instance.fetch_data()
                break

{"".join(task_lines)}
'''
    return dag_content


def main():
    DAG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Airflow DAG Generator ===")
    print(f"Scripts directory: {SCRIPTS_DIR}")
    print(f"DAG output directory: {DAG_OUTPUT_DIR}")
    print()

    groups = scan_scripts()
    print(f"Found {sum(len(v) for v in groups.values())} scripts in {len(groups)} groups:")
    print()

    generated = 0
    for group_name, scripts in sorted(groups.items()):
        dag_content = generate_dag_file(group_name, scripts)
        if not dag_content:
            continue

        output_path = DAG_OUTPUT_DIR / f"dag_{group_name}.py"
        output_path.write_text(dag_content, encoding="utf-8")
        print(f"  ✅ dag_{group_name}.py ({len(scripts)} tasks)")
        generated += 1

    print(f"\n=== Generated {generated} DAG files ===")
    print(f"Total tasks across all DAGs: {sum(len(v) for v in groups.values())}")
    print(f"\nDAG files are in: {DAG_OUTPUT_DIR}")
    print("Start Airflow and these DAGs will be automatically loaded.")


if __name__ == "__main__":
    main()
