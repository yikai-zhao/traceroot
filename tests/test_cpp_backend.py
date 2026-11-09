"""Optional GCC-only integration; the rest of TraceRoot remains stdlib Python."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from http.client import HTTPConnection

from test_real_http import HERE
from reproduce_http_regression import cpp_backend, experiment


@unittest.skipUnless(shutil.which('g++'), 'requires g++ for optional local C++ backend')
class CppHttpBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / 'cpp_backend'
        subprocess.run(['g++', '-O2', '-std=c++17', '-Wall', '-Wextra', '-Wpedantic',
                        str(HERE / 'examples' / 'cpp_backend.cpp'), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_cpp_backend_rejects_bad_trace_header(self):
        with cpp_backend(self.binary, 1) as port:
            connection = HTTPConnection('127.0.0.1', port, timeout=3)
            try:
                connection.request('GET', '/work', headers={'X-Trace-Id': 'not valid'})
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                connection.close()

    def test_python_frontend_cpp_backend_reproduces_regressions(self):
        with tempfile.TemporaryDirectory() as directory:
            report = experiment(Path(directory), count=4, back_extra_ms=40,
                                front_extra_ms=40, backend_binary=self.binary)
            self.assertEqual(report['backend_runtime'], 'C++17')
            self.assertEqual(report['comparisons']['backend_regression']['hypothesis']['service'], 'backend')
            self.assertEqual(report['comparisons']['frontend_regression']['hypothesis']['service'], 'frontend')
            self.assertEqual(report['comparisons']['negative_control']['decision'],
                             'no_threshold_regression_observed')
            self.assertEqual(len((Path(directory) / 'baseline.jsonl').read_text().splitlines()), 8)


if __name__ == '__main__':
    unittest.main()
