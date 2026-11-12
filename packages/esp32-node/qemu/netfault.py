#!/usr/bin/env python3
"""Network fault injection for QEMU devices through Toxiproxy.

Every QEMU device reaches the broker through its own Toxiproxy proxy, so a
fault on one proxy affects exactly one device, the way a bad uplink would.

  netfault.py list
  netfault.py blackhole PROXY             # drop all traffic until cleared
  netfault.py latency PROXY MS [JITTER]   # delay broker -> device traffic
  netfault.py reset PROXY [HOLD_S]        # RST the device's connection on its next packet
  netfault.py clear PROXY
  netfault.py schedule PROXY EVERY_S DURATION_S   # recurring outage, runs forever
  netfault.py resets PROXY EVERY_S [HOLD_S]       # recurring peer resets, runs forever
  netfault.py apply PROXY SPEC            # SPEC from NETWORK_FAULT, see below

NETWORK_FAULT specs: "outage:every=600,duration=70", "latency:ms=8000,jitter=4000",
"reset:every=240,hold=12".

Toxiproxy's reset_peer swallows the packet that triggers it and sends a TCP RST
instead, so it is only ever installed briefly: for HOLD_S seconds the device's
next packet (a publish or PINGREQ, and any reconnect attempt) is answered with a
reset, after which traffic flows normally again.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("TOXIPROXY_URL", "http://toxiproxy:8474").rstrip("/")
TOXIC_PREFIX = "netfault"


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        # Removing a toxic waits for its in-flight packet, so allow more than a GET needs.
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if method == "DELETE" and error.code == 404:
            return None
        raise SystemExit(f"netfault: {method} {path} -> {error.code} {error.read().decode()}")
    except OSError as error:  # URLError, timeouts, refused connections
        raise SystemExit(f"netfault: {method} {path} failed: {error}")


def clear(proxy: str) -> None:
    for toxic in call("GET", f"/proxies/{proxy}/toxics") or []:
        if toxic["name"].startswith(TOXIC_PREFIX):
            call("DELETE", f"/proxies/{proxy}/toxics/{toxic['name']}")


def add(proxy: str, kind: str, attributes: dict, streams=("downstream",)) -> None:
    for stream in streams:
        call("POST", f"/proxies/{proxy}/toxics", {
            "name": f"{TOXIC_PREFIX}_{kind}_{stream}",
            "type": kind,
            "stream": stream,
            "toxicity": 1.0,
            "attributes": attributes,
        })


def blackhole(proxy: str) -> None:
    clear(proxy)
    add(proxy, "timeout", {"timeout": 0}, ("upstream", "downstream"))


def wait_for_api() -> None:
    for _ in range(30):
        try:
            call("GET", "/version")
            return
        except (OSError, SystemExit):
            time.sleep(1)
    raise SystemExit(f"netfault: Toxiproxy API {API} not reachable")


def reset(proxy: str, hold: int) -> None:
    clear(proxy)
    try:
        add(proxy, "reset_peer", {"timeout": 0}, ("upstream",))
        time.sleep(hold)
    finally:
        clear(proxy)


def recurring(label: str, episode) -> None:
    """Runs one fault episode; a Toxiproxy hiccup is logged and the schedule goes on."""
    try:
        episode()
    except SystemExit as error:
        print(f"{error} (during {label}, will retry next cycle)", file=sys.stderr, flush=True)


def resets(proxy: str, every: int, hold: int) -> None:
    wait_for_api()
    print(f"netfault: {proxy} peer resets every {every}s (held {hold}s)", flush=True)
    while True:
        time.sleep(max(every - hold, 1))
        print(f"netfault: {proxy} peer resetting connections", flush=True)
        recurring("reset", lambda: reset(proxy, hold))


def schedule(proxy: str, every: int, duration: int) -> None:
    wait_for_api()
    print(f"netfault: {proxy} outage of {duration}s every {every}s", flush=True)

    def outage() -> None:
        try:
            blackhole(proxy)
            time.sleep(duration)
        finally:
            clear(proxy)

    while True:
        time.sleep(max(every - duration, 1))
        print(f"netfault: {proxy} uplink down", flush=True)
        recurring("outage", outage)
        print(f"netfault: {proxy} uplink restored", flush=True)


def parse_spec(spec: str) -> tuple[str, dict[str, int]]:
    kind, _, rest = spec.partition(":")
    options = {}
    for pair in filter(None, rest.split(",")):
        key, _, value = pair.partition("=")
        options[key.strip()] = int(value)
    return kind.strip(), options


def apply(proxy: str, spec: str) -> None:
    kind, options = parse_spec(spec)
    wait_for_api()
    clear(proxy)
    if kind == "outage":
        schedule(proxy, options.get("every", 600), options.get("duration", 70))
    elif kind == "latency":
        add(proxy, "latency", {"latency": options.get("ms", 5000), "jitter": options.get("jitter", 0)})
    elif kind == "reset":
        resets(proxy, options.get("every", 240), options.get("hold", 12))
    else:
        raise SystemExit(f"netfault: unknown NETWORK_FAULT kind {kind!r}")
    print(f"netfault: {proxy} {spec} applied", flush=True)


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    command, args = argv[0], argv[1:]
    if command == "list":
        print(json.dumps(call("GET", "/proxies"), indent=2, ensure_ascii=False))
    elif command == "blackhole" and len(args) == 1:
        blackhole(args[0])
    elif command == "latency" and len(args) in (2, 3):
        clear(args[0])
        add(args[0], "latency", {"latency": int(args[1]), "jitter": int(args[2]) if len(args) == 3 else 0})
    elif command == "reset" and len(args) in (1, 2):
        reset(args[0], int(args[1]) if len(args) == 2 else 12)
    elif command == "resets" and len(args) in (2, 3):
        resets(args[0], int(args[1]), int(args[2]) if len(args) == 3 else 12)
    elif command == "clear" and len(args) == 1:
        clear(args[0])
    elif command == "schedule" and len(args) == 3:
        schedule(args[0], int(args[1]), int(args[2]))
    elif command == "apply" and len(args) == 2:
        apply(args[0], args[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
