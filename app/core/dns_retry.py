"""Retry host-name lookups that fail with a temporary error ("Try again").

A local resolver that rate-limits (AdGuard Home allows 20 queries per second per /24 by
default) answers a burst of lookups, such as every app's backup starting at once, with
``EAI_AGAIN``. Every Python HTTP client the workers and destinations use (requests,
websockets, python-socketio, google-auth, msal) resolves names through
``socket.getaddrinfo``, so retrying there covers all of them in one place.

Only ``EAI_AGAIN`` is retried: an unknown name (``EAI_NONAME``) fails at once as before.
The wait is blocking, which is fine because lookups only happen in worker threads (the
event loop runs its own lookups in an executor too).
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable, Sequence
from typing import Any

logger = logging.getLogger(__name__)

DELAYS = (0.5, 1.0, 2.0, 4.0)

_installed = False


def retrying(
    getaddrinfo: Callable[..., Any],
    delays: Sequence[float] = DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[..., Any]:
    """Wrap ``getaddrinfo`` so a temporary failure is retried after each of ``delays``."""

    def lookup(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 - same signature as socket's
        for delay in delays:
            try:
                return getaddrinfo(*args, **kwargs)
            except socket.gaierror as e:
                if e.errno != socket.EAI_AGAIN:
                    raise
                logger.info(f"DNS lookup of {args[0] if args else '?'} failed for now; retrying")
                sleep(delay)
        return getaddrinfo(*args, **kwargs)

    return lookup


def install() -> None:
    """Make ``socket.getaddrinfo`` retry temporary failures (safe to call more than once)."""
    global _installed
    if _installed:
        return
    socket.getaddrinfo = retrying(socket.getaddrinfo)
    _installed = True
