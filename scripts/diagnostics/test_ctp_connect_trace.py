#!/usr/bin/env python3
"""Trace data flow between CTP and server via HTTP CONNECT tunnel."""
import sys, os, time, threading, tempfile, socket, selectors

sys.path.insert(0, '/Users/yunjinqi/Documents/new_projects/ctp-python')
from ctp import CThostFtdcMdApi, CThostFtdcMdSpi

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 15732
REMOTE_HOST = "182.254.243.31"
REMOTE_PORT = 40011

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

# Create a tracing tunnel
server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_sock.bind(("127.0.0.1", 0))
server_sock.listen(4)
local_port = server_sock.getsockname()[1]

stop = threading.Event()
total_client = [0]
total_remote = [0]

def trace_forward():
    server_sock.settimeout(1.0)
    while not stop.is_set():
        try:
            client_sock, _ = server_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # HTTP CONNECT
        remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote.settimeout(10)
        remote.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        remote.connect((PROXY_HOST, PROXY_PORT))
        target = f"{REMOTE_HOST}:{REMOTE_PORT}"
        remote.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = remote.recv(4096)
            if not chunk: break
            resp += chunk

        hdr_end = resp.index(b"\r\n\r\n") + 4
        leftover = resp[hdr_end:]
        status = resp[:hdr_end].split(b"\r\n")[0]
        print(f"  CONNECT: {status.decode()}, leftover={len(leftover)}b", flush=True)

        if leftover:
            print(f"  -> leftover to client: {leftover[:50]}", flush=True)
            client_sock.sendall(leftover)

        remote.settimeout(None)

        # Bidirectional forward with tracing
        sel = selectors.DefaultSelector()
        sel.register(client_sock, selectors.EVENT_READ, "C")
        sel.register(remote, selectors.EVENT_READ, "R")

        try:
            while not stop.is_set():
                events = sel.select(timeout=2.0)
                for key, mask in events:
                    if key.data == "C":
                        data = client_sock.recv(65536)
                        if not data:
                            print(f"  CLIENT EOF (total sent {total_client[0]}b)", flush=True)
                            raise StopIteration
                        total_client[0] += len(data)
                        print(f"  C->R: {len(data)}b (total {total_client[0]}b) first={data[:20].hex()}", flush=True)
                        remote.sendall(data)
                    elif key.data == "R":
                        data = remote.recv(65536)
                        if not data:
                            print(f"  REMOTE EOF (total recv {total_remote[0]}b)", flush=True)
                            raise StopIteration
                        total_remote[0] += len(data)
                        print(f"  R->C: {len(data)}b (total {total_remote[0]}b) first={data[:20].hex()}", flush=True)
                        client_sock.sendall(data)
        except (StopIteration, OSError) as e:
            print(f"  Forward ended: {e}", flush=True)
        finally:
            sel.close()
            client_sock.close()
            remote.close()

fwd = threading.Thread(target=trace_forward, daemon=True)
fwd.start()

# Connect CTP
d = os.path.join(tempfile.gettempdir(), "ctp_trace_test") + os.sep
os.makedirs(d, exist_ok=True)
for f in os.listdir(d): os.remove(os.path.join(d, f))

api = CThostFtdcMdApi.CreateFtdcMdApi(d)
spi = MySpi()
api.RegisterSpi(spi)
api.RegisterFront(f"tcp://127.0.0.1:{local_port}")
print(f"CTP -> 127.0.0.1:{local_port} -> CONNECT -> {REMOTE_HOST}:{REMOTE_PORT}", flush=True)
api.Init()
t = threading.Thread(target=api.Join, daemon=True)
t.start()

# Wait
for i in range(15):
    time.sleep(1)
    td = api.GetTradingDay()
    if td and td != "19800100":
        print(f"  TradingDay={td}!", flush=True)
        break

print(f"\nFinal: TradingDay={api.GetTradingDay()}, events={spi.events}", flush=True)
print(f"Total bytes: client->remote={total_client[0]}, remote->client={total_remote[0]}", flush=True)

stop.set()
api.RegisterSpi(None)
server_sock.close()
