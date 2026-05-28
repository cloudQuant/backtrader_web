#!/usr/bin/env python3
"""Test CTP connection through HTTP CONNECT tunnel."""
import sys, os, time, threading, tempfile

sys.path.insert(0, 'src/backend')
sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from app.services.ctp_tunnel import ensure_tunnel, is_proxy_tunnel_needed, stop_all_tunnels
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

REMOTE_HOST = "182.254.243.31"
REMOTE_PORT = 40011

print(f"Proxy tunnel needed: {is_proxy_tunnel_needed()}", flush=True)

class MySpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
        self.events = []
    def OnFrontConnected(self):
        self.events.append("CONNECTED")
        print(f"  SPI: CONNECTED!", flush=True)
    def OnFrontDisconnected(self, nReason):
        self.events.append(f"DISCONNECTED:{nReason}")
        print(f"  SPI: DISCONNECTED {nReason}", flush=True)

# Start HTTP CONNECT tunnel
local_port = ensure_tunnel(REMOTE_HOST, REMOTE_PORT)
local_front = f"tcp://127.0.0.1:{local_port}"
print(f"\nTunnel: {local_front} -> HTTP CONNECT -> {REMOTE_HOST}:{REMOTE_PORT}", flush=True)

# Connect CTP through tunnel
d = os.path.join(tempfile.gettempdir(), "ctp_tunnel_test2") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d): os.remove(os.path.join(d, f))

api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront(local_front)
print(f"Init...", flush=True)
api.Init()

t = threading.Thread(target=api.Join, daemon=True)
t.start()

for i in range(30):
    time.sleep(0.5)
    td = api.GetTradingDay()
    if td and td != "19800100":
        print(f"  t={i*0.5:.1f}s TradingDay={td} <- CONNECTED!", flush=True)
        time.sleep(1)
        break
    if i % 4 == 0:
        print(f"  t={i*0.5:.1f}s TradingDay={td} events={spi.events}", flush=True)

print(f"\nFinal: TradingDay={api.GetTradingDay()}, events={spi.events}", flush=True)
if any("CONNECTED" in e for e in spi.events):
    print("SUCCESS: CTP connected via HTTP CONNECT tunnel!", flush=True)
elif api.GetTradingDay() not in ("", "19800100"):
    print("SUCCESS: CTP connected (TradingDay updated)!", flush=True)
else:
    print("FAIL: No connection established", flush=True)

api.RegisterSpi(None)
stop_all_tunnels()
