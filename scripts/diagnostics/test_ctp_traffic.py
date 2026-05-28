#!/usr/bin/env python3
"""Check if CTP SDK sends data after Init by monitoring with lsof."""
import sys, os, time, threading, tempfile, subprocess

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

class MySpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
    def OnFrontConnected(self):
        print("  SPI: CONNECTED!", flush=True)
    def OnFrontDisconnected(self, nReason):
        print(f"  SPI: DISCONNECTED {nReason}", flush=True)

d = os.path.join(tempfile.gettempdir(), "ctp_traffic_test") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d): os.remove(os.path.join(d, f))

pid = os.getpid()
api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront("tcp://182.254.243.31:40011")
api.Init()

t = threading.Thread(target=api.Join, daemon=True)
t.start()

# Monitor TCP state and bytes transferred
for i in range(15):
    time.sleep(1)
    try:
        r = subprocess.run(
            ["lsof", "-i", f"TCP@182.254.243.31:40011", "-P", "-n", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        )
        lines = [l for l in r.stdout.strip().split("\n") if "182.254" in l]
        for l in lines:
            print(f"  t={i+1}s: {l.strip()}", flush=True)
    except:
        pass

    # Also check netstat for byte counters
    try:
        r2 = subprocess.run(
            ["netstat", "-anb"],
            capture_output=True, text=True, timeout=3,
        )
        for l in r2.stdout.split("\n"):
            if "40011" in l and "182.254" in l:
                print(f"  netstat: {l.strip()}", flush=True)
    except:
        pass

print(f"\nTradingDay: {api.GetTradingDay()}", flush=True)
api.RegisterSpi(None)
