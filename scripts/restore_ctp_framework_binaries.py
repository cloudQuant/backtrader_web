from __future__ import annotations

import json
import shutil
from pathlib import Path


REPO_ROOT = Path('/Users/yunjinqi/Documents/new_projects/bt_api_py')
RUNTIME_CTP_DIR = REPO_ROOT / 'bt_api_py' / 'ctp'
BUILD_CTP_DIR = REPO_ROOT / 'build' / 'lib.macosx-11.0-arm64-cpython-311' / 'bt_api_py' / 'ctp'


BINARY_PAIRS = [
    (
        BUILD_CTP_DIR / 'thostmduserapi_se.framework' / 'Versions' / 'A' / 'thostmduserapi_se',
        RUNTIME_CTP_DIR / 'thostmduserapi_se.framework' / 'Versions' / 'A' / 'thostmduserapi_se',
    ),
    (
        BUILD_CTP_DIR / 'thosttraderapi_se.framework' / 'Versions' / 'A' / 'thosttraderapi_se',
        RUNTIME_CTP_DIR / 'thosttraderapi_se.framework' / 'Versions' / 'A' / 'thosttraderapi_se',
    ),
]


def restore_binaries() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for src, dst in BINARY_PAIRS:
        item: dict[str, object] = {
            'src': str(src),
            'dst': str(dst),
            'src_exists': src.exists(),
            'dst_exists': dst.exists(),
        }
        if not src.exists():
            item['status'] = 'missing_source'
            results.append(item)
            continue
        backup = dst.with_name(dst.name + '.bak_lfs_pointer')
        if dst.exists() and not backup.exists():
            shutil.copy2(dst, backup)
        shutil.copy2(src, dst)
        item['backup'] = str(backup)
        item['src_size'] = src.stat().st_size
        item['dst_size'] = dst.stat().st_size
        item['status'] = 'copied'
        results.append(item)
    return results


if __name__ == '__main__':
    print(json.dumps(restore_binaries(), ensure_ascii=False, indent=2))
