"""
并行运行 strategies/ 下所有策略的 run.py，使用 8 个进程。
每个策略运行前先清空其 logs/ 目录。
"""
import subprocess
import glob
import os
import sys
import shutil
import time
from multiprocessing import Pool, cpu_count

PYTHON = sys.executable
STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'strategies')
WORKERS = 8


def run_strategy(strategy_dir: str) -> dict:
    """运行单个策略的 run.py，运行前清空 logs 目录。"""
    name = os.path.basename(strategy_dir)
    run_py = os.path.join(strategy_dir, 'run.py')

    if not os.path.isfile(run_py):
        return {'name': name, 'status': 'skip', 'msg': 'no run.py', 'elapsed': 0}

    # 清空 logs 目录
    logs_dir = os.path.join(strategy_dir, 'logs')
    if os.path.isdir(logs_dir):
        shutil.rmtree(logs_dir)

    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, 'run.py'],
            cwd=strategy_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            return {'name': name, 'status': 'ok', 'msg': '', 'elapsed': elapsed}
        else:
            err_lines = (result.stderr or result.stdout or '').strip().split('\n')
            last_err = err_lines[-1][:200] if err_lines else 'unknown'
            return {'name': name, 'status': 'fail', 'msg': last_err, 'elapsed': elapsed}
    except subprocess.TimeoutExpired:
        return {'name': name, 'status': 'timeout', 'msg': 'exceeded 300s', 'elapsed': 300}
    except Exception as e:
        return {'name': name, 'status': 'error', 'msg': str(e)[:200], 'elapsed': time.time() - start}


def main():
    strategy_dirs = sorted(glob.glob(os.path.join(STRATEGIES_DIR, '*')))
    strategy_dirs = [d for d in strategy_dirs if os.path.isdir(d)]

    total = len(strategy_dirs)
    print(f"Found {total} strategies, running with {WORKERS} workers...\n")

    start_all = time.time()

    with Pool(processes=WORKERS) as pool:
        results = pool.map(run_strategy, strategy_dirs)

    elapsed_all = time.time() - start_all

    # 汇总结果
    ok = [r for r in results if r['status'] == 'ok']
    skip = [r for r in results if r['status'] == 'skip']
    fail = [r for r in results if r['status'] == 'fail']
    timeout = [r for r in results if r['status'] == 'timeout']
    error = [r for r in results if r['status'] == 'error']

    print("=" * 60)
    print(f"RESULTS: {len(ok)} OK, {len(fail)} FAILED, {len(timeout)} TIMEOUT, {len(skip)} SKIPPED, {len(error)} ERROR")
    print(f"Total time: {elapsed_all:.1f}s")
    print("=" * 60)

    if fail:
        print(f"\nFailed ({len(fail)}):")
        for r in fail:
            print(f"  {r['name']}: {r['msg']}")

    if timeout:
        print(f"\nTimeout ({len(timeout)}):")
        for r in timeout:
            print(f"  {r['name']}")

    if error:
        print(f"\nError ({len(error)}):")
        for r in error:
            print(f"  {r['name']}: {r['msg']}")

    if ok:
        print(f"\nOK ({len(ok)}):")
        for r in ok:
            print(f"  {r['name']} ({r['elapsed']:.1f}s)")


if __name__ == '__main__':
    main()
