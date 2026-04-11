import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / 'src' / 'backend'
os.environ.setdefault('DATABASE_URL', f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'backtrader.db').resolve()}")
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.workspace import StrategyUnitUpdate
from app.services.workspace_service import WorkspaceService

WORKSPACE_ID = '5e5ca26f-dbc6-47cd-9016-20c3024cdc51'
USER_ID = '50b591ae-4bf9-4f83-a26c-b3663afc5a9b'
TARGET_STRATEGY_ID = 'backtest/097_dema_crossover'
START_DATE = '2020-01-01T00:00:00+00:00'


async def main() -> None:
    service = WorkspaceService()
    units = await service.list_units(WORKSPACE_ID, USER_ID) or []
    updated = 0
    end_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for unit in units:
        if str(unit.get('strategy_id') or '').strip() != TARGET_STRATEGY_ID:
            continue
        data_config = dict(unit.get('data_config') or {})
        data_config.update(
            {
                'range_type': 'date',
                'start_date': START_DATE,
                'end_date': end_date,
                'use_end_date': True,
            }
        )
        data_config.pop('sample_count', None)
        data_config.pop('bar_count', None)
        await service.update_unit(
            WORKSPACE_ID,
            unit['id'],
            USER_ID,
            StrategyUnitUpdate(data_config=data_config),
        )
        updated += 1

    print(f'updated_units={updated}')
    print(f'start_date={START_DATE}')
    print(f'end_date={end_date}')


if __name__ == '__main__':
    asyncio.run(main())
