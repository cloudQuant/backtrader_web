#!/usr/bin/env python3
"""Check if CTP actually opens TCP connections after Init."""
import sys, os, time, threading, tempfile, subprocess

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

class MySpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
    def OnFrontConnected(self):
        print("  CONNECTED!", flush=True)
    def OnFrontDisconnected(self, nReason):
        print(f"  DISCONNECTED {nReason}", flush=True)

d = os.path.join(tempfile.gettempdir(), "ctp_lsof_test") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d): os.remove(os.path.join(d, f))

pid = os.getpid()

def show_tcp():
    r = subprocess.run(["lsof", "-i", "TCP", "-P", "-n", "-p", str(pid)],
                       capture_output=True, text=True, timeout=5)
    lines = [l for l in r.stdout.strip().split("\n") if "182.254" in l or "40011" in l or "40001" in l]
    return lines

print(f"PID: {pid}")
print(f"Before Init - TCP to CTP: {show_tcp()}")

api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront("tcp://182.254.243.31:40011")
api.Init()

t = threading.Thread(target=api.Join, daemon=True)
t.start()

for i in range(10):
    time.sleep(1)
    conns = show_tcp()
    print(f"  t={i+1}s TCP: {conns}")
    if conns:
        break

# Also check all threads
r = subprocess.run(["ps", "-M", str(pid)], capture_output=True, text=True, timeout=5)
thread_count = len(r.stdout.strip().split("\n")) - 1
print(f"\nNative threads: {thread_count}")

api.RegisterSpi(None)
print("Done")
