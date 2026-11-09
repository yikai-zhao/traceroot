# TraceRoot

Evidence-grounded latency regression diagnosis across service boundaries.

TraceRoot validates request/span relationships, attributes **exclusive** service time and compares repeated traces. It reports the largest measured latency contributor and cites the underlying event IDs. If requests, services or clocks are incomparable, it abstains instead of guessing.

**What runs now:** deterministic offline analyzer; real localhost Python→C++ HTTP experiment with trace propagation, monotonic timestamps and controlled CPU regressions. **Not** a production profiler, OpenTelemetry collector, AI agent or proven autonomous root-cause detector.

## Reproduce

Python 3.10+ (standard library only); C++ demonstration requires Linux and g++:

```bash
# Offline synthetic fixtures
PYTHONPATH=src python3 -m traceroot --compare \
  fixtures/regression/baseline.jsonl fixtures/regression/db_slow.jsonl

# Actual loopback Python frontend + C++17 backend (no external traffic)
mkdir -p build
g++ -O2 -std=c++17 -Wall -Wextra -Wpedantic \
  examples/cpp_backend.cpp -o build/cpp_backend
python3 scripts/reproduce_http_regression.py --cpp-backend build/cpp_backend \
  --output lab-output/real-http-regression

# All regression, negative-evidence, and real-socket tests
python3 -m unittest discover -s tests -v

# Label-withheld, real-socket evaluation (4 classes x 3 seeded repetitions)
python3 scripts/evaluate_blind_cases.py --cpp-backend build/cpp_backend \
  --output lab-output/blind-evaluation --seeds 11 23 37 --requests 4
```

The local experiment injects backend CPU work, frontend CPU work and a no-regression control. Seven independent requests are collected per cohort; reports include verified event IDs, source SHA-256, measured CPU time and explicit limits. A separate label-withheld test evaluates backend, frontend, no-regression and subthreshold cases; mismatched span topology now causes abstention rather than confident misattribution. [Experimental evidence and reasoning](docs/REAL_HTTP_EVIDENCE.md) · [Label-withheld evaluation and limits](docs/BLIND_EVALUATION.md) · [Captured sample SHA-256 manifest](evidence/real-http-cpp/SHA256SUMS).

## Why this project exists

When a multi-service request becomes slower, parent span duration alone is a poor diagnosis: it includes downstream time. TraceRoot validates span containment and subtracts the **union of child intervals** to avoid double-counting, then screens comparable cohorts using published median thresholds. A ranked contributor is an *investigation target*, not causal proof. The comparator also fingerprints the **full rooted call tree**, so moving a child between two same-named service spans no longer yields a false comparable-cohort claim. [Adversarial counterexample](docs/TOPOLOGY_COMPARABILITY.md).

Route Incident Lab separately covers network datapaths, kernel routing failures, UDP backpressure and low-latency trade-offs. TraceRoot focuses on application/service diagnosis and evidence integrity; it does **not** duplicate the routing lab.

No employer/customer data, paid APIs, hosted CI, GitHub Actions or autonomous system changes. The optional future LLM/agent layer is **not implemented**.
