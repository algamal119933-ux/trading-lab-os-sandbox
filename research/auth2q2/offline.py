#!/usr/bin/env python3
"""The science phase runs with the network removed (review section 3, stages 5 and 6).

    python -m auth2q2.offline probe [--out FILE]

Two layers, so neither has to be trusted alone:

  outside   the workflow runs the science step in a new network namespace (``sudo unshare --net``), dropped back
            to the runner's own user, where only a loopback device exists. ``probe`` is run first inside that
            namespace and passes only if no name resolves and no address can be reached; a probe that reaches
            anything fails the step before any science starts.
  inside    ``guard()`` replaces the socket module's calls in this Python process (connect, connect_ex,
            sendto and sendmsg on socket.socket; create_connection and the name lookups) with refusals and
            records every attempt. It is a second layer, not a sandbox: code that calls the C-level _socket
            type directly is not seen by it, and the namespace is what removes the network.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

PROBE_HOSTS = ("github.com", "data.binance.vision", "s3-ap-northeast-1.amazonaws.com")
PROBE_ADDRESSES = (("1.1.1.1", 443), ("8.8.8.8", 53), ("140.82.112.3", 443))
PROBE_TIMEOUT = 3.0


GUARDED_METHODS = ("connect", "connect_ex", "sendto", "sendmsg")
GUARDED_FUNCTIONS = ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr",
                     "getnameinfo")


class NetworkRemoved(BaseException):
    """A socket call in the science phase. BaseException, so no ``except Exception`` retry loop (archive._get
    retries every Exception) can swallow it: the attempt is final."""


def probe(timeout: float = PROBE_TIMEOUT) -> dict:
    """Try to resolve each probe host and to connect to each probe address. NETWORK_REMOVED only if every one
    fails."""
    out: dict = {"dns": {}, "tcp": {}}
    for host in PROBE_HOSTS:
        try:
            got = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            out["dns"][host] = f"RESOLVED {sorted({g[4][0] for g in got})[:3]}"
        except OSError as exc:
            out["dns"][host] = f"refused: {type(exc).__name__}: {exc}"[:160]
    for ip, port in PROBE_ADDRESSES:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                out["tcp"][f"{ip}:{port}"] = "CONNECTED"
        except OSError as exc:
            out["tcp"][f"{ip}:{port}"] = f"refused: {type(exc).__name__}: {exc}"[:160]
    reached = [k for k, v in {**out["dns"], **out["tcp"]}.items() if not v.startswith("refused")]
    out["reached"] = reached
    out["network_removed"] = not reached
    return out


@contextmanager
def guard(log: list | None = None):
    """Refuse the socket module's connections, datagram sends and name lookups in this process while the
    context is open (GUARDED_METHODS, GUARDED_FUNCTIONS)."""
    log = log if log is not None else []
    lock = threading.Lock()
    methods = {name: socket.socket.__dict__.get(name) for name in GUARDED_METHODS}
    functions = {name: getattr(socket, name) for name in GUARDED_FUNCTIONS}

    def refuse(what: str, method: bool):
        def _refused(*args, **kwargs):
            target = (args[-1] if what.startswith("socket.send") else args[1]) if method and len(args) > 1 \
                else (args[0] if args else None)
            with lock:
                log.append(f"{what} {str(target)[:120]}")
            raise NetworkRemoved(f"{what} {target!r}: the network is removed in the science phase")
        return _refused

    for name in methods:
        setattr(socket.socket, name, refuse(f"socket.{name}", True))
    for name in functions:
        setattr(socket, name, refuse(name, False))
    try:
        yield log
    finally:
        for name, original in methods.items():
            if original is None:
                delattr(socket.socket, name)  # inherited from _socket.socket: leave no override behind
            else:
                setattr(socket.socket, name, original)
        for name, original in functions.items():
            setattr(socket, name, original)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--out")
    a = ap.parse_args(argv)
    rec = probe()
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(body)
    print(body, end="")
    if not rec["network_removed"]:
        print(f"::error::NETWORK_REMOVED = FAIL: reached {rec['reached']}")
        return 3
    print("NETWORK_REMOVED = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
