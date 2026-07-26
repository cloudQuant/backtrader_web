#!/usr/bin/env python3
"""Test openctp-ctp callbacks."""
import sys, os, time, threading, tempfile, signal

# Timeout to prevent hang
signal.alarm(20)

sys.path.insert(0, '/tmp/openctp_test')
from openctp_ctp import mdapi

print("openctp-ctp imported OK", flush=True)

class MySpi(mdapi.CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
        self.events = []
    def OnFrontConnected(self):
        self.events.append("CONNECTED")
        print(f"  CONNECTED", flush=True)
    def OnFrontDisconnected(self, nReason):
        self.events.append(f"DISCONNECTED:{nReason}")
        print(f"  DISCONNECTED {nReason}", flush=True)

d = os.path.join(tempfile.gettempdir(), "openctp_md_test") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d):
    os.remove(os.path.join(d, f))

print("Creating API...", flush=True)
api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront("tcp://182.254.243.31:40011")
print("Init...", flush=True)
api.Init()
print("Init done", flush=True)

t = threading.Thread(target=api.Join, daemon=True)
t.start()

for i in range(20):
    time.sleep(0.5)
    if spi.events:
        time.sleep(1)
        break

print(f"Events: {spi.events}", flush=True)
api.RegisterSpi(None)
