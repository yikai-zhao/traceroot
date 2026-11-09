"""Real socket integration: injected and negative-control performance regression."""
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'scripts'))
sys.path.insert(0, str(HERE / 'src'))
from reproduce_http_regression import experiment, local_service, request


class RealHttpIntegrationTest(unittest.TestCase):
    def test_cpu_instrumentation_is_actual_work(self):
        from traceroot.local_http import burn_cpu
        import time
        start = time.thread_time_ns()
        measured, checksum = burn_cpu(2)
        self.assertGreaterEqual(measured, 2_000_000)
        self.assertGreaterEqual(time.thread_time_ns() - start, 2_000_000)
        self.assertIsInstance(checksum, int)

    def test_bad_trace_id_rejected(self):
        from http.client import HTTPConnection
        with local_service('backend', 0) as port:
            connection = HTTPConnection('127.0.0.1', port, timeout=3)
            try:
                connection.request('GET', '/work', headers={'X-Trace-Id': 'bad id'})
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                connection.close()

    def test_actual_two_process_http_regressions(self):
        with tempfile.TemporaryDirectory() as directory:
            result = experiment(Path(directory), count=4, back_extra_ms=40,
                                front_extra_ms=40)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['comparisons']['backend_regression']['hypothesis']['service'], 'backend')
            self.assertEqual(result['comparisons']['frontend_regression']['hypothesis']['service'], 'frontend')
            self.assertEqual(result['comparisons']['negative_control']['decision'],
                             'no_threshold_regression_observed')
            for name, config in result['interventions'].items():
                self.assertEqual(len((Path(directory) / f'{name}.jsonl').read_text().splitlines()), 8)
                for data in result['observed_cpu_ms_per_request'][name]:
                    self.assertGreaterEqual(data['backend_cpu_ms'], config['backend_cpu_ms'])
                    self.assertGreaterEqual(data['frontend_cpu_ms'], config['frontend_cpu_ms'])


if __name__ == '__main__':
    unittest.main()
