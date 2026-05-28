#!/usr/bin/env python3
"""Test CTP connection by polling GetTradingDay instead of relying on callbacks."""
import sys, os, time, threading, tempfile

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

class MySpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
        self.connected_count = 0
    def OnFrontConnected(self):
        self.connected_count += 1
        print(f"  SPI: OnFrontConnected (count={self.connected_count})", flush=True)
    def OnFrontDisconnected(self, nReason):
        print(f"  SPI: OnFrontDisconnected {nReason}", flush=True)

d = os.path.join(tempfile.gettempdir(), "ctp_poll_test") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d):
    os.remove(os.path.join(d, f))

api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront("tcp://182.254.243.31:40011")

print(f"Before Init: TradingDay={api.GetTradingDay()}", flush=True)
api.Init()

t = threading.Thread(target=api.Join, daemon=True)
t.start()

# Poll TradingDay to detect connection
for i in range(20):
    time.sleep(0.5)
    td = api.GetTradingDay()
    if td and td != "" and td != "19800100":
        print(f"  t={i*0.5:.1f}s TradingDay={td} <- CONNECTED via polling!", flush=True)
        break
    if i % 4 == 0:
        print(f"  t={i*0.5:.1f}s TradingDay={td} callbacks={spi.connected_count}", flush=True)

print(f"\nFinal: TradingDay={api.GetTradingDay()}, SPI callbacks={spi.connected_count}", flush=True)

# Try direct SPI method call from Python (this should work regardless of C++ threads)
print("\nDirect Python call test:", flush=True)
spi.OnFrontConnected()
print(f"Direct call worked, count={spi.connected_count}", flush=True)

api.RegisterSpi(None)
