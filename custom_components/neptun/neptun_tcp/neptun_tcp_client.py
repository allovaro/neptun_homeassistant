"""Client for the Neptun water leak protection controller.

Wire format
-----------
Every frame, in both directions, looks like::

    02 'T' <dir> <op> <length:u16be> <payload> <crc:u16be>

``dir`` is ``Q`` for a request and ``A`` for an answer, ``op`` is ``R`` for a
status read and ``W`` for a write.  ``length`` covers the payload only.  The
trailing checksum is CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no
reflection, no final xor) over every preceding byte of the frame.

The payload is a sequence of TLV blocks::

    <tag:1> <length:u16be> <value:length>

Tags seen on an N3220 controller::

    'I'  model string, e.g. "N3220"
    'M'  MAC address as ASCII, e.g. "60:C5:A8:75:51:35"
    'A'  one byte, purpose unknown
    'S'  system status, see the _ST_* offsets below
    's'  wireless sensors, empty while none are paired
    'L'  wired leak lines, one byte per line
    'C'  counters, five bytes each: u32be litres + step
    'D'  controller clock as an ASCII unix timestamp
    'W'  one byte, purpose unknown

The controller serves a single session at a time.  Concurrent connections are
accepted but left unanswered until they time out, so every exchange is
serialised through a lock and separated by a short cool-down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import socket
import threading
import time

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 6350
DEFAULT_TIMEOUT = 5.0
DEFAULT_RETRIES = 3

_MAGIC = 0x02
_HEADER_LEN = 6
_CRC_LEN = 2
_MAX_PAYLOAD = 4096

# The controller is documented to hang when polled harder than once every few
# seconds, so exchanges are spaced out and retries back off rather than
# hammering a device that is already struggling.
_MIN_INTERVAL = 1.0
_RETRY_BACKOFF = 1.0

_REQ_READ = b"\x02TQR"
_REQ_WRITE = b"\x02TQW"

_TAG_MODEL = 0x49       # 'I'
_TAG_MAC = 0x4D         # 'M'
_TAG_STATUS = 0x53      # 'S'
_TAG_WIRELESS = 0x73    # 's'
_TAG_LINES = 0x4C       # 'L'
_TAG_COUNTERS = 0x43    # 'C'
_TAG_CLOCK = 0x44       # 'D'

# Byte offsets inside the 'S' status block.
_ST_VALVES = 0
_ST_DRY = 3
_ST_ALARM = 6

_COUNTER_RECORD = 5
_DEFAULT_WIRELESS_RECORD = 4


class NeptunError(Exception):
    """Base error for all Neptun failures."""


class NeptunConnectionError(NeptunError):
    """The controller could not be reached, or went silent mid-exchange."""


class NeptunProtocolError(NeptunError):
    """The controller answered with something we cannot make sense of."""


def crc16(data: bytes) -> int:
    """Return the CRC-16/CCITT-FALSE checksum of ``data``."""
    reg = 0xFFFF
    for byte in data:
        reg ^= byte << 8
        for _ in range(8):
            if reg & 0x8000:
                reg = ((reg << 1) ^ 0x1021) & 0xFFFF
            else:
                reg = (reg << 1) & 0xFFFF
    return reg


def build_frame(tag: bytes, payload: bytes = b"") -> bytes:
    """Wrap ``payload`` into a complete frame addressed with ``tag``."""
    body = tag + len(payload).to_bytes(2, "big") + payload
    return body + crc16(body).to_bytes(2, "big")


def split_tlv(payload: bytes) -> dict[int, bytes]:
    """Split a payload into its TLV blocks, keyed by tag."""
    blocks: dict[int, bytes] = {}
    pos = 0
    while pos + 3 <= len(payload):
        tag = payload[pos]
        length = int.from_bytes(payload[pos + 1 : pos + 3], "big")
        end = pos + 3 + length
        if end > len(payload):
            raise NeptunProtocolError(
                f"TLV block {tag:#04x} claims {length} bytes but only "
                f"{len(payload) - pos - 3} are left"
            )
        blocks[tag] = payload[pos + 3 : end]
        pos = end
    return blocks


@dataclass
class Counter:
    """A single water meter slot reported by the controller."""

    index: int
    litres: int
    step: int

    @property
    def cubic_metres(self) -> float:
        """Return the reading in m³, the unit the controller counts in."""
        return round(self.litres / 1000, 3)


@dataclass
class WirelessSensor:
    """A paired wireless sensor.

    The controller reports these in the 's' block, which stays empty until
    sensors are paired.  The record layout below is therefore inferred rather
    than observed; the raw bytes are kept so it can be confirmed against real
    hardware without another protocol dig.
    """

    index: int
    raw: bytes

    @property
    def alarm(self) -> bool:
        """Return True while this sensor reports a leak."""
        return bool(self.raw[0]) if self.raw else False

    @property
    def battery(self) -> int | None:
        """Return the battery level, if the record carries one."""
        return self.raw[1] if len(self.raw) > 1 else None

    @property
    def signal(self) -> int | None:
        """Return the link quality, if the record carries one."""
        return self.raw[2] if len(self.raw) > 2 else None


@dataclass
class NeptunStatus:
    """Decoded controller status."""

    model: str | None = None
    mac: str | None = None
    valves_open: bool = False
    dry_mode: bool = False
    alarm: bool = False
    lines: list[bool] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    wireless: list[WirelessSensor] = field(default_factory=list)
    raw_blocks: dict[int, bytes] = field(default_factory=dict)


class NeptunClient:
    """Talks to one controller, one request at a time."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        wireless_record_size: int = _DEFAULT_WIRELESS_RECORD,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = max(1, retries)
        self.wireless_record_size = max(1, wireless_record_size)
        self._lock = threading.Lock()
        self._last_exchange = 0.0
        self._logged_wireless = False

    def get_status(self) -> NeptunStatus:
        """Poll the controller and return its decoded state."""
        return self._decode(self._transact(build_frame(_REQ_READ)))

    def set_state(self, valves_open: bool, dry_mode: bool) -> None:
        """Set valve position and dry mode.

        Both flags travel in one frame, so callers must pass the full desired
        state rather than only the field they mean to change.
        """
        body = bytes(
            [_TAG_STATUS, 0x00, 0x04, int(valves_open), int(dry_mode), 0x00, 0x03]
        )
        self._transact(build_frame(_REQ_WRITE, body))

    def _decode(self, payload: bytes) -> NeptunStatus:
        blocks = split_tlv(payload)
        status = NeptunStatus(raw_blocks=blocks)

        if (model := blocks.get(_TAG_MODEL)) is not None:
            status.model = model.decode("ascii", "replace").strip("\x00") or None
        if (mac := blocks.get(_TAG_MAC)) is not None:
            status.mac = mac.decode("ascii", "replace").strip("\x00") or None

        state = blocks.get(_TAG_STATUS, b"")
        if len(state) <= _ST_ALARM:
            raise NeptunProtocolError(
                f"status block is {len(state)} bytes, expected at least "
                f"{_ST_ALARM + 1}"
            )
        status.valves_open = bool(state[_ST_VALVES])
        status.dry_mode = bool(state[_ST_DRY])
        status.alarm = bool(state[_ST_ALARM])

        status.lines = [bool(byte) for byte in blocks.get(_TAG_LINES, b"")]

        counters = blocks.get(_TAG_COUNTERS, b"")
        for index in range(len(counters) // _COUNTER_RECORD):
            record = counters[index * _COUNTER_RECORD : (index + 1) * _COUNTER_RECORD]
            status.counters.append(
                Counter(
                    index=index + 1,
                    litres=int.from_bytes(record[:4], "big"),
                    step=record[4],
                )
            )

        status.wireless = self._decode_wireless(blocks.get(_TAG_WIRELESS, b""))
        return status

    def _decode_wireless(self, block: bytes) -> list[WirelessSensor]:
        if not block:
            return []
        if not self._logged_wireless:
            self._logged_wireless = True
            _LOGGER.info(
                "Neptun %s reported %d bytes of wireless sensor data: %s. The "
                "record layout is inferred; if the resulting entities look wrong, "
                "this dump is what is needed to decode it properly",
                self.host,
                len(block),
                block.hex(" "),
            )
        size = self.wireless_record_size
        return [
            WirelessSensor(index=i + 1, raw=block[i * size : (i + 1) * size])
            for i in range(len(block) // size)
        ]

    def _transact(self, frame: bytes) -> bytes:
        """Run one exchange, retrying transient failures, never concurrently."""
        with self._lock:
            since = time.monotonic() - self._last_exchange
            if since < _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL - since)
            try:
                last_error: NeptunError | None = None
                for attempt in range(1, self.retries + 1):
                    try:
                        return self._exchange(frame)
                    except NeptunError as err:
                        last_error = err
                        _LOGGER.debug(
                            "Neptun %s: attempt %d/%d failed: %s",
                            self.host,
                            attempt,
                            self.retries,
                            err,
                        )
                        if attempt < self.retries:
                            time.sleep(_RETRY_BACKOFF * attempt)
                raise last_error  # type: ignore[misc]
            finally:
                self._last_exchange = time.monotonic()

    def _exchange(self, frame: bytes) -> bytes:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(frame)
            header = self._recv_exact(sock, _HEADER_LEN)
            if header[0] != _MAGIC or header[1:2] != b"T":
                raise NeptunProtocolError(f"unexpected frame header {header.hex()}")
            length = int.from_bytes(header[4:6], "big")
            if length > _MAX_PAYLOAD:
                raise NeptunProtocolError(f"frame claims an absurd length of {length}")
            rest = self._recv_exact(sock, length + _CRC_LEN)
        except NeptunError:
            raise
        except (TimeoutError, OSError) as err:
            raise NeptunConnectionError(f"{self.host}:{self.port}: {err}") from err
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

        expected = int.from_bytes(rest[-_CRC_LEN:], "big")
        actual = crc16(header + rest[:-_CRC_LEN])
        if expected != actual:
            raise NeptunProtocolError(
                f"checksum mismatch: frame says {expected:#06x}, computed {actual:#06x}"
            )
        return rest[:-_CRC_LEN]

    @staticmethod
    def _recv_exact(sock: socket.socket, count: int) -> bytes:
        """Read exactly ``count`` bytes, or fail.

        A plain recv() returns whatever has arrived so far, which is what let
        the previous implementation decode truncated frames as "no leak".
        """
        buffer = bytearray()
        while len(buffer) < count:
            chunk = sock.recv(count - len(buffer))
            if not chunk:
                raise NeptunConnectionError(
                    f"connection closed after {len(buffer)} of {count} bytes"
                )
            buffer.extend(chunk)
        return bytes(buffer)


# The previous class name, kept so direct importers keep working.
NeptunTcp = NeptunClient
