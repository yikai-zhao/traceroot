import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from traceroot.core import run, read_events

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/service_performance.jsonl'

class InfraTests(unittest.TestCase):
    def test_cross_service_evidence(self):
        r = run(FIXTURE)
        labels = [h['label'] for h in r['hypotheses']]
        self.assertIn('slow_service_span_observed', labels)
        self.assertIn('cpu_saturation_correlated_with_slow_span', labels)
        self.assertIn('agent_tool_failure_observed', labels)
        self.assertIsNone(r['root_cause'])
    def test_evidence_ids_are_grounded(self):
        events, _ = read_events(FIXTURE)
        valid = {e.id for e in events}
        for h in run(FIXTURE)['hypotheses']:
            self.assertTrue(set(h['evidence_ids']) <= valid)
    def test_no_cross_trace_join(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            events = [json.loads(x) for x in FIXTURE.read_text().splitlines()]
            events[1]['fields']['trace_id'] = 'unrelated'
            path.write_text(''.join(json.dumps(x)+'\n' for x in events))
            result = run(path)
            first = next(h for h in result['hypotheses'] if h['label'] == 'slow_service_span_observed')
            self.assertEqual(first['evidence_ids'], ['span-001'])
    def test_missing_evidence_abstains(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'empty.jsonl'
            path.write_text('')
            self.assertEqual(run(path)['hypotheses'], [])
            self.assertIsNone(run(path)['root_cause'])

if __name__ == '__main__': unittest.main()
