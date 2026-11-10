# Live localhost HTTP propagation and clock-provenance audit (2026-11-10)

**Scope:** Two actual Python standard-library HTTP servers, client → frontend → backend, running on one Linux host/process. Trace IDs travel in a real HTTP header, both services measure their own `time.monotonic_ns` intervals, and backend time lies inside frontend time. The analyzer uses current `traceroot.traces.compare_runs`, not a parallel implementation.

Twenty-eight actual client requests (7 baseline, 7 backend CPU intervention, 7 frontend CPU intervention and 7 unchanged controls) yielded **56 linked service-span records**. Work was performed with thread CPU-time-bounded arithmetic, *not sleep*; measured median backend CPU ~2 ms baseline versus ~42 ms under backend intervention, and median frontend CPU ~1 ms baseline versus ~41 ms under frontend intervention.

| Candidate vs baseline | Outcome |
|---|---|
| Backend CPU +40ms | `regression_observed`, largest exclusive contributor `db` |
| Frontend CPU +40ms | `regression_observed`, largest exclusive contributor `api` |
| Unchanged control | `no_threshold_regression_observed` |
| Backend intervention with **candidate clock IDs removed** | `insufficient_comparable_evidence` (abstained) |

Host identifier is read from Linux `/proc/sys/kernel/random/boot_id` on this same process and reported as an **observed, self-reported clock origin**. It is not a cryptographically verified remote clock identity, nor cross-host clock synchronization. The intervention is known and synthetic; this is a real-network-system test of instrumentation and abstention, **not autonomous discovery of an unknown production root cause**.

## Reproduce

```bash
PYTHONPATH=src python3 scripts/probe_live_regression.py \
    --requests 7 --output lab-output/live-http
PYTHONPATH=src python3 -m unittest discover -s tests \
    -p test_live_http_provenance.py -v
```

Captured JSONL, report, all source SHA256 digests and CPU observations are retained in [`evidence/live-http-20261110/`](../evidence/live-http-20261110). The negative test deliberately removes host IDs only from a derived in-memory candidate copy; original captured request evidence is unchanged.

The 16 local tests in the accompanying reconstruction covered `core.py`, `topology.py`, `clock_provenance.py`, `traces.py` and the new HTTP experiment. **This is not a claim that the complete remote repository's separate pre-existing C++ HTTP and blind-evaluation tests were re-run.**
