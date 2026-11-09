"""Real socket tests for the blind evaluation harness."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_blind_cases import evaluate, SCENARIOS


class BlindEvaluationTests(unittest.TestCase):
    def test_four_hidden_classes_real_sockets(self):
        with tempfile.TemporaryDirectory() as temp:
            report = evaluate(Path(temp), seeds=(193,), requests=3)
            self.assertEqual(report["cases_total"], len(SCENARIOS))
            self.assertEqual(report["cases_passed"], len(SCENARIOS))
            self.assertEqual(set(report["confusion_matrix"]),
                             {"backend", "frontend", "no_regression", "subthreshold"})
            for case in report["cases"]:
                self.assertIn(case["case_id"], [p.name for p in Path(temp).iterdir()])
                source_path = Path(temp) / case["case_id"] / "baseline.jsonl"
                self.assertTrue(source_path.exists())
                self.assertEqual(len(source_path.read_text().splitlines()), 6)
                self.assertTrue(case["trace_sources"]["baseline"]["sha256"])

    def test_reject_duplicate_seeds(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                evaluate(Path(temp), seeds=(11, 11))

    def test_reject_too_few_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                evaluate(Path(temp), requests=2)


if __name__ == "__main__":
    unittest.main()
