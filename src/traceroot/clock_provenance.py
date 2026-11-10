"""Fail-closed host identity checks for one-host monotonic span arithmetic.

CLOCK_MONOTONIC timestamps from different hosts do not share an origin, even
if each process labels its clock domain 'local_monotonic'. Any trace claiming
an explicit clock_host_id must provide that identity for *every* span.
"""
from __future__ import annotations


class ClockHostTracker:
    def __init__(self) -> None:
        self._identity: dict[str, str | None] = {}

    def observe(self, trace_id: str, fields: dict) -> None:
        host = fields.get('clock_host_id')
        if host is not None and (not isinstance(host, str) or
                                 not host or len(host) > 200):
            raise ValueError(f'{trace_id}: invalid clock_host_id')
        if trace_id in self._identity and self._identity[trace_id] != host:
            raise ValueError(f'{trace_id}: mixed or missing clock host identities')
        self._identity[trace_id] = host

    def status(self, trace_id: str) -> str:
        if trace_id not in self._identity:
            raise KeyError(trace_id)
        return ('consistent_reported_clock_host_id' if self._identity[trace_id] is not None
                else 'assumed_single_host_not_verified')

    def identity(self, trace_id: str) -> str | None:
        """Self-reported host identity; not cryptographic or clock-sync proof."""
        return self._identity[trace_id]
