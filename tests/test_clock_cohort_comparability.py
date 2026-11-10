"""Adversarial cohorts: provenance consistency matters beyond per-trace validity."""
import unittest
from traceroot.core import Event
from traceroot.traces import compare_runs


def cohort(prefix, slow=0, host=None, n=3):
    events=[]
    for i in range(n):
        name=f'{prefix}-{i}'
        for span_id, service, start_ms, duration, parent in (
            ('front','api',0,65+slow,None),
            ('db','db',5,50+slow,'front'),
        ):
            fields={'trace_id':name,'span_id':span_id,'service':service,
                    'duration_ms':duration,'clock_domain':'local_monotonic',
                    'operation':'read'}
            if parent is not None:fields['parent_span_id']=parent
            if host is not None:fields['clock_host_id']=host
            events.append(Event(f'{name}-{span_id}',int(start_ms*1e6),'service_span',service,fields))
    return events


class ClockCohortTests(unittest.TestCase):
    def test_mixed_provenance_between_cohorts_must_abstain(self):
        actual=compare_runs(cohort('before',host='vm-a'),cohort('after',slow=50))
        self.assertEqual(actual['decision'],'insufficient_comparable_evidence')
        self.assertIsNone(actual['hypothesis'])

    def test_mixed_provenance_among_trace_replicates_must_abstain(self):
        before=cohort('before',host='vm-a')
        after=cohort('after',slow=50,host='vm-a')
        del after[-1].fields['clock_host_id']
        # This is already rejected as a missing identity inside one trace.
        with self.assertRaisesRegex(ValueError, 'clock host'):
            compare_runs(before,after)

    def test_untagged_legacy_comparison_is_explicitly_unverified(self):
        x=compare_runs(cohort('before'),cohort('after',slow=50))
        self.assertEqual(x['decision'],'regression_observed')
        self.assertEqual(x['clock_identity_status'],'assumed_single_host_not_verified')

    def test_two_explicit_single_host_cohorts_remain_comparable(self):
        # The two cohorts may be on different hosts: only within-request
        # subtraction of same-origin clock stamps is required here.
        x=compare_runs(cohort('before',host='vm-a'),cohort('after',slow=50,host='vm-b'))
        self.assertEqual(x['decision'],'regression_observed')
        self.assertEqual(x['clock_identity_status'],'consistent_reported_clock_host_id')

if __name__ == '__main__':unittest.main()
