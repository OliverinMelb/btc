"""Shared CCXT proxy failover for read-only market-data requests."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import ccxt

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _proxy_candidates(config: Mapping[str, Any]) -> list[str | None]:
    """Return configured proxies in priority order, without duplicates."""
    configured = [config.get("ccxt_proxy")]
    fallbacks = config.get("ccxt_proxy_fallbacks") or []
    if isinstance(fallbacks, str):
        fallbacks = fallbacks.split(",")
    configured.extend(fallbacks)

    candidates: list[str | None] = []
    for value in configured:
        proxy = value.strip() if isinstance(value, str) else value
        if proxy and proxy not in candidates:
            candidates.append(proxy)
    return candidates or [None]


def call_with_proxy_failover(
    config: Mapping[str, Any],
    exchange_factory: Callable[[], Any],
    request: Callable[[Any], _T],
) -> _T:
    """Run one CCXT request, changing proxy only after network failures."""
    candidates = _proxy_candidates(config)
    for index, proxy in enumerate(candidates):
        exchange = exchange_factory()
        if proxy:
            exchange.httpsProxy = proxy
        try:
            return request(exchange)
        except ccxt.NetworkError:
            if index == len(candidates) - 1:
                raise
            logger.warning(
                "CCXT network request failed through proxy candidate %d/%d; trying next",
                index + 1,
                len(candidates),
            )
    raise AssertionError("proxy candidate loop completed without a request result")
