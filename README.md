# TraceRoot — Evidence-Driven Infrastructure Debugging

An offline, reproducible baseline for investigating cross-service latency regressions. It reads normalized JSONL events, validates trace relationships and compares repeated service traces without inventing a root cause.

**Status:** deterministic prototype only. No LLM agent, production profiler, OpenTelemetry collector, paid API or CI automation.

## Run locally

```bash
PYTHONPATH=src python3 -m traceroot fixtures/service_performance.jsonl
PYTHONPATH=src python3 -m traceroot --compare fixtures/regression/baseline.jsonl fixtures/regression/db_slow.jsonl
python3 -m unittest discover -s tests -v
```

The supplied regression cases are **synthetic**. Five baseline and five candidate request traces expose a deliberately injected 80 ms database-only slowdown; the comparator reports the largest increase in exclusive span time, not a proven causal root cause. It refuses insufficient, mismatched, or malformed trace evidence.

Focus: cross-service trace correlation, local C++/Python performance diagnosis, evidence integrity and eventually bounded, evaluated read-only agent tooling. Route Incident Lab separately covers Linux network datapaths, backpressure and fault recovery.

No commercial, employer or customer data belongs in this repository. No GitHub Actions, paid hosting, remote APIs or auto-deployments.
