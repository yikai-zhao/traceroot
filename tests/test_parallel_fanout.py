"""Controlled multi-service trace graphs; no production accuracy claim."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from traceroot.core import Event
from traceroot.traces import compare_runs, summarize_traces


def span(trace, sid, service, begin, duration, parent=None):
    fields = {"trace_id": trace, "span_id": sid, "service": service,
              "duration_ms": duration}
    if parent is not None:
        fields["parent_span_id"] = parent
    else:
        fields["operation"] = "get_quote"
    return Event(trace + "-" + sid, int(begin * 1_000_000),
                 "service_span", service, fields)


def parallel_cohort(prefix, extra=0):
    events = []
    for index in range(3):
        t = prefix + str(index)
        events.extend([
            span(t, "root", "api", 0, 100 + extra),
            span(t, "db", "db", 10, 60, "root"),
            span(t, "cache", "cache", 40, 50 + extra, "root"),
        ])
    return events


def serial_cohort(prefix, db_extra=0):
    events = []
    for index in range(3):
        t = prefix + str(index)
        events.extend([
            span(t, "api", "api", 0, 100 + db_extra),
            span(t, "rpc", "rpc", 10, 80 + db_extra, "api"),
            span(t, "db", "db", 20, 50 + db_extra, "rpc"),
        ])
    return events


class FanoutRiskTests(unittest.TestCase):
    def test_parallel_siblings_are_detected(self):
        reports = summarize_traces(parallel_cohort("a"))
        self.assertEqual(len(reports), 3)
        self.assertTrue(all(r["parallel_sibling_pairs"] == 1 for r in reports))

    def test_parallel_baseline_candidate_abstains(self):
        report = compare_runs(parallel_cohort("a"), parallel_cohort("b", extra=45))
        self.assertEqual(report["decision"], "insufficient_comparable_evidence")
        self.assertEqual(report["parallel_span_warning"],
                         "overlapping_sibling_spans_require_critical_path_analysis")
        self.assertIsNone(report["hypothesis"])

    def test_serial_three_service_contributor(self):
        report = compare_runs(serial_cohort("a"), serial_cohort("b", db_extra=45))
        self.assertEqual(report["decision"], "regression_observed")
        self.assertEqual(report["hypothesis"]["service"], "db")
        self.assertNotIn("parallel_span_warning", report)


if __name__ == "__main__":
    unittest.main()
