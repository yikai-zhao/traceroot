# Local HTTP cross-runtime regression evidence

**2026-11-08 · real Linux loopback requests · controlled intervention · single host**

## Design

A Python standard-library frontend handles HTTP GET `/work`. It forwards the `X-Trace-Id` header to a separate C++17 HTTP backend via `127.0.0.1`. Each process timestamps its work with the same host's `CLOCK_MONOTONIC` domain and records CPU time with a per-thread CPU clock. The client captures both returned spans, validates parent/child containment and creates evidence-linked JSONL. The C++ demonstration is deliberately a small one-request-per-connection test service, **not** a general HTTP parser or production server.

The experiment has four sequential cohorts of **7 requests each**: baseline, backend CPU slowdown, frontend CPU slowdown, and an unmodified negative control. The interventions and independently observed CPU time are recorded in the generated `lab-output/real-http-regression/report.json` (a captured run is supplied separately in the evidence archive). Each comparison uses the same deterministic `compare_runs()` algorithm as the offline fixture tests: at least 3 comparable traces, >=25% and >=20 ms median wall-time increase, and the largest median *exclusive* span-time delta.

| Cohort | Median request wall time | Expected contributor | Observed decision |
|---|---:|---|---|
| Baseline | 3.544 ms | n/a | reference |
| Backend CPU +45 ms | 48.687 ms | backend | backend regression observed |
| Frontend CPU +45 ms | 49.491 ms | frontend | frontend regression observed |
| Negative control | 3.437 ms | none | no threshold regression |

In the C++ backend experiment, measured backend CPU medians are ~2.001 ms baseline and ~47.000 ms with the intervention. Frontend CPU medians are ~1.004 ms baseline and ~46.248 ms for its intervention. These are intentional CPU loads, not natural production failures.

## Reproduce and audit

```bash
mkdir -p build
g++ -O2 -std=c++17 -Wall -Wextra -Wpedantic \
  examples/cpp_backend.cpp -o build/cpp_backend
python3 scripts/reproduce_http_regression.py \
  --cpp-backend build/cpp_backend --count 7 \
  --output lab-output/real-http-regression
python3 -m unittest discover -s tests -v
```

Expected: three explicit decisions (backend, frontend, no regression), complete raw `*.jsonl`, measured `cpu_ns`, SHA-256 for each baseline/candidate comparison, and PASS; the benchmark fails if the expected intervention attribution is not observed. Times fluctuate with host load, so **do not expect identical latency values**. If a run is affected by resource contention, it must be investigated, not silently omitted or relabeled PASS. Captured raw JSONL and report files are retained in the companion evidence archive, not in the Git repository; SHA-256 values for that run are checked in at `evidence/real-http-cpp/SHA256SUMS`. Anyone can regenerate and audit an independent run locally.

The Python-only fallback (`python3 scripts/reproduce_http_regression.py`) is useful to verify the same analyzer without a C++ compiler. The full test suite has 32 tests on this host, including C++-backend integration if g++ is available.

## Limitations

- One Linux host, one monotonic clock domain; not cross-host distributed clock synchronization.
- Serial requests, no saturating concurrency, no TLS or production tracing pipeline.
- Slowdowns are known, deliberately injected CPU work. Identifying the largest measured contributor does not prove an unknown real incident's root cause.
- No OpenTelemetry collector, sampling correction, profiler stack frames, LLM diagnosis or agent evaluation.
- The standalone C++ backend is scoped to localhost experiments, not hardened HTTP protocol handling.
