"""Diagnose Binance listen key REST call path."""
import sys
import os
import traceback

OUT = r"D:\new_projects\backtrader_web\scripts\diag_result.txt"
sys.path.insert(0, r"D:\new_projects\bt_api_py")

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
    os.environ.pop(k, None)

lines = []
try:
    from bt_api_py.containers.exchanges.binance_exchange_data import BinanceExchangeDataSwap
    ed = BinanceExchangeDataSwap()
    lines.append(f"rest_url: {ed.rest_url}")
    lines.append(f"wss_url: {ed.wss_url}")
except Exception:
    lines.append(traceback.format_exc())
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    sys.exit(1)

try:
    from bt_api_py.feeds.http_client import HttpClient
    client = HttpClient(proxies={"https": "", "http": ""})
    url = f"{ed.rest_url}/fapi/v1/listenKey"
    headers = {"X-MBX-APIKEY": "U7thNsgVBaEjtLvsAH79ibMYvsM25uAch6BgzQvAm204Jl41jLobDPNxkEtKflsB"}
    r = client.request("POST", url, headers=headers, timeout=10)
    lines.append(f"HttpClient: {r.status_code} {r.text[:200]}")
except Exception:
    lines.append(f"HttpClient error:\n{traceback.format_exc()}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

