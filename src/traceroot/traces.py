"""Local-clock span attribution and repeated-run regression comparison.

Inputs are normalized, synthetic or explicitly permissioned traces. This module
never calls a service or an LLM. A slow exclusive span is a location to inspect,
not proof of the underlying cause.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from statistics import median
from typing import Iterable

from .core import Event
from .topology import canonical_topology


@dataclass(frozen=True)
class Span:
    trace_id: str
    span_id: str
    evidence_id: str
    service: str
    parent: str | None
    start_ns: int
    end_ns: int
    operation: str | None

    @property
    def duration_ns(self) -> int:
        return self.end_ns - self.start_ns


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError(f'invalid {field}')
    return value


def _union_ns(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    intervals.sort()
    left, right = intervals[0]
    covered = 0
    for begin, end in intervals[1:]:
        if begin > right:
            covered += right - left
            left, right = begin, end
        else:
            right = max(right, end)
    return covered + right - left


def summarize_traces(events: Iterable[Event]) -> list[dict]:
    """Attribute inclusive and exclusive time to spans in one clock domain.

    Child intervals must lie within their parent. Sibling overlaps count only
    once when subtracting child time, unlike a naive sum-of-durations model.
    """
    groups: dict[str, dict[str, Span]] = defaultdict(dict)
    domains: dict[str, str] = {}
    for e in events:
        if e.kind != 'service_span':
            continue
        f = e.fields
        trace_id = _string(f.get('trace_id'), 'trace_id')
        span_id = _string(f.get('span_id'), 'span_id')
        service = _string(f.get('service'), 'service')
        clock_domain = _string(f.get('clock_domain', 'local_monotonic'), 'clock_domain')
        if trace_id in domains and domains[trace_id] != clock_domain:
            raise ValueError(f'{trace_id}: mixed clock domains')
        domains[trace_id] = clock_domain
        if clock_domain != 'local_monotonic':
            raise ValueError('clock sync unavailable: only local_monotonic is supported')
        parent = f.get('parent_span_id')
        if parent is not None:
            parent = _string(parent, 'parent_span_id')
        duration = f.get('duration_ms')
        if type(duration) not in (float, int) or not math.isfinite(duration) or duration < 0 or duration > 3600000:
            raise ValueError(f'{e.id}: invalid duration_ms')
        if e.time_ns > 2**63 - 1 - duration * 1_000_000:
            raise ValueError(f'{e.id}: timestamp overflow')
        operation = f.get('operation')
        if operation is not None:
            operation = _string(operation, 'operation')
        if span_id in groups[trace_id]:
            raise ValueError(f'{trace_id}: duplicate span ID {span_id}')
        groups[trace_id][span_id] = Span(
            trace_id=trace_id, span_id=span_id, evidence_id=e.id,
            service=service, parent=parent, start_ns=e.time_ns,
            end_ns=e.time_ns + round(duration * 1_000_000), operation=operation)

    reports = []
    for trace_id in sorted(groups):
        nodes = groups[trace_id]
        children: dict[str, list[Span]] = defaultdict(list)
        roots = []
        for span in nodes.values():
            if span.parent is None:
                roots.append(span)
                continue
            if span.parent not in nodes:
                raise ValueError(f'{trace_id}: missing parent {span.parent}')
            parent = nodes[span.parent]
            if (span.span_id == span.parent or span.start_ns < parent.start_ns or
                    span.end_ns > parent.end_ns):
                raise ValueError(f'{trace_id}: child outside parent interval')
            children[span.parent].append(span)
        if not roots:
            raise ValueError(f'{trace_id}: no root span')
        # A directed parent graph cannot cycle if each child lies within a
        # parent (zero-duration cycles are still possible); detect explicitly.
        for span in nodes.values():
            seen = set()
            cursor = span
            while cursor.parent is not None:
                if cursor.span_id in seen:
                    raise ValueError(f'{trace_id}: cyclic parent chain')
                seen.add(cursor.span_id)
                cursor = nodes[cursor.parent]
        # Compare full parent/child span shape, not only the set of service names.
        # An extra retry or missing child in one cohort makes its latency
        # attribution structurally incomparable, even if the service set matches.
        topology = canonical_topology(nodes)
        rows = []
        for span in nodes.values():
            child_coverage = _union_ns([(c.start_ns, c.end_ns) for c in children[span.span_id]])
            exclusive = span.duration_ns - child_coverage
            if exclusive < 0:
                raise ValueError(f'{trace_id}: exclusive duration underflow')
            rows.append({'span_id': span.span_id, 'evidence_id': span.evidence_id,
                         'service': span.service, 'parent_span_id': span.parent,
                         'inclusive_ms': round(span.duration_ns / 1e6, 3),
                         'exclusive_ms': round(exclusive / 1e6, 3)})
        rows.sort(key=lambda x: (-x['exclusive_ms'], x['evidence_id']))
        top = rows[0]
        reports.append({
            'trace_id': trace_id, 'clock_domain': domains[trace_id],
            'operation': roots[0].operation if len(roots) == 1 else None,
            'span_count': len(nodes), 'root_count': len(roots),
            'topology_signature': topology,
            'wall_ms': round((max(n.end_ns for n in nodes.values()) -
                              min(n.start_ns for n in nodes.values())) / 1e6, 3),
            'largest_exclusive_span': {'evidence_id': top['evidence_id'],
                                       'span_id': top['span_id'],
                                       'service': top['service'],
                                       'exclusive_ms': top['exclusive_ms']},
            'spans': rows,
            'interpretation': 'measured exclusive span time, not causal root cause',
        })
    return reports


def compare_runs(baseline: Iterable[Event], candidate: Iterable[Event],
                 min_runs: int = 3) -> dict:
    """Median-based same-operation regression screening; no causal diagnosis.

    Rejects incomplete cohorts and differing service topology. Thresholds are
    deliberately simple, public decision rules (>=25% and >=20 ms wall time).
    """
    before = summarize_traces(baseline)
    after = summarize_traces(candidate)
    result = {'decision': 'insufficient_comparable_evidence',
              'hypothesis': None, 'thresholds': {'wall_ratio': 1.25, 'wall_increase_ms': 20},
              'baseline_runs': len(before), 'candidate_runs': len(after)}
    if len(before) < min_runs or len(after) < min_runs:
        return result
    all_runs = before + after
    if any(r['root_count'] != 1 or r['operation'] is None for r in all_runs):
        return result
    if len({r['operation'] for r in all_runs}) != 1:
        return result
    if any(r['topology_signature'] != all_runs[0]['topology_signature'] for r in all_runs[1:]):
        return result
    def service_totals(run: dict) -> dict[str, float]:
        totals = defaultdict(float)
        for span in run['spans']:
            totals[span['service']] += span['exclusive_ms']
        return dict(totals)
    services = [service_totals(r) for r in all_runs]
    required = set(services[0])
    if not required or any(set(s) != required for s in services[1:]):
        return result
    before_wall = median(r['wall_ms'] for r in before)
    after_wall = median(r['wall_ms'] for r in after)
    before_services = services[:len(before)]
    after_services = services[len(before):]
    contributors = sorted(({
        'service': service,
        'baseline_median_exclusive_ms': round(median(s[service] for s in before_services), 3),
        'candidate_median_exclusive_ms': round(median(s[service] for s in after_services), 3),
        'delta_ms': round(median(s[service] for s in after_services) -
                          median(s[service] for s in before_services), 3),
    } for service in required), key=lambda r: (-r['delta_ms'], r['service']))
    result.update({'operation': before[0]['operation'],
                   'baseline_median_wall_ms': before_wall,
                   'candidate_median_wall_ms': after_wall,
                   'contributors': contributors})
    regression = after_wall >= before_wall * 1.25 and after_wall - before_wall >= 20
    result['decision'] = 'regression_observed' if regression else 'no_threshold_regression_observed'
    if regression:
        affected = contributors[0]
        result['hypothesis'] = {'label': 'largest_exclusive_time_increase',
                                'service': affected['service'],
                                'status': 'measured_contributor_not_proven_cause',
                                'baseline_evidence_ids': [span['evidence_id'] for r in before
                                                          for span in r['spans'] if span['service'] == affected['service']],
                                'candidate_evidence_ids': [span['evidence_id'] for r in after
                                                           for span in r['spans'] if span['service'] == affected['service']]}
    return result
