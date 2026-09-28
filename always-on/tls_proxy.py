#!/usr/bin/env python3
"""tls_proxy — tiny HTTPS front for the ttyd web terminal (WebSocket-safe byte pump).

Why: browsers only allow clipboard access etc. in a "secure context", and a phone
browser on your VPN is happier with https. ttyd itself can do TLS, but a separate
front lets you use one cert for several local services later.

Robustness rules (each one fixed a real outage):
  * the TLS handshake runs in a WORKER thread with a timeout — done in the accept
    loop, one phone that drops mid-handshake freezes every other connection
  * backend connect has its own timeout
  * after the upgrade, pumps have no read timeout (terminals idle for hours) but
    TCP keepalive on both sides reaps dead peers; an overall idle cap is optional

Env: BIND_ADDR, TLS_PORT (7683), TTYD_HOST (BIND_ADDR), TTYD_PORT (7681),
     TLS_CERT / TLS_KEY (default $AGENT_HOME/state/tls/server.{crt,key}),
     TLS_HANDSHAKE_TIMEOUT (15), TLS_IDLE_TIMEOUT (0 = none, seconds)
"""
import os, select, socket, ssl, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import agentlib as A

BIND = A.env("BIND_ADDR", "127.0.0.1")
PORT = A.env_int("TLS_PORT", 7683)
UP_HOST = A.env("TTYD_HOST", BIND)
UP_PORT = A.env_int("TTYD_PORT", 7681)
CERT = A.env("TLS_CERT", os.path.join(A.STATE, "tls", "server.crt"))
KEY = A.env("TLS_KEY", os.path.join(A.STATE, "tls", "server.key"))
HS_TIMEOUT = A.env_float("TLS_HANDSHAKE_TIMEOUT", 15)
IDLE = A.env_float("TLS_IDLE_TIMEOUT", 0)
BUF = 65536


def keepalive(s):
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, val in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 20), ("TCP_KEEPCNT", 4)):
            if hasattr(socket, opt):
                s.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
    except OSError:
        pass


def pump(a, b):
    """Splice bytes both ways until either side closes (or the idle cap passes)."""
    socks = [a, b]
    try:
        while True:
            r, _, _ = select.select(socks, [], [], IDLE or None)
            if not r:
                return  # idle cap reached
            for s in r:
                # SSL sockets may hold buffered plaintext beyond what select() sees
                data = s.recv(BUF)
                if not data:
                    return
                (b if s is a else a).sendall(data)
                while isinstance(s, ssl.SSLSocket) and s.pending():
                    more = s.recv(BUF)
                    if not more:
                        return
                    (b if s is a else a).sendall(more)
    except (OSError, ssl.SSLError):
        return
    finally:
        for s in socks:
            try:
                s.close()
            except OSError:
                pass


def handle(ctx, raw):
    try:
        raw.settimeout(HS_TIMEOUT)
        client = ctx.wrap_socket(raw, server_side=True)
    except (OSError, ssl.SSLError):
        raw.close()
        return
    try:
        up = socket.create_connection((UP_HOST, UP_PORT), timeout=10)
    except OSError:
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        finally:
            client.close()
        return
    for s in (client, up):
        s.settimeout(None)
        keepalive(s)
    pump(client, up)


def main():
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, KEY)
    srv = socket.socket(socket.AF_INET6 if ":" in BIND else socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((BIND, PORT))
    srv.listen(64)
    print(f"tls_proxy {BIND}:{PORT} -> {UP_HOST}:{UP_PORT}", flush=True)
    while True:
        raw, _ = srv.accept()
        threading.Thread(target=handle, args=(ctx, raw), daemon=True).start()


if __name__ == "__main__":
    main()
