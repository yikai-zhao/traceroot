"""The new structural check must be exercised through the real comparator."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from traceroot.core import Event
from traceroot.traces import compare_runs


def cohort(prefix, merged=False, root_duration=200):
    events=[]
    for i in range(3):
        tid=f'{prefix}-{i}'
        def add(sid, service, start, duration, parent=None, op='read'):
            fields={'trace_id':tid,'span_id':sid,'service':service,
                    'duration_ms':duration,'clock_domain':'local_monotonic',
                    'operation':op}
            if parent is not None:fields['parent_span_id']=parent
            events.append(Event(f'{tid}-{sid}',start*1_000_000,
                                'service_span',service,fields))
        add('root','api',0,root_duration)
        add('a','worker',5,75,'root')
        add('b','worker',90,90,'root')
        add('db','db',10,30,'a')
        # Same service/parent-service edge multiset in either cohort.
        add('cache','cache',45 if merged else 110,30,'a' if merged else 'b')
    return events


class ComparatorStructureGuardTests(unittest.TestCase):
    def test_same_flat_edges_different_call_trees_abstain(self):
        r=compare_runs(cohort('base'),cohort('cand',merged=True,root_duration=300))
        self.assertEqual(r['decision'],'insufficient_comparable_evidence')
        self.assertIsNone(r['hypothesis'])

    def test_identical_tree_can_still_detect_frontend_regression(self):
        r=compare_runs(cohort('base'),cohort('cand',root_duration=300))
        self.assertEqual(r['decision'],'regression_observed')
        self.assertEqual(r['hypothesis']['service'],'api')


if __name__ == '__main__': unittest.main()
