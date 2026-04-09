#!/usr/bin/env python3
"""Test if the CTP tunnel actually forwards data correctly."""
import sys, os, socket, struct, subprocess, time, threading

sys.path.insert(0, 'src/backend')
import logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')

# Step 1: Test direct TCP to CTP server (without tunnel)
print("=== Step 1: Direct TCP to 182.254.243.31:40011 ===", flush=True)
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(("182.254.243.31", 40011))
    print(f"  Connected! Local: {s.getsockname()}", flush=True)
    # Wait for data from server
    s.settimeout(3)
    try:
        data = s.recv(4096)
        print(f"  Received {len(data)} bytes: {data[:100]}", flush=True)
    except socket.timeout:
        print(f"  No data received in 3s (proxy intercepts?)", flush=True)
    s.close()
except Exception as e:
    print(f"  Error: {e}", flush=True)

# Step 2: Test with IP_BOUND_IF
print("\n=== Step 2: Direct TCP with IP_BOUND_IF to en0 ===", flush=True)
try:
    iface_idx = socket.if_nametoindex("en0")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    IP_BOUND_IF = 25
    s.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, struct.pack("I", iface_idx))
    s.connect(("182.254.243.31", 40011))
    print(f"  Connected with IF binding! Local: {s.getsockname()}", flush=True)
    s.settimeout(3)
    try:
        data = s.recv(4096)
        print(f"  Received {len(data)} bytes: {data[:100]}", flush=True)
    except socket.timeout:
        print(f"  No data received in 3s", flush=True)
    s.close()
except Exception as e:
    print(f"  Error: {e}", flush=True)

# Step 3: Test tunnel
print("\n=== Step 3: Through CTP tunnel ===", flush=True)
from app.services.ctp_tunnel import ensure_tunnel, stop_all_tunnels
local_port = ensure_tunnel("182.254.243.31", 40011)
time.sleep(0.5)
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(("127.0.0.1", local_port))
    print(f"  Connected to tunnel! Local: {s.getsockname()}", flush=True)
    s.settimeout(3)
    try:
        data = s.recv(4096)
        print(f"  Received {len(data)} bytes: {data[:100]}", flush=True)
    except socket.timeout:
        print(f"  No data received in 3s", flush=True)
    s.close()
except Exception as e:
    print(f"  Error: {e}", flush=True)
stop_all_tunnels()
