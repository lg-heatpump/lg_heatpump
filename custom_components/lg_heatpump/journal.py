"""A short, always-on record of what the integration asked the unit and what came back.

Home Assistant's debug log has to be switched on before a fault, and on a busy
installation its buffer turns over within hours. This journal costs nothing to
leave on and is part of the diagnostics download, so a fault can be looked at
after the fact.

Three bounded buffers, newest last:

* ``requests``: every Modbus request, with function, address, count, duration and
  outcome. Values read are left out (the diagnostics carry a raw dump); values
  written are kept.
* ``polls``: one line per poll of the measurements or the settings, with its
  duration and which sub-systems failed, and why.
* ``events``: the rare things worth keeping longer than the polls: setups,
  sub-systems failing and coming back, timeouts, link errors and writes.

The journal lives in memory, in the entry's runtime data: a reload of the entry
or a restart of Home Assistant starts it afresh.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING, Any

from modbus_connection import ModbusTimeoutError

from homeassistant.util.dt import utcnow

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping


MAX_REQUESTS = 2000
MAX_POLLS = 1000
MAX_EVENTS = 300

#: Requests of the ``ModbusUnit`` protocol that are recorded: the plain data
#: accesses, which are all the device library sends.
RECORDED_REQUESTS = frozenset(
    {
        "read_coils",
        "read_discrete_inputs",
        "read_holding_registers",
        "read_input_registers",
        "write_coil",
        "write_coils",
        "write_register",
        "write_registers",
        "mask_write_register",
    }
)

#: Requests of the protocol passed on without a record; the device library sends
#: none of them. A test keeps both sets in step with the protocol.
UNRECORDED_REQUESTS = frozenset(
    {
        "read_device_identification",
        "read_exception_status",
        "read_fifo_queue",
        "read_file_record",
        "read_write_registers",
        "write_file_record",
    }
)


def _now() -> str:
    return utcnow().isoformat(timespec="milliseconds")


def outcome_of(error: BaseException | None) -> str:
    """Return a short, stable description of how a request or a block ended."""
    if error is None:
        return "ok"
    text = str(error)
    name = type(error).__name__
    return f"{name}: {text}" if text and text != name else name


@dataclass
class Journal:
    """The bounded buffers of one config entry."""

    requests: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_REQUESTS)
    )
    polls: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_POLLS)
    )
    events: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_EVENTS)
    )
    started: str = field(default_factory=_now)

    def event(self, kind: str, **details: Any) -> None:
        """Keep a rare occurrence."""
        self.events.append({"time": _now(), "event": kind, **details})

    def poll(
        self,
        table: str,
        duration: float,
        *,
        updated: list[str] | None = None,
        failed: Mapping[str, BaseException] | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Keep one poll's summary."""
        entry: dict[str, Any] = {
            "time": _now(),
            "table": table,
            "ms": round(duration * 1000),
        }
        if error is not None:
            entry["error"] = outcome_of(error)
        else:
            entry["updated"] = list(updated or [])
            if failed:
                entry["failed"] = {
                    name: outcome_of(cause) for name, cause in failed.items()
                }
        self.polls.append(entry)

    def as_dict(self) -> dict[str, Any]:
        """Return the buffers for the diagnostics download."""
        return {
            "started": self.started,
            "limits": {
                "requests": MAX_REQUESTS,
                "polls": MAX_POLLS,
                "events": MAX_EVENTS,
            },
            "events": list(self.events),
            "polls": list(self.polls),
            "requests": list(self.requests),
        }


class RecordingUnit:
    """Stands in for a ``ModbusUnit`` and records every data access it passes on.

    Each recorded request has its own method with the protocol's signature, and
    records a fixed set of fields. Everything else (``require_timeout``,
    ``connected``, the requests in :data:`UNRECORDED_REQUESTS`) goes straight to
    the real unit.
    """

    def __init__(self, unit: Any, journal: Journal) -> None:
        """Wrap ``unit``; requests are recorded in ``journal``."""
        self._unit = unit
        self._journal = journal

    def __getattr__(self, name: str) -> Any:
        """Return the unit's attribute for everything that is not recorded."""
        return getattr(self._unit, name)

    async def read_coils(self, address: int, count: int) -> list[bool]:
        """Read coils."""
        return await self._record(
            "read_coils",
            lambda: self._unit.read_coils(address, count),
            address=address,
            count=count,
        )

    async def read_discrete_inputs(self, address: int, count: int) -> list[bool]:
        """Read discrete inputs."""
        return await self._record(
            "read_discrete_inputs",
            lambda: self._unit.read_discrete_inputs(address, count),
            address=address,
            count=count,
        )

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers."""
        return await self._record(
            "read_holding_registers",
            lambda: self._unit.read_holding_registers(address, count),
            address=address,
            count=count,
        )

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        """Read input registers."""
        return await self._record(
            "read_input_registers",
            lambda: self._unit.read_input_registers(address, count),
            address=address,
            count=count,
        )

    async def write_coil(self, address: int, value: bool) -> None:
        """Write one coil."""
        await self._record(
            "write_coil",
            lambda: self._unit.write_coil(address, value),
            address=address,
            value=value,
        )

    async def write_coils(self, address: int, values: list[bool]) -> None:
        """Write several coils."""
        await self._record(
            "write_coils",
            lambda: self._unit.write_coils(address, values),
            address=address,
            values=list(values),
        )

    async def write_register(self, address: int, value: int) -> None:
        """Write one holding register."""
        await self._record(
            "write_register",
            lambda: self._unit.write_register(address, value),
            address=address,
            value=value,
        )

    async def write_registers(self, address: int, values: list[int]) -> None:
        """Write several holding registers."""
        await self._record(
            "write_registers",
            lambda: self._unit.write_registers(address, values),
            address=address,
            values=list(values),
        )

    async def mask_write_register(
        self, address: int, and_mask: int, or_mask: int
    ) -> None:
        """Change bits of one holding register."""
        await self._record(
            "mask_write_register",
            lambda: self._unit.mask_write_register(address, and_mask, or_mask),
            address=address,
            and_mask=and_mask,
            or_mask=or_mask,
        )

    async def _record[T](
        self, request: str, send: Callable[[], Awaitable[T]], **fields: Any
    ) -> T:
        """Send the request and keep one line with ``fields``, duration and outcome."""
        journal = self._journal
        entry: dict[str, Any] = {"time": _now(), "request": request, **fields}
        start = time.monotonic()
        error: BaseException | None = None
        try:
            return await send()
        except BaseException as err:
            error = err
            raise
        finally:
            entry["ms"] = round((time.monotonic() - start) * 1000)
            entry["outcome"] = outcome_of(error)
            journal.requests.append(entry)
            if not request.startswith("read_"):
                journal.event(
                    "write", **{k: v for k, v in entry.items() if k != "time"}
                )
            elif isinstance(error, ModbusTimeoutError):
                journal.event(
                    "timeout", **{k: v for k, v in entry.items() if k != "time"}
                )
