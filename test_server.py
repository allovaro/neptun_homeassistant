#!/usr/bin/env python3
"""A stand-in Neptun controller, for working on the integration without hardware.

It speaks the real framing and checksum rather than replaying one canned buffer,
so it is a genuine test of the client.  Valve and dry-mode writes are decoded
and show up in later status reads.

The fault-injection switches exist because the failures worth guarding against
are the ones that are awkward to reproduce on a real controller::

    --truncate        reply with half a frame, as happens when a response is
                      split across TCP segments
    --corrupt         reply with a well-formed frame carrying a bad checksum
    --hang N          ignore the first N requests
    --single-session  leave overlapping connections unanswered, which is what
                      the real controller does

Examples::

    ./test_server.py                        # healthy 4-line, 2-meter unit
    ./test_server.py --counters 4 --leak 3  # every meter set up, line 3 wet
    ./test_server.py --truncate             # a client must not read this as dry
"""
from __future__ import annotations

import argparse
import logging
import socketserver
import threading
import time

_LOGGER = logging.getLogger("neptun.mock")

REQ_WRITE = b"\x02TQW"
RESP_READ = b"\x02TAR"
RESP_ACK = b"\x02TA\x00"

HEADER_LEN = 6


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, spelled out here so the mock stays independent."""
    reg = 0xFFFF
    for byte in data:
        reg ^= byte << 8
        for _ in range(8):
            reg = ((reg << 1) ^ 0x1021) & 0xFFFF if reg & 0x8000 else (reg << 1) & 0xFFFF
    return reg


def frame(tag: bytes, payload: bytes = b"") -> bytes:
    """Wrap a payload into a complete frame."""
    body = tag + len(payload).to_bytes(2, "big") + payload
    return body + crc16(body).to_bytes(2, "big")


def tlv(tag: bytes, value: bytes) -> bytes:
    """Encode one TLV block."""
    return tag + len(value).to_bytes(2, "big") + value


class Controller:
    """The state a real controller would keep."""

    def __init__(self, args: argparse.Namespace) -> None:
        """Set up the simulated controller."""
        self.lock = threading.Lock()
        self.valves = True
        self.dry = False
        self.model = b"N3220"
        self.mac = b"60:C5:A8:75:51:35"
        self.lines = [False] * args.lines
        if args.leak and 1 <= args.leak <= len(self.lines):
            self.lines[args.leak - 1] = True
        # Configured meters carry a non-zero step; unused slots read as zero,
        # which is how the integration tells the two apart.
        readings = [174254, 66739, 12345, 6789]
        self.counters = [(readings[i], 10) for i in range(args.counters)]
        self.counters += [(0, 0)] * (4 - len(self.counters))
        self.wireless = bytes(args.wireless * 4)
        self.requests = 0

    @property
    def alarm(self) -> bool:
        """A leak on any line raises the alarm."""
        return any(self.lines)

    def status_payload(self) -> bytes:
        """Build the payload of a status response."""
        status = bytes([int(self.valves), 0, 0, int(self.dry), 0, 3, int(self.alarm)])
        counters = b"".join(
            value.to_bytes(4, "big") + bytes([step]) for value, step in self.counters
        )
        return (
            tlv(b"I", self.model)
            + tlv(b"M", self.mac)
            + tlv(b"A", b"\x00")
            + tlv(b"S", status)
            + tlv(b"s", self.wireless)
            + tlv(b"L", bytes(int(line) for line in self.lines))
            + tlv(b"C", counters)
            + tlv(b"D", str(int(time.time())).encode())
            + tlv(b"W", b"\x04")
        )

    def apply_write(self, payload: bytes) -> None:
        """Apply a write command to the stored state."""
        if len(payload) >= 5 and payload[0:1] == b"S":
            self.valves = bool(payload[3])
            self.dry = bool(payload[4])
            _LOGGER.info("write: valves=%s dry=%s", self.valves, self.dry)


class Handler(socketserver.BaseRequestHandler):
    """Serves one connection."""

    def handle(self) -> None:
        """Answer requests until the peer goes away."""
        controller: Controller = self.server.controller
        args: argparse.Namespace = self.server.args

        if args.single_session and not self.server.session.acquire(blocking=False):
            _LOGGER.info(
                "%s: a session is already open, going quiet", self.client_address[0]
            )
            time.sleep(args.timeout)
            return

        try:
            self.request.settimeout(args.timeout)
            while True:
                header = self._read_exact(HEADER_LEN)
                if header is None:
                    return
                length = int.from_bytes(header[4:6], "big")
                rest = self._read_exact(length + 2)
                if rest is None:
                    return

                with controller.lock:
                    controller.requests += 1
                    count = controller.requests

                if count <= args.hang:
                    _LOGGER.info("request %d: staying silent on purpose", count)
                    time.sleep(args.timeout)
                    continue

                if header[:4] == REQ_WRITE:
                    with controller.lock:
                        controller.apply_write(rest[:-2])
                    self.request.sendall(frame(RESP_ACK))
                    continue

                with controller.lock:
                    reply = frame(RESP_READ, controller.status_payload())

                if args.corrupt:
                    reply = reply[:-2] + b"\x00\x00"
                    _LOGGER.info("request %d: replying with a bad checksum", count)
                if args.truncate:
                    reply = reply[: len(reply) // 2]
                    _LOGGER.info("request %d: replying with half a frame", count)

                self.request.sendall(reply)
        except (TimeoutError, OSError) as err:
            _LOGGER.debug("%s: %s", self.client_address[0], err)
        finally:
            if args.single_session:
                self.server.session.release()

    def _read_exact(self, count: int) -> bytes | None:
        buffer = bytearray()
        while len(buffer) < count:
            chunk = self.request.recv(count - len(buffer))
            if not chunk:
                return None
            buffer.extend(chunk)
        return bytes(buffer)


class Server(socketserver.ThreadingTCPServer):
    """Threading server, so concurrent-client behaviour can be exercised."""

    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    """Run the mock controller."""
    parser = argparse.ArgumentParser(
        description="Simulate a Neptun ProW+ WiFi controller."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6350)
    parser.add_argument("--lines", type=int, default=4, help="wired leak inputs")
    parser.add_argument("--counters", type=int, default=2, help="configured meters")
    parser.add_argument(
        "--wireless", type=int, default=0, help="paired wireless sensors"
    )
    parser.add_argument("--leak", type=int, default=0, help="report a leak on this line")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--truncate", action="store_true", help="reply with half a frame"
    )
    parser.add_argument(
        "--corrupt", action="store_true", help="reply with a bad checksum"
    )
    parser.add_argument("--hang", type=int, default=0, help="ignore the first N requests")
    parser.add_argument(
        "--single-session",
        action="store_true",
        help="leave overlapping connections unanswered, like the real controller",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    server = Server((args.host, args.port), Handler)
    server.controller = Controller(args)
    server.args = args
    server.session = threading.Semaphore(1)

    _LOGGER.info(
        "listening on %s:%d (%d lines, %d meters, %d wireless)",
        args.host,
        args.port,
        args.lines,
        args.counters,
        args.wireless,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _LOGGER.info("shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
