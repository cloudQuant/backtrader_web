#!/usr/bin/env python3
"""Quick CTP connection test after proxy bypass."""
import sys, os, time, threading, tempfile, hashlib

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')

from ctp import CThostFtdcMdApi, CThostFtdcMdSpi, CThostFtdcReqUserLoginField

MD_FRONT = "tcp://182.254.243.31:40011"
BROKER = "9999"
USER = "089763"
PASS = "yunjinqi2015!"

class MySpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
        self.events = []
    def OnFrontConnected(self):
        self.events.append("CONNECTED")
        print(f"[{time.strftime('%H:%M:%S')}] CONNECTED", flush=True)
    def OnFrontDisconnected(self, nReason):
        self.events.append(f"DISCONNECTED:{nReason}")
        print(f"[{time.strftime('%H:%M:%S')}] DISCONNECTED reason={nReason}", flush=True)
    def OnRspUserLogin(self, pLogin, pInfo, nReqID, bIsLast):
        eid = pInfo.ErrorID if pInfo else -1
        td = pLogin.TradingDay if pLogin else ""
        self.events.append(f"LOGIN:{eid}:{td}")
        print(f"[{time.strftime('%H:%M:%S')}] LOGIN ErrorID={eid} TradingDay={td}", flush=True)
    def OnRspError(self, pInfo, nReqID, bIsLast):
        eid = pInfo.ErrorID if pInfo else -1
        emsg = pInfo.ErrorMsg if pInfo else ""
        self.events.append(f"ERROR:{eid}")
        print(f"[{time.strftime('%H:%M:%S')}] ERROR {eid}: {emsg}", flush=True)

d = os.path.join(tempfile.gettempdir(), "ctp_test_now") + os.sep
os.makedirs(d, exist_ok=True)
# Clean stale flow files
for f in os.listdir(d):
    os.remove(os.path.join(d, f))

api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront(MD_FRONT)
print(f"API version: {api.GetApiVersion()}", flush=True)
print(f"Connecting to {MD_FRONT}...", flush=True)
api.Init()

# Start Join in background
t = threading.Thread(target=api.Join, daemon=True)
t.start()

# Also try login if connected
def try_login():
    time.sleep(3)
    if spi.events and "CONNECTED" in spi.events[-1]:
        field = CThostFtdcReqUserLoginField()
        field.BrokerID = BROKER
        field.UserID = USER
        field.Password = PASS
        ret = api.ReqUserLogin(field, 1)
        print(f"ReqUserLogin: {ret}", flush=True)

login_t = threading.Thread(target=try_login, daemon=True)
login_t.start()

# Wait 15s
for i in range(30):
    time.sleep(0.5)
    if any("LOGIN" in e for e in spi.events):
        break

print(f"\nResult: {spi.events}", flush=True)
if not spi.events:
    print("FAIL: No events - SPI callbacks not working", flush=True)
elif any("LOGIN:0" in e for e in spi.events):
    print("SUCCESS: CTP connected and logged in!", flush=True)
else:
    print("PARTIAL: Got events but login failed", flush=True)

api.RegisterSpi(None)
