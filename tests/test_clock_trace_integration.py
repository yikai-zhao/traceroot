"""Actual trace summarization must reject unsupported mixed-host clock math."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traceroot.core import Event
from traceroot.traces import summarize_traces, compare_runs


def span(id,trace,parent=None,host=None,start=0,duration=100,operation=None):
    fields={'trace_id':trace,'span_id':id,'service':id,'duration_ms':duration}
    if parent: fields['parent_span_id']=parent
    if host is not None: fields['clock_host_id']=host
    if operation is not None: fields['operation']=operation
    return Event(trace+'-'+id,int(start*1e6),'service_span',id,fields)


class ClockProvenanceIntegrationTests(unittest.TestCase):
    def test_matching_hosts_are_validated(self):
        r=summarize_traces([span('front','t',host='localhost',operation='get'),
                            span('back','t',parent='front',host='localhost',start=10,duration=50)])[0]
        self.assertEqual(r['clock_identity_status'],'consistent_reported_clock_host_id')
        self.assertEqual(r['wall_ms'],100)
    def test_mixed_hosts_rejected_before_latency_attribution(self):
        with self.assertRaisesRegex(ValueError,'mixed or missing clock host'):
            summarize_traces([span('front','t',host='host-a',operation='get'),
                              span('back','t',parent='front',host='host-b',start=10,duration=50)])
    def test_partially_tagged_trace_rejected(self):
        with self.assertRaisesRegex(ValueError,'mixed or missing clock host'):
            summarize_traces([span('front','t',operation='get'),
                              span('back','t',parent='front',host='host-b',start=10,duration=50)])
    def test_legacy_trace_explicitly_assumes_single_host(self):
        r=summarize_traces([span('front','t',operation='get'),
                            span('back','t',parent='front',start=10,duration=50)])[0]
        self.assertEqual(r['clock_identity_status'],'assumed_single_host_not_verified')
    def test_compare_runs_with_consistent_host_can_attribute(self):
        def cohort(prefix,wall):
            return [event for i in range(3) for event in
                    [span('front',f'{prefix}-{i}',host='same-node',duration=wall,operation='get'),
                     span('back',f'{prefix}-{i}',parent='front',host='same-node',start=10,duration=50)]]
        outcome=compare_runs(cohort('before',100),cohort('after',160))
        self.assertEqual(outcome['decision'],'regression_observed')
        self.assertEqual(outcome['hypothesis']['service'],'front')
    def test_compare_runs_cannot_rank_mixed_hosts(self):
        def cohort(prefix,host):
            return [item for i in range(3) for item in
                    [span('front',f'{prefix}-{i}',host=host,operation='get'),
                     span('back',f'{prefix}-{i}',parent='front',host='other',start=10,duration=50)]]
        with self.assertRaisesRegex(ValueError,'mixed or missing clock host'):
            compare_runs(cohort('before','localhost'),cohort('after','localhost'))

if __name__=='__main__':unittest.main()
