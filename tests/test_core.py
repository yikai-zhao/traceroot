import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from traceroot.core import read_events, analyze, run

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/network_incident.jsonl'

class CoreTests(unittest.TestCase):
    def test_fixture_has_grounded_hypotheses_but_no_causal_claim(self):
        result = run(FIXTURE)
        self.assertEqual(result['root_cause'], None)
        self.assertEqual(len(result['hypotheses']), 2)
        self.assertEqual(result['hypotheses'][0]['evidence_ids'], ['route-001','tcp-001'])
        self.assertEqual(result['hypotheses'][1]['evidence_ids'], ['queue-001'])
    def test_empty_abstains(self):
        self.assertEqual(analyze([], '0')['hypotheses'], [])
    def test_duplicate_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.jsonl'
            line = FIXTURE.read_text().splitlines()[0]
            p.write_text(line+'\n'+line+'\n')
            with self.assertRaises(ValueError): read_events(p)
    def test_bad_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.jsonl'
            item = json.loads(FIXTURE.read_text().splitlines()[0]);item['time_ns'] = -1
            p.write_text(json.dumps(item)+'\n')
            with self.assertRaises(ValueError): read_events(p)
    def test_no_network_change_no_network_causality_guess(self):
        events, sha = read_events(FIXTURE)
        result = analyze([e for e in events if e.kind != 'route_change'], sha)
        self.assertEqual(len(result['hypotheses']), 1)
        self.assertIsNone(result['root_cause'])
    def test_hash_changes_with_evidence(self):
        _, sha = read_events(FIXTURE)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.jsonl';p.write_bytes(FIXTURE.read_bytes()+b'\n')
            _, other = read_events(p)
            self.assertNotEqual(sha, other)

if __name__ == '__main__': unittest.main()
