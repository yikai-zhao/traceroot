import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from probe_live_regression import reproduce

class LiveHttpProvenance(unittest.TestCase):
    def test_actual_loopback_http_and_clock_abstention(self):
        with tempfile.TemporaryDirectory() as td:
            out=reproduce(Path(td),n=3)
            self.assertEqual(out['status'],'PASS')
            self.assertEqual(out['span_rows'],24)
            self.assertEqual(out['clock_provenance_negative']['decision'],'insufficient_comparable_evidence')
            for name in ('backend_slow','frontend_slow','control','baseline'):
                self.assertEqual(len((Path(td)/f'{name}.jsonl').read_text().splitlines()),6)
    def test_reject_too_few_cohort_samples(self):
        with self.assertRaises(ValueError):reproduce(Path('unused'),n=2)
if __name__=='__main__':unittest.main()
