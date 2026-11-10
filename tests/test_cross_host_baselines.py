"""Counterexample: self-reported clock hosts need identity comparisons, not just presence."""
import unittest
from traceroot.core import Event
from traceroot.traces import compare_runs


def cohort(prefix: str, host: str | None, extra: int) -> list[Event]:
    events = []
    for i in range(4):
        trace = f'{prefix}-{i}'
        root = dict(trace_id=trace, span_id='r', service='api', operation='lookup',
                    duration_ms=110+extra, clock_domain='local_monotonic')
        child = dict(trace_id=trace, span_id='db', parent_span_id='r', service='db',
                     duration_ms=90+extra, clock_domain='local_monotonic')
        if host is not None:
            root['clock_host_id'] = child['clock_host_id'] = host
        events.extend([Event(f'{trace}-r', i*1_000_000_000, 'service_span','api', root),
                       Event(f'{trace}-db',i*1_000_000_000+5_000_000,'service_span','db',child)])
    return events


class CohortHostTests(unittest.TestCase):
    def test_different_explicit_hosts_produce_confounding_warning(self):
        result = compare_runs(cohort('base','host-A',0),cohort('cand','host-B',50))
        self.assertEqual(result['decision'],'regression_observed')
        self.assertEqual(result['hypothesis']['service'],'db')
        self.assertEqual(result['cohort_host_warning'],'distinct_reported_hosts_confound_attribution')

    def test_matching_explicit_hosts_can_compare(self):
        result=compare_runs(cohort('base','host-A',0),cohort('cand','host-A',50))
        self.assertEqual(result['decision'],'regression_observed')
        self.assertEqual(result['hypothesis']['service'],'db')
        self.assertIsNone(result['cohort_host_warning'])

    def test_untagged_legacy_is_not_silently_verified(self):
        result=compare_runs(cohort('base',None,0),cohort('cand',None,50))
        self.assertEqual(result['decision'],'regression_observed')
        self.assertEqual(result['clock_identity_status'],'assumed_single_host_not_verified')

if __name__=='__main__': unittest.main()
