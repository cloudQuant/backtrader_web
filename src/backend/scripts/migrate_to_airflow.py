"""
CLI script to migrate APScheduler tasks to Airflow DAGs.

Usage:
    cd src/backend
    python scripts/migrate_to_airflow.py

This reads all active ScheduledTasks from the database and generates
corresponding Airflow DAG files in the configured output directory.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from app.config import get_settings
    from app.services.orchestration.migration import MigrationTool

    settings = get_settings()
    dag_dir = settings.AIRFLOW_DAG_OUTPUT_DIR or "./dags"

    print(f"=== Airflow Migration Tool ===")
    print(f"DAG output directory: {dag_dir}")
    print()

    tool = MigrationTool(dag_output_dir=dag_dir)

    # Run migration
    print("Migrating active tasks to Airflow DAGs...")
    report = await tool.migrate_all()

    print(f"\n=== Migration Report ===")
    print(f"Total tasks: {report['total_count']}")
    print(f"Success: {report['success_count']}")
    print(f"Failed: {report['failure_count']}")

    if report["successes"]:
        print(f"\n✅ Successfully migrated:")
        for s in report["successes"]:
            print(f"   - {s['task_name']} → {s['dag_file']}")

    if report["failures"]:
        print(f"\n❌ Failed:")
        for f in report["failures"]:
            print(f"   - {f['task_name']}: {f['reason']}")

    # Validate generated files
    print(f"\nValidating generated DAG files...")
    errors = await tool.validate_generated_dags()
    if errors:
        print(f"⚠️  Validation errors:")
        for e in errors:
            print(f"   - {e}")
    else:
        print(f"✅ All generated DAG files are valid Python")

    print(f"\n=== Done ===")
    return 0 if report["failure_count"] == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
