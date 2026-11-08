"""Checks interval arithmetic, evidence provenance and regression abstention.

24 hand-defined parameter combinations exercise synthetic cohorts. They are
not claims of 24 independently observed production incidents.
"""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'src'))
from traceroot.core import Event
from traceroot.traces import summarize_traces, compare_runs


def span(event_id, trace, sid, service, start_ms, duration_ms, parent=None,
         operation=None, clock_domain='local_monotonic'):
    fields={'trace_id': trace, 'span_id':sid, 'service':service,
            'duration_ms': duration_ms, 'clock_domain': clock_domain}
    if parent is not None:fields['parent_span_id']=parent
    if operation is not None:fields['operation']=operation
    return Event(event_id,round(start_ms*1_000_000),'service_span',service,fields)


def cohort(prefix, db_extra=0, frontend_extra=0, n=5, operation='get_item'):
    """A frontend span encloses one downstream database span, with real variation."""
    events=[]
    for i in range(n):
        t=f'{prefix}-{i}'
        extra=(i%3-1)*3
        db=60+db_extra+extra
        front_self=15+frontend_extra
        events.extend([
            span(f'{t}-front',t,'front','api',0,db+front_self,None,operation),
            span(f'{t}-db',t,'db','db',front_self/2,db,'front'),
        ])
    return events


class TraceAttributionTests(unittest.TestCase):
    def test_simple_parent_child_exclusive(self):
        x=summarize_traces([span('f','tr','f','api',0,100,operation='read'),
                            span('d','tr','d','db',20,70,'f')])[0]
        self.assertEqual(x['wall_ms'],100)
        self.assertEqual({i['service']:i['exclusive_ms'] for i in x['spans']},{'db':70.,'api':30.})
        self.assertEqual(x['largest_exclusive_span']['evidence_id'],'d')
    def test_parallel_children_use_interval_union(self):
        x=summarize_traces([span('root','t','r','api',0,100,operation='read'),
                            span('a','t','a','x',10,70,'r'),
                            span('b','t','b','y',40,50,'r')])[0]
        self.assertEqual(next(i['exclusive_ms'] for i in x['spans'] if i['service']=='api'),20.)
    def test_separate_trace_ids_not_joined(self):
        a=span('a','x','parent','api',0,100,operation='get')
        b=span('b','y','child','db',10,20,'parent')
        with self.assertRaisesRegex(ValueError,'missing parent'):summarize_traces([a,b])
    def test_reject_duplicate_span_ids(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):summarize_traces([
            span('a','t','a','x',0,1),span('b','t','a','x',0,2)])
    def test_reject_missing_parent(self):
        with self.assertRaisesRegex(ValueError,'missing parent'):summarize_traces([
            span('a','t','a','x',10,5,'missing')])
    def test_reject_child_outside_parent(self):
        with self.assertRaisesRegex(ValueError,'outside parent'):summarize_traces([
            span('a','t','a','x',0,10),span('b','t','b','db',8,5,'a')])
    def test_reject_cross_clock_domains(self):
        with self.assertRaisesRegex(ValueError,'mixed clock'):summarize_traces([
            span('a','t','a','x',0,10),
            span('b','t','b','db',0,5,'a',clock_domain='remote')])
    def test_reject_nan_duration(self):
        with self.assertRaisesRegex(ValueError,'duration'):summarize_traces([
            span('a','t','a','x',0,float('nan'))])
    def test_invalid_cycle_fails(self):
        with self.assertRaises(ValueError):summarize_traces([
            span('a','t','a','x',0,10,'b'),span('b','t','b','x',0,10,'a')])
    def test_old_service_fixture_still_loads(self):
        from traceroot.core import read_events
        path=Path(__file__).resolve().parents[1]/'fixtures'/'service_performance.jsonl'
        events,_=read_events(path)
        self.assertEqual(len(summarize_traces(events)),1)
    def test_regression_detects_downstream_not_inclusive_frontend(self):
        x=compare_runs(cohort('before'),cohort('after',db_extra=80))
        self.assertEqual(x['decision'],'regression_observed')
        self.assertEqual(x['hypothesis']['service'],'db')
        self.assertEqual(len(x['hypothesis']['candidate_evidence_ids']),5)
        self.assertTrue(all(name.endswith('-db') for name in x['hypothesis']['candidate_evidence_ids']))
    def test_regression_detects_frontend_exclusive(self):
        x=compare_runs(cohort('before'),cohort('after',frontend_extra=65))
        self.assertEqual(x['hypothesis']['service'],'api')
    def test_small_jitter_no_regression(self):
        x=compare_runs(cohort('before'),cohort('after',db_extra=5))
        self.assertEqual(x['decision'],'no_threshold_regression_observed')
        self.assertIsNone(x['hypothesis'])
    def test_no_claim_from_one_run(self):
        x=compare_runs(cohort('a',n=1),cohort('b',db_extra=100,n=1))
        self.assertEqual(x['decision'],'insufficient_comparable_evidence')
    def test_mismatched_operations_abstain(self):
        x=compare_runs(cohort('a'),cohort('b',db_extra=100,operation='delete_item'))
        self.assertEqual(x['decision'],'insufficient_comparable_evidence')
    def test_no_samples_abstain(self):
        self.assertEqual(compare_runs([],[])['decision'],'insufficient_comparable_evidence')
    def test_synthetic_label_grid(self):
        labels=[]
        # 3 candidate signatures x 8 controlled strengths = 24 labeled variations.
        # No model training, random labels, production claims or hand-picking passes.
        for category in ('db','api','none'):
            for extra in (0,5,10,15,25,50,75,100):
                kwargs={}
                if category=='db':kwargs['db_extra']=extra
                elif category=='api':kwargs['frontend_extra']=extra
                got=compare_runs(cohort('base'),cohort('cand',**kwargs))
                if extra>=25 and category != 'none':
                    self.assertEqual(got['decision'],'regression_observed',(category,extra))
                    self.assertEqual(got['hypothesis']['service'],category)
                    labels.append('positive')
                else:
                    self.assertEqual(got['decision'],'no_threshold_regression_observed',(category,extra))
                    labels.append('negative')
        self.assertEqual(len(labels),24)
        self.assertEqual(labels.count('positive'),8)

if __name__=='__main__':unittest.main()
