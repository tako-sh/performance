#!/usr/bin/env python3
import json
import socket
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: takoctl.py /path/to/tako.sock", file=sys.stderr)
        return 2
    command = json.load(sys.stdin)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(sys.argv[1])
    sock.sendall(json.dumps(command, separators=(",", ":")).encode() + b"\n")
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    if not buf:
        print("no response", file=sys.stderr)
        return 1
    sys.stdout.write(buf.decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

