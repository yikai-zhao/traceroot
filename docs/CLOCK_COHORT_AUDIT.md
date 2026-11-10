# Cross-cohort clock provenance audit — 2026-11-10

A trace's span durations can only support an exclusive-time attribution if its timestamp origin is consistent. The existing `ClockHostTracker` correctly rejected mixed or partly tagged `clock_host_id` *within* a trace, but `compare_runs` did not check whether the baseline and candidate cohorts had comparable **provenance quality**. Thus a baseline where all spans identified their clock host could still be compared to completely untagged candidate spans and receive a confident-looking regression label.

The comparator now abstains with `insufficient_comparable_evidence` and `clock_identity_status=mixed_reported_and_assumed_clock_origin` when the cohorts combine *reported* and merely *assumed* host identity. A legacy untagged-only comparison may still run, but its output explicitly carries `assumed_single_host_not_verified`. Independent within-trace measurements from two separately identified hosts remain comparable **as durations**, without subtracting the hosts' absolute monotonic timestamps.

The clock-host field is only a self-reported string. Equal IDs do **not** prove NTP/PTP synchronization or actual physical origin. Nor does this change verify cross-service instrumentation on multiple machines.

`tests/test_clock_cohort_comparability.py` contains four targeted tests, including a counterexample that produced `regression_observed` before this fix. All 39 locally reconstructed parser/topology/core tests passed after the change. The complete live HTTP/C++ backend and blind evaluation suites were **not** reconstructed or rerun in this audit; do not claim they passed on the new revision.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_clock_cohort_comparability.py -v
```
