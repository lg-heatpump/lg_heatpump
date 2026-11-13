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

#: Unit methods that put a request on the wire.
_RECORDED_PREFIXES = ("read_", "write_", "mask_write_")


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
    """Stands in for a ``ModbusUnit`` and records every request it passes on.

    Everything else (``require_timeout``, ``connected``, ...) goes straight to
    the real unit.
    """

    def __init__(self, unit: Any, journal: Journal) -> None:
        """Wrap ``unit``; requests are recorded in ``journal``."""
        self._unit = unit
        self._journal = journal

    def __getattr__(self, name: str) -> Any:
        """Return the unit's attribute, wrapped if it sends a request."""
        attribute = getattr(self._unit, name)
        if name.startswith(_RECORDED_PREFIXES) and callable(attribute):
            return self._recorded(name, attribute)
        return attribute

    def _recorded(
        self, name: str, method: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        journal = self._journal
        writes = not name.startswith("read_")

        async def call(*args: Any, **kwargs: Any) -> Any:
            entry: dict[str, Any] = {"time": _now(), "request": name}
            if args:
                entry["address"] = args[0]
            if len(args) > 1:
                entry["count" if not writes else "value"] = args[1]
            entry.update(kwargs)
            start = time.monotonic()
            error: BaseException | None = None
            try:
                return await method(*args, **kwargs)
            except BaseException as err:
                error = err
                raise
            finally:
                entry["ms"] = round((time.monotonic() - start) * 1000)
                entry["outcome"] = outcome_of(error)
                journal.requests.append(entry)
                if writes:
                    journal.event(
                        "write", **{k: v for k, v in entry.items() if k != "time"}
                    )
                elif isinstance(error, ModbusTimeoutError):
                    journal.event(
                        "timeout", **{k: v for k, v in entry.items() if k != "time"}
                    )

        return call
