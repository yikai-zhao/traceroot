# Cross-host comparison: observable durations versus causal attribution

TraceRoot's per-request exclusive durations are computed from timestamps
within each single-host trace. Two traces captured on different hosts can
therefore be compared **without subtracting absolute monotonic timestamps
across hosts**. Rejecting every different-host comparison would be overly
restrictive.

Nevertheless, a baseline captured on host A and a candidate captured on
host B do **not** isolate a software-version change: CPU, kernel, and scheduler
differences can confound the observed latency delta. The comparator now sets
`cohort_host_warning=distinct_reported_hosts_confound_attribution` when any
self-reported host identity in a cohort differs. It still reports the observed
latency change and candidate service, with the existing
`measured_contributor_not_proven_cause` status. Same-host cohorts receive a
`null` warning. Legacy untagged traces retain `assumed_single_host_not_verified`.

A failing-before test showed that cross-host cohorts were reported without any
host-confounding annotation. The tests also verify that same-host comparison
still functions and legacy untagged evidence stays explicitly unverified.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_cross_host_baselines.py -v
```

Host identity is self-reported data, not cryptographic provenance or clock
synchronization proof. There are no production distributed traces, remote host
connections, LLM conclusions or autonomous changes in this experiment.
