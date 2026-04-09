#!/usr/bin/env python3
"""Test CTP connection to all SimNow servers via HTTP CONNECT tunnel."""
import sys, os, time, threading, tempfile, socket

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

PROXY = ("127.0.0.1", 15732)
SERVERS = [
    ("182.254.243.31", 40011, "7x24 MD"),
    ("182.254.243.31", 40001, "7x24 TD"),
    ("182.254.243.31", 30011, "SimNow1 MD"),
    ("182.254.243.31", 30001, "SimNow1 TD"),
    ("182.254.243.31", 30012, "SimNow2 MD"),
    ("182.254.243.31", 30013, "SimNow3 MD"),
]

print("=== Testing raw TCP CONNECT to all servers ===", flush=True)
for host, port, label in SERVERS:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(PROXY)
        target = f"{host}:{port}"
        s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(4096)
            if not chunk: break
            resp += chunk
        status = resp.split(b"\r\n")[0].decode()
        if b"200" in resp.split(b"\r\n")[0]:
            s.settimeout(3)
            # Send CTP-like probe (invalid but forces server response)
            s.sendall(b"\x00\x06\x00\x00\x07\x04\x00\x00\x00\x27")
            try:
                data = s.recv(4096)
                if len(data) == 0:
                    print(f"  {label:15s} ({target}): server closed (EOF)", flush=True)
                else:
                    print(f"  {label:15s} ({target}): got {len(data)}b response!", flush=True)
            except socket.timeout:
                print(f"  {label:15s} ({target}): no response (timeout)", flush=True)
        else:
            print(f"  {label:15s} ({target}): CONNECT failed: {status}", flush=True)
        s.close()
    except Exception as e:
        print(f"  {label:15s} ({host}:{port}): ERROR {e}", flush=True)

# Now test actual CTP MdApi with best candidate via tunnel
print("\n=== Testing CTP MdApi via HTTP CONNECT tunnel ===", flush=True)
import selectors

class TracingSpi(CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()
        self.events = []
    def OnFrontConnected(self):
        self.events.append("CONNECTED")
        print(f"    SPI: CONNECTED!", flush=True)
    def OnFrontDisconnected(self, nReason):
        self.events.append(f"DISC:{nReason}")
        print(f"    SPI: DISCONNECTED {nReason}", flush=True)
    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
        eid = getattr(pRspInfo, 'ErrorID', None) if pRspInfo else None
        self.events.append(f"LOGIN:{eid}")
        print(f"    SPI: OnRspUserLogin ErrorID={eid}", flush=True)
    def OnRspError(self, pRspInfo, nRequestID, bIsLast):
        eid = getattr(pRspInfo, 'ErrorID', None) if pRspInfo else None
        self.events.append(f"ERR:{eid}")
        print(f"    SPI: OnRspError ErrorID={eid}", flush=True)

# Try multiple fronts
for md_host, md_port, label in [
    ("182.254.243.31", 30011, "SimNow1"),
    ("182.254.243.31", 30012, "SimNow2"),
    ("182.254.243.31", 40011, "7x24"),
]:
    print(f"\n--- Testing {label} ({md_host}:{md_port}) ---", flush=True)

    # Create tunnel
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    lp = srv.getsockname()[1]
    stop = threading.Event()

    def run_tunnel(srv_sock=srv, rh=md_host, rp=md_port, stop_evt=stop):
        srv_sock.settimeout(1.0)
        while not stop_evt.is_set():
            try:
                cs, _ = srv_sock.accept()
            except (socket.timeout, OSError):
                continue
            cs.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            rs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            rs.settimeout(10)
            rs.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                rs.connect(PROXY)
                t = f"{rh}:{rp}"
                rs.sendall(f"CONNECT {t} HTTP/1.1\r\nHost: {t}\r\n\r\n".encode())
                resp = b""
                while b"\r\n\r\n" not in resp:
                    chunk = rs.recv(4096)
                    if not chunk: break
                    resp += chunk
                if b"200" not in resp.split(b"\r\n")[0]:
                    cs.close(); rs.close(); continue
                hdr_end = resp.index(b"\r\n\r\n") + 4
                leftover = resp[hdr_end:]
                if leftover: cs.sendall(leftover)
                rs.settimeout(None)
                sel = selectors.DefaultSelector()
                sel.register(cs, selectors.EVENT_READ, "C")
                sel.register(rs, selectors.EVENT_READ, "R")
                try:
                    while not stop_evt.is_set():
                        evts = sel.select(timeout=2.0)
                        for k, _ in evts:
                            if k.data == "C":
                                d = cs.recv(65536)
                                if not d: raise StopIteration
                                rs.sendall(d)
                            else:
                                d = rs.recv(65536)
                                if not d: raise StopIteration
                                cs.sendall(d)
                except: pass
                finally: sel.close()
            except: pass
            finally:
                try: cs.close()
                except: pass
                try: rs.close()
                except: pass

    tt = threading.Thread(target=run_tunnel, daemon=True)
    tt.start()

    d = os.path.join(tempfile.gettempdir(), f"ctp_test_{label}") + os.sep
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d, f))

    api = CThostFtdcMdApi.CreateFtdcMdApi(d)
    spi = TracingSpi()
    api.RegisterSpi(spi)
    api.RegisterFront(f"tcp://127.0.0.1:{lp}")
    api.Init()
    jt = threading.Thread(target=api.Join, daemon=True)
    jt.start()

    for i in range(12):
        time.sleep(1)
        td = api.GetTradingDay()
        if td and td != "19800100":
            print(f"    TradingDay={td} at t={i+1}s", flush=True)
            break
    print(f"    Result: TD={api.GetTradingDay()}, events={spi.events}", flush=True)
    api.RegisterSpi(None)
    stop.set()
    srv.close()
    time.sleep(0.5)
