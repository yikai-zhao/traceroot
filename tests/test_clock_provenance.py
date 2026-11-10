"""Same-clock guard against invalid cross-host exclusive span attribution."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from traceroot.clock_provenance import ClockHostTracker


class ClockHostTests(unittest.TestCase):
    def test_explicit_identity_all_spans_same_host(self):
        x=ClockHostTracker()
        x.observe('t',{'clock_host_id':'node-1'})
        x.observe('t',{'clock_host_id':'node-1'})
        self.assertEqual(x.status('t'),'consistent_reported_clock_host_id')
    def test_cross_host_child_rejected(self):
        x=ClockHostTracker();x.observe('t',{'clock_host_id':'node-1'})
        with self.assertRaisesRegex(ValueError,'mixed'):x.observe('t',{'clock_host_id':'node-2'})
    def test_parent_without_identity_child_with_identity_rejected(self):
        x=ClockHostTracker();x.observe('t',{})
        with self.assertRaisesRegex(ValueError,'mixed'):x.observe('t',{'clock_host_id':'node-1'})
    def test_parent_with_identity_child_missing_rejected(self):
        x=ClockHostTracker();x.observe('t',{'clock_host_id':'node-1'})
        with self.assertRaisesRegex(ValueError,'mixed'):x.observe('t',{})
    def test_legacy_no_identity_is_explicitly_unverified(self):
        x=ClockHostTracker();x.observe('t',{});x.observe('t',{})
        self.assertEqual(x.status('t'),'assumed_single_host_not_verified')
    def test_separate_traces_may_use_distinct_hosts(self):
        x=ClockHostTracker();x.observe('t1',{'clock_host_id':'a'});x.observe('t2',{'clock_host_id':'b'})
        self.assertEqual(x.status('t2'),'consistent_reported_clock_host_id')
    def test_invalid_identity_rejected(self):
        for bad in ('',3,True,'z'*201):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                ClockHostTracker().observe('t',{'clock_host_id':bad})
    def test_missing_trace_status_rejected(self):
        with self.assertRaises(KeyError):ClockHostTracker().status('t')

if __name__=='__main__':unittest.main()
