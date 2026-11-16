#!/usr/bin/env python3
"""Run one command on the VM's console (dev/haos/console.sock) and print the output.

    python3 dev/console.py 'ha supervisor info'
"""
import pathlib
import socket
import sys
import time

sock = socket.socket(socket.AF_UNIX)
sock.connect(str(pathlib.Path(__file__).parent / "haos" / "console.sock"))
sock.settimeout(1)


def read(seconds):
    data = b""
    end = time.time() + seconds
    while time.time() < end:
        try:
            data += sock.recv(65536)
        except socket.timeout:
            pass
    return data.decode(errors="replace")


sock.send(b"\n")
text = read(2)
if "login:" in text.splitlines()[-1:][0] if text.strip() else False:
    sock.send(b"root\n")
    read(3)
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 8
sock.send(sys.argv[1].encode() + b"\n")
print(read(wait).replace("\r", ""))
