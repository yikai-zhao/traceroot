"""Read-only, stdlib-only incident evidence normalization and diagnosis.

No LLM is needed for the baseline. No network calls, shell commands or side effects.
Input is a synthetic/public normalized event stream, never employer data.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

KINDS = {'tcp_connect', 'route_change', 'link_change', 'queue_stats', 'service_health',
         'service_span', 'resource_sample', 'agent_tool_call'}

@dataclass(frozen=True)
class Event:
    id: str
    time_ns: int
    kind: str
    source: str
    fields: dict[str, Any]


def read_events(path: Path) -> tuple[list[Event], str]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > 8_000_000:
        raise ValueError('input too large')
    events = []
    seen = set()
    for line_no, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        if len(line) > 16384:
            raise ValueError(f'line {line_no}: oversized')
        obj = json.loads(line)
        if not isinstance(obj, dict) or set(obj) != {'id', 'time_ns', 'kind', 'source', 'fields'}:
            raise ValueError(f'line {line_no}: invalid event schema')
        if not isinstance(obj['id'], str) or not obj['id'] or obj['id'] in seen:
            raise ValueError(f'line {line_no}: invalid or duplicate evidence id')
        if type(obj['time_ns']) is not int or obj['time_ns'] < 0:
            raise ValueError(f'line {line_no}: invalid monotonic time')
        if obj['kind'] not in KINDS or not isinstance(obj['source'], str) or not obj['source']:
            raise ValueError(f'line {line_no}: invalid source/kind')
        if not isinstance(obj['fields'], dict):
            raise ValueError(f'line {line_no}: invalid fields')
        seen.add(obj['id'])
        events.append(Event(**obj))
    return sorted(events, key=lambda e: (e.time_ns, e.id)), digest


def analyze(events: list[Event], digest: str) -> dict:
    """Correlate symptoms with independent observations; never assert causality."""
    failures = [e for e in events if e.kind == 'tcp_connect' and e.fields.get('ok') is False]
    success = [e for e in events if e.kind == 'tcp_connect' and e.fields.get('ok') is True]
    route = [e for e in events if e.kind == 'route_change']
    link = [e for e in events if e.kind == 'link_change']
    queues = [e for e in events if e.kind == 'queue_stats' and
              type(e.fields.get('application_queue_drops')) is int and
              e.fields['application_queue_drops'] > 0]
    unhealthy = [e for e in events if e.kind == 'service_health' and e.fields.get('healthy') is False]
    hypotheses = []
    if failures and (route or link):
        nearby = [e for e in route + link if any(abs(e.time_ns - f.time_ns) <= 2_000_000_000 for f in failures)]
        if nearby:
            hypotheses.append({'label': 'network_state_change_correlated_with_tcp_failure',
                               'evidence_ids': [nearby[0].id, failures[0].id],
                               'status': 'correlated_not_proven',
                               'next_check': 'Reproduce with isolated route/link manipulation and compare recovery'})
    if failures and unhealthy:
        hypotheses.append({'label': 'service_unhealthy_during_tcp_failure',
                           'evidence_ids': [unhealthy[0].id, failures[0].id],
                           'status': 'candidate_not_proven',
                           'next_check': 'Verify listener state and connect errno at failure time'})
    if queues:
        hypotheses.append({'label': 'application_queue_backpressure_observed',
                           'evidence_ids': [queues[0].id],
                           'status': 'direct_observation_not_wire_loss',
                           'next_check': 'Check queue depth, consumer delay and kernel RX overflow separately'})
    # Cross-service latency: a slow downstream span is a grounded candidate,
    # not a proven root cause. Use trace_id to avoid cross-request mixing.
    spans = [e for e in events if e.kind == 'service_span' and
             type(e.fields.get('duration_ms')) in (int, float) and
             e.fields['duration_ms'] >= 0 and isinstance(e.fields.get('trace_id'), str)]
    slow_spans = [e for e in spans if e.fields['duration_ms'] >= 500]
    for slow in slow_spans[:10]:
        peers = [e for e in spans if e.id != slow.id and
                 e.fields['trace_id'] == slow.fields['trace_id']]
        hypotheses.append({'label': 'slow_service_span_observed',
                           'evidence_ids': [slow.id] + ([peers[0].id] if peers else []),
                           'status': 'latency_observed_cause_unproven',
                           'next_check': 'Compare upstream/downstream spans and CPU or lock contention'})
    # A resource spike correlated with a slow span is not by itself causality.
    resources = [e for e in events if e.kind == 'resource_sample' and
                 type(e.fields.get('cpu_percent')) in (int, float) and
                 e.fields['cpu_percent'] >= 90]
    for sample in resources[:10]:
        near = [e for e in slow_spans if abs(e.time_ns - sample.time_ns) <= 2_000_000_000]
        if near:
            hypotheses.append({'label': 'cpu_saturation_correlated_with_slow_span',
                               'evidence_ids': [sample.id, near[0].id],
                               'status': 'correlated_not_proven',
                               'next_check': 'Collect repeated process CPU profiles and compare baselines'})
    calls = [e for e in events if e.kind == 'agent_tool_call' and
             e.fields.get('status') == 'error']
    if calls:
        hypotheses.append({'label': 'agent_tool_failure_observed',
                           'evidence_ids': [calls[0].id],
                           'status': 'direct_observation',
                           'next_check': 'Inspect tool error and retry policy without executing tools'})
    evidence_ids = {e.id for e in events}
    assert all(set(h['evidence_ids']) <= evidence_ids for h in hypotheses)
    from .traces import summarize_traces
    trace_summaries = summarize_traces(events)
    return {'schema_version': 1, 'source_sha256': digest, 'events': len(events),
            'trace_summaries': trace_summaries,
            'tcp_successes': len(success), 'tcp_failures': len(failures),
            'hypotheses': hypotheses,
            'root_cause': None,
            'decision': 'insufficient_evidence_for_causal_root_cause',
            'evidence_policy': 'All claims must cite event IDs; correlation is not causation'}


def run(path: Path) -> dict:
    events, digest = read_events(path)
    return analyze(events, digest)
