#!/usr/bin/env python3
"""Exercise the client against the mock controller.

Run it directly; it starts a mock per case on its own port and needs neither
pytest nor hardware::

    ./test_client.py
"""
from __future__ import annotations

import concurrent.futures
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "neptun"))

from neptun_tcp import (  # noqa: E402
    NeptunClient,
    NeptunConnectionError,
    NeptunProtocolError,
    build_frame,
)

MOCK = Path(__file__).parent / "test_server.py"
PORT = 16350
_failures: list[str] = []


class Mock:
    """Runs test_server.py on its own port for the duration of a test."""

    def __init__(self, *flags: str) -> None:
        global PORT
        PORT += 1
        self.port = PORT
        self.flags = flags

    def __enter__(self) -> int:
        self.proc = subprocess.Popen(
            [sys.executable, str(MOCK), "--port", str(self.port), *self.flags],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                NeptunClient("127.0.0.1", self.port, timeout=1, retries=1).get_status()
                break
            except Exception:
                time.sleep(0.05)
        return self.port

    def __exit__(self, *exc: object) -> None:
        self.proc.terminate()
        self.proc.wait(timeout=5)


def check(name: str, passed: bool, detail: str = "") -> None:
    """Record and print one result."""
    print(f"  {'PASS' if passed else 'FAIL'}  {name}{f'  -- {detail}' if detail else ''}")
    if not passed:
        _failures.append(name)


def test_frames() -> None:
    """The builder must reproduce the constants the old client hardcoded."""
    print("\nframe encoding")
    known = {
        "0254515200002a45": (b"\x02TQR", b""),
        "025451570007530004010100037b35": (b"\x02TQW", bytes([0x53, 0, 4, 1, 1, 0, 3])),
        "025451570007530004010000034c05": (b"\x02TQW", bytes([0x53, 0, 4, 1, 0, 0, 3])),
        "025451570007530004000000033ab1": (b"\x02TQW", bytes([0x53, 0, 4, 0, 0, 0, 3])),
    }
    for expected, (tag, payload) in known.items():
        got = build_frame(tag, payload).hex()
        check(f"builds {expected[:12]}...", got == expected, f"got {got}")


def test_healthy() -> None:
    """A well-behaved controller decodes into the expected entities."""
    print("\nhealthy controller")
    with Mock("--counters", "2", "--lines", "4") as port:
        status = NeptunClient("127.0.0.1", port).get_status()
    check("model decoded", status.model == "N3220", status.model or "")
    check("mac decoded", status.mac == "60:C5:A8:75:51:35", status.mac or "")
    check("four wired lines", len(status.lines) == 4, str(len(status.lines)))
    check("no leak reported", not any(status.lines) and not status.alarm)
    configured = [c for c in status.counters if c.step]
    check("two meters configured", len(configured) == 2, str(len(configured)))
    check(
        "reading in m3",
        configured and configured[0].cubic_metres == 174.254,
        str(configured[0].cubic_metres if configured else None),
    )


def test_counter_autodetect() -> None:
    """Unused meter slots are distinguishable from meters reading zero."""
    print("\nmeter auto-detection")
    for wanted in (0, 1, 2, 4):
        with Mock("--counters", str(wanted)) as port:
            status = NeptunClient("127.0.0.1", port).get_status()
        configured = [c for c in status.counters if c.step]
        check(f"{wanted} configured meter(s) found", len(configured) == wanted,
              str(len(configured)))


def test_leak() -> None:
    """A wet line must surface on that line and raise the alarm."""
    print("\nleak reporting")
    with Mock("--leak", "3") as port:
        status = NeptunClient("127.0.0.1", port).get_status()
    check("line 3 wet", status.lines[2] is True)
    check("other lines dry", not status.lines[0] and not status.lines[1])
    check("alarm raised", status.alarm is True)


def test_truncated_frame() -> None:
    """A half-delivered frame must fail loudly, never decode as "no leak"."""
    print("\ntruncated response")
    with Mock("--truncate") as port:
        client = NeptunClient("127.0.0.1", port, timeout=2, retries=1)
        try:
            status = client.get_status()
        except (NeptunConnectionError, NeptunProtocolError) as err:
            check("raises instead of guessing", True, type(err).__name__)
        else:
            check(
                "raises instead of guessing",
                False,
                f"decoded lines={status.lines} alarm={status.alarm}",
            )


def test_corrupt_frame() -> None:
    """A bad checksum must be rejected."""
    print("\ncorrupted response")
    with Mock("--corrupt") as port:
        client = NeptunClient("127.0.0.1", port, timeout=2, retries=1)
        try:
            client.get_status()
        except NeptunProtocolError as err:
            check("checksum verified", "checksum" in str(err), str(err))
        else:
            check("checksum verified", False, "accepted a corrupt frame")


def test_retry() -> None:
    """Transient silence must be retried, not reported as a missing device."""
    print("\ntransient failure")
    with Mock("--hang", "2", "--timeout", "1") as port:
        client = NeptunClient("127.0.0.1", port, timeout=1.5, retries=4)
        try:
            client.get_status()
            check("recovers after 2 dropped requests", True)
        except Exception as err:
            check("recovers after 2 dropped requests", False, f"{type(err).__name__}: {err}")


def test_serialised_access() -> None:
    """Concurrent callers must queue rather than collide."""
    print("\nconcurrent access against a single-session controller")
    with Mock("--single-session", "--timeout", "2") as port:
        client = NeptunClient("127.0.0.1", port, timeout=3, retries=3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
            futures = [pool.submit(client.get_status) for _ in range(9)]
            results = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as err:  # noqa: BLE001
                    results.append(err)
    good = sum(1 for r in results if not isinstance(r, Exception))
    check("all 9 concurrent reads succeed", good == 9, f"{good}/9")


def test_dry_mode_keeps_valves() -> None:
    """Enabling dry mode must not fling the valves open.

    The old client sent one canned frame for "dry on" that also carried
    valves=1, so turning on cleaning mode opened the water.
    """
    print("\ndry mode does not disturb the valves")
    with Mock() as port:
        client = NeptunClient("127.0.0.1", port)
        client.set_state(valves_open=False, dry_mode=False)
        before = client.get_status()
        check("valves closed to start", before.valves_open is False)

        # What the switch entity does: keep the valve state, change only dry.
        client.set_state(valves_open=before.valves_open, dry_mode=True)
        after = client.get_status()
        check("dry mode on", after.dry_mode is True)
        check("valves still closed", after.valves_open is False,
              f"valves_open={after.valves_open}")


def test_valve_control() -> None:
    """Every valve/dry combination must round-trip."""
    print("\nvalve and dry combinations")
    with Mock() as port:
        client = NeptunClient("127.0.0.1", port)
        for valves in (True, False):
            for dry in (True, False):
                client.set_state(valves_open=valves, dry_mode=dry)
                status = client.get_status()
                check(
                    f"valves={valves} dry={dry}",
                    status.valves_open is valves and status.dry_mode is dry,
                    f"got valves={status.valves_open} dry={status.dry_mode}",
                )


def main() -> int:
    """Run every case and report."""
    test_frames()
    test_healthy()
    test_counter_autodetect()
    test_leak()
    test_truncated_frame()
    test_corrupt_frame()
    test_retry()
    test_serialised_access()
    test_dry_mode_keeps_valves()
    test_valve_control()

    print()
    if _failures:
        print(f"{len(_failures)} failed: {', '.join(_failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
